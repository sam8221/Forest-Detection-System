"""Small synthetic raster tests for Sentinel grid alignment."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_bounds, from_origin
from rasterio.warp import transform_bounds

from app.core.constants import NDVI_NODATA
from app.services.cloud_mask_service import CloudMaskService
from app.services.sentinel_processor_service import SentinelProcessorService


TEST_CRS = CRS.from_epsg(32735)
TARGET_TRANSFORM = from_origin(500000.0, 8600040.0, 10.0, 10.0)


def write_raster(
    path: Path,
    values: np.ndarray,
    *,
    crs=TEST_CRS,
    transform=TARGET_TRANSFORM,
    nodata=None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=values.shape[1],
        height=values.shape[0],
        count=1,
        dtype=values.dtype,
        crs=crs,
        transform=transform,
        nodata=nodata,
    ) as destination:
        destination.write(values, 1)
    return path


def test_scl_categories_are_resampled_nearest_to_exact_ndvi_grid(tmp_path):
    ndvi = write_raster(
        tmp_path / "ndvi.tif",
        np.full((4, 4), 0.6, dtype="float32"),
        nodata=NDVI_NODATA,
    )
    scl = write_raster(
        tmp_path / "scl.tif",
        np.array([[4, 8], [3, 9]], dtype="uint8"),
        transform=from_origin(500000.0, 8600040.0, 20.0, 20.0),
        nodata=0,
    )
    output = tmp_path / "valid-mask.tif"

    CloudMaskService().create_valid_mask(scl, ndvi, output)

    with rasterio.open(output) as mask, rasterio.open(ndvi) as reference:
        values = mask.read(1)
        assert mask.crs == reference.crs
        assert mask.transform == reference.transform
        assert mask.shape == reference.shape
    assert np.all(values[:2, :2] == 1)  # SCL vegetation (4)
    assert np.all(values[:2, 2:] == 0)  # medium cloud (8)
    assert np.all(values[2:, :2] == 0)  # cloud shadow (3)
    assert np.all(values[2:, 2:] == 0)  # high cloud (9)
    assert set(np.unique(values)).issubset({0, 1})


def test_scl_nodata_and_shifted_affine_become_invalid_pixels(tmp_path):
    ndvi = write_raster(
        tmp_path / "ndvi.tif",
        np.full((4, 4), 0.6, dtype="float32"),
        nodata=NDVI_NODATA,
    )
    scl = write_raster(
        tmp_path / "scl-shifted.tif",
        np.array([[4, 0], [4, 4]], dtype="uint8"),
        transform=from_origin(500010.0, 8600040.0, 20.0, 20.0),
        nodata=0,
    )
    output = tmp_path / "valid-mask.tif"

    CloudMaskService().create_valid_mask(scl, ndvi, output)

    with rasterio.open(output) as mask:
        values = mask.read(1)
    assert values.shape == (4, 4)
    assert np.any(values == 1)
    # The target region corresponding to SCL NoData and the uncovered
    # left edge are invalid rather than being treated as clear pixels.
    assert np.any(values == 0)


def test_scl_with_another_crs_is_reprojected_to_ndvi_grid(tmp_path):
    ndvi = write_raster(
        tmp_path / "ndvi.tif",
        np.full((4, 4), 0.6, dtype="float32"),
        nodata=NDVI_NODATA,
    )
    target_bounds = rasterio.transform.array_bounds(4, 4, TARGET_TRANSFORM)
    source_bounds = transform_bounds(
        TEST_CRS,
        CRS.from_epsg(3857),
        *target_bounds,
        densify_pts=21,
    )
    scl = write_raster(
        tmp_path / "scl-3857.tif",
        np.array([[4, 8], [4, 4]], dtype="uint8"),
        crs=CRS.from_epsg(3857),
        transform=from_bounds(*source_bounds, 2, 2),
        nodata=0,
    )
    output = tmp_path / "valid-mask-3857.tif"

    CloudMaskService().create_valid_mask(scl, ndvi, output)

    with rasterio.open(output) as mask:
        values = mask.read(1)
        assert mask.crs == TEST_CRS
        assert mask.transform == TARGET_TRANSFORM
    assert np.any(values == 1)
    assert np.any(values == 0)


def test_b08_is_resampled_to_b04_grid_before_ndvi(tmp_path):
    red = write_raster(
        tmp_path / "red_B04.tif",
        np.full((4, 4), 1000, dtype="uint16"),
        nodata=0,
    )
    nir = write_raster(
        tmp_path / "nir_B08.tif",
        np.full((2, 2), 3000, dtype="uint16"),
        transform=from_origin(500000.0, 8600040.0, 20.0, 20.0),
        nodata=0,
    )
    output = tmp_path / "ndvi.tif"

    SentinelProcessorService().calculate_ndvi(red, nir, output)

    with rasterio.open(output) as result:
        assert result.shape == (4, 4)
        assert result.transform == TARGET_TRANSFORM
        assert result.crs == TEST_CRS
        assert np.allclose(result.read(1), 0.5)


def test_b08_from_another_crs_is_reprojected_and_nodata_is_preserved(tmp_path):
    red_values = np.full((4, 4), 1000, dtype="uint16")
    red_values[0, 0] = 0
    red = write_raster(
        tmp_path / "red_B04.tif",
        red_values,
        nodata=0,
    )
    target_bounds = rasterio.transform.array_bounds(4, 4, TARGET_TRANSFORM)
    source_bounds = transform_bounds(
        TEST_CRS,
        CRS.from_epsg(3857),
        *target_bounds,
        densify_pts=21,
    )
    nir = write_raster(
        tmp_path / "nir_B08.tif",
        np.full((4, 4), 3000, dtype="uint16"),
        crs=CRS.from_epsg(3857),
        transform=from_bounds(*source_bounds, 4, 4),
        nodata=0,
    )
    output = tmp_path / "ndvi.tif"

    SentinelProcessorService().calculate_ndvi(red, nir, output)

    with rasterio.open(output) as result:
        values = result.read(1)
        assert result.crs == TEST_CRS
        assert result.transform == TARGET_TRANSFORM
    assert values[0, 0] == NDVI_NODATA
    assert np.allclose(values[1:, :], 0.5)


def test_ndvi_fails_when_bands_have_no_overlap_after_alignment(tmp_path):
    red = write_raster(
        tmp_path / "red_B04.tif",
        np.full((4, 4), 1000, dtype="uint16"),
        nodata=0,
    )
    nir = write_raster(
        tmp_path / "nir_B08.tif",
        np.full((4, 4), 3000, dtype="uint16"),
        transform=from_origin(600000.0, 8700040.0, 10.0, 10.0),
        nodata=0,
    )

    with pytest.raises(ValueError, match="do not overlap"):
        SentinelProcessorService().calculate_ndvi(
            red,
            nir,
            tmp_path / "ndvi.tif",
        )
