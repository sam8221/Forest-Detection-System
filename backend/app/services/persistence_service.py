"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Persistence Service

Purpose:
    Confirm potential vegetation loss using observations
    from multiple Sentinel-2 dates.

Responsibilities:
    - Compare masked NDVI images from two dates.
    - Ensure pixels are valid on both dates.
    - Calculate NDVI change.
    - Apply a configurable deforestation threshold.
    - Generate a persistence-confirmed deforestation mask.
    - Calculate confirmed affected area.

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


class PersistenceService:
    """
    Confirms potential deforestation using multiple
    valid Sentinel-2 observations.
    """

    # =========================================================
    # PROCESS TWO DATES
    # =========================================================

    def process(
        self,
        previous_ndvi_path: str | Path,
        latest_ndvi_path: str | Path,
        working_directory: str | Path,
        threshold: float = 0.30,
    ) -> dict[str, str | float]:
        """
        Compare two cloud-masked NDVI rasters.

        A pixel is confirmed as potential deforestation when:

            previous NDVI - latest NDVI >= threshold

        and the pixel is valid on BOTH dates.

        Args:
            previous_ndvi_path:
                Cloud-masked NDVI from the earlier date.

            latest_ndvi_path:
                Cloud-masked NDVI from the later date.

            working_directory:
                Directory for generated outputs.

            threshold:
                Minimum NDVI decrease required.

        Returns:
            Dictionary containing generated raster paths
            and statistics.
        """

        previous_ndvi_path = Path(
            previous_ndvi_path
        )

        latest_ndvi_path = Path(
            latest_ndvi_path
        )

        working_directory = Path(
            working_directory
        )

        # =====================================================
        # VALIDATE INPUTS
        # =====================================================

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

        if threshold <= 0:
            raise ValueError(
                "Threshold must be greater than zero."
            )

        # =====================================================
        # OUTPUT DIRECTORIES
        # =====================================================

        difference_directory = (
            working_directory
            / "ndvi_difference"
        )

        persistence_directory = (
            working_directory
            / "persistence"
        )

        difference_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        persistence_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        difference_output = (
            difference_directory
            / "ndvi_change.tif"
        )

        persistence_output = (
            persistence_directory
            / "confirmed_deforestation.tif"
        )

        # =====================================================
        # READ PREVIOUS NDVI
        # =====================================================

        with rasterio.open(
            previous_ndvi_path
        ) as previous_src:

            previous = previous_src.read(
                1
            ).astype(
                np.float32
            )

            previous_profile = (
                previous_src.profile.copy()
            )

            previous_transform = (
                previous_src.transform
            )

            previous_crs = (
                previous_src.crs
            )

            previous_width = (
                previous_src.width
            )

            previous_height = (
                previous_src.height
            )

            previous_nodata = (
                previous_src.nodata
            )

        # =====================================================
        # READ LATEST NDVI
        # =====================================================

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

            latest_width = (
                latest_src.width
            )

            latest_height = (
                latest_src.height
            )

            latest_nodata = (
                latest_src.nodata
            )

        # =====================================================
        # GRID VALIDATION
        # =====================================================

        if (
            previous.shape
            != latest.shape
        ):
            raise ValueError(
                "Previous and latest NDVI dimensions "
                "do not match."
            )

        if (
            previous_width
            != latest_width
            or previous_height
            != latest_height
        ):
            raise ValueError(
                "Previous and latest NDVI sizes "
                "do not match."
            )

        if (
            previous_transform
            != latest_transform
        ):
            raise ValueError(
                "Previous and latest NDVI transforms "
                "do not match."
            )

        if previous_crs != latest_crs:
            raise ValueError(
                "Previous and latest NDVI CRS "
                "do not match."
            )

        # =====================================================
        # CREATE VALIDITY MASKS
        # =====================================================

        previous_valid = (
            np.isfinite(previous)
        )

        latest_valid = (
            np.isfinite(latest)
        )

        if previous_nodata is not None:

            previous_valid &= (
                previous
                != previous_nodata
            )

        if latest_nodata is not None:

            latest_valid &= (
                latest
                != latest_nodata
            )

        # -----------------------------------------------------
        # Our cloud-masked NDVI uses -9999.
        # Make sure these pixels are excluded even if
        # metadata does not expose nodata correctly.
        # -----------------------------------------------------

        previous_valid &= (
            previous > -9990
        )

        latest_valid &= (
            latest > -9990
        )

        # =====================================================
        # BOTH-DATE VALIDITY
        # =====================================================

        both_dates_valid = (
            previous_valid
            & latest_valid
        )

        # =====================================================
        # NDVI CHANGE
        # =====================================================

        ndvi_change = np.full(
            previous.shape,
            -9999.0,
            dtype=np.float32,
        )

        ndvi_change[
            both_dates_valid
        ] = (
            previous[
                both_dates_valid
            ]
            -
            latest[
                both_dates_valid
            ]
        )

        # =====================================================
        # CONFIRMED DEFORESTATION
        # =====================================================

        confirmed_deforestation = np.zeros(
            previous.shape,
            dtype=np.uint8,
        )

        confirmed_deforestation[
            both_dates_valid
            &
            (
                ndvi_change
                >= threshold
            )
        ] = 1

        # =====================================================
        # SAVE NDVI CHANGE
        # =====================================================

        difference_profile = (
            previous_profile.copy()
        )

        difference_profile.update(
            driver="GTiff",
            dtype="float32",
            count=1,
            nodata=-9999.0,
            compress="lzw",
        )

        with rasterio.open(
            difference_output,
            "w",
            **difference_profile,
        ) as dst:

            dst.write(
                ndvi_change,
                1,
            )

        # =====================================================
        # SAVE PERSISTENCE MASK
        # =====================================================

        persistence_profile = (
            previous_profile.copy()
        )

        persistence_profile.update(
            driver="GTiff",
            dtype="uint8",
            count=1,
            nodata=0,
            compress="lzw",
        )

        with rasterio.open(
            persistence_output,
            "w",
            **persistence_profile,
        ) as dst:

            dst.write(
                confirmed_deforestation,
                1,
            )

        # =====================================================
        # AREA CALCULATION
        # =====================================================

        pixel_width = abs(
            previous_transform.a
        )

        pixel_height = abs(
            previous_transform.e
        )

        pixel_area_m2 = (
            pixel_width
            * pixel_height
        )

        confirmed_pixels = int(
            np.count_nonzero(
                confirmed_deforestation
                == 1
            )
        )

        confirmed_area_m2 = (
            confirmed_pixels
            * pixel_area_m2
        )

        confirmed_area_hectares = (
            confirmed_area_m2
            / 10000.0
        )

        # =====================================================
        # STATISTICS
        # =====================================================

        valid_pixels = int(
            np.count_nonzero(
                both_dates_valid
            )
        )

        total_pixels = (
            previous.size
        )

        print(
            "PERSISTENCE ANALYSIS"
        )

        print(
            "Total pixels:",
            total_pixels,
        )

        print(
            "Valid on both dates:",
            valid_pixels,
        )

        print(
            "Confirmed deforestation pixels:",
            confirmed_pixels,
        )

        print(
            "Threshold:",
            threshold,
        )

        print(
            "Pixel size:",
            pixel_width,
            "x",
            pixel_height,
            "metres",
        )

        print(
            "Confirmed affected area:",
            round(
                confirmed_area_hectares,
                4,
            ),
            "hectares",
        )

        # =====================================================
        # RETURN
        # =====================================================

        return {
            "ndvi_change": str(
                difference_output
            ),
            "confirmed_deforestation": str(
                persistence_output
            ),
            "threshold": float(
                threshold
            ),
            "valid_pixels": float(
                valid_pixels
            ),
            "confirmed_pixels": float(
                confirmed_pixels
            ),
            "affected_area_hectares": float(
                confirmed_area_hectares
            ),
        }