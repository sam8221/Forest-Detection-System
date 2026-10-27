"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Sentinel Processor Service

Purpose:
    Extract and prepare Sentinel-2 imagery for analysis.

Responsibilities:
    - Extract Sentinel-2 ZIP products.
    - Locate Sentinel-2 B04 (Red) band.
    - Locate Sentinel-2 B08 (NIR) band.
    - Determine the correct CRS.
    - Calculate NDVI.
    - Save the NDVI raster locally.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Version:
    1.3.0
===========================================================
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

import math

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.warp import reproject, transform_bounds
from rasterio.windows import Window, from_bounds

from app.core.constants import NDVI_NODATA
from app.services.ndvi_service import NDVIService

# Built from a PROJ string rather than an EPSG code, for the
# reason given against determine_crs below: an EPSG lookup
# needs the PROJ database, which is not always the one this
# process is pointed at.
WGS84 = CRS.from_proj4("+proj=longlat +datum=WGS84 +no_defs")

# Bilinear resampling of B08, and nearest resampling of the
# 20 m SCL, both read one pixel beyond the target. Two 10 m
# pixels of slack covers that and the 20 m SCL grid.
BOUNDARY_WINDOW_BUFFER_PIXELS = 2


class SentinelProcessorService:
    """
    Handles Sentinel-2 image extraction and NDVI processing.
    """

    # =========================================================
    # EXTRACT SENTINEL-2 PRODUCT
    # =========================================================

    def extract_product(
        self,
        zip_path: str | Path,
        extract_directory: str | Path,
    ) -> Path:
        """
        Extract a downloaded Sentinel-2 ZIP product.

        Args:
            zip_path:
                The downloaded product archive, roughly a
                gigabyte for a full Level-2A tile.
            extract_directory:
                Directory to extract into. Created if
                absent.

        Returns:
            Path:
                Root of the extracted SAFE structure.

        Raises:
            FileNotFoundError:
                The archive does not exist.
            zipfile.BadZipFile:
                The archive is corrupt or incomplete, which
                normally means the download was truncated.

        Products are distributed as a SAFE directory tree
        inside the archive, so the bands are not at a fixed
        path and are located afterwards by find_band rather
        than by name here.
        """

        zip_path = Path(zip_path)
        extract_directory = Path(extract_directory)

        if self.has_complete_extracted_product(extract_directory):
            return extract_directory

        if not zip_path.is_file():
            raise FileNotFoundError(
                "The selected Sentinel-2 archive is unavailable and no complete extracted product exists."
            )

        extract_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        with zipfile.ZipFile(
            zip_path,
            "r",
        ) as archive:
            archive.extractall(
                extract_directory
            )

        if not self.has_complete_extracted_product(extract_directory):
            raise ValueError(
                "The selected Sentinel-2 archive is missing required Level-2A metadata or bands."
            )

        return extract_directory

    @staticmethod
    def has_complete_extracted_product(
        extract_directory: str | Path,
    ) -> bool:
        """Return whether an extracted SAFE tree has the analysis inputs."""

        extract_directory = Path(extract_directory)
        if not extract_directory.is_dir():
            return False

        candidates = [
            path
            for path in extract_directory.iterdir()
            if path.is_dir() and path.name.casefold().endswith(".safe")
        ]
        if extract_directory.name.casefold().endswith(".safe"):
            candidates.append(extract_directory)

        required_patterns = (
            "*_B02_10m.jp2",
            "*_B03_10m.jp2",
            "*_B04_10m.jp2",
            "*_B08_10m.jp2",
            "*_SCL_20m.jp2",
        )
        for product_directory in candidates:
            metadata = list(product_directory.rglob("MTD_MSIL2A.xml"))
            if not any(
                path.is_file() and path.stat().st_size > 0
                for path in metadata
            ):
                continue
            if all(
                any(
                    path.is_file() and path.stat().st_size > 0
                    for path in product_directory.rglob(pattern)
                )
                for pattern in required_patterns
            ):
                return True

        return False

    # =========================================================
    # FIND SENTINEL-2 BAND
    # =========================================================

    def find_band(
        self,
        extracted_directory: str | Path,
        band: str,
    ) -> Path:
        """
        Locate one Sentinel-2 10 m band within a product.

        Args:
            extracted_directory:
                Root of an extracted SAFE product, searched
                recursively because the granule identifier
                in the path is not known in advance.
            band:
                Band identifier as it appears in the file
                name. The two this system uses are:

                    B04 = Red
                    B08 = Near Infrared

        Returns:
            Path:
                The band file.

        Raises:
            FileNotFoundError:
                The directory does not exist, or holds no
                file for that band at 10 m.

        Both bands are requested at the native 10 m
        resolution. B04 defines the output grid; if B08's
        recorded transform or CRS differs, B08 is warped to
        that grid before NDVI is calculated.
        """

        extracted_directory = Path(
            extracted_directory
        )

        band = band.upper()

        if band not in {"B02", "B03", "B04", "B08"}:
            raise ValueError(
                "Only Sentinel-2 10 m bands B02, B03, B04 and B08 are supported."
            )

        matches = list(
            extracted_directory.rglob(
                f"*_{band}_10m.jp2"
            )
        )

        if not matches:
            raise FileNotFoundError(
                f"The selected Sentinel-2 product is missing its required "
                f"{band} 10 m band."
            )

        return matches[0]

    # =========================================================
    # DETERMINE CRS FROM SENTINEL TILE
    # =========================================================

    def get_crs_from_tile(
        self,
        band_path: str | Path,
    ) -> CRS:
        """
        Determine the UTM CRS from a Sentinel-2 MGRS tile.

        Args:
            band_path:
                Path to a band file whose name carries the
                MGRS tile identifier, matched case
                insensitively anywhere in the path.

        Returns:
            CRS:
                The UTM coordinate reference system for
                that tile.

        Raises:
            ValueError:
                No MGRS tile identifier appears in the path,
                so the zone cannot be derived.

        Example:

            T35LPF

        T35 = UTM Zone 35
        L   = Southern Hemisphere

        For the Copperbelt tile T35LPF:

            WGS 84 / UTM Zone 35 South

        Used only when a band file carries no CRS of its
        own. Deriving it from the tile identifier is exact
        rather than a guess, because the MGRS grid defines
        which UTM zone each tile belongs to.

        A projected system is required, not a geographic
        one: areas are measured in this CRS, and metres
        convert to hectares by a constant whereas degrees do
        not.
        """

        band_path = Path(
            band_path
        )

        # -----------------------------------------------------
        # Find MGRS tile
        # -----------------------------------------------------

        match = re.search(
            r"T(\d{2})([A-Z]{3})",
            str(band_path),
            re.IGNORECASE,
        )

        if not match:
            raise ValueError(
                "Unable to determine Sentinel-2 MGRS tile "
                f"from path: {band_path}"
            )

        zone = int(
            match.group(1)
        )

        latitude_band = (
            match.group(2)[0].upper()
        )

        # -----------------------------------------------------
        # Validate UTM zone
        # -----------------------------------------------------

        if zone < 1 or zone > 60:
            raise ValueError(
                f"Invalid UTM zone detected: {zone}"
            )

        # -----------------------------------------------------
        # Determine hemisphere
        #
        # C-M = Southern Hemisphere
        # N-X = Northern Hemisphere
        # -----------------------------------------------------

        if "C" <= latitude_band <= "M":

            south = True

        elif "N" <= latitude_band <= "X":

            south = False

        else:
            raise ValueError(
                "Unable to determine hemisphere from "
                f"latitude band: {latitude_band}"
            )

        # -----------------------------------------------------
        # IMPORTANT
        #
        # Do NOT use:
        #
        #     CRS.from_epsg(...)
        #
        # because the current Windows environment has a
        # PostGIS/Rasterio PROJ database conflict.
        #
        # Instead construct the UTM CRS directly from a
        # PROJ definition.
        # -----------------------------------------------------

        if south:

            proj4 = (
                f"+proj=utm "
                f"+zone={zone} "
                f"+south "
                f"+datum=WGS84 "
                f"+units=m "
                f"+no_defs"
            )

        else:

            proj4 = (
                f"+proj=utm "
                f"+zone={zone} "
                f"+datum=WGS84 "
                f"+units=m "
                f"+no_defs"
            )

        return CRS.from_proj4(
            proj4
        )

    # =========================================================
    # DETERMINE OUTPUT CRS
    # =========================================================

    def determine_crs(
        self,
        red_band_path: str | Path,
        nir_band_path: str | Path,
    ) -> CRS:
        """
        Determine the CRS to use for the NDVI output.

        Args:
            red_band_path:
                Band B04 file.
            nir_band_path:
                Band B08 file.

        Returns:
            CRS:
                The coordinate reference system to write on
                the NDVI raster.

        Raises:
            ValueError:
                Neither band declares a CRS and no MGRS tile
                identifier can be read from either path.
            rasterio.errors.RasterioIOError:
                A band cannot be opened.

        A CRS declared by the file itself is preferred, as
        it is what the data provider recorded. Falling back
        to the MGRS tile identifier covers products whose
        JP2 files carry no georeference, which would
        otherwise produce an NDVI raster that cannot be
        placed on the ground at all.
        """

        red_band_path = Path(
            red_band_path
        )

        nir_band_path = Path(
            nir_band_path
        )

        red_crs = None
        nir_crs = None

        # -----------------------------------------------------
        # Read B04 CRS
        # -----------------------------------------------------

        with rasterio.open(
            red_band_path
        ) as red_src:

            red_crs = red_src.crs

        # -----------------------------------------------------
        # Read B08 CRS
        # -----------------------------------------------------

        with rasterio.open(
            nir_band_path
        ) as nir_src:

            nir_crs = nir_src.crs

        # -----------------------------------------------------
        # B04 is the target grid for NDVI. If it has a CRS,
        # use it and reproject B08 to it when necessary.
        if red_crs is not None:
            return red_crs

        # Some Sentinel JP2 files omit CRS metadata. For the
        # same product, a declared B08 CRS is the best
        # available reference for the B04 grid.
        if nir_crs is not None:
            return nir_crs

        # -----------------------------------------------------
        # Neither band has CRS.
        #
        # Determine from MGRS tile.
        # -----------------------------------------------------

        return self.get_crs_from_tile(
            red_band_path
        )

    # =========================================================
    # CALCULATE NDVI
    # =========================================================

    @staticmethod
    def covering_window(
        source,
        bounds: tuple[float, float, float, float],
        *,
        buffer_pixels: int = 0,
    ) -> Window:
        """
        Smallest whole-pixel window of source covering bounds.

        Args:
            source:
                An open rasterio dataset.
            bounds:
                left, bottom, right, top in that dataset's own
                coordinate reference system.
            buffer_pixels:
                Extra pixels kept on every side. Resampling a
                coarser band onto this grid reads neighbours,
                so a window cut exactly to the boundary would
                lose them and leave an edge of nodata.

        Returns:
            Window:
                Clamped to the dataset, so a boundary lying
                partly outside the tile still yields a window
                that can be read.

        Raises:
            ValueError:
                The bounds do not overlap the dataset at all.

        A Sentinel-2 tile is 10,980 x 10,980 pixels, roughly
        120 million. A Copperbelt forest area is a fraction of
        that, so reading only this window is what keeps an
        analysis to seconds rather than minutes.
        """

        requested = from_bounds(*bounds, transform=source.transform)

        column_start = max(
            0, int(math.floor(requested.col_off)) - buffer_pixels
        )
        row_start = max(
            0, int(math.floor(requested.row_off)) - buffer_pixels
        )
        column_stop = min(
            source.width,
            int(math.ceil(requested.col_off + requested.width)) + buffer_pixels,
        )
        row_stop = min(
            source.height,
            int(math.ceil(requested.row_off + requested.height)) + buffer_pixels,
        )

        if column_stop <= column_start or row_stop <= row_start:
            raise ValueError(
                "The selected forest boundary does not overlap this Sentinel-2 "
                "product, so no imagery can be read for it."
            )

        return Window(
            column_start,
            row_start,
            column_stop - column_start,
            row_stop - row_start,
        )

    def calculate_ndvi(
        self,
        red_band_path: str | Path,
        nir_band_path: str | Path,
        output_path: str | Path,
        bounds_wgs84: tuple[float, float, float, float] | None = None,
    ) -> Path:
        """
        Calculate NDVI from Sentinel-2 B04 and B08.

        Args:
            red_band_path:
                Band B04 (red) at 10 m.
            nir_band_path:
                Band B08 (near-infrared) at 10 m, covering
                the same tile.
            output_path:
                Destination for the NDVI GeoTIFF.

        Returns:
            Path:
                The NDVI raster written.

        Raises:
            ValueError:
                The bands differ in shape, or no CRS can be
                determined for the output.
            rasterio.errors.RasterioIOError:
                A band cannot be read, or the output cannot
                be written.

        Formula:

            NDVI = (NIR - RED) / (NIR + RED)

        B04 = Red
        B08 = Near Infrared

        B04 defines the 10 m target grid. B08 is aligned to
        that grid with bilinear resampling only when its CRS,
        transform, or dimensions differ.

        Output:
            Single-band float32 GeoTIFF in the PROJECTED
            UTM CRS returned by determine_crs, normally
            WGS 84 / UTM zone 35S for the Copperbelt.
            float32 preserves the fractional index and
            carries the nodata sentinel; a projected CRS
            means areas derived from this raster are in
            square metres and convert to hectares by a
            constant.
        """

        red_band_path = Path(
            red_band_path
        )

        nir_band_path = Path(
            nir_band_path
        )

        output_path = Path(
            output_path
        )

        # -----------------------------------------------------
        # Validate input files
        # -----------------------------------------------------

        if not red_band_path.exists():
            raise FileNotFoundError(
                f"Red band not found: {red_band_path}"
            )

        if not nir_band_path.exists():
            raise FileNotFoundError(
                f"NIR band not found: {nir_band_path}"
            )

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        # -----------------------------------------------------
        # Read B04
        # -----------------------------------------------------

        with rasterio.open(red_band_path) as red_src, rasterio.open(
            nir_band_path
        ) as nir_src:
            # Only the area under the forest boundary is read.
            # NDVI is a per-pixel ratio, so a windowed result is
            # identical to the same pixels of a whole-tile one;
            # the saving is simply not touching the other 99%
            # of a 120-million-pixel tile.
            red_window = None
            nir_window = None

            if bounds_wgs84 is not None:
                product_crs = red_src.crs or self.determine_crs(
                    red_band_path, nir_band_path
                )
                red_window = self.covering_window(
                    red_src,
                    transform_bounds(WGS84, product_crs, *bounds_wgs84),
                    buffer_pixels=BOUNDARY_WINDOW_BUFFER_PIXELS,
                )
                # The NIR window is taken from the ground area
                # the red window covers, not from its pixel
                # indices: the two bands need not share a grid,
                # and reprojection reads beyond the edges.
                nir_window = self.covering_window(
                    nir_src,
                    transform_bounds(
                        product_crs,
                        nir_src.crs or product_crs,
                        *rasterio.windows.bounds(red_window, red_src.transform),
                    ),
                    buffer_pixels=BOUNDARY_WINDOW_BUFFER_PIXELS,
                )

            red = red_src.read(1, window=red_window).astype(np.float32)
            red_valid = red_src.read_masks(1, window=red_window) > 0
            red_profile = red_src.profile.copy()
            red_transform = red_src.window_transform(red_window) if red_window else red_src.transform
            red_crs = red_src.crs
            red_resolution = red_src.res
            red_height, red_width = red.shape

            nir = nir_src.read(1, window=nir_window).astype(np.float32)
            nir_valid = nir_src.read_masks(1, window=nir_window) > 0
            nir_transform = nir_src.window_transform(nir_window) if nir_window else nir_src.transform
            nir_crs = nir_src.crs
            nir_nodata = nir_src.nodata

        # The red 10 m band defines this observation's output
        # grid. The NIR band may have a different affine grid
        # or CRS, so it is reprojected before the ratio is
        # calculated.
        output_crs = self.determine_crs(red_band_path, nir_band_path)
        if not output_crs.is_projected or output_crs.linear_units.lower() not in {
            "metre",
            "meter",
            "metres",
            "meters",
        }:
            raise ValueError("Sentinel-2 NDVI must use a projected metre-based CRS.")
        if not np.allclose(np.abs(red_resolution), (10.0, 10.0), atol=0.05):
            raise ValueError("B04 must define the native 10 m NDVI grid.")

        # If a JP2 omits CRS metadata, these bands belong to
        # one Sentinel product. Use the known product CRS for
        # that band's coordinate values; explicit CRS values
        # are always honored and reprojected when different.
        nir_source_crs = nir_crs or output_crs
        red[~red_valid] = np.nan
        if nir_nodata is not None:
            nir_valid &= nir != nir_nodata
        nir[~nir_valid] = np.nan

        same_nir_grid = (
            nir.shape == (red_height, red_width)
            and nir_transform == red_transform
            and nir_source_crs == output_crs
        )
        if same_nir_grid:
            aligned_nir = nir
        else:
            aligned_nir = np.full(
                (red_height, red_width), np.nan, dtype=np.float32
            )
            reproject(
                source=nir,
                destination=aligned_nir,
                src_transform=nir_transform,
                src_crs=nir_source_crs,
                src_nodata=np.nan,
                dst_transform=red_transform,
                dst_crs=output_crs,
                dst_nodata=np.nan,
                resampling=Resampling.bilinear,
                init_dest_nodata=True,
            )

        if not np.any(np.isfinite(red) & np.isfinite(aligned_nir)):
            raise ValueError(
                "B04 and B08 do not overlap on the target 10 m NDVI grid."
            )

        # -----------------------------------------------------
        # Calculate NDVI
        #
        # The formula itself lives in NDVIService so that the
        # value this pipeline writes to disk and the value
        # verified by the unit tests come from exactly the
        # same code.
        #
        # NDVIService marks unmeasurable pixels (where
        # NIR + RED is zero) as NaN; the step below converts
        # those to this pipeline's NDVI_NODATA sentinel.
        # -----------------------------------------------------

        ndvi = NDVIService().calculate_ndvi(
            red_band=red,
            nir_band=aligned_nir,
        )

        # -----------------------------------------------------
        # Remove invalid values
        # -----------------------------------------------------

        ndvi = np.where(
            np.isfinite(ndvi),
            ndvi,
            NDVI_NODATA,
        ).astype(
            np.float32
        )

        # -----------------------------------------------------
        # Prepare GeoTIFF
        # -----------------------------------------------------

        profile = red_profile
        profile.update(
            driver="GTiff",
            dtype="float32",
            count=1,
            nodata=NDVI_NODATA,
            compress="lzw",
            crs=output_crs,
            transform=red_transform,
            width=red_width,
            height=red_height,
        )

        # -----------------------------------------------------
        # Write NDVI
        # -----------------------------------------------------

        with rasterio.open(
            output_path,
            "w",
            **profile,
        ) as dst:

            dst.write(
                ndvi,
                1,
            )

        return output_path

    # =========================================================
    # COMPLETE PROCESSING PIPELINE
    # =========================================================

    def process_product(
        self,
        zip_path: str | Path,
        working_directory: str | Path,
        extract_directory: str | Path | None = None,
        bounds_wgs84: tuple[float, float, float, float] | None = None,
    ) -> dict[str, str]:
        """
        Turn a downloaded product into an NDVI raster.

        Args:
            zip_path:
                The downloaded Sentinel-2 Level-2A archive.
            working_directory:
                Directory to extract into and write under.

        Returns:
            dict[str, str]:
                Paths as strings under the keys "red_band",
                "nir_band" and "ndvi".

        Raises:
            FileNotFoundError:
                The archive is absent, or a required band
                is not present once extracted.
            zipfile.BadZipFile:
                The archive is corrupt or truncated.
            ValueError:
                No CRS can be determined for the output.
            rasterio.errors.RasterioIOError:
                A band cannot be read, or the output cannot
                be written.

        Runs the four steps in order: extract the archive,
        locate B04 and B08, settle the output CRS, and
        write NDVI.

        The band paths are returned alongside the NDVI so
        the later cloud-masking stage can work from the same
        extracted product rather than unpacking it again;
        a Level-2A tile is roughly a gigabyte.
        """

        zip_path = Path(
            zip_path
        )

        working_directory = Path(
            working_directory
        )

        # Extraction can be shared between jobs. The unpacked
        # bands are read-only inputs and identical whichever
        # analysis reads them, so copying a gigabyte of them
        # into every job directory only consumes the volume.
        # Derived rasters still go under working_directory,
        # which is the job's own.
        extracted_directory = (
            Path(extract_directory)
            if extract_directory is not None
            else working_directory / "extracted"
        )

        ndvi_directory = (
            working_directory
            / "ndvi"
        )

        # -----------------------------------------------------
        # Extract product
        # -----------------------------------------------------

        self.extract_product(
            zip_path=zip_path,
            extract_directory=extracted_directory,
        )

        # -----------------------------------------------------
        # Locate B04
        # -----------------------------------------------------

        red_band = self.find_band(
            extracted_directory,
            "B04",
        )

        # -----------------------------------------------------
        # Locate B08
        # -----------------------------------------------------

        nir_band = self.find_band(
            extracted_directory,
            "B08",
        )

        # -----------------------------------------------------
        # NDVI output
        # -----------------------------------------------------

        ndvi_output = (
            ndvi_directory
            / "ndvi.tif"
        )

        # -----------------------------------------------------
        # Calculate NDVI
        # -----------------------------------------------------

        self.calculate_ndvi(
            red_band_path=red_band,
            nir_band_path=nir_band,
            output_path=ndvi_output,
            bounds_wgs84=bounds_wgs84,
        )

        return {
            "red_band": str(
                red_band
            ),
            "nir_band": str(
                nir_band
            ),
            "ndvi": str(
                ndvi_output
            ),
        }
