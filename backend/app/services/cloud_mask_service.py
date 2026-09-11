"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Cloud Mask Service

Purpose:
    Identify and remove unreliable Sentinel-2 pixels using
    the Scene Classification Layer (SCL).

Responsibilities:
    - Locate Sentinel-2 SCL 20 m band.
    - Resample SCL from 20 m to the NDVI 10 m grid.
    - Identify clouds and cloud shadows.
    - Identify cirrus and snow/ice.
    - Handle SCL NoData pixels.
    - Create a valid-pixel mask.
    - Apply the mask to NDVI.
    - Save cloud-masked NDVI as GeoTIFF.
    - Provide SCL class statistics.

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

from pathlib import Path

import numpy as np
import rasterio

from rasterio.enums import Resampling
from rasterio.warp import reproject


class CloudMaskService:
    """
    Handles Sentinel-2 SCL cloud masking.
    """

    # =========================================================
    # SENTINEL-2 SCL CLASSES
    # =========================================================

    SCL_NO_DATA = 0
    SCL_SATURATED_DEFECTIVE = 1
    SCL_DARK_AREA = 2
    SCL_CLOUD_SHADOW = 3
    SCL_VEGETATION = 4
    SCL_BARE_SOIL = 5
    SCL_WATER = 6
    SCL_UNCLASSIFIED = 7
    SCL_CLOUD_MEDIUM = 8
    SCL_CLOUD_HIGH = 9
    SCL_CIRRUS = 10
    SCL_SNOW_ICE = 11

    # =========================================================
    # CLASSES THAT SHOULD BE MASKED
    # =========================================================

    MASKED_CLASSES = {
        SCL_NO_DATA,
        SCL_SATURATED_DEFECTIVE,
        SCL_CLOUD_SHADOW,
        SCL_CLOUD_MEDIUM,
        SCL_CLOUD_HIGH,
        SCL_CIRRUS,
        SCL_SNOW_ICE,
    }

    # =========================================================
    # FIND SCL BAND
    # =========================================================

    def find_scl_band(
        self,
        extracted_directory: str | Path,
    ) -> Path:
        """
        Locate the Sentinel-2 SCL 20 m band.
        """

        extracted_directory = Path(
            extracted_directory
        )

        if not extracted_directory.exists():
            raise FileNotFoundError(
                f"Extracted directory not found: "
                f"{extracted_directory}"
            )

        matches = list(
            extracted_directory.rglob(
                "*_SCL_20m.jp2"
            )
        )

        if not matches:
            raise FileNotFoundError(
                "Sentinel-2 SCL 20 m band was not found "
                f"inside {extracted_directory}"
            )

        return matches[0]

    # =========================================================
    # GET SCL CLASS STATISTICS
    # =========================================================

    def get_scl_statistics(
        self,
        scl_band_path: str | Path,
    ) -> dict[int, dict[str, float]]:
        """
        Calculate the number and percentage of pixels
        belonging to each SCL class.
        """

        scl_band_path = Path(
            scl_band_path
        )

        if not scl_band_path.exists():
            raise FileNotFoundError(
                f"SCL band not found: "
                f"{scl_band_path}"
            )

        with rasterio.open(
            scl_band_path
        ) as src:

            scl = src.read(1)

        total_pixels = scl.size

        class_names = {
            0: "No Data",
            1: "Saturated/Defective",
            2: "Dark Area",
            3: "Cloud Shadow",
            4: "Vegetation",
            5: "Bare Soil",
            6: "Water",
            7: "Unclassified",
            8: "Cloud Medium Probability",
            9: "Cloud High Probability",
            10: "Cirrus",
            11: "Snow/Ice",
        }

        statistics = {}

        for class_value in sorted(
            np.unique(scl)
        ):

            count = int(
                np.count_nonzero(
                    scl == class_value
                )
            )

            percentage = (
                count
                / total_pixels
                * 100
            )

            statistics[int(class_value)] = {
                "name": class_names.get(
                    int(class_value),
                    "Unknown",
                ),
                "pixels": count,
                "percentage": round(
                    percentage,
                    2,
                ),
            }

        return statistics

    # =========================================================
    # CREATE VALID MASK
    # =========================================================

    def create_valid_mask(
        self,
        scl_band_path: str | Path,
        reference_ndvi_path: str | Path,
        output_path: str | Path,
    ) -> Path:
        """
        Create a valid-pixel mask from Sentinel-2 SCL.

        SCL resolution:
            20 m

        NDVI resolution:
            10 m

        The SCL is resampled to the exact NDVI grid using
        nearest-neighbour resampling.

        Output:

            1 = valid pixel
            0 = masked pixel
        """

        scl_band_path = Path(
            scl_band_path
        )

        reference_ndvi_path = Path(
            reference_ndvi_path
        )

        output_path = Path(
            output_path
        )

        # =====================================================
        # VALIDATE FILES
        # =====================================================

        if not scl_band_path.exists():
            raise FileNotFoundError(
                f"SCL band not found: "
                f"{scl_band_path}"
            )

        if not reference_ndvi_path.exists():
            raise FileNotFoundError(
                f"Reference NDVI not found: "
                f"{reference_ndvi_path}"
            )

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        # =====================================================
        # READ SCL
        # =====================================================

        with rasterio.open(
            scl_band_path
        ) as scl_src:

            scl = scl_src.read(1)

            scl_transform = (
                scl_src.transform
            )

            scl_crs = scl_src.crs

            scl_width = (
                scl_src.width
            )

            scl_height = (
                scl_src.height
            )

            scl_bounds = (
                scl_src.bounds
            )

            scl_resolution = (
                scl_src.res
            )

        print(
            "SCL size:",
            scl_width,
            "x",
            scl_height,
        )

        print(
            "SCL resolution:",
            scl_resolution,
        )

        print(
            "SCL CRS:",
            scl_crs,
        )

        print(
            "SCL bounds:",
            scl_bounds,
        )

        # =====================================================
        # READ REFERENCE NDVI
        # =====================================================

        with rasterio.open(
            reference_ndvi_path
        ) as ndvi_src:

            ndvi_height = (
                ndvi_src.height
            )

            ndvi_width = (
                ndvi_src.width
            )

            ndvi_transform = (
                ndvi_src.transform
            )

            ndvi_crs = (
                ndvi_src.crs
            )

            ndvi_bounds = (
                ndvi_src.bounds
            )

            ndvi_resolution = (
                ndvi_src.res
            )

        print(
            "NDVI size:",
            ndvi_width,
            "x",
            ndvi_height,
        )

        print(
            "NDVI resolution:",
            ndvi_resolution,
        )

        print(
            "NDVI CRS:",
            ndvi_crs,
        )

        print(
            "NDVI bounds:",
            ndvi_bounds,
        )

        # =====================================================
        # CRS VALIDATION
        # =====================================================

        if ndvi_crs is None:
            raise ValueError(
                "Reference NDVI does not contain a CRS."
            )

        # -----------------------------------------------------
        # SCL CRS may be missing because of the JP2/PROJ
        # configuration on Windows.
        #
        # Since SCL and NDVI originate from the same
        # Sentinel-2 tile, use the NDVI CRS.
        # -----------------------------------------------------

        if scl_crs is None:

            print(
                "WARNING: SCL raster has no CRS."
            )

            print(
                "Using CRS from reference NDVI."
            )

            scl_crs = ndvi_crs

        # =====================================================
        # VERIFY SPATIAL ALIGNMENT
        # =====================================================

        bounds_tolerance = 1.0

        if (
            abs(
                scl_bounds.left
                - ndvi_bounds.left
            )
            > bounds_tolerance
            or
            abs(
                scl_bounds.right
                - ndvi_bounds.right
            )
            > bounds_tolerance
            or
            abs(
                scl_bounds.top
                - ndvi_bounds.top
            )
            > bounds_tolerance
            or
            abs(
                scl_bounds.bottom
                - ndvi_bounds.bottom
            )
            > bounds_tolerance
        ):

            raise ValueError(
                "SCL and NDVI spatial bounds do not match."
            )

        print(
            "SCL/NDVI spatial alignment: OK"
        )

        # =====================================================
        # RESAMPLE SCL TO NDVI GRID
        # =====================================================

        resampled_scl = np.zeros(
            (
                ndvi_height,
                ndvi_width,
            ),
            dtype=np.uint8,
        )

        reproject(
            source=scl,
            destination=resampled_scl,

            src_transform=scl_transform,
            src_crs=scl_crs,

            dst_transform=ndvi_transform,
            dst_crs=ndvi_crs,

            resampling=Resampling.nearest,
        )

        print(
            "SCL resampled from 20 m to 10 m."
        )

        # =====================================================
        # CREATE VALID MASK
        # =====================================================

        valid_mask = np.ones(
            (
                ndvi_height,
                ndvi_width,
            ),
            dtype=np.uint8,
        )

        # -----------------------------------------------------
        # Mask all unreliable classes
        # -----------------------------------------------------

        for class_value in (
            self.MASKED_CLASSES
        ):

            valid_mask[
                resampled_scl
                == class_value
            ] = 0

        # =====================================================
        # SAVE MASK
        # =====================================================

        profile = {
            "driver": "GTiff",
            "height": ndvi_height,
            "width": ndvi_width,
            "count": 1,
            "dtype": "uint8",
            "crs": ndvi_crs,
            "transform": ndvi_transform,
            "nodata": 0,
            "compress": "lzw",
        }

        with rasterio.open(
            output_path,
            "w",
            **profile,
        ) as dst:

            dst.write(
                valid_mask,
                1,
            )

        # =====================================================
        # REPORT RESULTS
        # =====================================================

        total_pixels = (
            valid_mask.size
        )

        valid_pixels = int(
            np.count_nonzero(
                valid_mask == 1
            )
        )

        masked_pixels = int(
            np.count_nonzero(
                valid_mask == 0
            )
        )

        valid_percentage = (
            valid_pixels
            / total_pixels
            * 100
        )

        masked_percentage = (
            masked_pixels
            / total_pixels
            * 100
        )

        print(
            "Valid pixels:",
            valid_pixels,
        )

        print(
            "Masked pixels:",
            masked_pixels,
        )

        print(
            "Valid percentage:",
            round(
                valid_percentage,
                2,
            ),
            "%",
        )

        print(
            "Masked percentage:",
            round(
                masked_percentage,
                2,
            ),
            "%",
        )

        return output_path

    # =========================================================
    # APPLY MASK TO NDVI
    # =========================================================

    def apply_mask_to_ndvi(
        self,
        ndvi_path: str | Path,
        valid_mask_path: str | Path,
        output_path: str | Path,
    ) -> Path:
        """
        Apply the valid-pixel mask to NDVI.

        Invalid pixels are stored as -9999.
        """

        ndvi_path = Path(
            ndvi_path
        )

        valid_mask_path = Path(
            valid_mask_path
        )

        output_path = Path(
            output_path
        )

        if not ndvi_path.exists():
            raise FileNotFoundError(
                f"NDVI raster not found: "
                f"{ndvi_path}"
            )

        if not valid_mask_path.exists():
            raise FileNotFoundError(
                f"Valid mask not found: "
                f"{valid_mask_path}"
            )

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        # =====================================================
        # READ NDVI
        # =====================================================

        with rasterio.open(
            ndvi_path
        ) as ndvi_src:

            ndvi = ndvi_src.read(
                1
            ).astype(
                np.float32
            )

            profile = (
                ndvi_src.profile.copy()
            )

            ndvi_nodata = (
                ndvi_src.nodata
            )

        # =====================================================
        # READ MASK
        # =====================================================

        with rasterio.open(
            valid_mask_path
        ) as mask_src:

            valid_mask = mask_src.read(
                1
            )

        # =====================================================
        # CHECK DIMENSIONS
        # =====================================================

        if ndvi.shape != valid_mask.shape:

            raise ValueError(
                "NDVI and cloud mask dimensions "
                "do not match."
            )

        # =====================================================
        # HANDLE NDVI NODATA
        # =====================================================

        if ndvi_nodata is not None:

            ndvi_invalid = (
                ndvi == ndvi_nodata
            )

        else:

            ndvi_invalid = (
                ~np.isfinite(ndvi)
            )

        # =====================================================
        # APPLY CLOUD MASK
        # =====================================================

        masked_ndvi = np.where(
            (
                valid_mask == 1
            )
            & (
                ~ndvi_invalid
            ),
            ndvi,
            -9999.0,
        ).astype(
            np.float32
        )

        # =====================================================
        # REMOVE INVALID VALUES
        # =====================================================

        masked_ndvi = np.where(
            np.isfinite(
                masked_ndvi
            ),
            masked_ndvi,
            -9999.0,
        ).astype(
            np.float32
        )

        # =====================================================
        # SAVE MASKED NDVI
        # =====================================================

        profile.update(
            driver="GTiff",
            dtype="float32",
            count=1,
            nodata=-9999.0,
            compress="lzw",
        )

        with rasterio.open(
            output_path,
            "w",
            **profile,
        ) as dst:

            dst.write(
                masked_ndvi,
                1,
            )

        return output_path

    # =========================================================
    # COMPLETE CLOUD MASKING PIPELINE
    # =========================================================

    def process(
        self,
        scl_band_path: str | Path,
        ndvi_path: str | Path,
        working_directory: str | Path,
    ) -> dict[str, str]:
        """
        Create a cloud mask and apply it to NDVI.
        """

        working_directory = Path(
            working_directory
        )

        mask_directory = (
            working_directory
            / "cloud_mask"
        )

        masked_ndvi_directory = (
            working_directory
            / "masked_ndvi"
        )

        mask_output = (
            mask_directory
            / "valid_pixel_mask.tif"
        )

        masked_ndvi_output = (
            masked_ndvi_directory
            / "ndvi_masked.tif"
        )

        # =====================================================
        # CREATE MASK
        # =====================================================

        self.create_valid_mask(
            scl_band_path=scl_band_path,
            reference_ndvi_path=ndvi_path,
            output_path=mask_output,
        )

        # =====================================================
        # APPLY MASK
        # =====================================================

        self.apply_mask_to_ndvi(
            ndvi_path=ndvi_path,
            valid_mask_path=mask_output,
            output_path=masked_ndvi_output,
        )

        # =====================================================
        # RETURN RESULTS
        # =====================================================

        return {
            "scl_band": str(
                scl_band_path
            ),
            "valid_mask": str(
                mask_output
            ),
            "masked_ndvi": str(
                masked_ndvi_output
            ),
        }