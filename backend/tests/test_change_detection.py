"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Change Detection Tests

Purpose:
    Verify the rule that decides whether a pixel's NDVI
    decline counts as possible deforestation.

Responsibilities:
    - Confirm a decline above the threshold is flagged.
    - Confirm a decline below the threshold is not flagged.
    - Confirm the threshold boundary itself is flagged.
    - Confirm vegetation growth is never flagged.
    - Confirm unmeasurable pixels are never flagged.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Note:
    The decline passed to flag_change is calculated as

        previous NDVI - latest NDVI

    so a POSITIVE value means vegetation was lost.
===========================================================
"""

import numpy as np

from app.services.ndvi_service import NDVIService


# =========================================================
# THRESHOLD BEHAVIOUR
# =========================================================

def test_decline_above_threshold_is_flagged() -> None:
    """
    A pixel whose NDVI fell by more than the threshold is
    flagged as possible deforestation.
    """

    service = NDVIService()

    decline = np.array([[0.45]], dtype="float32")

    flagged = service.flag_change(
        ndvi_decline=decline,
        threshold=0.30,
    )

    assert flagged[0][0] == 1


def test_decline_below_threshold_is_not_flagged() -> None:
    """
    A pixel whose NDVI fell by less than the threshold is
    not flagged.

    This is what keeps ordinary variation in vegetation
    vigour from being reported as clearing.
    """

    service = NDVIService()

    decline = np.array([[0.29]], dtype="float32")

    flagged = service.flag_change(
        ndvi_decline=decline,
        threshold=0.30,
    )

    assert flagged[0][0] == 0


def test_decline_exactly_at_threshold_is_flagged() -> None:
    """
    The threshold is inclusive: a decline exactly equal to
    it is flagged.

    Fixing the boundary in a test means the rule cannot
    change silently when the code is edited.
    """

    service = NDVIService()

    decline = np.array([[0.30]], dtype="float32")

    flagged = service.flag_change(
        ndvi_decline=decline,
        threshold=0.30,
    )

    assert flagged[0][0] == 1


def test_vegetation_growth_is_never_flagged() -> None:
    """
    A negative decline means NDVI rose, so vegetation grew.

    Growth must never be reported as deforestation, however
    large the change.
    """

    service = NDVIService()

    decline = np.array([[-0.60]], dtype="float32")

    flagged = service.flag_change(
        ndvi_decline=decline,
        threshold=0.30,
    )

    assert flagged[0][0] == 0


def test_unmeasurable_pixels_are_never_flagged() -> None:
    """
    A pixel that could not be measured, typically because
    cloud was masked out on one of the two dates, is not
    evidence of vegetation loss.
    """

    service = NDVIService()

    decline = np.array([[np.nan]], dtype="float32")

    flagged = service.flag_change(
        ndvi_decline=decline,
        threshold=0.30,
    )

    assert flagged[0][0] == 0


def test_threshold_selects_only_qualifying_pixels() -> None:
    """
    Across a mixed array, only the pixels reaching the
    threshold are flagged.
    """

    service = NDVIService()

    decline = np.array(
        [[0.10, 0.29, 0.30, 0.55, -0.40, np.nan]],
        dtype="float32",
    )

    flagged = service.flag_change(
        ndvi_decline=decline,
        threshold=0.30,
    )

    expected = np.array(
        [[0, 0, 1, 1, 0, 0]],
        dtype="uint8",
    )

    assert np.array_equal(flagged, expected)
