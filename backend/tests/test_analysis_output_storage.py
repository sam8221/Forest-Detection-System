"""Tests for preflighting job-specific analysis output storage."""

from pathlib import Path
from types import SimpleNamespace

import pytest

import app.services.analysis_service as analysis_service_module
from app.core.config import BACKEND_ROOT, Settings
from app.services.analysis_service import (
    AnalysisOutputStorageError,
    AnalysisService,
    public_analysis_error_message,
)
from app.services.cloud_mask_service import CloudMaskService
from app.services.sentinel_processor_service import SentinelProcessorService
from app.models.enums import AnalysisJobStatus, AnalysisJobType


def make_service(storage_root: Path) -> AnalysisService:
    service = AnalysisService.__new__(AnalysisService)
    service.settings = SimpleNamespace(
        satellite_image_storage_path=storage_root,
    )
    return service


def make_job(forest_area_id: int, job_id: int):
    return SimpleNamespace(
        forest_area_id=forest_area_id,
        id=job_id,
        output_directory=None,
    )


class FakeDatabase:
    def __init__(self):
        self.job = None

    def add(self, job):
        job.id = 69
        self.job = job

    def commit(self):
        pass

    def refresh(self, _job):
        pass

    def rollback(self):
        pass

    def get(self, _model, job_id):
        return self.job if self.job and self.job.id == job_id else None


def make_analysis_service(storage_root: Path) -> AnalysisService:
    service = make_service(storage_root)
    service.db = FakeDatabase()
    service.settings.ndvi_threshold = 0.15
    service.settings.image_search_days = 90
    return service


def test_relative_storage_root_resolves_from_backend_root():
    settings = Settings.model_construct(
        satellite_image_storage_root="storage/satellite_images"
    )

    assert settings.satellite_image_storage_path == (
        BACKEND_ROOT / "storage" / "satellite_images"
    ).resolve()


def test_output_directory_is_created_and_recorded_for_the_job(tmp_path):
    service = make_service(tmp_path / "storage" / "satellite_images")
    job = make_job(69, 69)

    output_root = service.prepare_job_output_directory(job)

    assert output_root == tmp_path / "storage" / "satellite_images" / "69" / "jobs" / "69"
    assert output_root.is_dir()
    assert job.output_directory == str(output_root)
    assert list(output_root.iterdir()) == []


def test_output_directories_are_isolated_by_forest_and_job(tmp_path):
    service = make_service(tmp_path / "storage")
    first = make_job(69, 69)
    second = make_job(69, 70)
    other_forest = make_job(70, 69)

    first_root = service.prepare_job_output_directory(first)
    second_root = service.prepare_job_output_directory(second)
    other_forest_root = service.prepare_job_output_directory(other_forest)

    assert len({first_root, second_root, other_forest_root}) == 3
    assert first_root.parts[-3:] == ("69", "jobs", "69")
    assert second_root.parts[-3:] == ("69", "jobs", "70")
    assert other_forest_root.parts[-3:] == ("70", "jobs", "69")


def test_storage_root_that_is_a_file_returns_a_specific_error(tmp_path):
    storage_root = tmp_path / "storage-file"
    storage_root.write_text("not a directory", encoding="utf-8")
    service = make_service(storage_root)

    with pytest.raises(
        AnalysisOutputStorageError,
        match="file occupies the configured imagery storage root",
    ):
        service.prepare_job_output_directory(make_job(69, 69))


def test_analysis_job_persists_its_output_root_before_processing(tmp_path):
    service = make_analysis_service(tmp_path / "storage")

    job = service.create_analysis_job(
        forest_area_id=69,
        satellite_image_id=46,
        started_by=5,
        job_type=AnalysisJobType.MANUAL,
    )

    expected_root = tmp_path / "storage" / "69" / "jobs" / "69"
    assert job.status is AnalysisJobStatus.PENDING
    assert job.output_directory == str(expected_root)
    assert expected_root.is_dir()


def test_analysis_job_fails_before_queueing_when_output_root_cannot_be_created(
    tmp_path, monkeypatch
):
    service = make_analysis_service(tmp_path / "storage")
    expected_root = tmp_path / "storage" / "69" / "jobs" / "69"
    original_mkdir = Path.mkdir

    def fail_job_root(path, *args, **kwargs):
        if path == expected_root:
            raise FileNotFoundError(2, "The system cannot find the file specified", str(path))
        return original_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", fail_job_root)

    with pytest.raises(AnalysisOutputStorageError):
        service.create_analysis_job(
            forest_area_id=69,
            satellite_image_id=46,
            started_by=5,
            job_type=AnalysisJobType.MANUAL,
        )

    assert service.db.job.status is AnalysisJobStatus.FAILED
    assert "analysis job's output folder" in service.db.job.error_message
    assert str(expected_root) not in service.db.job.error_message


def test_windows_path_creation_failure_returns_safe_storage_error(
    tmp_path, monkeypatch
):
    service = make_service(tmp_path / "storage")
    job = make_job(69, 69)
    expected_root = tmp_path / "storage" / "69" / "jobs" / "69"
    original_mkdir = Path.mkdir

    def fail_job_root(path, *args, **kwargs):
        if path == expected_root:
            raise FileNotFoundError(2, "The system cannot find the file specified", str(path))
        return original_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", fail_job_root)

    with pytest.raises(AnalysisOutputStorageError, match="analysis job's output folder") as error:
        service.prepare_job_output_directory(job)

    assert str(expected_root) not in str(error.value)
    assert job.output_directory is None


def test_unwritable_output_directory_is_rejected_before_analysis(tmp_path, monkeypatch):
    service = make_service(tmp_path / "storage")
    job = make_job(69, 69)

    def fail_probe(**_kwargs):
        raise PermissionError("write denied")

    monkeypatch.setattr(analysis_service_module, "NamedTemporaryFile", fail_probe)

    with pytest.raises(
        AnalysisOutputStorageError,
        match="account running the backend cannot create or write",
    ):
        service.prepare_job_output_directory(job)

    assert job.output_directory is None


@pytest.mark.parametrize(
    "relative_path",
    [Path("69"), Path("69/jobs"), Path("69/jobs/81")],
)
def test_file_conflicting_with_required_job_directory_is_reported(
    tmp_path,
    relative_path,
):
    storage_root = tmp_path / "storage"
    conflict = storage_root / relative_path
    conflict.parent.mkdir(parents=True, exist_ok=True)
    conflict.write_text("preserve this conflicting file", encoding="utf-8")

    with pytest.raises(
        AnalysisOutputStorageError,
        match="file occupies a path where this analysis job needs a directory",
    ):
        make_service(storage_root).prepare_job_output_directory(make_job(69, 81))

    assert conflict.read_text(encoding="utf-8") == "preserve this conflicting file"


def test_missing_required_band_message_does_not_expose_storage_path(tmp_path):
    with pytest.raises(FileNotFoundError, match="B04 10 m band") as error:
        SentinelProcessorService().find_band(tmp_path, "B04")

    assert str(tmp_path) not in str(error.value)


def test_missing_scl_message_identifies_expected_input_without_path(tmp_path):
    with pytest.raises(FileNotFoundError, match="SCL classification band") as error:
        CloudMaskService().find_scl_band(tmp_path)

    assert str(tmp_path) not in str(error.value)


def test_api_error_message_redacts_absolute_windows_paths():
    message = (
        "[WinError 2] The system cannot find the file specified: "
        "'D:\\forest-detection-system\\backend\\storage\\satellite_images\\69\\jobs\\69'"
    )

    safe_message = public_analysis_error_message(message)

    assert safe_message is not None
    assert "jobs" not in safe_message
    assert "D:\\" not in safe_message
    assert "backend storage" in safe_message
