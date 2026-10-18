"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Storage Paths

Purpose:
    Decides where an analysis job's raster outputs live, and
    finds them again afterwards.

Responsibilities:
    - Give each job its own output directory.
    - Resolve a layer for a specific job.
    - Fall back to the pre-job layout for older results.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Why this module exists:

    Outputs used to be written to

        storage/satellite_images/<forest_area_id>/...

    so every analysis of an area overwrote the one before
    it. Only the newest rasters survived, and asking for an
    older job returned the newest rasters under that job's
    observation dates: the figures and the dates described
    different observations, which is worse than having no
    figures at all.

    Outputs now go to

        storage/satellite_images/<forest_area_id>/jobs/<job_id>/...

    which is immutable once written, because a job is
    created before it is processed and its identifier never
    changes. A new analysis cannot touch an older job's
    results.

    The writer and the three readers all resolve paths
    through this module, so there is one definition of where
    a layer lives rather than four that can drift apart.

The legacy layout:

    Results produced before this change are still on disk in
    the old location, and are still the only record of those
    analyses. They are not moved or deleted. A job with no
    directory of its own falls back to them, so existing
    maps keep working.

    What cannot be recovered is which of those older jobs
    produced them: they overwrote each other, and only the
    last survives. Every job for one area therefore resolves
    to the same legacy rasters, and is_legacy says so in the
    responses that carry them. Separating them would require
    re-running the analyses.

Version:
    1.0.0
===========================================================
"""

from __future__ import annotations

from pathlib import Path

from app.core.config import get_settings


#: Directory holding per-job outputs beneath a forest area.
JOBS_DIRECTORY = "jobs"


def forest_area_root(
    forest_area_id: int,
    storage_root: Path | None = None,
) -> Path:
    """
    Return the directory holding everything for an area.

    Downloaded products live here directly; processed
    outputs live under the jobs subdirectory.

    storage_root overrides the configured imagery root. A
    caller that already holds its own settings passes it in
    rather than letting this module read the configuration
    again, so the writer and the readers cannot end up
    pointing at two different roots.
    """

    base = (
        storage_root
        if storage_root is not None
        else get_settings().satellite_image_storage_path
    )

    return base / str(forest_area_id)


def job_output_root(
    forest_area_id: int,
    job_id: int,
    storage_root: Path | None = None,
) -> Path:
    """
    Return the output directory belonging to one job.

    This is where a new analysis writes. It is specific to
    the job, so running another analysis over the same
    forest area cannot overwrite it.
    """

    return (
        forest_area_root(forest_area_id, storage_root)
        / JOBS_DIRECTORY
        / str(job_id)
    )


def shared_extract_root(
    forest_area_id: int,
    satellite_image_id: int,
    storage_root: Path | None = None,
) -> Path:
    """
    Return where one product's extracted bands are kept.

    Extraction is shared per product rather than copied into
    each job, because the unpacked bands are identical
    whichever analysis reads them. A Level-2A product unpacks
    to roughly a gigabyte, so copying it per job filled the
    volume at a rate of about two gigabytes a run: one
    analysis of one forest area consumed 3.7 GB, of which
    1.9 GB was two copies of imagery already on disk.

    Only the DERIVED rasters belong to a job, and those stay
    under its own directory. They are the outputs an audit
    needs, and they are a few hundred megabytes rather than
    gigabytes.

    Sharing is safe because the extracted bands are read-only
    inputs. Nothing writes into them, so two jobs reading the
    same product cannot interfere, and a product can always
    be unpacked again from the .SAFE.zip that is retained
    beside it.

    The directory is named after the satellite image's row
    id, not its product name. A Sentinel-2 product name is
    about 60 characters and the .SAFE folder inside the
    archive already repeats it, so naming the directory after
    the product too pushed paths past the 260-character limit
    Windows enforces by default:

        [WinError 206] The filename or extension is too long

    An id keeps the directory short while staying unique per
    product and traceable to the row that describes it. Each
    product still unpacks into its own .SAFE folder beneath,
    so band lookups cannot stray into a different product.
    """

    return (
        forest_area_root(forest_area_id, storage_root)
        / "extracted"
        / f"img{satellite_image_id}"
    )


def legacy_output_root(
    forest_area_id: int,
    storage_root: Path | None = None,
) -> Path:
    """
    Return the pre-job output directory for an area.

    Kept only for reading results produced before outputs
    were separated by job. Nothing writes here any more.
    """

    return forest_area_root(forest_area_id, storage_root)


def resolve_output_root(
    forest_area_id: int,
    job_id: int | None,
    storage_root: Path | None = None,
) -> tuple[Path, bool]:
    """
    Find the outputs to read for a job.

    Args:
        forest_area_id:
            The area the job ran over.
        job_id:
            The job whose outputs are wanted. None asks for
            whatever the area has, which is the legacy
            layout.

    Returns:
        (root, is_legacy). is_legacy is True when the
        returned directory is the shared pre-job location,
        so the caller can tell the officer that the rasters
        may belong to a later analysis of the same area.

    A job directory that exists always wins. Only when a job
    has none, because it predates this layout, does the
    legacy directory stand in.
    """

    if job_id is not None:

        job_root = job_output_root(
            forest_area_id, job_id, storage_root
        )

        if job_root.exists():
            return job_root, False

    return (
        legacy_output_root(forest_area_id, storage_root),
        True,
    )


def resolve_layer(
    forest_area_id: int,
    job_id: int | None,
    relative_path: str,
    storage_root: Path | None = None,
) -> tuple[Path | None, bool]:
    """
    Find one raster belonging to a job.

    Args:
        relative_path:
            Path of the layer beneath the output root, as
            RasterRenderService.LAYERS records it.

    Returns:
        (path, is_legacy), with path None when the layer
        does not exist in either location. Absent means the
        pipeline never produced it, and the caller should
        report that rather than drawing an empty overlay.
    """

    if job_id is not None:

        candidate = (
            job_output_root(
                forest_area_id, job_id, storage_root
            )
            / relative_path
        )

        if candidate.exists():
            return candidate, False

    candidate = (
        legacy_output_root(forest_area_id, storage_root)
        / relative_path
    )

    if candidate.exists():
        return candidate, True

    return None, False
