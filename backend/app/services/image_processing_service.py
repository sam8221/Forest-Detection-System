"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Image Processing Service

Purpose:
    Processes downloaded Sentinel-2 imagery.

Responsibilities:
    - Extract Sentinel ZIP archives.
    - Locate Sentinel bands.
    - Prepare files for NDVI analysis.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia
===========================================================
"""

from __future__ import annotations

import zipfile
from pathlib import Path


class ImageProcessingService:
    """
    Handles processing of Sentinel-2 products.
    """

    def extract_product(
        self,
        zip_file: Path,
        output_directory: Path,
    ) -> Path:
        """
        Extract a Sentinel-2 ZIP archive.
        """

        output_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        with zipfile.ZipFile(zip_file, "r") as archive:
            archive.extractall(output_directory)

        return output_directory

    def find_band(
        self,
        product_directory: Path,
        band_name: str,
    ) -> Path | None:
        """
        Locate a Sentinel-2 band.

        Example:
            B04
            B08
        """

        for file in product_directory.rglob("*.jp2"):

            if band_name in file.name:

                return file

        return None
        def get_red_band(
        self,
        product_directory: Path,
    ) -> Path:
          """
            Return the Sentinel-2 Red band (B04).

        Raises:
            FileNotFoundError: If the band is not found.
        """

        band = self.find_band(
            product_directory,
            "B04",
        )

        if band is None:
            raise FileNotFoundError(
                "Sentinel-2 Band B04 not found."
            )

        return band

    def get_nir_band(
        self,
        product_directory: Path,
    ) -> Path:
        """
        Return the Sentinel-2 Near Infrared band (B08).

        Raises:
            FileNotFoundError: If the band is not found.
        """

        band = self.find_band(
            product_directory,
            "B08",
        )

        if band is None:
            raise FileNotFoundError(
                "Sentinel-2 Band B08 not found."
            )

        return band

    def validate_product(
        self,
        product_directory: Path,
    ) -> bool:
        """
        Validate that the Sentinel product
        contains both required bands.
        """

        red = self.find_band(
            product_directory,
            "B04",
        )

        nir = self.find_band(
            product_directory,
            "B08",
        )

        return (
            red is not None
            and nir is not None
        )

    def prepare_ndvi_inputs(
        self,
        product_directory: Path,
    ) -> tuple[Path, Path]:
        """
        Prepare inputs required by the NDVI engine.

        Returns:
            (red_band, nir_band)
        """

        if not self.validate_product(
            product_directory,
        ):
            raise FileNotFoundError(
                "Sentinel-2 product is missing one or more required bands."
            )

        red_band = self.get_red_band(
            product_directory,
        )

        nir_band = self.get_nir_band(
            product_directory,
        )

        return (
            red_band,
            nir_band,
        )