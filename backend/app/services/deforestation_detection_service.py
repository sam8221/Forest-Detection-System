"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Deforestation Detection Service

Purpose:
    Detect possible vegetation loss by comparing two
    Sentinel-2 NDVI rasters.

Responsibilities:
    - Compare previous and latest NDVI rasters.
    - Calculate NDVI difference.
    - Identify significant vegetation loss.
    - Remove invalid pixels.
    - Calculate affected area.
    - Save a deforestation mask as GeoTIFF.

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


class DeforestationDetectionService:
    """
    Detects possible deforestation using NDVI change.
    """

    # ---------------------------------------------------------
    # Default NDVI loss threshold
    # ---------------------------------------------------------

    DEFAULT_NDVI_LOSS_THRESHOLD = 0.30

    # ---------------------------------------------------------
    # Compare NDVI rasters
    # ---------------------------------------------------------

    def calculate_ndvi_difference(
        self,
        previous_ndvi_path: str | Path,
        latest_ndvi_path: str | Path,
        output_path: str | Path,
    ) -> Path:
        """
        Calculate the change between previous and latest NDVI.

        Formula:

            NDVI Difference =
                Previous NDVI - Latest NDVI

        A positive value therefore represents vegetation loss.
        """

        previous_ndvi_path = Path(
            previous_ndvi_path
        )

        latest_ndvi_path = Path(
            latest_ndvi_path
        )

        output_path = Path(
            output_path
        )

        if not previous_ndvi_path.exists():
            raise FileNotFoundError(
                f"Previous NDVI not found: "
                f"{previous_ndvi_path}"
            )

        if not latest_ndvi_path.exists():
            raise FileNotFoundError(
                f"Latest NDVI not found: "
                f"{latest_ndvi_path}"
            )

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        # -----------------------------------------------------
        # Read previous NDVI
        # -----------------------------------------------------

        with rasterio.open(
            previous_ndvi_path
        ) as previous_src:

            previous = previous_src.read(
                1
            ).astype(
                np.float32
            )

            profile = (
                previous_src.profile.copy()
            )

            previous_transform = (
                previous_src.transform
            )

            previous_crs = (
                previous_src.crs
            )

        # -----------------------------------------------------
        # Read latest NDVI
        # -----------------------------------------------------

        with rasterio.open(
            latest_ndvi_path
        ) as latest_src:

            latest = latest_src.read(
                1
            ).astype(
                np.float32
            )

            latest_transform = (
                latest_src.transform
            )

            latest_crs = (
                latest_src.crs
            )

        # -----------------------------------------------------
        # Validate dimensions
        # -----------------------------------------------------

        if previous.shape != latest.shape:
            raise ValueError(
                "Previous and latest NDVI rasters "
                "have different dimensions."
            )

        # -----------------------------------------------------
        # Validate CRS
        # -----------------------------------------------------

        if (
            previous_crs is not None
            and latest_crs is not None
            and previous_crs != latest_crs
        ):
            raise ValueError(
                "Previous and latest NDVI rasters "
                "have different CRS."
            )

        # -----------------------------------------------------
        # Validate spatial transform
        # -----------------------------------------------------

        if previous_transform != latest_transform:
            raise ValueError(
                "Previous and latest NDVI rasters "
                "have different spatial transforms."
            )

        # -----------------------------------------------------
        # Identify valid pixels
        # -----------------------------------------------------

        previous_valid = (
            previous != -9999.0
        )

        latest_valid = (
            latest != -9999.0
        )

        valid_pixels = (
            previous_valid
            & latest_valid
        )

        # -----------------------------------------------------
        # Calculate NDVI difference
        # -----------------------------------------------------

        ndvi_difference = np.full(
            previous.shape,
            -9999.0,
            dtype=np.float32,
        )

        ndvi_difference[valid_pixels] = (
            previous[valid_pixels]
            - latest[valid_pixels]
        )

        # -----------------------------------------------------
        # Prepare output
        # -----------------------------------------------------

        profile.update(
            driver="GTiff",
            dtype="float32",
            count=1,
            nodata=-9999.0,
            compress="lzw",
            crs=(
                previous_crs
                if previous_crs is not None
                else latest_crs
            ),
            transform=previous_transform,
        )

        # -----------------------------------------------------
        # Write difference raster
        # -----------------------------------------------------

        with rasterio.open(
            output_path,
            "w",
            **profile,
        ) as dst:

            dst.write(
                ndvi_difference,
                1,
            )

        return output_path

    # ---------------------------------------------------------
    # Detect vegetation loss
    # ---------------------------------------------------------

    def detect_deforestation(
        self,
        ndvi_difference_path: str | Path,
        output_path: str | Path,
        threshold: float = DEFAULT_NDVI_LOSS_THRESHOLD,
    ) -> Path:
        """
        Create a binary deforestation mask.

        A pixel is classified as possible deforestation when:

            Previous NDVI - Latest NDVI >= threshold

        Default threshold:

            0.30
        """

        ndvi_difference_path = Path(
            ndvi_difference_path
        )

        output_path = Path(
            output_path
        )

        if not ndvi_difference_path.exists():
            raise FileNotFoundError(
                f"NDVI difference file not found: "
                f"{ndvi_difference_path}"
            )

        if threshold <= 0:
            raise ValueError(
                "NDVI loss threshold must be greater than zero."
            )

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        # -----------------------------------------------------
        # Read NDVI difference
        # -----------------------------------------------------

        with rasterio.open(
            ndvi_difference_path
        ) as src:

            difference = src.read(
                1
            ).astype(
                np.float32
            )

            profile = (
                src.profile.copy()
            )

        # -----------------------------------------------------
        # Create deforestation mask
        #
        # 1 = possible deforestation
        # 0 = no detected loss
        # -----------------------------------------------------

        valid_pixels = (
            difference != -9999.0
        )

        deforestation_mask = np.zeros(
            difference.shape,
            dtype=np.uint8,
        )

        deforestation_mask[
            valid_pixels
            & (difference >= threshold)
        ] = 1

        # -----------------------------------------------------
        # Prepare output
        # -----------------------------------------------------

        profile.update(
            driver="GTiff",
            dtype="uint8",
            count=1,
            nodata=0,
            compress="lzw",
        )

        # -----------------------------------------------------
        # Write mask
        # -----------------------------------------------------

        with rasterio.open(
            output_path,
            "w",
            **profile,
        ) as dst:

            dst.write(
                deforestation_mask,
                1,
            )

        return output_path

    # ---------------------------------------------------------
    # Calculate affected area
    # ---------------------------------------------------------

    def calculate_affected_area(
        self,
        deforestation_mask_path: str | Path,
    ) -> float:
        """
        Calculate detected deforestation area in hectares.

        Sentinel-2 B04/B08 resolution:

            10 m × 10 m

        Therefore:

            1 pixel = 100 m²

            1 hectare = 10,000 m²

            1 pixel = 0.01 hectares
        """

        deforestation_mask_path = Path(
            deforestation_mask_path
        )

        if not deforestation_mask_path.exists():
            raise FileNotFoundError(
                f"Deforestation mask not found: "
                f"{deforestation_mask_path}"
            )

        with rasterio.open(
            deforestation_mask_path
        ) as src:

            mask = src.read(
                1
            )

            pixel_width = abs(
                src.transform.a
            )

            pixel_height = abs(
                src.transform.e
            )

        # -----------------------------------------------------
        # Count detected pixels
        # -----------------------------------------------------

        detected_pixels = int(
            np.count_nonzero(
                mask == 1
            )
        )

        # -----------------------------------------------------
        # Calculate square metres
        # -----------------------------------------------------

        pixel_area_m2 = (
            pixel_width
            * pixel_height
        )

        total_area_m2 = (
            detected_pixels
            * pixel_area_m2
        )

        # -----------------------------------------------------
        # Convert to hectares
        # -----------------------------------------------------

        total_area_hectares = (
            total_area_m2
            / 10_000
        )

        return float(
            total_area_hectares
        )

    # ---------------------------------------------------------
    # Complete detection pipeline
    # ---------------------------------------------------------

    def process(
        self,
        previous_ndvi_path: str | Path,
        latest_ndvi_path: str | Path,
        working_directory: str | Path,
        threshold: float = DEFAULT_NDVI_LOSS_THRESHOLD,
    ) -> dict[str, str | float]:
        """
        Execute the complete deforestation detection process.
        """

        working_directory = Path(
            working_directory
        )

        difference_directory = (
            working_directory
            / "ndvi_difference"
        )

        detection_directory = (
            working_directory
            / "deforestation"
        )

        difference_output = (
            difference_directory
            / "ndvi_difference.tif"
        )

        deforestation_output = (
            detection_directory
            / "deforestation_mask.tif"
        )

        # -----------------------------------------------------
        # Calculate NDVI difference
        # -----------------------------------------------------

        self.calculate_ndvi_difference(
            previous_ndvi_path=previous_ndvi_path,
            latest_ndvi_path=latest_ndvi_path,
            output_path=difference_output,
        )

        # -----------------------------------------------------
        # Detect deforestation
        # -----------------------------------------------------

        self.detect_deforestation(
            ndvi_difference_path=difference_output,
            output_path=deforestation_output,
            threshold=threshold,
        )

        # -----------------------------------------------------
        # Calculate affected area
        # -----------------------------------------------------

        area_hectares = (
            self.calculate_affected_area(
                deforestation_mask_path=deforestation_output
            )
        )

        return {
            "previous_ndvi": str(
                previous_ndvi_path
            ),
            "latest_ndvi": str(
                latest_ndvi_path
            ),
            "ndvi_difference": str(
                difference_output
            ),
            "deforestation_mask": str(
                deforestation_output
            ),
            "threshold": threshold,
            "affected_area_hectares": area_hectares,
        }