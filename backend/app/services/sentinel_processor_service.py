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

import numpy as np
import rasterio
from rasterio.crs import CRS

from app.core.constants import NDVI_NODATA
from app.services.ndvi_service import NDVIService


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

        if not zip_path.exists():
            raise FileNotFoundError(
                f"Sentinel-2 ZIP file not found: {zip_path}"
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

        return extract_directory

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

        Both bands are taken at 10 m, their native
        resolution, so they share a pixel grid and NDVI can
        be computed without resampling either one. Taking
        one band at 20 m would require resampling and would
        put an interpolated value into the ratio.
        """

        extracted_directory = Path(
            extracted_directory
        )

        band = band.upper()

        if band not in {
            "B04",
            "B08",
        }:
            raise ValueError(
                "Only B04 and B08 are currently supported."
            )

        matches = list(
            extracted_directory.rglob(
                f"*_{band}_10m.jp2"
            )
        )

        if not matches:
            raise FileNotFoundError(
                f"Sentinel-2 {band} 10m band was not found "
                f"inside {extracted_directory}"
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
        # Both CRS values available
        # -----------------------------------------------------

        if (
            red_crs is not None
            and nir_crs is not None
        ):

            if red_crs != nir_crs:
                raise ValueError(
                    "B04 and B08 have different CRS values."
                )

            return red_crs

        # -----------------------------------------------------
        # Only B04 has CRS
        # -----------------------------------------------------

        if red_crs is not None:
            return red_crs

        # -----------------------------------------------------
        # Only B08 has CRS
        # -----------------------------------------------------

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

    def calculate_ndvi(
        self,
        red_band_path: str | Path,
        nir_band_path: str | Path,
        output_path: str | Path,
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

        Both bands are 10 m, so they share a pixel grid and
        neither is resampled before the ratio is taken.

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

        with rasterio.open(
            red_band_path
        ) as red_src:

            red = red_src.read(
                1
            ).astype(
                np.float32
            )

            profile = (
                red_src.profile.copy()
            )

            red_transform = (
                red_src.transform
            )

            red_crs = (
                red_src.crs
            )

        # -----------------------------------------------------
        # Read B08
        # -----------------------------------------------------

        with rasterio.open(
            nir_band_path
        ) as nir_src:

            nir = nir_src.read(
                1
            ).astype(
                np.float32
            )

            nir_transform = (
                nir_src.transform
            )

            nir_crs = (
                nir_src.crs
            )

        # -----------------------------------------------------
        # Validate dimensions
        # -----------------------------------------------------

        if red.shape != nir.shape:
            raise ValueError(
                "B04 and B08 dimensions do not match."
            )

        # -----------------------------------------------------
        # Validate transforms
        # -----------------------------------------------------

        if red_transform != nir_transform:
            raise ValueError(
                "B04 and B08 have different spatial "
                "transforms."
            )

        # -----------------------------------------------------
        # Determine CRS
        # -----------------------------------------------------

        output_crs = self.determine_crs(
            red_band_path=red_band_path,
            nir_band_path=nir_band_path,
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
            nir_band=nir,
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

        profile.update(
            driver="GTiff",
            dtype="float32",
            count=1,
            nodata=NDVI_NODATA,
            compress="lzw",
            crs=output_crs,
            transform=red_transform,
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

        extracted_directory = (
            working_directory
            / "extracted"
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