"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Tests: Change statistics

What these protect:

    The reason this module was written. A run measured
    227,836 pixels, found the steepest NDVI decline anywhere
    to be 0.286 against a 0.30 threshold, and reported
    "0.00%" and "None detected" with no evidence that
    anything had been measured. A second run found 42
    contiguous pixels past the threshold, 0.42 hectares,
    and discarded them for being below the 0.5 hectare
    minimum without recording that they had been seen.

    Both outcomes were correct. Neither was legible. These
    tests keep the three outcomes distinguishable:

        nothing approached the threshold,
        something passed it but was too small to report,
        clearings were reported.

    Every figure is checked against a hand-worked array, so
    none of this needs a raster, a database or a network.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia
===========================================================
"""

import numpy as np
import pytest

from app.core.constants import NDVI_NODATA
from app.services.change_statistics import (
    largest_contiguous_hectares,
    measurable_mask,
    summarise_ndvi_change,
)


#: One Sentinel-2 pixel at 10 m.
PIXEL_AREA = 100.0

#: 0.5 ha is 50 pixels at 100 m² each.
MINIMUM_AREA = 0.5

THRESHOLD = 0.30


def flat(value, shape=(20, 20)):
    return np.full(shape, value, dtype=np.float32)


# =========================================================
# WHAT COUNTS AS MEASURABLE
# =========================================================


def test_a_pixel_clouded_on_either_date_is_not_measurable():
    """
    Counting it as unchanged would let a cloudy scene look
    like a quiet forest, which is exactly the confusion
    these statistics exist to remove.
    """

    previous = np.array([[0.8, NDVI_NODATA, 0.8]], dtype=np.float32)
    latest = np.array([[0.4, 0.4, NDVI_NODATA]], dtype=np.float32)

    assert measurable_mask(previous, latest).tolist() == [[True, False, False]]


def test_a_non_finite_value_is_not_measurable():
    previous = np.array([[0.8, np.nan, np.inf]], dtype=np.float32)
    latest = np.array([[0.4, 0.4, 0.4]], dtype=np.float32)

    assert measurable_mask(previous, latest).tolist() == [[True, False, False]]


# =========================================================
# PATCH AREA
# =========================================================


def test_the_largest_patch_is_measured_in_hectares():
    mask = np.zeros((10, 10), dtype=bool)

    # 50 pixels at 100 m² is exactly 0.5 ha, the minimum.
    mask[0:5, 0:10] = True

    assert largest_contiguous_hectares(mask, PIXEL_AREA) == pytest.approx(0.5)


def test_diagonally_touching_pixels_are_one_patch():
    """
    Eight-way connectivity, matching
    extract_detection_patches. Four-way would split a
    diagonal clearing and understate the patch the
    minimum-area filter actually judged, making a suppressed
    detection look further below the threshold than it was.
    """

    mask = np.zeros((4, 4), dtype=bool)

    mask[0, 0] = True
    mask[1, 1] = True

    assert largest_contiguous_hectares(mask, PIXEL_AREA) == pytest.approx(0.02)


def test_separate_patches_report_only_the_largest():
    mask = np.zeros((10, 20), dtype=bool)

    mask[0:2, 0:3] = True       # 6 pixels
    mask[5:9, 10:16] = True     # 24 pixels

    assert largest_contiguous_hectares(mask, PIXEL_AREA) == pytest.approx(0.24)


def test_an_empty_mask_has_no_patch():
    assert largest_contiguous_hectares(
        np.zeros((5, 5), dtype=bool),
        PIXEL_AREA,
    ) == 0.0


# =========================================================
# THE SUMMARY
# =========================================================


def test_a_quiet_forest_reports_the_steepest_decline_it_saw():
    """
    The case that looked like a fault.

    Nothing passed the threshold, so the officer needs to
    know how close anything came. A scene whose worst
    decline was 0.286 against a 0.30 threshold is a
    different situation from one whose worst was 0.01.
    """

    previous = flat(0.80)
    latest = flat(0.80)

    # One pixel declines by 0.286: just short of 0.30.
    latest[5, 5] = 0.80 - 0.286

    summary = summarise_ndvi_change(
        previous=previous,
        latest=latest,
        pixel_area_m2=PIXEL_AREA,
        ndvi_threshold=THRESHOLD,
        minimum_area_hectares=MINIMUM_AREA,
    )

    assert summary["measured"] is True
    assert summary["candidate_pixels"] == 0
    assert summary["largest_decline"] == pytest.approx(0.286, abs=1e-3)

    # The threshold is reported beside the measurement, so
    # the outcome can be read against the rule.
    assert summary["ndvi_threshold"] == THRESHOLD

    assert "No pixel declined" in summary["outcome"]
    assert "0.286" in summary["outcome"] or "0.29" in summary["outcome"]


def test_a_suppressed_candidate_is_reported_not_discarded():
    """
    The run that found 0.42 ha and said nothing.

    42 pixels passed the threshold, eight short of the 50
    the Forests Act criterion requires. Dropping them from
    the record entirely is what made a correct result look
    like a broken one.
    """

    previous = flat(0.80, shape=(30, 30))
    latest = flat(0.80, shape=(30, 30))

    # 42 contiguous pixels, a clear decline.
    latest[0, 0:30] = 0.30
    latest[1, 0:12] = 0.30

    summary = summarise_ndvi_change(
        previous=previous,
        latest=latest,
        pixel_area_m2=PIXEL_AREA,
        ndvi_threshold=THRESHOLD,
        minimum_area_hectares=MINIMUM_AREA,
    )

    assert summary["candidate_pixels"] == 42
    assert summary["largest_candidate_hectares"] == pytest.approx(0.42)

    # Said plainly: something changed and was deliberately
    # not reported, with both numbers that decided it.
    assert "42 pixels" in summary["outcome"]
    assert "0.42" in summary["outcome"]
    assert "0.50 ha minimum" in summary["outcome"]


def test_a_reportable_clearing_is_described_as_such():
    previous = flat(0.80, shape=(30, 30))
    latest = flat(0.80, shape=(30, 30))

    # 60 pixels: past both the threshold and the minimum.
    latest[0:2, 0:30] = 0.30

    summary = summarise_ndvi_change(
        previous=previous,
        latest=latest,
        pixel_area_m2=PIXEL_AREA,
        ndvi_threshold=THRESHOLD,
        minimum_area_hectares=MINIMUM_AREA,
    )

    assert summary["candidate_pixels"] == 60
    assert summary["largest_candidate_hectares"] == pytest.approx(0.6)

    assert "0.60 ha" in summary["outcome"]
    assert "below" not in summary["outcome"]


def test_change_percentages_use_comparable_pixels_and_the_change_criterion():
    """
    Describing a change and detecting a clearing are two
    different questions with two different thresholds.

    This test previously asserted that both used the
    detection threshold, and that is the assertion that kept
    the defect in place: a 0.30 NDVI swing is most of a
    canopy, so almost nothing in a real scene qualifies and
    the cards sat at 0.00 percent while the difference map
    showed red and green across the frame.

    The four pixels below change by -0.40, +0.40, -0.10 and
    +0.20. All four are real movements well clear of sensor
    noise, so all four are significant changes; only the
    first is steep enough to be a detection candidate.
    """

    previous = np.array(
        [[0.80, 0.40], [0.80, 0.40]],
        dtype=np.float32,
    )
    latest = np.array(
        [
            [0.40, 0.80],  # -0.40 and +0.40
            [0.70, 0.60],  # -0.10 and +0.20
        ],
        dtype=np.float32,
    )

    summary = summarise_ndvi_change(
        previous=previous,
        latest=latest,
        pixel_area_m2=PIXEL_AREA,
        ndvi_threshold=THRESHOLD,
        minimum_area_hectares=MINIMUM_AREA,
        significant_change_threshold=0.05,
    )

    assert summary["measured_pixels"] == 4

    # Sign only: any movement, noise included.
    assert summary["decline_pixels"] == 2
    assert summary["increase_pixels"] == 2
    assert summary["decline_hectares"] == pytest.approx(0.02)

    # Described change: both declines and both increases are
    # larger than the noise floor.
    assert summary["significant_decline_pixels"] == 2
    assert summary["significant_increase_pixels"] == 2
    assert summary["little_change_pixels"] == 0
    assert summary["significant_decline_percentage"] == 50.0
    assert summary["significant_increase_percentage"] == 50.0
    assert summary["little_change_percentage"] == 0.0
    assert summary["significant_change_percentage"] == 100.0

    # Detection: only the -0.40 pixel reaches the 0.30
    # threshold. Unchanged by anything above.
    assert summary["candidate_pixels"] == 1

    # The criterion is reported so the interface can name it
    # instead of hard-coding a number that would then
    # disagree with configuration.
    assert summary["significant_change_threshold"] == 0.05


def test_the_change_criterion_does_not_alter_detection():
    """
    The guarantee that makes the new threshold safe. It
    describes; it never detects. Moving it must not create
    or destroy a single detection candidate.
    """

    previous = flat(0.80, shape=(30, 30))
    latest = flat(0.80, shape=(30, 30))

    latest[0:2, 0:30] = 0.30   # 60 px past the 0.30 threshold
    latest[5, 0:20] = 0.70     # 20 px of -0.10: described only

    candidates = set()

    for significance in (0.01, 0.05, 0.10, 0.25):
        summary = summarise_ndvi_change(
            previous=previous,
            latest=latest,
            pixel_area_m2=PIXEL_AREA,
            ndvi_threshold=THRESHOLD,
            minimum_area_hectares=MINIMUM_AREA,
            significant_change_threshold=significance,
        )

        candidates.add(
            (
                summary["candidate_pixels"],
                round(summary["candidate_hectares"], 4),
                round(summary["largest_candidate_hectares"], 4),
            )
        )

    # One distinct result across four very different
    # criteria: the detection figures did not move.
    assert candidates == {(60, 0.6, 0.6)}


def test_a_noise_level_movement_is_not_called_vegetation_change():
    """
    Below the noise floor a difference cannot be told from
    atmospheric correction residue and sensor noise.
    Reporting it as vegetation change would present
    measurement error as a finding, and at a sign-only
    criterion a quiet scene is half declining.
    """

    previous = flat(0.80)
    latest = flat(0.80)

    latest[0:5, 0:5] = 0.78  # -0.02, below the floor

    summary = summarise_ndvi_change(
        previous=previous,
        latest=latest,
        pixel_area_m2=PIXEL_AREA,
        ndvi_threshold=THRESHOLD,
        minimum_area_hectares=MINIMUM_AREA,
        significant_change_threshold=0.05,
    )

    # Every pixel moved downward by sign...
    assert summary["decline_pixels"] == 25

    # ...and none of it is reported as change or as area.
    assert summary["significant_decline_pixels"] == 0
    assert summary["significant_decline_hectares"] == 0.0
    assert summary["little_change_percentage"] == 100.0


def test_change_percentages_are_unavailable_when_no_pixels_are_measurable():
    summary = summarise_ndvi_change(
        previous=flat(NDVI_NODATA, shape=(2, 2)),
        latest=flat(NDVI_NODATA, shape=(2, 2)),
        pixel_area_m2=PIXEL_AREA,
        ndvi_threshold=THRESHOLD,
        minimum_area_hectares=MINIMUM_AREA,
    )

    assert summary["measured"] is False
    assert summary["significant_change_percentage"] is None
    assert summary["significant_decline_percentage"] is None
    assert summary["significant_increase_percentage"] is None
    assert summary["little_change_percentage"] is None
    assert summary["decline_hectares"] is None


def test_the_three_outcomes_are_worded_differently():
    """
    An officer acts differently on each, so none may read
    like another.
    """

    def outcome(latest):
        return summarise_ndvi_change(
            previous=flat(0.80, shape=(30, 30)),
            latest=latest,
            pixel_area_m2=PIXEL_AREA,
            ndvi_threshold=THRESHOLD,
            minimum_area_hectares=MINIMUM_AREA,
        )["outcome"]

    quiet = flat(0.80, shape=(30, 30))

    small = flat(0.80, shape=(30, 30))
    small[0, 0:10] = 0.30

    large = flat(0.80, shape=(30, 30))
    large[0:2, 0:30] = 0.30

    wordings = {outcome(quiet), outcome(small), outcome(large)}

    assert len(wordings) == 3


def test_a_wholly_clouded_scene_is_unmeasured_not_unchanged():
    """
    The distinction this module turns on. No comparable
    pixel is not a change of zero, and an officer reading
    the first waits for clearer imagery while one reading
    the second concludes the forest is intact.
    """

    previous = flat(NDVI_NODATA)
    latest = flat(0.80)

    summary = summarise_ndvi_change(
        previous=previous,
        latest=latest,
        pixel_area_m2=PIXEL_AREA,
        ndvi_threshold=THRESHOLD,
        minimum_area_hectares=MINIMUM_AREA,
    )

    assert summary["measured"] is False
    assert summary["measured_pixels"] == 0
    assert "cloud-covered" in summary["reason"]

    # No change figure is offered at all.
    assert "ndvi_change_mean" not in summary


def test_how_much_ground_was_observed_is_reported():
    """
    A result from a quarter of the scene deserves less
    confidence than one from all of it, and the officer
    cannot see the cloud mask.
    """

    previous = flat(0.80, shape=(10, 10))
    latest = flat(0.75, shape=(10, 10))

    # Three quarters of the scene unusable on one date.
    previous[0:75 // 10, :] = NDVI_NODATA

    summary = summarise_ndvi_change(
        previous=previous,
        latest=latest,
        pixel_area_m2=PIXEL_AREA,
        ndvi_threshold=THRESHOLD,
        minimum_area_hectares=MINIMUM_AREA,
    )

    assert summary["measured_pixels"] == 30
    assert summary["measured_percentage"] == pytest.approx(30.0)
    assert summary["measured_hectares"] == pytest.approx(0.3)


def test_greening_is_reported_as_a_positive_mean():
    """
    All three of the real runs had a positive mean: the
    vegetation got greener. Reporting the sign correctly is
    what shows an officer that the forest was not declining
    at all.
    """

    summary = summarise_ndvi_change(
        previous=flat(0.60),
        latest=flat(0.70),
        pixel_area_m2=PIXEL_AREA,
        ndvi_threshold=THRESHOLD,
        minimum_area_hectares=MINIMUM_AREA,
    )

    assert summary["ndvi_change_mean"] == pytest.approx(0.1, abs=1e-3)
    assert summary["candidate_pixels"] == 0
    assert summary["largest_decline"] < 0 or summary["largest_decline"] == pytest.approx(
        -0.1, abs=1e-3
    )


def test_only_pixels_inside_the_monitored_area_are_counted():
    """
    A Sentinel-2 tile is about 110 km square and a monitored
    area is a small part of it. Statistics over the whole
    tile would describe land the analysis was not
    commissioned for.
    """

    previous = flat(0.80, shape=(10, 10))
    latest = flat(0.80, shape=(10, 10))

    # A steep decline outside the boundary.
    latest[9, :] = 0.10

    inside = np.zeros((10, 10), dtype=bool)
    inside[0:5, :] = True

    summary = summarise_ndvi_change(
        previous=previous,
        latest=latest,
        pixel_area_m2=PIXEL_AREA,
        ndvi_threshold=THRESHOLD,
        minimum_area_hectares=MINIMUM_AREA,
        inside_area=inside,
    )

    assert summary["total_pixels"] == 50
    assert summary["measured_pixels"] == 50

    # The decline outside is not reported at all.
    assert summary["candidate_pixels"] == 0
    assert summary["ndvi_change_min"] == pytest.approx(0.0)


def test_the_statistics_decide_nothing():
    """
    Descriptive only. The summary reports the threshold and
    the minimum area it was given; it never alters them, and
    nothing in it classifies a patch or raises an alert.
    """

    summary = summarise_ndvi_change(
        previous=flat(0.80),
        latest=flat(0.40),
        pixel_area_m2=PIXEL_AREA,
        ndvi_threshold=0.25,
        minimum_area_hectares=0.75,
    )

    assert summary["ndvi_threshold"] == 0.25
    assert summary["minimum_area_hectares"] == 0.75

    assert "detection" not in summary
    assert "alert" not in summary
