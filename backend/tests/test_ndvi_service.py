"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: NDVI Calculation Tests

Purpose:
    Verify the NDVI formula against hand-calculated values.

Responsibilities:
    - Confirm NDVI matches values calculated by hand.
    - Confirm NDVI is zero when red equals near-infrared.
    - Confirm unmeasurable pixels do not produce a value.
    - Confirm the full expected NDVI range is reachable.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Note:
    These tests run without a database, without a network
    connection and without reading any raster file. They
    exercise the NDVI formula directly, which is what allows
    the detection results to be checked independently of the
    imagery pipeline.
===========================================================
"""

import numpy as np

from app.services.ndvi_service import NDVIService


# =========================================================
# NDVI FORMULA
# =========================================================

def test_ndvi_matches_hand_calculated_value() -> None:
    """
    NDVI = (NIR - RED) / (NIR + RED)

    With RED = 0.2 and NIR = 0.6:

        (0.6 - 0.2) / (0.6 + 0.2)
        = 0.4 / 0.8
        = 0.5
    """

    service = NDVIService()

    red = np.array([[0.2]], dtype="float32")
    nir = np.array([[0.6]], dtype="float32")

    ndvi = service.calculate_ndvi(red, nir)

    assert np.isclose(ndvi[0][0], 0.5, atol=1e-6)


def test_ndvi_is_zero_when_red_equals_nir() -> None:
    """
    When red and near-infrared are equal the numerator is
    zero, so NDVI is exactly zero.

    This is the boundary between vegetation and bare ground
    in the index, and it must not drift.
    """

    service = NDVIService()

    red = np.array([[0.3]], dtype="float32")
    nir = np.array([[0.3]], dtype="float32")

    ndvi = service.calculate_ndvi(red, nir)

    assert ndvi[0][0] == 0.0


def test_ndvi_is_not_measurable_when_both_bands_are_zero(
) -> None:
    """
    A pixel where both bands read zero carries no
    information: the denominator is zero and NDVI is
    undefined.

    Such a pixel must not be reported as a value, because
    zero would wrongly mean "no vegetation" rather than
    "not measured".
    """

    service = NDVIService()

    red = np.array([[0.0]], dtype="float32")
    nir = np.array([[0.0]], dtype="float32")

    ndvi = service.calculate_ndvi(red, nir)

    assert not np.isfinite(ndvi[0][0])


def test_ndvi_spans_the_expected_range() -> None:
    """
    NDVI is bounded by -1 and +1.

    Dense vegetation approaches +1 because near-infrared
    reflectance greatly exceeds red. Bare or cleared ground
    sits near zero or below.
    """

    service = NDVIService()

    red = np.array(
        [[0.05, 0.40, 0.80]],
        dtype="float32",
    )

    nir = np.array(
        [[0.80, 0.40, 0.05]],
        dtype="float32",
    )

    ndvi = service.calculate_ndvi(red, nir)

    # Healthy vegetation
    assert ndvi[0][0] > 0.8

    # Equal bands
    assert ndvi[0][1] == 0.0

    # Cleared ground
    assert ndvi[0][2] < -0.8

    assert np.all(ndvi >= -1.0)
    assert np.all(ndvi <= 1.0)
