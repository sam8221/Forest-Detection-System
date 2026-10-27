"""Synthetic raster tests for boundary-scoped Sentinel comparisons."""

from __future__ import annotations

import json
from pathlib import Path
from datetime import date
from types import SimpleNamespace

import numpy as np
import pytest
import rasterio
from PIL import Image
from rasterio.crs import CRS
from rasterio.transform import from_bounds, from_origin
from rasterio.warp import transform_bounds, transform_geom
from shapely.geometry import box, mapping, shape

from app.services.boundary_comparison_service import (
    BoundaryComparisonService,
    manifest_matches_selected_images,
    read_matching_manifest,
    validate_forest_boundary,
    validate_stored_forest_boundary,
    write_comparison_manifest,
)
from app.services.persistence_service import PersistenceService


TEST_CRS = CRS.from_proj4(
    "+proj=utm +zone=35 +south +datum=WGS84 +units=m +no_defs"
)
WGS84 = CRS.from_proj4("+proj=longlat +datum=WGS84 +no_defs")
TRANSFORM = from_origin(500000.0, 8600000.0, 10.0, 10.0)


def boundary_from_pixels(
    left: float = 0,
    bottom: float = 4,
    right: float = 2,
    top: float = 6,
):
    projected = box(
        500000.0 + left * 10.0,
        8600000.0 - top * 10.0,
        500000.0 + right * 10.0,
        8600000.0 - bottom * 10.0,
    )
    return shape(transform_geom(TEST_CRS, WGS84, mapping(projected)))


def write_raster(
    path: Path,
    values: np.ndarray,
    *,
    crs=TEST_CRS,
    transform=TRANSFORM,
    nodata=-9999.0,
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
    ) as target:
        target.write(values, 1)
    return path


def create_ndvi_pair(tmp_path, previous_values=None, recent_values=None):
    previous_values = (
        np.full((6, 6), 0.8, dtype="float32")
        if previous_values is None
        else previous_values
    )
    recent_values = (
        np.full((6, 6), 0.2, dtype="float32")
        if recent_values is None
        else recent_values
    )
    return (
        write_raster(tmp_path / "source-previous.tif", previous_values),
        write_raster(tmp_path / "source-recent.tif", recent_values),
    )


def test_change_and_area_use_only_pixels_inside_forest_boundary(tmp_path):
    previous, recent = create_ndvi_pair(tmp_path)
    boundary = boundary_from_pixels()
    previous_out = tmp_path / "job" / "comparison" / "previous.tif"
    recent_out = tmp_path / "job" / "comparison" / "recent.tif"

    grid = BoundaryComparisonService().mask_ndvi_pair(
        previous, recent, boundary, previous_out, recent_out
    )
    with rasterio.open(previous_out) as old, rasterio.open(recent_out) as new:
        old_data, new_data = old.read(1), new.read(1)
        assert old_data.shape == new_data.shape
        valid = old_data != old.nodata
        assert np.count_nonzero(valid) == 4
        assert np.all(old_data[valid] == 0.8)
        assert np.all(new_data[valid] == 0.2)
        assert grid["inside_pixels"] == 4
        assert grid["common_valid_pixels"] == 4

    result = PersistenceService().process(
        previous_ndvi_path=previous_out,
        latest_ndvi_path=recent_out,
        working_directory=tmp_path / "job" / "persistence",
        threshold=0.15,
    )
    assert result["confirmed_pixels"] == 4
    assert result["affected_area_hectares"] == pytest.approx(0.04)


def test_selected_pair_change_is_recent_minus_previous_inside_boundary(tmp_path):
    previous_values = np.full((6, 6), 0.8, dtype="float32")
    recent_values = np.full((6, 6), 0.99, dtype="float32")
    # The selected 2x2 forest area occupies the bottom-left pixels.
    recent_values[4:6, 0:2] = 0.2
    previous, recent = create_ndvi_pair(tmp_path, previous_values, recent_values)
    previous_out = tmp_path / "job" / "comparison" / "previous.tif"
    recent_out = tmp_path / "job" / "comparison" / "recent.tif"
    change_out = tmp_path / "job" / "comparison" / "ndvi-change.tif"
    service = BoundaryComparisonService()

    grid = service.mask_ndvi_pair(
        previous, recent, boundary_from_pixels(), previous_out, recent_out
    )
    change = service.write_recent_minus_previous_ndvi_change(
        previous_out, recent_out, change_out
    )

    with rasterio.open(change_out) as result:
        values = result.read(1)
        inside = values != result.nodata
        assert np.count_nonzero(inside) == 4
        assert np.allclose(values[inside], -0.6, atol=1e-6)
        assert np.all(values[~inside] == result.nodata)

    assert grid["common_valid_pixels"] == 4
    assert grid["mean_previous_ndvi"] == pytest.approx(0.8)
    assert grid["mean_recent_ndvi"] == pytest.approx(0.2)
    assert grid["mean_ndvi_change"] == pytest.approx(-0.6)
    assert change["valid_pixels"] == 4
    assert change["sign_convention"] == "recent_minus_previous"


def test_outside_change_cannot_influence_ndvi_change_or_area(tmp_path):
    previous_values = np.full((6, 6), 0.8, dtype="float32")
    recent_values = previous_values.copy()
    # This is a large apparent change, but lies outside the selected 2x2 AOI.
    recent_values[0:2, 2:6] = 0.1
    previous, recent = create_ndvi_pair(tmp_path, previous_values, recent_values)
    boundary = boundary_from_pixels()
    previous_out = tmp_path / "comparison" / "previous.tif"
    recent_out = tmp_path / "comparison" / "recent.tif"

    BoundaryComparisonService().mask_ndvi_pair(
        previous, recent, boundary, previous_out, recent_out
    )
    result = PersistenceService().process(
        previous_ndvi_path=previous_out,
        latest_ndvi_path=recent_out,
        working_directory=tmp_path / "persistence",
        threshold=0.15,
    )

    assert result["confirmed_pixels"] == 0
    assert result["affected_area_hectares"] == 0


def test_cloud_or_shadow_nodata_is_removed_from_both_date_overlap(tmp_path):
    previous_values = np.full((6, 6), 0.8, dtype="float32")
    recent_values = np.full((6, 6), 0.2, dtype="float32")
    recent_values[4, 0] = -9999.0
    previous, recent = create_ndvi_pair(tmp_path, previous_values, recent_values)
    previous_out = tmp_path / "comparison" / "previous.tif"
    recent_out = tmp_path / "comparison" / "recent.tif"

    result = BoundaryComparisonService().mask_ndvi_pair(
        previous, recent, boundary_from_pixels(), previous_out, recent_out
    )
    with rasterio.open(recent_out) as source:
        data = source.read(1)
        assert data[0, 0] == source.nodata
    assert result["common_valid_pixels"] == 3


@pytest.mark.parametrize("invalid_kind", ["missing", "empty", "self-intersection", "outside-wgs84"])
def test_invalid_forest_boundaries_are_rejected(invalid_kind):
    if invalid_kind == "missing":
        boundary = None
    elif invalid_kind == "empty":
        boundary = box(0, 0, 1, 1).difference(box(0, 0, 1, 1))
    elif invalid_kind == "self-intersection":
        from shapely.geometry import Polygon

        boundary = Polygon([(0, 0), (1, 1), (0, 1), (1, 0), (0, 0)])
    else:
        boundary = box(500000, 8600000, 500010, 8600010)
    with pytest.raises(ValueError, match="boundary|EPSG:4326"):
        validate_forest_boundary(boundary)


def test_stored_boundary_rejects_wrong_srid():
    from geoalchemy2.elements import WKBElement
    from shapely import wkb

    zambian_boundary = boundary_from_pixels()
    with pytest.raises(ValueError, match="EPSG:4326"):
        validate_stored_forest_boundary(
            WKBElement(wkb.dumps(zambian_boundary), srid=3857)
        )


def test_boundary_without_raster_coverage_fails_clearly(tmp_path):
    previous, recent = create_ndvi_pair(tmp_path)
    far_boundary = boundary_from_pixels(left=1000, bottom=1002, right=1002, top=1004)
    with pytest.raises(ValueError, match="does not overlap"):
        BoundaryComparisonService().mask_ndvi_pair(
            previous,
            recent,
            far_boundary,
            tmp_path / "out-previous.tif",
            tmp_path / "out-recent.tif",
        )


def test_no_common_clear_pixels_fails_instead_of_reporting_zero(tmp_path):
    values = np.full((6, 6), -9999.0, dtype="float32")
    previous, recent = create_ndvi_pair(tmp_path, values, values)
    with pytest.raises(ValueError, match="No clear, valid pixels"):
        BoundaryComparisonService().mask_ndvi_pair(
            previous,
            recent,
            boundary_from_pixels(),
            tmp_path / "previous.tif",
            tmp_path / "recent.tif",
        )


def test_pair_aligns_recent_observation_with_shifted_affine(tmp_path):
    previous = write_raster(
        tmp_path / "previous.tif",
        np.full((6, 6), 0.8, dtype="float32"),
    )
    recent = write_raster(
        tmp_path / "recent.tif",
        np.full((8, 8), 0.2, dtype="float32"),
        transform=from_origin(499990.0, 8600010.0, 10.0, 10.0),
    )
    previous_out = tmp_path / "job" / "previous-out.tif"
    recent_out = tmp_path / "job" / "recent-out.tif"

    stats = BoundaryComparisonService().mask_ndvi_pair(
        previous,
        recent,
        boundary_from_pixels(),
        previous_out,
        recent_out,
    )

    with rasterio.open(previous_out) as previous_aligned, rasterio.open(
        recent_out
    ) as recent_aligned:
        assert previous_aligned.crs == recent_aligned.crs
        assert previous_aligned.transform == recent_aligned.transform
        assert previous_aligned.shape == recent_aligned.shape
        assert np.allclose(recent_aligned.read(1)[recent_aligned.read(1) > -9990], 0.2)
    assert stats["mean_ndvi_change"] == -0.6


def test_pair_reprojects_recent_observation_from_different_crs(tmp_path):
    previous_values = np.full((6, 6), 0.8, dtype="float32")
    previous = write_raster(tmp_path / "previous.tif", previous_values)
    projected_bounds = rasterio.transform.array_bounds(6, 6, TRANSFORM)
    recent_bounds = transform_bounds(
        TEST_CRS,
        CRS.from_epsg(3857),
        *projected_bounds,
        densify_pts=21,
    )
    recent = write_raster(
        tmp_path / "recent-3857.tif",
        np.full((6, 6), 0.2, dtype="float32"),
        crs=CRS.from_epsg(3857),
        transform=from_bounds(*recent_bounds, 6, 6),
    )

    result = BoundaryComparisonService().mask_ndvi_pair(
        previous,
        recent,
        boundary_from_pixels(),
        tmp_path / "previous-out.tif",
        tmp_path / "recent-out.tif",
    )

    with rasterio.open(tmp_path / "recent-out.tif") as aligned:
        assert aligned.crs == TEST_CRS
        assert np.any(aligned.read(1) > -9990)
    assert result["mean_ndvi_change"] == -0.6


def test_pair_resamples_recent_observation_to_the_native_10m_target(tmp_path):
    previous = write_raster(
        tmp_path / "previous.tif",
        np.full((6, 6), 0.8, dtype="float32"),
    )
    recent = write_raster(
        tmp_path / "recent-20m.tif",
        np.full((3, 3), 0.2, dtype="float32"),
        transform=from_origin(500000.0, 8600000.0, 20.0, 20.0),
    )

    BoundaryComparisonService().mask_ndvi_pair(
        previous,
        recent,
        boundary_from_pixels(),
        tmp_path / "previous-out.tif",
        tmp_path / "recent-out.tif",
    )

    with rasterio.open(tmp_path / "previous-out.tif") as previous_out, rasterio.open(
        tmp_path / "recent-out.tif"
    ) as recent_out:
        assert previous_out.crs == recent_out.crs
        assert previous_out.transform == recent_out.transform
        assert previous_out.res == recent_out.res == (10.0, 10.0)
        values = recent_out.read(1)
        valid = values != recent_out.nodata
        assert np.any(valid)
        assert np.allclose(values[valid], 0.2)
        assert np.all(values[~valid] == recent_out.nodata)


def test_true_colour_preview_is_masked_by_boundary_and_quality_mask(tmp_path):
    extracted = tmp_path / "product"
    extracted.mkdir()
    base = np.full((6, 6), 1200, dtype="uint16")
    for band in ("B04", "B03", "B02"):
        write_raster(
            extracted / f"S2_PRODUCT_{band}_10m.jp2",
            base,
            crs=None,
            nodata=0,
        )
    valid = np.ones((6, 6), dtype="uint8")
    valid[4, 0] = 0  # cloud or shadow excluded by the existing SCL mask
    valid_path = write_raster(
        tmp_path / "valid.tif", valid, nodata=0
    )
    output = tmp_path / "preview.png"

    stats = BoundaryComparisonService().render_rgb_preview(
        extracted,
        valid_path,
        boundary_from_pixels(),
        output,
    )
    with Image.open(output) as preview:
        alpha = np.asarray(preview.convert("RGBA"))[:, :, 3]
    assert alpha.shape[0] == 2
    assert alpha[0, 0] == 0
    assert np.count_nonzero(alpha) == 3
    assert stats["inside_pixels"] == 4
    assert stats["valid_pixels"] == 3


def test_true_colour_preview_maps_b04_b03_b02_to_red_green_blue(tmp_path):
    # Distinct values per band, or a swapped channel order would still pass.
    extracted = tmp_path / "ordered-product"
    extracted.mkdir()
    for band, reflectance in (("B04", 2400), ("B03", 1500), ("B02", 600)):
        write_raster(
            extracted / f"S2_PRODUCT_{band}_10m.jp2",
            np.full((6, 6), reflectance, dtype="uint16"),
            crs=None,
            nodata=0,
        )
    valid_path = write_raster(
        tmp_path / "valid.tif", np.ones((6, 6), dtype="uint8"), nodata=0
    )
    output = tmp_path / "ordered-preview.png"

    BoundaryComparisonService().render_rgb_preview(
        extracted,
        valid_path,
        boundary_from_pixels(),
        output,
    )

    with Image.open(output) as preview:
        pixels = np.asarray(preview.convert("RGBA"))
    red, green, blue, alpha = pixels[0, 0]
    assert alpha == 255
    # L2A reflectance / 3000, clipped, then gamma 1/1.1 and scaled to 0-255.
    def expected(reflectance: int) -> int:
        return int(round((min(reflectance / 3000.0, 1.0) ** (1.0 / 1.1)) * 255))

    assert (red, green, blue) == (expected(2400), expected(1500), expected(600))
    # The brightest band is the red one, so the ordering cannot be reversed.
    assert red > green > blue


def test_rgb_preview_aligns_rgb_bands_to_the_mask_grid(tmp_path):
    extracted = tmp_path / "misaligned-product"
    extracted.mkdir()
    target = np.full((6, 6), 1200, dtype="uint16")
    shifted = np.full((8, 8), 1800, dtype="uint16")
    write_raster(
        extracted / "S2_PRODUCT_B04_10m.jp2",
        target,
        crs=None,
        nodata=0,
    )
    write_raster(
        extracted / "S2_PRODUCT_B03_10m.jp2",
        shifted,
        crs=None,
        transform=from_origin(499990.0, 8600010.0, 10.0, 10.0),
        nodata=0,
    )
    write_raster(
        extracted / "S2_PRODUCT_B02_10m.jp2",
        target,
        crs=None,
        nodata=0,
    )
    valid_path = write_raster(
        tmp_path / "valid.tif",
        np.ones((6, 6), dtype="uint8"),
        nodata=0,
    )

    stats = BoundaryComparisonService().render_rgb_preview(
        extracted,
        valid_path,
        boundary_from_pixels(),
        tmp_path / "aligned-preview.png",
    )

    assert stats["valid_pixels"] == stats["inside_pixels"] == 4
    with Image.open(tmp_path / "aligned-preview.png") as preview:
        alpha = np.asarray(preview.convert("RGBA"))[:, :, 3]
    assert np.count_nonzero(alpha) == 4


def test_manifest_rejects_another_job_pair_or_boundary(tmp_path):
    boundary = boundary_from_pixels()
    manifest_path = tmp_path / "jobs" / "8" / "comparison" / "manifest.json"
    write_comparison_manifest(
        manifest_path,
        forest_area_id=3,
        job_id=8,
        previous_image_id=11,
        recent_image_id=12,
        boundary=boundary,
        imagery={"previous": {}, "recent": {}},
    )

    assert read_matching_manifest(
        manifest_path,
        forest_area_id=3,
        job_id=8,
        previous_image_id=11,
        recent_image_id=12,
        boundary=boundary,
    ) is not None
    assert read_matching_manifest(
        manifest_path,
        forest_area_id=3,
        job_id=9,
        previous_image_id=11,
        recent_image_id=12,
        boundary=boundary,
    ) is None
    assert read_matching_manifest(
        manifest_path,
        forest_area_id=3,
        job_id=8,
        previous_image_id=11,
        recent_image_id=99,
        boundary=boundary,
    ) is None
    assert read_matching_manifest(
        manifest_path,
        forest_area_id=3,
        job_id=8,
        previous_image_id=11,
        recent_image_id=12,
        boundary=boundary_from_pixels(right=3),
    ) is None


def test_manifest_is_json_and_only_contains_selected_pair_ids(tmp_path):
    path = tmp_path / "manifest.json"
    write_comparison_manifest(
        path,
        forest_area_id=3,
        job_id=8,
        previous_image_id=11,
        recent_image_id=12,
        boundary=boundary_from_pixels(),
        imagery={"previous": {}, "recent": {}},
    )
    value = json.loads(path.read_text(encoding="utf-8"))
    assert value["previous_satellite_image_id"] == 11
    assert value["recent_satellite_image_id"] == 12


def test_manifest_is_bound_to_the_current_product_metadata():
    def image(image_id, product, day):
        return SimpleNamespace(
            id=image_id,
            product_id=product,
            tile_id="35KPV",
            processing_level="L2A",
            acquisition_date=date.fromisoformat(day),
            cloud_cover_percentage=12.5,
        )

    previous = image(11, "S2_PREVIOUS", "2024-04-10")
    recent = image(12, "S2_RECENT", "2025-04-10")
    manifest = {
        "imagery": {
            "previous": {
                "product_id": previous.product_id,
                "tile_id": previous.tile_id,
                "processing_level": previous.processing_level,
                "acquisition_date": previous.acquisition_date.isoformat(),
                "cloud_cover_percentage": 12.5,
            },
            "recent": {
                "product_id": recent.product_id,
                "tile_id": recent.tile_id,
                "processing_level": recent.processing_level,
                "acquisition_date": recent.acquisition_date.isoformat(),
                "cloud_cover_percentage": 12.5,
            },
        }
    }

    assert manifest_matches_selected_images(manifest, previous, recent)
    recent.product_id = "S2_REPLACEMENT"
    assert not manifest_matches_selected_images(manifest, previous, recent)
