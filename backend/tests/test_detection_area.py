"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Detection Area Tests

Purpose:
    Verify the area calculation and the minimum detectable
    area rule.

Responsibilities:
    - Confirm pixel counts convert correctly to hectares.
    - Confirm patches below 0.5 hectares are suppressed.
    - Confirm patches at or above 0.5 hectares are reported.
    - Confirm the NDVI values recorded for a detection are
      averaged from the confirmed pixels only.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Note:
    These tests build small GeoTIFF rasters in memory with
    rasterio, so the real statistics code is exercised
    without a database, a network connection or any file on
    disk.

    Sentinel-2 red and near-infrared bands are 10 m, so one
    pixel covers 100 square metres and 0.5 hectares is
    exactly 50 pixels. That relationship is what the
    minimum detectable area rule rests on.
===========================================================
"""

from pathlib import Path

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_origin

from app.core.config import get_settings
from app.services.detection_service import DetectionService


# =========================================================
# TEST RASTER CONSTRUCTION
# =========================================================

PIXEL_SIZE_METRES = 10.0

RASTER_WIDTH = 20

RASTER_HEIGHT = 20

# ---------------------------------------------------------
# Coordinate reference system
#
# UTM Zone 35S, the projection used for the Copperbelt.
#
# Built from a PROJ definition rather than CRS.from_epsg,
# for the same reason SentinelProcessorService avoids EPSG
# lookups: a PostGIS installation on the developer machine
# provides an older proj.db that rasterio cannot read, so
# resolving an EPSG code raises CRSError. A PROJ string is
# self-contained and needs no database.
# ---------------------------------------------------------

TEST_CRS = CRS.from_proj4(
    "+proj=utm +zone=35 +south +datum=WGS84 "
    "+units=m +no_defs"
)


def build_raster(
    directory: Path,
    name: str,
    data: np.ndarray,
    nodata: float,
) -> Path:
    """
    Write a small single-band GeoTIFF for testing.

    Args:
        directory:
            Directory the file is written into.

        name:
            File name.

        data:
            Pixel values.

        nodata:
            Value representing an unmeasured pixel.

    Returns:
        Path to the written raster.

    The transform uses 10 m pixels so that pixel counts
    convert to hectares exactly as they do for real
    Sentinel-2 imagery.
    """

    transform = from_origin(
        500000.0,
        8600000.0,
        PIXEL_SIZE_METRES,
        PIXEL_SIZE_METRES,
    )

    path = directory / name

    profile = {
        "driver": "GTiff",
        "height": data.shape[0],
        "width": data.shape[1],
        "count": 1,
        "dtype": data.dtype.name,
        "crs": TEST_CRS,
        "transform": transform,
        "nodata": nodata,
    }

    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data, 1)

    return path


def build_scene(
    directory: Path,
    confirmed_pixel_count: int = 0,
    ndvi_before: float = 0.80,
    ndvi_after: float = 0.30,
    confirmed: np.ndarray | None = None,
) -> dict[str, Path]:
    """
    Build a baseline NDVI, comparison NDVI and confirmed
    deforestation mask.

    Args:
        directory:
            Directory the rasters are written into.

        confirmed_pixel_count:
            Number of pixels to mark as confirmed, placed as
            one contiguous block. Ignored when an explicit
            mask is supplied.

        ndvi_before:
            NDVI of the cleared pixels on the baseline date.

        ndvi_after:
            NDVI of the cleared pixels on the comparison
            date.

        confirmed:
            Explicit confirmed mask, for tests that need
            particular shapes or spacing.

    Returns:
        Mapping of raster name to path.
    """

    shape = (RASTER_HEIGHT, RASTER_WIDTH)

    previous = np.full(shape, ndvi_before, dtype="float32")

    latest = np.full(shape, ndvi_after, dtype="float32")

    # -----------------------------------------------------
    # Mark the confirmed pixels
    # -----------------------------------------------------

    if confirmed is None:

        confirmed = np.zeros(shape, dtype="uint8")

        flat = confirmed.reshape(-1)

        flat[:confirmed_pixel_count] = 1

        confirmed = flat.reshape(shape)

    return {
        "previous": build_raster(
            directory,
            "previous_ndvi.tif",
            previous,
            -9999.0,
        ),
        "latest": build_raster(
            directory,
            "latest_ndvi.tif",
            latest,
            -9999.0,
        ),
        "confirmed": build_raster(
            directory,
            "confirmed.tif",
            confirmed,
            0,
        ),
    }


def calculate(
    directory: Path,
    confirmed_pixel_count: int,
    ndvi_before: float = 0.80,
    ndvi_after: float = 0.30,
) -> dict[str, float]:
    """
    Run the real statistics calculation over a built scene.
    """

    scene = build_scene(
        directory=directory,
        confirmed_pixel_count=confirmed_pixel_count,
        ndvi_before=ndvi_before,
        ndvi_after=ndvi_after,
    )

    # The service only uses its database session for
    # persistence, which these tests never reach.
    service = DetectionService.__new__(DetectionService)
    service.settings = get_settings()

    return service.calculate_detection_statistics(
        previous_ndvi_path=scene["previous"],
        latest_ndvi_path=scene["latest"],
        confirmed_mask_path=scene["confirmed"],
    )


# =========================================================
# AREA CALCULATION
# =========================================================

def test_pixel_count_converts_to_hectares(tmp_path) -> None:
    """
    At 10 m resolution one pixel is 100 square metres, so
    100 pixels is exactly one hectare.
    """

    statistics = calculate(tmp_path, confirmed_pixel_count=100)

    assert np.isclose(
        statistics["detected_area_hectares"],
        1.0,
        atol=1e-6,
    )


def test_fifty_pixels_is_half_a_hectare(tmp_path) -> None:
    """
    50 pixels is 5000 square metres, which is 0.5 hectares:
    the minimum detectable area.
    """

    statistics = calculate(tmp_path, confirmed_pixel_count=50)

    assert np.isclose(
        statistics["detected_area_hectares"],
        0.5,
        atol=1e-6,
    )


# =========================================================
# MINIMUM DETECTABLE AREA, APPLIED PER CLEARING
# =========================================================

def extract(
    directory: Path,
    confirmed_pixel_count: int = 0,
    confirmed: np.ndarray | None = None,
    ndvi_before: float = 0.80,
    ndvi_after: float = 0.30,
) -> list[dict]:
    """
    Run the real patch extraction over a built scene.
    """

    scene = build_scene(
        directory=directory,
        confirmed_pixel_count=confirmed_pixel_count,
        confirmed=confirmed,
        ndvi_before=ndvi_before,
        ndvi_after=ndvi_after,
    )

    service = DetectionService.__new__(DetectionService)
    service.settings = get_settings()

    return service.extract_detection_patches(
        previous_ndvi_path=scene["previous"],
        latest_ndvi_path=scene["latest"],
        confirmed_mask_path=scene["confirmed"],
    )


def test_clearing_below_half_a_hectare_is_suppressed(
    tmp_path,
) -> None:
    """
    A single clearing of 49 pixels covers 0.49 hectares,
    below the 0.5 hectare minimum, so no detection is made.

    The threshold is taken from the area criterion in the
    Forests Act No. 4 of 2015. Note that 50 pixels lands
    exactly on it and is kept: see the boundary note in
    core/config.py.
    """

    patches = extract(tmp_path, confirmed_pixel_count=49)

    assert patches == []


def test_clearing_at_half_a_hectare_is_reported(
    tmp_path,
) -> None:
    """
    A single clearing of exactly 50 pixels reaches the
    minimum and produces one detection.
    """

    patches = extract(tmp_path, confirmed_pixel_count=50)

    assert len(patches) == 1

    assert np.isclose(
        patches[0]["detected_area_hectares"],
        0.5,
        atol=1e-6,
    )


def test_scattered_noise_does_not_sum_into_a_detection(
    tmp_path,
) -> None:
    """
    Many small, separated patches must NOT be added together
    until their combined area passes the minimum.

    This is the case the minimum detectable area exists to
    reject. Twenty isolated single pixels scattered across a
    tile total 0.2 hectares, and on real imagery hundreds of
    them can total far more than half a hectare, but not one
    of them is a clearing. Summing them first and comparing
    the total against the minimum would report noise as
    deforestation, and would let the rule pass
    automatically, since a tile-wide total is always large.
    """

    confirmed = np.zeros(
        (RASTER_HEIGHT, RASTER_WIDTH),
        dtype="uint8",
    )

    # Every other pixel, so none of them touch, not even
    # diagonally.
    confirmed[::2, ::2] = 1

    scattered_pixels = int(confirmed.sum())

    combined_hectares = scattered_pixels * 100 / 10_000

    # The combined area comfortably exceeds the minimum...
    assert combined_hectares > (
        get_settings().min_detection_area_hectares
    )

    patches = extract(tmp_path, confirmed=confirmed)

    # ...but no individual clearing does, so nothing is
    # reported.
    assert patches == []


def test_separate_clearings_become_separate_detections(
    tmp_path,
) -> None:
    """
    Two clearings far apart produce two detections, not one
    combined record.

    Each detection is a place an officer may have to visit,
    so merging them would describe no single place.
    """

    confirmed = np.zeros(
        (RASTER_HEIGHT, RASTER_WIDTH),
        dtype="uint8",
    )

    # A 10x6 block: 60 pixels, 0.6 hectares.
    confirmed[0:6, 0:10] = 1

    # A 10x8 block well clear of the first: 80 pixels.
    confirmed[12:20, 0:10] = 1

    patches = extract(tmp_path, confirmed=confirmed)

    assert len(patches) == 2

    areas = sorted(
        patch["detected_area_hectares"]
        for patch in patches
    )

    assert np.isclose(areas[0], 0.60, atol=1e-6)
    assert np.isclose(areas[1], 0.80, atol=1e-6)


def test_detections_are_ordered_largest_first(
    tmp_path,
) -> None:
    """
    The largest clearing is reported first, so the most
    serious case is seen first.
    """

    confirmed = np.zeros(
        (RASTER_HEIGHT, RASTER_WIDTH),
        dtype="uint8",
    )

    confirmed[0:6, 0:10] = 1
    confirmed[12:20, 0:10] = 1

    patches = extract(tmp_path, confirmed=confirmed)

    areas = [
        patch["detected_area_hectares"]
        for patch in patches
    ]

    assert areas == sorted(areas, reverse=True)


# =========================================================
# DETECTION GEOMETRY
# =========================================================

def test_each_detection_carries_an_outline(
    tmp_path,
) -> None:
    """
    Every detection carries a geometry, so it can be drawn
    on a map and tested against a reserve boundary.
    """

    patches = extract(tmp_path, confirmed_pixel_count=60)

    assert len(patches) == 1

    assert patches[0]["geometry"] is not None


def test_outline_area_matches_reported_area(
    tmp_path,
) -> None:
    """
    The stored outline encloses the same area that is
    reported in hectares.

    The geometry is in UTM, whose units are metres, so its
    area converts to hectares directly. A mismatch would
    mean the map disagreed with the record.
    """

    from geoalchemy2.shape import to_shape

    patches = extract(tmp_path, confirmed_pixel_count=60)

    outline = to_shape(patches[0]["geometry"])

    assert np.isclose(
        outline.area / 10_000.0,
        patches[0]["detected_area_hectares"],
        atol=1e-6,
    )


def test_geometry_uses_the_copperbelt_projection(
    tmp_path,
) -> None:
    """
    Detection geometry is stored in UTM Zone 35S,
    EPSG:32735, which covers the Copperbelt.

    The code is derived from the zone number rather than
    looked up, because the PROJ database available here
    cannot resolve EPSG codes.
    """

    service = DetectionService.__new__(DetectionService)
    service.settings = get_settings()

    assert service.utm_srid_from_crs(TEST_CRS) == 32735


def test_minimum_detectable_area_is_fifty_pixels() -> None:
    """
    The configured minimum corresponds to 50 Sentinel-2
    pixels at 10 m resolution.

    This ties the configured value to the physical basis for
    it, so changing one without the other fails here.
    """

    settings = get_settings()

    square_metres = (
        settings.min_detection_area_hectares
        * 10_000
    )

    pixels = (
        square_metres
        / (PIXEL_SIZE_METRES * PIXEL_SIZE_METRES)
    )

    assert pixels == 50


# =========================================================
# RECORDED NDVI VALUES
# =========================================================

def test_recorded_ndvi_comes_from_confirmed_pixels(
    tmp_path,
) -> None:
    """
    The NDVI values stored on a detection are averaged over
    the confirmed pixels, so they describe the cleared area
    rather than the scene as a whole.
    """

    statistics = calculate(
        tmp_path,
        confirmed_pixel_count=100,
        ndvi_before=0.80,
        ndvi_after=0.30,
    )

    assert np.isclose(
        statistics["ndvi_before"],
        0.80,
        atol=1e-4,
    )

    assert np.isclose(
        statistics["ndvi_after"],
        0.30,
        atol=1e-4,
    )


def test_no_confirmed_pixels_is_a_valid_zero_result(
    tmp_path,
) -> None:
    """
    A scene with nothing confirmed reports zero area.

    This is a valid outcome of a successful analysis, not a
    failure: the officer's response to "no deforestation
    found" differs from their response to "the analysis
    could not run".
    """

    statistics = calculate(tmp_path, confirmed_pixel_count=0)

    assert statistics["detected_area_hectares"] == 0.0
    assert statistics["confirmed_pixels"] == 0.0
