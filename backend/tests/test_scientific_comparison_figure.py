"""Tests for job-scoped scientific comparison figure rendering."""

from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import rasterio
from fastapi import HTTPException
from PIL import Image
from rasterio.crs import CRS
from rasterio.transform import from_origin

from app.api import monitoring
from app.services.comparison_figure_service import (
    CHANGE_NEGATIVE,
    CHANGE_POSITIVE,
    CHANGE_ZERO,
    DIFFERENCE_DISPLAY_FLOOR,
    DIFFERENCE_DISPLAY_PERCENTILE,
    NDVI_CLASS_COLORS,
    ComparisonFigureService,
    _colorize_ndvi,
    _difference_display_range,
)


TEST_CRS = CRS.from_epsg(32735)
TRANSFORM = from_origin(500000.0, 8600000.0, 10.0, 10.0)


def write_raster(path: Path, values: np.ndarray) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=values.shape[1],
        height=values.shape[0],
        count=1,
        dtype="float32",
        crs=TEST_CRS,
        transform=TRANSFORM,
        nodata=-9999.0,
    ) as destination:
        destination.write(values.astype("float32"), 1)
    return path


def comparison_inputs(tmp_path: Path):
    previous = np.full((20, 40), 0.55, dtype=np.float32)
    recent = np.full((20, 40), 0.45, dtype=np.float32)
    difference = np.full((20, 40), -0.1, dtype=np.float32)
    previous[0, :] = -9999
    recent[0, :] = -9999
    difference[0, :] = -9999
    # A real observed positive difference sets the display range symmetrically.
    recent[10, 20] = 0.95
    difference[10, 20] = 0.5

    previous_path = write_raster(tmp_path / "previous_ndvi.tif", previous)
    recent_path = write_raster(tmp_path / "recent_ndvi.tif", recent)
    difference_path = write_raster(tmp_path / "ndvi_difference.tif", difference)
    rgb_path = tmp_path / "previous_rgb.png"
    rgb = np.zeros((20, 40, 4), dtype=np.uint8)
    rgb[..., :3] = (176, 128, 80)
    rgb[..., 3] = 255
    rgb[0, :, 3] = 0
    Image.fromarray(rgb, mode="RGBA").save(rgb_path)

    imagery = {
        "previous": {
            "product_id": "S2A_TEST_PREVIOUS",
            "acquisition_date": "2025-05-10",
            "cloud_cover_percentage": 6.2,
            "bounds": [27.0, -13.0, 27.1, -12.9],
        },
        "recent": {
            "product_id": "S2B_TEST_RECENT",
            "acquisition_date": "2026-05-11",
            "cloud_cover_percentage": 3.1,
        },
        "grid": {"bounds": [27.0, -13.0, 27.1, -12.9]},
        "mean_previous_ndvi": 0.55,
        "mean_recent_ndvi": 0.46,
        "mean_ndvi_change": -0.09,
        "valid_comparison_pixels": 760,
        "affected_area_hectares": 0.24,
    }
    return rgb_path, previous_path, recent_path, difference_path, imagery


def test_shared_ndvi_classes_use_identical_fixed_boundaries_and_colors():
    values = np.asarray([[-0.5, 0.0, 0.2, 0.4, 0.6, 0.8]], dtype=np.float32)
    image = _colorize_ndvi(values, np.ones(values.shape, dtype=bool))
    pixels = [image.getpixel((x, 0))[:3] for x in range(values.shape[1])]
    expected = [
        tuple(bytes.fromhex(color.lstrip("#")))
        for color in NDVI_CLASS_COLORS
    ]
    assert pixels == expected


def test_difference_ramp_distinguishes_negative_zero_and_positive_values():
    from app.services.comparison_figure_service import _colorize_difference

    values = np.asarray([[-0.5, 0.0, 0.5]], dtype=np.float32)
    image = _colorize_difference(values, np.ones(values.shape, dtype=bool), 0.5)
    assert image.getpixel((0, 0))[:3] == CHANGE_NEGATIVE
    assert image.getpixel((1, 0))[:3] == CHANGE_ZERO
    assert image.getpixel((2, 0))[:3] == CHANGE_POSITIVE


def test_export_uses_actual_job_rasters_and_has_high_resolution_metadata(tmp_path):
    rgb, previous, recent, difference, imagery = comparison_inputs(tmp_path)
    output_directory = tmp_path / "area-8" / "jobs" / "21" / "comparison"

    result = ComparisonFigureService().render(
        previous_rgb_path=rgb,
        previous_ndvi_path=previous,
        recent_ndvi_path=recent,
        difference_path=difference,
        output_directory=output_directory,
        forest_area_id=8,
        forest_area_name="Kitwe Trial Forest",
        job_id=21,
        previous_image_id=41,
        recent_image_id=42,
        imagery=imagery,
    )

    export_path = output_directory / "scientific_comparison.png"
    assert export_path.is_file()
    with Image.open(export_path) as exported:
        assert exported.format == "PNG"
        assert exported.width >= 2000
        # PNG stores resolution as integer pixels per metre, so
        # 200 dpi is quantized to 199.9996 dpi on readback.
        assert exported.info["dpi"][0] == pytest.approx(200, abs=0.001)

    assert result["desktop"]["width"] >= 2000
    assert result["desktop"]["sha256"] == hashlib.sha256(export_path.read_bytes()).hexdigest()
    assert result["source"] == {
        "forest_area_id": 8,
        "analysis_job_id": 21,
        "previous_satellite_image_id": 41,
        "recent_satellite_image_id": 42,
        "previous_product_id": "S2A_TEST_PREVIOUS",
        "recent_product_id": "S2B_TEST_RECENT",
        "previous_acquisition_date": "2025-05-10",
        "recent_acquisition_date": "2026-05-11",
    }
    assert result["difference_scale"]["maximum_absolute_valid_difference"] == pytest.approx(0.5)
    assert result["difference_scale"]["sign_convention"] == "recent_minus_previous"
    assert result["difference_scale"]["observed_minimum"] == pytest.approx(-0.1)
    assert result["difference_scale"]["observed_maximum"] == pytest.approx(0.5)
    assert set(result["panels"]) == {
        "previous_rgb",
        "previous_ndvi",
        "recent_ndvi",
        "ndvi_difference",
    }
    with Image.open(output_directory / result["panels"]["previous_ndvi"]["filename"]) as ndvi_panel:
        assert ndvi_panel.mode == "RGBA"
        assert ndvi_panel.getpixel((0, 0))[3] == 0
        assert ndvi_panel.getpixel((5, 5))[3] == 255


def test_one_extreme_pixel_does_not_set_the_difference_display_range(tmp_path):
    # 759 pixels decline by 0.1 and a single pixel jumps by 0.5. Stretching to
    # that one pixel would compress the real signal into a fifth of the ramp.
    rgb, previous, recent, difference, imagery = comparison_inputs(tmp_path)

    result = ComparisonFigureService().render(
        previous_rgb_path=rgb,
        previous_ndvi_path=previous,
        recent_ndvi_path=recent,
        difference_path=difference,
        output_directory=tmp_path / "out",
        forest_area_id=8,
        forest_area_name="Kitwe Trial Forest",
        job_id=21,
        previous_image_id=41,
        recent_image_id=42,
        imagery=imagery,
    )

    scale = result["difference_scale"]
    displayed = scale["display_maximum_absolute_difference"]
    # Driven by the bulk of the scene, not by the outlier.
    assert displayed == pytest.approx(0.1, abs=0.001)
    assert displayed < scale["maximum_absolute_valid_difference"]
    assert scale["display_percentile"] == DIFFERENCE_DISPLAY_PERCENTILE
    # The outlier is reported as saturated rather than silently discarded.
    assert scale["saturated_pixels"] == 1
    assert scale["valid_pixels"] == 760
    assert scale["minimum"] == pytest.approx(-displayed)
    assert scale["maximum"] == pytest.approx(displayed)


def test_difference_raster_values_are_never_rewritten_by_the_display_stretch(tmp_path):
    rgb, previous, recent, difference, imagery = comparison_inputs(tmp_path)
    with rasterio.open(difference) as source:
        before = source.read(1)

    ComparisonFigureService().render(
        previous_rgb_path=rgb,
        previous_ndvi_path=previous,
        recent_ndvi_path=recent,
        difference_path=difference,
        output_directory=tmp_path / "out",
        forest_area_id=8,
        forest_area_name="Kitwe Trial Forest",
        job_id=21,
        previous_image_id=41,
        recent_image_id=42,
        imagery=imagery,
    )

    with rasterio.open(difference) as source:
        after = source.read(1)
    assert np.array_equal(before, after)
    # The outlier the stretch saturates is still 0.5 in the stored raster.
    assert after[10, 20] == pytest.approx(0.5)


def test_a_quiet_scene_is_not_amplified_below_the_display_floor(tmp_path):
    # Without a floor, a scene whose change is pure noise would be stretched
    # until that noise filled the ramp and looked like real deforestation.
    rgb, previous, recent, _difference, imagery = comparison_inputs(tmp_path)
    quiet = np.full((20, 40), 0.001, dtype=np.float32)
    quiet[0, :] = -9999
    quiet_path = write_raster(tmp_path / "quiet_difference.tif", quiet)

    result = ComparisonFigureService().render(
        previous_rgb_path=rgb,
        previous_ndvi_path=previous,
        recent_ndvi_path=recent,
        difference_path=quiet_path,
        output_directory=tmp_path / "quiet",
        forest_area_id=8,
        forest_area_name="Kitwe Trial Forest",
        job_id=21,
        previous_image_id=41,
        recent_image_id=42,
        imagery=imagery,
    )

    scale = result["difference_scale"]
    # Capped at the observed range, which is below the floor, so nothing is
    # saturated and the panel stays legitimately blank.
    assert scale["display_maximum_absolute_difference"] <= DIFFERENCE_DISPLAY_FLOOR
    assert scale["saturated_pixels"] == 0


def test_difference_legend_labels_never_collide_on_a_narrow_ramp():
    from PIL import ImageDraw

    from app.services.comparison_figure_service import _font, _gradient_labels

    draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    font = _font(17)

    wide = _gradient_labels(draw, width=900, maximum=0.207, saturated=True, font=font)
    narrow = _gradient_labels(draw, width=540, maximum=0.207, saturated=True, font=font)

    assert "potential decline" in wide[0]
    # The in-panel ramp is too narrow for the wording, so only the values show.
    assert narrow == ("≤ −0.2070", "0", "≥ +0.2070")
    # Whatever is chosen must leave the centred middle label room on both sides.
    for width, labels in ((900, wide), (540, narrow)):
        start, middle, end = (draw.textlength(text, font=font) for text in labels)
        assert max(start, end) + middle / 2 <= width / 2

    # Without saturation the labels lose the ≤ / ≥ prefixes.
    assert _gradient_labels(draw, width=540, maximum=0.207, saturated=False, font=font) == (
        "−0.2070",
        "0",
        "+0.2070",
    )


def test_footer_note_is_drawn_inside_the_figure(tmp_path):
    rgb, previous, recent, difference, imagery = comparison_inputs(tmp_path)
    output_directory = tmp_path / "footer"

    result = ComparisonFigureService().render(
        previous_rgb_path=rgb,
        previous_ndvi_path=previous,
        recent_ndvi_path=recent,
        difference_path=difference,
        output_directory=output_directory,
        forest_area_id=8,
        forest_area_name="Kitwe Trial Forest",
        job_id=21,
        previous_image_id=41,
        recent_image_id=42,
        imagery=imagery,
    )

    from PIL import ImageDraw

    from app.services.comparison_figure_service import _font, _wrapped_height

    service = ComparisonFigureService()
    difference_range = _difference_display_range(difference)
    metric_line, note = service._footer_text(imagery, difference_range)
    assert "not proof of deforestation" in note

    draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    width = 2400
    note_width = (width - 48 - 20) - (width // 2 + 18)
    text_height = sum(
        _wrapped_height(draw, text, font=_font(17), max_width=note_width, line_spacing=3)
        for text in (metric_line, note)
    )
    # The canvas must leave room for the whole caveat, not clip its last line.
    assert result["desktop"]["height"] >= 163 + text_height


def test_export_rejects_misaligned_or_missing_job_outputs(tmp_path):
    rgb, previous, recent, difference, imagery = comparison_inputs(tmp_path)
    misaligned = tmp_path / "misaligned.tif"
    values = np.full((20, 40), 0.2, dtype=np.float32)
    with rasterio.open(
        misaligned,
        "w",
        driver="GTiff",
        width=40,
        height=20,
        count=1,
        dtype="float32",
        crs=TEST_CRS,
        transform=from_origin(500010.0, 8600000.0, 10.0, 10.0),
        nodata=-9999.0,
    ) as destination:
        destination.write(values, 1)

    arguments = {
        "previous_rgb_path": rgb,
        "previous_ndvi_path": previous,
        "recent_ndvi_path": recent,
        "difference_path": difference,
        "output_directory": tmp_path / "comparison",
        "forest_area_id": 8,
        "forest_area_name": "Kitwe Trial Forest",
        "job_id": 21,
        "previous_image_id": 41,
        "recent_image_id": 42,
        "imagery": imagery,
    }
    with pytest.raises(ValueError, match="aligned CRS"):
        ComparisonFigureService().render(**{**arguments, "difference_path": misaligned})
    with pytest.raises(ValueError, match="missing"):
        ComparisonFigureService().render(**{**arguments, "difference_path": tmp_path / "absent.tif"})


def _figure_route_context(tmp_path, monkeypatch, *, figure_source=None, include_export=True):
    root = tmp_path / "area-8" / "jobs" / "21"
    comparison = root / "comparison"
    comparison.mkdir(parents=True, exist_ok=True)
    export = comparison / "scientific_comparison.png"
    if include_export:
        export.write_bytes(b"verified figure")
    panel_files = {
        "previous_rgb": "previous_rgb.png",
        "previous_ndvi": "previous_ndvi_panel.png",
        "recent_ndvi": "recent_ndvi_panel.png",
        "ndvi_difference": "ndvi_difference_panel.png",
    }
    panel_records = {}
    for name, filename in panel_files.items():
        payload = f"verified {name}".encode()
        panel_path = comparison / filename
        panel_path.write_bytes(payload)
        panel_records[name] = {
            "filename": filename,
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
    forest = SimpleNamespace(id=8, name="Kitwe Trial Forest")
    job = SimpleNamespace(
        id=21,
        forest_area_id=8,
        previous_satellite_image_id=41,
        satellite_image_id=42,
    )
    source = figure_source or {
        "forest_area_id": 8,
        "analysis_job_id": 21,
        "previous_satellite_image_id": 41,
        "recent_satellite_image_id": 42,
        "previous_product_id": "S2A_TEST_PREVIOUS",
        "recent_product_id": "S2B_TEST_RECENT",
        "previous_acquisition_date": "2025-05-10",
        "recent_acquisition_date": "2026-05-11",
    }
    manifest = {
        "imagery": {
            "previous": {"product_id": "S2A_TEST_PREVIOUS", "acquisition_date": "2025-05-10"},
            "recent": {"product_id": "S2B_TEST_RECENT", "acquisition_date": "2026-05-11"},
        },
        "figure": {
            "source": source,
            "panels": panel_records,
            "desktop": {
                "width": 2400,
                "height": 1800,
                "sha256": hashlib.sha256(export.read_bytes()).hexdigest() if include_export else "",
            },
        },
    }
    monkeypatch.setattr(
        monitoring,
        "resolve_comparison_context",
        lambda *_args, **_kwargs: (forest, job, None, root, manifest),
    )
    return manifest


def test_figure_route_serves_only_matching_job_specific_export(tmp_path, monkeypatch):
    _figure_route_context(tmp_path, monkeypatch)
    response = monitoring.get_selected_comparison_figure(
        8, 21, db=None, current_user=None
    )
    assert response.body == b"verified figure"
    assert response.headers["x-figure-layout"] == "2x2"

    wrong_job_source = {
        "forest_area_id": 8,
        "analysis_job_id": 20,
        "previous_satellite_image_id": 41,
        "recent_satellite_image_id": 42,
        "previous_product_id": "S2A_TEST_PREVIOUS",
        "recent_product_id": "S2B_TEST_RECENT",
        "previous_acquisition_date": "2025-05-10",
        "recent_acquisition_date": "2026-05-11",
    }
    _figure_route_context(tmp_path, monkeypatch, figure_source=wrong_job_source)
    with pytest.raises(HTTPException) as error:
        monitoring.get_selected_comparison_figure(
            8, 21, db=None, current_user=None
        )
    assert error.value.status_code == 409


def test_figure_route_returns_clear_error_when_export_is_missing(tmp_path, monkeypatch):
    _figure_route_context(tmp_path, monkeypatch, include_export=False)
    with pytest.raises(HTTPException) as error:
        monitoring.get_selected_comparison_figure(
            8, 21, db=None, current_user=None
        )
    assert error.value.status_code == 409
    assert "missing" in error.value.detail


def test_panel_route_serves_manifest_verified_panel_only(tmp_path, monkeypatch):
    _figure_route_context(tmp_path, monkeypatch)
    response = monitoring.get_selected_comparison_panel(
        8, 21, "recent_ndvi", db=None, current_user=None
    )
    assert response.body == b"verified recent_ndvi"
    with pytest.raises(HTTPException) as error:
        monitoring.get_selected_comparison_panel(
            8, 21, "unrelated", db=None, current_user=None
        )
    assert error.value.status_code == 404
