"""A job may only reach COMPLETED once its outputs exist and belong to it."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from shapely.geometry import box

from app.models.enums import AnalysisJobStatus
from app.services.analysis_service import AnalysisService
from app.services.boundary_comparison_service import write_comparison_manifest
from app.services.storage_paths import job_output_root


FOREST_AREA_ID = 69
JOB_ID = 76
PREVIOUS_IMAGE_ID = 47
RECENT_IMAGE_ID = 46
BOUNDARY = box(28.24, -12.94, 28.31, -12.88)


class FakeQuery:
    def __init__(self, forest):
        self._forest = forest

    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        return self._forest


class FakeDatabase:
    """Only the forest lookup and the commit path are exercised here."""

    def __init__(self, forest):
        self._forest = forest
        self.commits = 0

    def query(self, _model):
        return FakeQuery(self._forest)

    def commit(self):
        self.commits += 1

    def refresh(self, _job):
        pass


def make_service(storage_root: Path, forest=None) -> AnalysisService:
    service = AnalysisService.__new__(AnalysisService)
    service.settings = SimpleNamespace(satellite_image_storage_path=storage_root)
    service.db = FakeDatabase(
        forest
        if forest is not None
        else SimpleNamespace(id=FOREST_AREA_ID, geometry=BOUNDARY)
    )
    return service


def make_job(storage_root: Path, **overrides):
    root = job_output_root(FOREST_AREA_ID, JOB_ID, storage_root=storage_root)
    job = SimpleNamespace(
        id=JOB_ID,
        forest_area_id=FOREST_AREA_ID,
        previous_satellite_image_id=PREVIOUS_IMAGE_ID,
        satellite_image_id=RECENT_IMAGE_ID,
        started_at=datetime(2026, 10, 22, 9, 47, tzinfo=UTC),
        completed_at=None,
        duration_seconds=None,
        status=AnalysisJobStatus.RUNNING,
        error_message=None,
        cloud_cover_percentage=None,
        vegetation_change_percentage=None,
        ndvi_threshold=0.3,
        output_directory=str(root),
    )
    for key, value in overrides.items():
        setattr(job, key, value)
    return job


def write_outputs(
    storage_root: Path,
    *,
    figure: bool = True,
    job_id: int = JOB_ID,
    previous_image_id: int = PREVIOUS_IMAGE_ID,
) -> Path:
    """Write the manifest and figure a healthy selected-pair run leaves behind."""

    root = job_output_root(FOREST_AREA_ID, job_id, storage_root=storage_root)
    comparison = root / "comparison"
    comparison.mkdir(parents=True, exist_ok=True)
    figure_path = comparison / "scientific_comparison.png"
    figure_path.write_bytes(b"four-panel figure bytes")

    figure_block = None
    if figure:
        figure_block = {
            "desktop": {
                "filename": "scientific_comparison.png",
                "width": 2400,
                "height": 2336,
                "sha256": hashlib.sha256(figure_path.read_bytes()).hexdigest(),
            }
        }

    write_comparison_manifest(
        comparison / "manifest.json",
        forest_area_id=FOREST_AREA_ID,
        job_id=job_id,
        previous_image_id=previous_image_id,
        recent_image_id=RECENT_IMAGE_ID,
        boundary=BOUNDARY,
        imagery={"previous": {}, "recent": {}},
        figure=figure_block,
    )
    return comparison


def complete(service, job):
    service.complete_analysis(
        job=job,
        cloud_cover=4.54,
        vegetation_change=0.0,
        ndvi_threshold=0.3,
    )


def test_a_run_with_all_its_outputs_completes(tmp_path):
    write_outputs(tmp_path)
    service = make_service(tmp_path)
    job = make_job(tmp_path)

    complete(service, job)

    assert job.status == AnalysisJobStatus.COMPLETED
    assert job.completed_at is not None
    assert job.error_message is None
    # Zero confirmed hectares is a valid completed outcome, not a failure.
    assert job.vegetation_change_percentage == 0.0


def test_a_job_that_never_started_cannot_be_completed(tmp_path):
    # Exactly how job 75 reached COMPLETED: outputs on disk, no run behind them.
    write_outputs(tmp_path)
    service = make_service(tmp_path)
    job = make_job(tmp_path, started_at=None)

    with pytest.raises(ValueError, match="never started"):
        complete(service, job)

    assert job.status is not AnalysisJobStatus.COMPLETED


def test_rasters_alone_do_not_complete_a_job(tmp_path):
    # The comparison directory exists but no manifest was written.
    root = job_output_root(FOREST_AREA_ID, JOB_ID, storage_root=tmp_path)
    (root / "comparison").mkdir(parents=True)
    (root / "comparison" / "previous_ndvi.tif").write_bytes(b"raster")
    service = make_service(tmp_path)
    job = make_job(tmp_path)

    with pytest.raises(ValueError, match="comparison manifest"):
        complete(service, job)

    assert job.status is not AnalysisJobStatus.COMPLETED


def test_a_manifest_from_another_pair_does_not_complete_this_job(tmp_path):
    write_outputs(tmp_path, previous_image_id=PREVIOUS_IMAGE_ID + 5)
    service = make_service(tmp_path)
    job = make_job(tmp_path)

    with pytest.raises(ValueError, match="comparison manifest"):
        complete(service, job)


def test_a_manifest_from_another_job_does_not_complete_this_job(tmp_path):
    write_outputs(tmp_path, job_id=JOB_ID)
    # Point the job at a different id whose directory holds no manifest.
    service = make_service(tmp_path)
    other_root = job_output_root(FOREST_AREA_ID, JOB_ID + 1, storage_root=tmp_path)
    job = make_job(tmp_path, id=JOB_ID + 1, output_directory=str(other_root))

    with pytest.raises(ValueError, match="comparison manifest"):
        complete(service, job)


def test_a_missing_figure_does_not_complete_the_job(tmp_path):
    write_outputs(tmp_path, figure=False)
    service = make_service(tmp_path)
    job = make_job(tmp_path)

    with pytest.raises(ValueError, match="four-panel comparison figure"):
        complete(service, job)


def test_a_figure_that_does_not_match_the_manifest_does_not_complete(tmp_path):
    comparison = write_outputs(tmp_path)
    # Something else overwrote the export after this run recorded it.
    (comparison / "scientific_comparison.png").write_bytes(b"a different figure")
    service = make_service(tmp_path)
    job = make_job(tmp_path)

    with pytest.raises(ValueError, match="does not match"):
        complete(service, job)


def test_a_job_pointing_at_another_directory_does_not_complete(tmp_path):
    write_outputs(tmp_path)
    service = make_service(tmp_path)
    job = make_job(tmp_path, output_directory=str(tmp_path / "somewhere-else"))

    with pytest.raises(ValueError, match="its own output directory"):
        complete(service, job)


def test_an_edited_boundary_does_not_complete_the_job(tmp_path):
    write_outputs(tmp_path)
    # The officer redrew the boundary after the run produced its outputs.
    moved = SimpleNamespace(id=FOREST_AREA_ID, geometry=box(28.0, -13.0, 28.05, -12.95))
    service = make_service(tmp_path, forest=moved)
    job = make_job(tmp_path)

    with pytest.raises(ValueError, match="comparison manifest"):
        complete(service, job)


def test_the_guard_records_nothing_when_it_rejects_a_job(tmp_path):
    write_outputs(tmp_path, figure=False)
    service = make_service(tmp_path)
    job = make_job(tmp_path)

    with pytest.raises(ValueError):
        complete(service, job)

    # No partial completion: the failure path in execute records the reason.
    assert job.completed_at is None
    assert job.duration_seconds is None
    assert job.cloud_cover_percentage is None
    assert service.db.commits == 0


def test_the_manifest_the_guard_reads_is_the_one_the_run_wrote(tmp_path):
    comparison = write_outputs(tmp_path)
    manifest = json.loads((comparison / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["analysis_job_id"] == JOB_ID
    assert manifest["previous_satellite_image_id"] == PREVIOUS_IMAGE_ID
    assert manifest["recent_satellite_image_id"] == RECENT_IMAGE_ID
