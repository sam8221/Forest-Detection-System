"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Storage Path Tests

Purpose:
    Verify that each analysis job keeps its own raster
    outputs, and that results produced before per-job
    storage are still readable.

Responsibilities:
    - Confirm two jobs over one area stay separate.
    - Confirm a new job cannot overwrite an older one.
    - Confirm a job reads its own rasters, not a newer job's.
    - Confirm the pre-job layout is still reachable.
    - Confirm the legacy fallback is reported, not hidden.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Note:
    The regression guarded here was real: outputs were named
    after the FOREST AREA, so every analysis overwrote the
    one before it. Asking for an older job then returned the
    newest rasters under that job's observation dates, and
    the figures and the dates described different
    observations.

    These tests write small files rather than rasters. What
    is under test is which file a job resolves to, not what
    is inside it.
===========================================================
"""

from pathlib import Path

from app.services.storage_paths import (
    job_output_root,
    legacy_output_root,
    resolve_layer,
    resolve_output_root,
)


LAYER = "processing/masked_ndvi/ndvi_masked.tif"


def write(path: Path, text: str) -> Path:
    """Create a file standing in for a raster output."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")

    return path


# =========================================================
# SEPARATION
# =========================================================

def test_two_jobs_over_one_area_keep_separate_outputs(
    tmp_path,
) -> None:
    """
    Each job writes to its own directory.

    This is the whole point of the change: an area may be
    analysed many times, and each analysis is a distinct
    observation that must survive the next one.
    """

    first = job_output_root(19, 100, tmp_path)
    second = job_output_root(19, 101, tmp_path)

    assert first != second

    write(first / LAYER, "job 100")
    write(second / LAYER, "job 101")

    assert (first / LAYER).read_text() == "job 100"
    assert (second / LAYER).read_text() == "job 101"


def test_a_new_job_does_not_disturb_an_older_one(
    tmp_path,
) -> None:
    """
    Writing a later job leaves the earlier one untouched.

    The regression this guards against: the later run
    replaced the earlier run's file, and the earlier
    observation was gone.
    """

    earlier = write(
        job_output_root(19, 100, tmp_path) / LAYER,
        "earlier observation",
    )

    write(
        job_output_root(19, 101, tmp_path) / LAYER,
        "later observation",
    )

    assert earlier.read_text() == "earlier observation"


def test_a_job_resolves_to_its_own_raster(tmp_path) -> None:
    """
    Asking for a job returns that job's file.

    Previously both jobs resolved to the same path, so the
    older one reported the newer one's measurements.
    """

    write(
        job_output_root(19, 100, tmp_path) / LAYER,
        "earlier observation",
    )

    write(
        job_output_root(19, 101, tmp_path) / LAYER,
        "later observation",
    )

    earlier_path, earlier_legacy = resolve_layer(
        19, 100, LAYER, tmp_path
    )

    later_path, later_legacy = resolve_layer(
        19, 101, LAYER, tmp_path
    )

    assert earlier_path.read_text() == "earlier observation"
    assert later_path.read_text() == "later observation"

    assert earlier_legacy is False
    assert later_legacy is False


# =========================================================
# LEGACY FALLBACK
# =========================================================

def test_a_job_without_its_own_outputs_falls_back(
    tmp_path,
) -> None:
    """
    Results from before the change are still readable.

    They are the only record of those analyses, so they are
    neither moved nor deleted, and a job with no directory
    of its own reads them.
    """

    write(
        legacy_output_root(19, tmp_path) / LAYER,
        "pre-job output",
    )

    path, is_legacy = resolve_layer(19, 100, LAYER, tmp_path)

    assert path.read_text() == "pre-job output"
    assert is_legacy is True


def test_the_legacy_fallback_is_reported_not_hidden(
    tmp_path,
) -> None:
    """
    A caller can tell which storage answered.

    It matters: pre-job outputs overwrote each other, so
    they may belong to a LATER analysis of the same area
    than the job whose dates are shown beside them. The
    interface has to say so rather than presenting them as
    that job's own measurements.
    """

    write(
        legacy_output_root(19, tmp_path) / LAYER,
        "shared output",
    )

    _, legacy_only = resolve_output_root(19, 100, tmp_path)

    assert legacy_only is True

    write(
        job_output_root(19, 100, tmp_path) / LAYER,
        "own output",
    )

    _, now_own = resolve_output_root(19, 100, tmp_path)

    assert now_own is False


def test_a_jobs_own_outputs_win_over_the_legacy_ones(
    tmp_path,
) -> None:
    """
    Where both exist, the job's own files are used.

    An area analysed before and after the change has both,
    and the job-specific result is the one that actually
    belongs to the job being asked about.
    """

    write(
        legacy_output_root(19, tmp_path) / LAYER,
        "shared output",
    )

    write(
        job_output_root(19, 100, tmp_path) / LAYER,
        "own output",
    )

    path, is_legacy = resolve_layer(19, 100, LAYER, tmp_path)

    assert path.read_text() == "own output"
    assert is_legacy is False


# =========================================================
# ABSENCE
# =========================================================

def test_a_layer_that_was_never_produced_is_absent(
    tmp_path,
) -> None:
    """
    Nothing is invented for an area with no outputs.

    Returning a path that does not exist would let a caller
    believe a layer is available and draw an empty overlay,
    which reads as measured ground carrying no vegetation.
    """

    path, is_legacy = resolve_layer(99, 1, LAYER, tmp_path)

    assert path is None
    assert is_legacy is False


def test_outputs_of_different_areas_do_not_collide(
    tmp_path,
) -> None:
    """
    Two areas analysed under the same job numbering stay
    apart, because the area is part of the path.
    """

    write(
        job_output_root(18, 100, tmp_path) / LAYER,
        "area 18",
    )

    write(
        job_output_root(19, 100, tmp_path) / LAYER,
        "area 19",
    )

    eighteen, _ = resolve_layer(18, 100, LAYER, tmp_path)
    nineteen, _ = resolve_layer(19, 100, LAYER, tmp_path)

    assert eighteen.read_text() == "area 18"
    assert nineteen.read_text() == "area 19"
