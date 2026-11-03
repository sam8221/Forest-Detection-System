"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Change Statistics

Purpose:
    Summarises what an analysis actually measured, so that a
    run which reports no deforestation can be told apart
    from a run that did not happen.

Why this exists:

    The pipeline computed an NDVI difference across 227,836
    pixels, found the largest decline anywhere in the scene
    to be 0.286 against a threshold of 0.30, and reported:

        Vegetation Change         0.00%
        Potential Affected Area   None detected

    Both figures were correct. Neither carried any evidence
    that a measurement had been taken, so an officer could
    not distinguish a clean negative result from a broken
    one, and reasonably concluded the system was faulty.

    A second run was more pointed still. It found 42
    contiguous pixels past the threshold, which is 0.42
    hectares, and discarded them because the minimum
    detectable area is 0.5 hectares. A real candidate
    clearing was suppressed eight pixels short of the legal
    criterion and nothing recorded that it had ever been
    seen.

    So every run now reports what it measured, not only what
    it concluded.

What this module will not do:
    It will not decide anything. Nothing here classifies a
    patch, raises an alert or alters a detection. These are
    descriptive statistics about a raster, kept apart from
    the detection rules so that reporting them cannot change
    what is detected.

    It holds no database session, opens no file and makes no
    request: it takes arrays and returns numbers, which is
    what lets the accuracy evaluation in Chapter Five check
    it against hand-worked values.

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

import numpy as np

import rasterio

from rasterio.features import shapes
from shapely.geometry import shape

from app.core.config import get_settings
from app.core.constants import NDVI_NODATA


#: Square metres in a hectare.
SQUARE_METRES_PER_HECTARE = 10_000.0


def measurable_mask(
    previous: np.ndarray,
    latest: np.ndarray,
) -> np.ndarray:
    """
    Pixels with a usable NDVI value on both dates.

    Args:
        previous:
            Cloud-masked NDVI from the baseline date.
        latest:
            Cloud-masked NDVI from the comparison date.

    Returns:
        A boolean array, true where both dates carry a real
        value.

    A pixel under cloud on either date cannot be compared,
    so it is excluded from every figure this module reports.
    Counting it as unchanged would let a cloudy scene look
    like a quiet one.
    """

    return (
        np.isfinite(previous)
        & np.isfinite(latest)
        & (previous != NDVI_NODATA)
        & (latest != NDVI_NODATA)
    )


def largest_contiguous_hectares(
    mask: np.ndarray,
    pixel_area_m2: float,
) -> float:
    """
    Area of the largest connected group of true pixels.

    Args:
        mask:
            Boolean array of pixels that passed the
            threshold.
        pixel_area_m2:
            Ground area of one pixel, 100 m² for Sentinel-2
            at 10 m.

    Returns:
        Hectares, or 0.0 when the mask is empty.

    Measured with eight-way connectivity, matching
    extract_detection_patches, so the figure reported here
    is the same one the minimum-area filter judged. Reporting
    four-way connectivity would understate the patch the
    filter actually considered and make a suppressed
    detection look further below the threshold than it was.

    Works on an array with no transform of its own: the
    polygons come out in pixel units and are converted with
    pixel_area_m2, which keeps this function free of any
    file.
    """

    if not np.any(mask):
        return 0.0

    as_bytes = mask.astype(np.uint8)

    largest_pixels = 0.0

    for geometry, value in shapes(
        as_bytes,
        mask=mask,
        transform=rasterio.Affine.identity(),
        connectivity=8,
    ):
        if value != 1:
            continue

        # With the identity transform a polygon's area is
        # its pixel count.
        largest_pixels = max(
            largest_pixels,
            shape(geometry).area,
        )

    return (
        largest_pixels
        * pixel_area_m2
        / SQUARE_METRES_PER_HECTARE
    )


def summarise_ndvi_change(
    previous: np.ndarray,
    latest: np.ndarray,
    pixel_area_m2: float,
    ndvi_threshold: float,
    minimum_area_hectares: float,
    inside_area: np.ndarray | None = None,
    significant_change_threshold: float | None = None,
) -> dict:
    """
    Describe the NDVI change a run measured.

    Args:
        previous:
            Cloud-masked NDVI from the baseline date.
        latest:
            Cloud-masked NDVI from the comparison date.
        pixel_area_m2:
            Ground area of one pixel.
        ndvi_threshold:
            Decline a pixel must show to be a candidate.
        minimum_area_hectares:
            Smallest clearing the system reports.
        inside_area:
            Boolean mask of the monitored forest area. When
            given, every figure describes only pixels inside
            it, because that is the area the analysis was
            commissioned for.

    Returns:
        A dictionary of plain numbers, or an "unmeasured"
        summary when no pixel was comparable on both dates.

    Every figure describes pixels, not conclusions. The
    threshold and minimum area are reported alongside the
    measurements so that a reader can see which rule
    produced the outcome, which is the difference between
    "nothing declined" and "something declined but was too
    small to report".
    """

    # Falls back to configuration so every caller gets the
    # same criterion without having to know it, while a test
    # can still state one explicitly.
    if significant_change_threshold is None:
        significant_change_threshold = (
            get_settings().ndvi_significant_change
        )

    measurable = measurable_mask(previous, latest)

    if inside_area is not None:
        measurable = measurable & inside_area

    total_pixels = int(
        inside_area.sum()
        if inside_area is not None
        else previous.size
    )

    measured_pixels = int(np.count_nonzero(measurable))

    if measured_pixels == 0:
        # Nothing was comparable. Reported as such rather
        # than as a change of zero: a wholly clouded scene
        # and a quiet forest are not the same finding.
        return {
            "measured": False,
            "reason": (
                "No pixel carried a usable NDVI value on "
                "both dates, so no change could be "
                "measured. The scene is cloud-covered or "
                "the two images do not overlap."
            ),
            "total_pixels": total_pixels,
            "measured_pixels": 0,
            "measured_percentage": 0.0,
            "ndvi_threshold": float(ndvi_threshold),
            "minimum_area_hectares": float(minimum_area_hectares),
            "significant_change_percentage": None,
            "significant_decline_percentage": None,
            "significant_increase_percentage": None,
            "little_change_percentage": None,
            "decline_hectares": None,
            "significant_decline_hectares": None,
            "significant_change_threshold": float(
                significant_change_threshold
            ),
        }

    # Negative means vegetation declined between the two
    # dates. The sign is stated here once because every
    # figure below depends on reading it the same way.
    change = (
        latest[measurable].astype(np.float64)
        - previous[measurable].astype(np.float64)
    )

    # Pixels that qualify for DETECTION. Judged against the
    # detection threshold and nothing else, because this is
    # the array the clearings are vectorised from.
    candidate = np.zeros(previous.shape, dtype=bool)

    candidate[measurable] = change <= -float(ndvi_threshold)

    candidate_pixels = int(np.count_nonzero(candidate))

    # Pixels that qualify as a DESCRIBED CHANGE. A separate,
    # much smaller criterion, and the separation is the whole
    # correction here.
    #
    # Significance used to be the detection threshold applied
    # symmetrically. That asks "was this pixel cleared", and
    # a 0.30 NDVI swing is most of a canopy either way, so a
    # scene with visible red and green across its difference
    # map reported 0.00 percent declined and 99.99 percent
    # unchanged. The cards were pinned near zero by the
    # criterion, not by the imagery.
    #
    # The detection figures above are untouched by this: no
    # value below alters which pixels become detections.
    significance = float(significant_change_threshold)

    significant_decline_pixels = int(
        np.count_nonzero(change <= -significance)
    )

    significant_increase_pixels = int(
        np.count_nonzero(change >= significance)
    )

    little_change_pixels = (
        measured_pixels
        - significant_decline_pixels
        - significant_increase_pixels
    )

    # Sign only: any movement at all, including movement far
    # below the noise floor. Kept because it is the honest
    # denominator for "did anything move", but never offered
    # as an affected area: at this criterion a scene of pure
    # sensor noise is half declining.
    decline_pixels = int(np.count_nonzero(change < 0.0))
    increase_pixels = int(np.count_nonzero(change > 0.0))

    def percentage(pixels: int) -> float:
        return round(100.0 * pixels / measured_pixels, 2)

    significant_decline_percentage = percentage(significant_decline_pixels)
    significant_increase_percentage = percentage(significant_increase_pixels)
    little_change_percentage = percentage(little_change_pixels)
    significant_change_percentage = percentage(
        significant_decline_pixels + significant_increase_pixels
    )

    largest_patch = largest_contiguous_hectares(
        candidate,
        pixel_area_m2,
    )

    return {
        "measured": True,
        "reason": None,
        # How much ground was actually looked at.
        "total_pixels": total_pixels,
        "measured_pixels": measured_pixels,
        "measured_percentage": round(
            100.0 * measured_pixels / total_pixels,
            2,
        )
        if total_pixels
        else 0.0,
        "measured_hectares": round(
            measured_pixels
            * pixel_area_m2
            / SQUARE_METRES_PER_HECTARE,
            4,
        ),
        # What the change looked like. The maximum decline
        # against the threshold is the single most useful
        # figure for a run that found nothing: it says
        # whether the scene was quiet or whether it came
        # close.
        "ndvi_change_min": round(float(change.min()), 4),
        "ndvi_change_max": round(float(change.max()), 4),
        "ndvi_change_mean": round(float(change.mean()), 4),
        "largest_decline": round(float(-change.min()), 4),
        # Sign-only counts distinguish any measured decline or
        # increase from significant change. The percentages below
        # use the recorded job threshold symmetrically, so a pixel
        # counts as significant only when |recent - previous| is at
        # least that threshold. Every share uses measurable pixels
        # as its denominator.
        "decline_pixels": decline_pixels,
        "increase_pixels": increase_pixels,
        "decline_hectares": round(
            decline_pixels
            * pixel_area_m2
            / SQUARE_METRES_PER_HECTARE,
            4,
        ),
        "significant_decline_pixels": significant_decline_pixels,
        "significant_increase_pixels": significant_increase_pixels,
        "little_change_pixels": little_change_pixels,
        # The area a decline large enough to be real covers.
        # This is what "potential affected area" means: not
        # every pixel that moved downward, which at a
        # sign-only criterion includes the noise floor and
        # would report hundreds of hectares from a quiet
        # scene.
        "significant_decline_hectares": round(
            significant_decline_pixels
            * pixel_area_m2
            / SQUARE_METRES_PER_HECTARE,
            4,
        ),
        # Stated so the interface can name the criterion
        # rather than hard-coding a number that would then
        # disagree with configuration.
        "significant_change_threshold": significance,
        "significant_decline_percentage": significant_decline_percentage,
        "significant_increase_percentage": significant_increase_percentage,
        "little_change_percentage": little_change_percentage,
        "significant_change_percentage": significant_change_percentage,
        # What passed the threshold, before the area filter.
        "candidate_pixels": candidate_pixels,
        "candidate_hectares": round(
            candidate_pixels
            * pixel_area_m2
            / SQUARE_METRES_PER_HECTARE,
            4,
        ),
        "largest_candidate_hectares": round(largest_patch, 4),
        # The rules that were applied, so the outcome can be
        # read against them.
        "ndvi_threshold": float(ndvi_threshold),
        "minimum_area_hectares": float(minimum_area_hectares),
        # Why a run reported nothing. Computed here rather
        # than in the interface so the same explanation
        # reaches the screen, the log and the dissertation.
        "outcome": _describe_outcome(
            candidate_pixels=candidate_pixels,
            largest_patch=largest_patch,
            largest_decline=float(-change.min()),
            ndvi_threshold=float(ndvi_threshold),
            minimum_area_hectares=float(minimum_area_hectares),
        ),
    }


def _describe_outcome(
    candidate_pixels: int,
    largest_patch: float,
    largest_decline: float,
    ndvi_threshold: float,
    minimum_area_hectares: float,
) -> str:
    """
    One sentence saying which rule produced the outcome.

    Args:
        candidate_pixels:
            Pixels that passed the NDVI threshold.
        largest_patch:
            Hectares in the largest connected candidate.
        largest_decline:
            Steepest NDVI decline measured, as a positive
            number.
        ndvi_threshold:
            Decline required of a pixel.
        minimum_area_hectares:
            Smallest clearing reported.

    Returns:
        Wording for the officer.

    Three outcomes, and an officer acts differently on each:

        Nothing approached the threshold. The forest was
        quiet over this interval; wait for the next pass.

        Pixels passed the threshold but no group of them
        reached the minimum area. Something changed and was
        deliberately not reported. Worth an eye on the next
        acquisition, and worth knowing about rather than
        being silently dropped.

        Clearings were reported. The detections speak for
        themselves.
    """

    if candidate_pixels == 0:
        return (
            f"No pixel declined by the {ndvi_threshold:.2f} "
            f"NDVI required. The steepest decline measured "
            f"anywhere in the monitored area was "
            f"{largest_decline:.3f}."
        )

    if largest_patch < minimum_area_hectares:
        return (
            f"{candidate_pixels} pixels declined past the "
            f"{ndvi_threshold:.2f} NDVI threshold, but the "
            f"largest connected group covers "
            f"{largest_patch:.2f} ha, below the "
            f"{minimum_area_hectares:.2f} ha minimum, so "
            f"none was reported as a clearing."
        )

    return (
        f"{candidate_pixels} pixels declined past the "
        f"{ndvi_threshold:.2f} NDVI threshold, the largest "
        f"group covering {largest_patch:.2f} ha."
    )
