"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Raster Render Tests

Purpose:
    Verify that stored rasters are coloured, bounded,
    summarised and sampled correctly for the monitoring map.

Responsibilities:
    - Confirm the NDVI ramp runs red at low to green at high.
    - Confirm invalid pixels are transparent, not coloured.
    - Confirm bounds come back in WGS 84.
    - Confirm the histogram counts only valid pixels.
    - Confirm a small clearing survives decimation.
    - Confirm a point outside the raster reads as nothing.
    - Confirm an absent layer is reported, not invented.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Note:
    The rasters here are SYNTHETIC FIXTURES written with
    hand-chosen values so the expected output can be worked
    out on paper. They are not satellite observations and
    nothing derived from them describes real vegetation
    anywhere.

    No database and no network: the service reads files and
    returns bytes.
===========================================================
"""

import io
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from rasterio.crs import CRS
from rasterio.transform import from_origin
from rasterio.warp import transform

from app.core.constants import NDVI_NODATA
from app.services.raster_render_service import (
    LAYERS,
    WGS84_CRS,
    RasterRenderService,
    _max_pool,
)


# =========================================================
# FIXTURES
# =========================================================

TEST_CRS = CRS.from_proj4(
    "+proj=utm +zone=35 +south +datum=WGS84 "
    "+units=m +no_defs"
)


def write_layer(
    root: Path,
    forest_area_id: int,
    layer: str,
    values: np.ndarray,
) -> Path:
    """
    Write a synthetic raster where the service expects it.

    The layout mirrors what the pipeline produces, so the
    service is exercised through its real path resolution
    rather than being handed a file directly.
    """

    path = (
        root
        / str(forest_area_id)
        / LAYERS[layer].relative_path
    )

    path.parent.mkdir(parents=True, exist_ok=True)

    profile = {
        "driver": "GTiff",
        "height": values.shape[0],
        "width": values.shape[1],
        "count": 1,
        "dtype": "float32",
        "crs": TEST_CRS,
        "transform": from_origin(
            500000.0, 8600000.0, 10.0, 10.0
        ),
        "nodata": NDVI_NODATA,
    }

    with rasterio.open(path, "w", **profile) as destination:
        destination.write(values.astype("float32"), 1)

    return path


def service_for(root: Path) -> RasterRenderService:
    """Point the service at the fixture directory."""

    service = RasterRenderService()
    service.settings = type(
        "StubSettings",
        (),
        {"satellite_image_storage_path": root},
    )()

    return service


def pixels(png: bytes) -> np.ndarray:
    """Decode a rendered PNG back to an RGBA array."""

    with Image.open(io.BytesIO(png)) as image:
        return np.array(image.convert("RGBA"))


# =========================================================
# COLOURING
# =========================================================

def test_ndvi_ramp_runs_red_at_low_to_green_at_high(
    tmp_path,
) -> None:
    """
    Low vegetation index draws red, high draws green.

    This is the reading the whole map depends on, so it is
    asserted on channel dominance rather than exact colours,
    which lets the palette be tuned without breaking the
    test.
    """

    values = np.array(
        [[-0.50, 0.90]], dtype="float32"
    )

    write_layer(tmp_path, 1, "ndvi_current", values)

    png, _, _ = service_for(tmp_path).render(
        1, "ndvi_current"
    )

    image = pixels(png)

    low = image[0][0]
    high = image[0][-1]

    assert low[0] > low[1], "low NDVI should be red-dominant"
    assert high[1] > high[0], "high NDVI should be green-dominant"


def test_selected_pair_change_renders_negative_decline_red_and_growth_green(
    tmp_path,
) -> None:
    values = np.array([[-0.45, NDVI_NODATA, 0.45]], dtype="float32")
    write_layer(tmp_path, 1, "selected_ndvi_difference", values)

    png, _, metadata = service_for(tmp_path).render(
        1, "selected_ndvi_difference"
    )
    image = pixels(png)
    service = service_for(tmp_path)

    assert metadata["description"].startswith("Recent NDVI minus previous NDVI")
    assert image[0, 0, 0] > image[0, 0, 1]
    assert image[0, 1, 3] == 0
    assert image[0, 2, 1] > image[0, 2, 0]
    assert service.layer_path(
        1, "selected_ndvi_difference", job_id=42, strict_job=True
    ) is None


def test_invalid_pixels_are_transparent(tmp_path) -> None:
    """
    A cloud-masked gap is transparent, not coloured.

    Drawn in the lowest colour of the ramp it would be
    indistinguishable from bare ground, which is the one
    reading an officer must not be given.
    """

    values = np.array(
        [[0.80, NDVI_NODATA]], dtype="float32"
    )

    write_layer(tmp_path, 1, "ndvi_current", values)

    png, _, metadata = service_for(tmp_path).render(
        1, "ndvi_current"
    )

    image = pixels(png)

    assert image[0][0][3] > 0, "measured pixel must be opaque"
    assert image[0][-1][3] == 0, "no-data pixel must be clear"
    assert metadata["valid_pixels"] == 1


def test_bounds_are_returned_in_wgs84(tmp_path) -> None:
    """
    Bounds come back as longitude and latitude.

    The map places the overlay with them, and the raster is
    in a projected system measured in metres, so an
    untransformed extent would put the image somewhere off
    the coast of Africa.
    """

    write_layer(
        tmp_path,
        1,
        "ndvi_current",
        np.full((4, 4), 0.5, dtype="float32"),
    )

    _, bounds, _ = service_for(tmp_path).render(
        1, "ndvi_current"
    )

    west, south, east, north = bounds

    assert -180.0 <= west < east <= 180.0
    assert -90.0 <= south < north <= 90.0

    # UTM 35S around this easting is the Copperbelt.
    assert 20.0 < west < 35.0
    assert -20.0 < south < -5.0


# =========================================================
# HISTOGRAM
# =========================================================

def test_histogram_counts_only_valid_pixels(
    tmp_path,
) -> None:
    """
    No-data pixels take no part in the distribution.

    Counted, they would pile a spike onto whichever bin the
    sentinel falls in and misrepresent the whole shape.
    """

    values = np.array(
        [
            [0.5, 0.5],
            [NDVI_NODATA, NDVI_NODATA],
        ],
        dtype="float32",
    )

    write_layer(tmp_path, 1, "ndvi_current", values)

    result = service_for(tmp_path).histogram(
        1, "ndvi_current", bins=10
    )

    assert result["valid_pixels"] == 2
    assert np.isclose(result["mean"], 0.5, atol=1e-4)

    assert (
        sum(row["count"] for row in result["bins"]) == 2
    )


def test_histogram_of_empty_scene_reports_nothing(
    tmp_path,
) -> None:
    """A fully masked scene yields no distribution."""

    write_layer(
        tmp_path,
        1,
        "ndvi_current",
        np.full((2, 2), NDVI_NODATA, dtype="float32"),
    )

    result = service_for(tmp_path).histogram(
        1, "ndvi_current"
    )

    assert result["valid_pixels"] == 0
    assert result["bins"] == []
    assert result["mean"] is None


# =========================================================
# DECIMATION
# =========================================================

def test_max_pool_keeps_a_small_clearing_visible() -> None:
    """
    One flagged pixel in a block keeps the block flagged.

    A clearing is a handful of pixels in a tile 10980 across.
    Averaging or nearest-sampling the mask when decimating
    would lose it, and the layer exists to show exactly that.
    """

    mask = np.zeros((40, 40), dtype="float32")

    mask[7][9] = 1.0

    pooled = _max_pool(mask, 4, 4)

    assert pooled.shape == (4, 4)
    assert pooled.max() == 1.0
    assert np.count_nonzero(pooled) == 1


# =========================================================
# POINT SAMPLING
# =========================================================

def test_sample_outside_the_raster_reads_nothing(
    tmp_path,
) -> None:
    """
    A click beyond the imagery returns null, never zero.

    Zero is a vegetation index an officer would read as bare
    ground. Null says the question has no answer here.
    """

    write_layer(
        tmp_path,
        1,
        "ndvi_current",
        np.full((4, 4), 0.6, dtype="float32"),
    )

    result = service_for(tmp_path).sample(
        1, longitude=10.0, latitude=10.0
    )

    assert result["readings"]["ndvi_current"] is None


def test_sample_on_a_masked_pixel_reads_nothing(
    tmp_path,
) -> None:
    """A click on a cloud gap is reported as no reading."""

    write_layer(
        tmp_path,
        1,
        "ndvi_current",
        np.full((4, 4), NDVI_NODATA, dtype="float32"),
    )

    service = service_for(tmp_path)

    # A point inside the fixture, converted to the
    # coordinates the API takes.
    with rasterio.open(
        service.layer_path(1, "ndvi_current")
    ) as source:
        xs, ys = transform(
            source.crs,
            WGS84_CRS,
            [source.bounds.left + 15],
            [source.bounds.top - 15],
        )

    result = service.sample(
        1, longitude=xs[0], latitude=ys[0]
    )

    assert result["readings"]["ndvi_current"] is None


# =========================================================
# ABSENT LAYERS
# =========================================================

def test_absent_layer_is_reported_not_invented(
    tmp_path,
) -> None:
    """
    A layer the pipeline never produced renders nothing.

    Returning a blank image instead would put an overlay on
    the map that looks like measured ground carrying no
    vegetation.
    """

    service = service_for(tmp_path)

    assert service.render(999, "ndvi_current") is None
    assert service.histogram(999, "ndvi_current") is None
    assert service.layer_path(999, "ndvi_current") is None


def test_strict_job_render_does_not_fall_back_to_legacy_scene_files(
    tmp_path,
) -> None:
    """A selected comparison can read only its own analysis job."""

    write_layer(
        tmp_path,
        7,
        "ndvi_difference",
        np.full((2, 2), 0.4, dtype="float32"),
    )
    service = service_for(tmp_path)

    assert service.layer_path(7, "ndvi_difference", job_id=42, strict_job=True) is None
    assert service.render(7, "ndvi_difference", job_id=42, strict_job=True) is None
    assert service.layer_path(7, "ndvi_difference") is not None


def test_available_layers_reports_what_exists(
    tmp_path,
) -> None:
    """The layer control is built from what is really there."""

    write_layer(
        tmp_path,
        1,
        "ndvi_current",
        np.full((2, 2), 0.4, dtype="float32"),
    )

    available = {
        entry["key"]: entry["available"]
        for entry in service_for(tmp_path).available_layers(1)
    }

    assert available["ndvi_current"] is True
    assert available["ndvi_previous"] is False
    assert available["ndvi_difference"] is False
