"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Deforestation Severity Service

Purpose:
    Classify confirmed vegetation loss according to the
    magnitude of NDVI decline.

Responsibilities:
    - Read NDVI change raster.
    - Read persistence-confirmed deforestation mask.
    - Classify confirmed pixels by severity.
    - Calculate affected area for each severity class.
    - Save a severity classification raster.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Version:
    1.0.0
===========================================================
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio


class DeforestationSeverityService:
    """
    Classifies confirmed deforestation according to
    NDVI decline magnitude.

    Severity thresholds are configurable.
    """

    # =========================================================
    # PROCESS SEVERITY
    # =========================================================

    def process(
        self,
        ndvi_change_path: str | Path,
        confirmed_mask_path: str | Path,
        working_directory: str | Path,
        low_threshold: float = 0.30,
        moderate_threshold: float = 0.40,
        severe_threshold: float = 0.50,
    ) -> dict[str, str | float]:
        """
        Classify confirmed deforestation.

        Classification:

            0 = No confirmed deforestation
            1 = Low
            2 = Moderate
            3 = Severe

        NDVI decline:

            0.30 - 0.39 = Low
            0.40 - 0.49 = Moderate
            >= 0.50     = Severe

        Args:
            ndvi_change_path:
                Raster containing NDVI decrease.

            confirmed_mask_path:
                Persistence-confirmed deforestation mask.

            working_directory:
                Directory for generated output.

        Returns:
            Dictionary containing output paths and
            severity statistics.
        """

        ndvi_change_path = Path(
            ndvi_change_path
        )

        confirmed_mask_path = Path(
            confirmed_mask_path
        )

        working_directory = Path(
            working_directory
        )

        # =====================================================
        # VALIDATE INPUTS
        # =====================================================

        if not ndvi_change_path.exists():
            raise FileNotFoundError(
                f"NDVI change raster not found: "
                f"{ndvi_change_path}"
            )

        if not confirmed_mask_path.exists():
            raise FileNotFoundError(
                f"Confirmed deforestation mask not found: "
                f"{confirmed_mask_path}"
            )

        # =====================================================
        # VALIDATE THRESHOLDS
        # =====================================================

        if not (
            low_threshold
            < moderate_threshold
            < severe_threshold
        ):
            raise ValueError(
                "Severity thresholds must be in "
                "ascending order."
            )

        # =====================================================
        # OUTPUT
        # =====================================================

        output_directory = (
            working_directory
            / "severity"
        )

        output_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        severity_output = (
            output_directory
            / "deforestation_severity.tif"
        )

        # =====================================================
        # READ NDVI CHANGE
        # =====================================================

        with rasterio.open(
            ndvi_change_path
        ) as ndvi_src:

            ndvi_change = ndvi_src.read(
                1
            ).astype(
                np.float32
            )

            profile = (
                ndvi_src.profile.copy()
            )

            transform = (
                ndvi_src.transform
            )

            crs = ndvi_src.crs

            width = ndvi_src.width
            height = ndvi_src.height

            nodata = ndvi_src.nodata

        # =====================================================
        # READ CONFIRMED MASK
        # =====================================================

        with rasterio.open(
            confirmed_mask_path
        ) as mask_src:

            confirmed_mask = mask_src.read(
                1
            )

            if (
                mask_src.width != width
                or mask_src.height != height
            ):
                raise ValueError(
                    "NDVI change and confirmed mask "
                    "dimensions do not match."
                )

            if mask_src.transform != transform:
                raise ValueError(
                    "NDVI change and confirmed mask "
                    "transforms do not match."
                )

            if mask_src.crs != crs:
                raise ValueError(
                    "NDVI change and confirmed mask "
                    "CRS do not match."
                )

        # =====================================================
        # CREATE VALID CONFIRMED PIXELS
        # =====================================================

        valid_change = np.isfinite(
            ndvi_change
        )

        if nodata is not None:
            valid_change &= (
                ndvi_change != nodata
            )

        confirmed = (
            confirmed_mask == 1
        )

        confirmed = (
            confirmed
            & valid_change
        )

        # =====================================================
        # CREATE SEVERITY RASTER
        # =====================================================

        severity = np.zeros(
            ndvi_change.shape,
            dtype=np.uint8,
        )

        # -----------------------------------------------------
        # LOW
        # -----------------------------------------------------

        low_pixels = (
            confirmed
            & (
                ndvi_change
                >= low_threshold
            )
            & (
                ndvi_change
                < moderate_threshold
            )
        )

        severity[
            low_pixels
        ] = 1

        # -----------------------------------------------------
        # MODERATE
        # -----------------------------------------------------

        moderate_pixels = (
            confirmed
            & (
                ndvi_change
                >= moderate_threshold
            )
            & (
                ndvi_change
                < severe_threshold
            )
        )

        severity[
            moderate_pixels
        ] = 2

        # -----------------------------------------------------
        # SEVERE
        # -----------------------------------------------------

        severe_pixels = (
            confirmed
            & (
                ndvi_change
                >= severe_threshold
            )
        )

        severity[
            severe_pixels
        ] = 3

        # =====================================================
        # WRITE SEVERITY RASTER
        # =====================================================

        profile.update(
            driver="GTiff",
            dtype="uint8",
            count=1,
            nodata=0,
            compress="lzw",
        )

        with rasterio.open(
            severity_output,
            "w",
            **profile,
        ) as dst:

            dst.write(
                severity,
                1,
            )

        # =====================================================
        # AREA CALCULATION
        # =====================================================

        pixel_width = abs(
            transform.a
        )

        pixel_height = abs(
            transform.e
        )

        pixel_area_m2 = (
            pixel_width
            * pixel_height
        )

        pixel_area_hectares = (
            pixel_area_m2
            / 10000.0
        )

        # =====================================================
        # COUNT PIXELS
        # =====================================================

        low_count = int(
            np.count_nonzero(
                severity == 1
            )
        )

        moderate_count = int(
            np.count_nonzero(
                severity == 2
            )
        )

        severe_count = int(
            np.count_nonzero(
                severity == 3
            )
        )

        total_count = (
            low_count
            + moderate_count
            + severe_count
        )

        # =====================================================
        # AREA BY CLASS
        # =====================================================

        low_area = (
            low_count
            * pixel_area_hectares
        )

        moderate_area = (
            moderate_count
            * pixel_area_hectares
        )

        severe_area = (
            severe_count
            * pixel_area_hectares
        )

        total_area = (
            total_count
            * pixel_area_hectares
        )

        # =====================================================
        # STATISTICS
        # =====================================================

        print(
            "DEFORESTATION SEVERITY ANALYSIS"
        )

        print(
            "Low pixels:",
            low_count,
        )

        print(
            "Moderate pixels:",
            moderate_count,
        )

        print(
            "Severe pixels:",
            severe_count,
        )

        print(
            "Total confirmed pixels:",
            total_count,
        )

        print(
            "Low area:",
            round(
                low_area,
                4,
            ),
            "hectares",
        )

        print(
            "Moderate area:",
            round(
                moderate_area,
                4,
            ),
            "hectares",
        )

        print(
            "Severe area:",
            round(
                severe_area,
                4,
            ),
            "hectares",
        )

        print(
            "Total affected area:",
            round(
                total_area,
                4,
            ),
            "hectares",
        )

        # =====================================================
        # RETURN
        # =====================================================

        return {
            "severity_raster": str(
                severity_output
            ),
            "low_pixels": float(
                low_count
            ),
            "moderate_pixels": float(
                moderate_count
            ),
            "severe_pixels": float(
                severe_count
            ),
            "total_confirmed_pixels": float(
                total_count
            ),
            "low_area_hectares": float(
                low_area
            ),
            "moderate_area_hectares": float(
                moderate_area
            ),
            "severe_area_hectares": float(
                severe_area
            ),
            "total_area_hectares": float(
                total_area
            ),
        }