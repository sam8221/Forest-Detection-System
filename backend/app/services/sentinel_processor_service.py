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
        Extract a Sentinel-2 ZIP product.
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
        Locate a Sentinel-2 10 m band.

        B04 = Red
        B08 = Near Infrared
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

        Example:

            T35LPF

        T35 = UTM Zone 35
        L   = Southern Hemisphere

        For the Copperbelt tile T35LPF:

            WGS 84 / UTM Zone 35 South
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

        If the Sentinel source bands contain a CRS, use it.

        If they do not contain a CRS, determine the CRS from
        the Sentinel-2 MGRS tile.
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

        Formula:

            NDVI = (NIR - RED) / (NIR + RED)

        B04 = Red
        B08 = Near Infrared

        Output:
            Float32 GeoTIFF with geographic CRS.
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
        # -----------------------------------------------------

        denominator = (
            nir + red
        )

        ndvi = np.full(
            red.shape,
            -9999.0,
            dtype=np.float32,
        )

        valid_pixels = (
            denominator != 0
        )

        ndvi[valid_pixels] = (
            (
                nir[valid_pixels]
                - red[valid_pixels]
            )
            /
            denominator[valid_pixels]
        )

        # -----------------------------------------------------
        # Remove invalid values
        # -----------------------------------------------------

        ndvi = np.where(
            np.isfinite(ndvi),
            ndvi,
            -9999.0,
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
            nodata=-9999.0,
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
        Extract Sentinel-2 product, locate B04/B08,
        determine CRS, and generate NDVI GeoTIFF.
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