"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: NDVI Service

Purpose:
    Calculates NDVI from Sentinel-2 imagery.

Responsibilities:
    - Read Sentinel-2 bands.
    - Calculate NDVI.
    - Save NDVI raster.
    - Compare NDVI images.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia
===========================================================
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio


class NDVIService:
    """
    Performs NDVI calculations using
    Sentinel-2 imagery.
    """

    def read_band(
        self,
        band_path: Path,
    ) -> tuple[np.ndarray, dict]:
        """
        Read a Sentinel-2 band.

        Returns
        -------
        tuple
            (image_array, raster_profile)
        """

        with rasterio.open(band_path) as src:

            image = src.read(1).astype("float32")

            profile = src.profile

        return image, profile

    def calculate_ndvi(
        self,
        red_band: np.ndarray,
        nir_band: np.ndarray,
    ) -> np.ndarray:
        """
        Calculate NDVI.

        Formula:
            (NIR - RED) / (NIR + RED)
        """

        np.seterr(divide="ignore", invalid="ignore")

        denominator = nir_band + red_band

        denominator[denominator == 0] = np.nan

        ndvi = (
            (nir_band - red_band)
            / denominator
        )

        return ndvi
        def save_ndvi(
        self,
        ndvi: np.ndarray,
        profile: dict,
        output_path: Path,
    ) -> Path:
          """
        Save the NDVI raster as a GeoTIFF.
        """

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        profile = profile.copy()

        profile.update(
            dtype="float32",
            count=1,
            compress="lzw",
        )

        with rasterio.open(
            output_path,
            "w",
            **profile,
        ) as dst:

            dst.write(
                ndvi.astype("float32"),
                1,
            )

        return output_path

    def calculate_change(
        self,
        previous_ndvi: np.ndarray,
        current_ndvi: np.ndarray,
    ) -> np.ndarray:
        """
        Calculate NDVI change between two dates.
        """

        return current_ndvi - previous_ndvi

    def calculate_statistics(
        self,
        ndvi: np.ndarray,
    ) -> dict[str, float]:
        """
        Calculate summary statistics for an NDVI image.
        """

        valid_pixels = ndvi[np.isfinite(ndvi)]

        if valid_pixels.size == 0:

            return {
                "minimum": 0.0,
                "maximum": 0.0,
                "mean": 0.0,
                "std": 0.0,
            }

        return {
            "minimum": float(np.min(valid_pixels)),
            "maximum": float(np.max(valid_pixels)),
            "mean": float(np.mean(valid_pixels)),
            "std": float(np.std(valid_pixels)),
        }
        def process_ndvi(
        self,
        red_band_path: Path,
        nir_band_path: Path,
        output_path: Path,
    ) -> tuple[np.ndarray, dict[str, float], Path]:
           """
        Execute the complete NDVI workflow.

        Returns
        -------
        tuple
            (
                ndvi_array,
                statistics,
                output_file
            )
        """

        # --------------------------------------------
        # Read Sentinel-2 bands
        # --------------------------------------------
        red_band, profile = self.read_band(
            red_band_path,
        )

        nir_band, _ = self.read_band(
            nir_band_path,
        )

        # --------------------------------------------
        # Calculate NDVI
        # --------------------------------------------
        ndvi = self.calculate_ndvi(
            red_band,
            nir_band,
        )

        # --------------------------------------------
        # Save NDVI raster
        # --------------------------------------------
        output_file = self.save_ndvi(
            ndvi,
            profile,
            output_path,
        )

        # --------------------------------------------
        # Calculate statistics
        # --------------------------------------------
        statistics = self.calculate_statistics(
            ndvi,
        )

        return (
            ndvi,
            statistics,
            output_file,
        )

    def compare_ndvi(
        self,
        previous_ndvi: np.ndarray,
        current_ndvi: np.ndarray,
    ) -> tuple[np.ndarray, dict[str, float]]:
        """
        Compare two NDVI rasters.

        Returns
        -------
        tuple
            (
                change_raster,
                statistics
            )
        """

        change = self.calculate_change(
            previous_ndvi,
            current_ndvi,
        )

        statistics = self.calculate_statistics(
            change,
        )

        return (
            change,
            statistics,
        )