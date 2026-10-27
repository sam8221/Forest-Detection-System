from __future__ import annotations

import zipfile
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
import requests
from fastapi import BackgroundTasks, HTTPException, Response
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.api import satellite_images as satellite_images_api
from app.api.satellite_images import (
    _raise_if_download_job_table_missing,
    _satellite_download_failure_message,
)
from app.database.session import Base
from app.models.satellite_download_job import SatelliteDownloadJob
from app.schemas.satellite_download import SatelliteDownloadJobResponse
from app.services.copernicus_service import CopernicusService
from app.services.copernicus_service import (
    CopernicusAuthenticationError,
    CopernicusAuthenticationServiceError,
)
from app.services.satellite_download_job_service import (
    SatelliteDownloadJobService,
    calculate_download_percentage,
)
from app.services.sentinel_service import SentinelService
from app.main import create_application


class FakeDownloadResponse:
    def __init__(self, chunks, content_length=None, error=None):
        self.status_code = 200
        self.headers = (
            {"Content-Length": str(content_length)}
            if content_length is not None
            else {}
        )
        self.chunks = chunks
        self.error = error

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size):
        yield from self.chunks
        if self.error is not None:
            raise self.error


class FakeDownloadSession:
    def __init__(self, response):
        self.response = response

    def get(self, *_args, **_kwargs):
        return self.response


@pytest.fixture
def download_job_session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[SatelliteDownloadJob.__table__],
    )
    with Session(engine) as db:
        yield db
    engine.dispose()


def test_download_percentage_uses_bytes_and_never_rounds_active_transfer_to_100():
    assert calculate_download_percentage(25, 100) == 25
    assert calculate_download_percentage(110, 100) == 99.9
    assert calculate_download_percentage(25, None) is None
    assert calculate_download_percentage(25, 0) is None
    assert calculate_download_percentage(
        25,
        None,
        transfer_complete=True,
    ) == 100


def test_copernicus_stream_reports_measured_progress_and_saved_file(tmp_path):
    service = CopernicusService()
    service._ensure_authenticated = lambda: None
    service.session = FakeDownloadSession(
        FakeDownloadResponse([b"ab", b"cdef"], content_length=6)
    )
    events = []
    destination = tmp_path / "product.zip"

    saved = service.download_file(
        "https://example.invalid/product",
        destination,
        progress_callback=lambda *event: events.append(event),
    )

    assert saved == destination
    assert destination.read_bytes() == b"abcdef"
    assert not (tmp_path / "product.zip.part").exists()
    assert events == [
        ("DOWNLOADING", 0, 6),
        ("DOWNLOADING", 2, 6),
        ("DOWNLOADING", 6, 6),
        ("VALIDATING", 6, 6),
    ]
    # A final chunk that happens to equal Content-Length is still
    # capped until the response closes and the file is atomically saved.
    assert calculate_download_percentage(events[-2][1], 6) == 99.9
    assert calculate_download_percentage(
        events[-1][1], events[-1][2], transfer_complete=True
    ) == 100


def test_unknown_content_length_reports_indeterminate_progress(tmp_path):
    service = CopernicusService()
    service._ensure_authenticated = lambda: None
    service.session = FakeDownloadSession(
        FakeDownloadResponse([b"abc"], content_length=None)
    )
    events = []

    service.download_file(
        "https://example.invalid/product",
        tmp_path / "unknown.zip",
        progress_callback=lambda *event: events.append(event),
    )

    assert events == [
        ("DOWNLOADING", 0, None),
        ("DOWNLOADING", 3, None),
        ("VALIDATING", 3, None),
    ]
    assert all(
        calculate_download_percentage(downloaded, total) is None
        for status, downloaded, total in events
        if status == "DOWNLOADING"
    )


def test_failed_transfer_does_not_leave_a_completed_file_or_report_validation(tmp_path):
    service = CopernicusService()
    service._ensure_authenticated = lambda: None
    service.session = FakeDownloadSession(
        FakeDownloadResponse(
            [b"partial"],
            content_length=100,
            error=requests.exceptions.ConnectionError("network interrupted"),
        )
    )
    events = []
    destination = tmp_path / "failed.zip"

    with pytest.raises(RuntimeError, match="Failed to download"):
        service.download_file(
            "https://example.invalid/product",
            destination,
            progress_callback=lambda *event: events.append(event),
        )

    assert not destination.exists()
    assert not (tmp_path / "failed.zip.part").exists()
    assert events[-1][0] == "DOWNLOADING"


def test_saved_product_must_be_a_readable_l2a_archive_with_analysis_bands(tmp_path):
    valid_archive = tmp_path / "valid-product.zip"
    with zipfile.ZipFile(valid_archive, "w") as archive:
        archive.writestr("GRANULE/G1/IMG_DATA/R10m/PRODUCT_B04_10m.jp2", b"red")
        archive.writestr("GRANULE/G1/IMG_DATA/R10m/PRODUCT_B08_10m.jp2", b"nir")
        archive.writestr("GRANULE/G1/IMG_DATA/R20m/PRODUCT_SCL_20m.jp2", b"scl")

    SentinelService._validate_downloaded_product(valid_archive)

    invalid_archive = tmp_path / "missing-bands.zip"
    with zipfile.ZipFile(invalid_archive, "w") as archive:
        archive.writestr("metadata.xml", b"metadata only")

    with pytest.raises(RuntimeError, match="missing bands"):
        SentinelService._validate_downloaded_product(invalid_archive)

    corrupted_archive = tmp_path / "corrupted-product.zip"
    corrupted_bytes = bytearray(valid_archive.read_bytes())
    payload_offset = corrupted_bytes.index(b"red")
    corrupted_bytes[payload_offset] = ord("R")
    corrupted_archive.write_bytes(corrupted_bytes)

    with pytest.raises(RuntimeError, match="integrity validation"):
        SentinelService._validate_downloaded_product(corrupted_archive)


def test_active_product_requests_reuse_one_job_and_isolate_other_products(
    download_job_session,
):
    service = SatelliteDownloadJobService(download_job_session)
    first, created = service.create_or_get_active(
        forest_area_id=7,
        product_id="product-one",
        product_name="Product One",
        started_by=4,
    )
    repeated, repeated_created = service.create_or_get_active(
        forest_area_id=7,
        product_id="product-one",
        product_name="Product One",
        started_by=4,
    )
    separate, separate_created = service.create_or_get_active(
        forest_area_id=7,
        product_id="product-two",
        product_name="Product Two",
        started_by=4,
    )

    assert created is True
    assert repeated_created is False
    assert repeated.job_id == first.job_id
    assert separate_created is True
    assert separate.job_id != first.job_id

    service.report_progress(
        first,
        status="DOWNLOADING",
        downloaded_bytes=25,
        total_bytes=100,
    )
    download_job_session.refresh(first)
    assert first.progress_percentage == 25
    assert separate.progress_percentage is None
    assert separate.downloaded_bytes == 0


def test_success_failure_and_refresh_status_are_persisted(download_job_session):
    service = SatelliteDownloadJobService(download_job_session)
    successful, _ = service.create_or_get_active(
        forest_area_id=2,
        product_id="valid-product",
        product_name="Valid product",
        started_by=9,
    )
    failed, _ = service.create_or_get_active(
        forest_area_id=2,
        product_id="failed-product",
        product_name="Failed product",
        started_by=9,
    )

    service.complete(successful, satellite_image_id=81)
    service.fail(failed.job_id, "The product could not be validated.")

    refreshed = download_job_session.get(
        SatelliteDownloadJob,
        successful.job_id,
    )
    response = SatelliteDownloadJobResponse.model_validate(refreshed)
    assert response.status == "COMPLETED"
    assert response.progress_percentage == 100
    assert response.satellite_image_id == 81

    failed_after_refresh = download_job_session.get(
        SatelliteDownloadJob,
        failed.job_id,
    )
    assert failed_after_refresh.status == "FAILED"
    assert failed_after_refresh.error_message == "The product could not be validated."


def test_restart_recovery_fails_interrupted_jobs_without_changing_completed_jobs(
    download_job_session,
):
    service = SatelliteDownloadJobService(download_job_session)
    completed, _ = service.create_or_get_active(
        forest_area_id=2,
        product_id="completed-before-restart",
        product_name="Completed product",
        started_by=9,
    )
    active, _ = service.create_or_get_active(
        forest_area_id=2,
        product_id="interrupted-by-restart",
        product_name="Interrupted product",
        started_by=9,
    )
    service.complete(completed, satellite_image_id=81)

    assert service.fail_abandoned() == 1

    download_job_session.refresh(completed)
    download_job_session.refresh(active)
    assert completed.status == "COMPLETED"
    assert completed.satellite_image_id == 81
    assert active.status == "FAILED"
    assert "server stopped" in active.error_message


def test_download_job_records_safe_permanent_and_transient_auth_failures():
    permanent = _satellite_download_failure_message(
        CopernicusAuthenticationError(
            "Copernicus rejected the configured server credentials."
        )
    )
    transient = _satellite_download_failure_message(
        CopernicusAuthenticationServiceError(
            "Copernicus authentication is temporarily unavailable."
        )
    )
    unexpected = _satellite_download_failure_message(
        RuntimeError("provider returned a sensitive response body")
    )

    assert "COPERNICUS_USERNAME" in permanent or "credentials" in permanent
    assert "temporarily unavailable" in transient
    assert "sensitive response body" not in unexpected
    assert "product did not pass validation" in unexpected


def test_download_routes_are_registered_with_the_job_response_contract():
    schema = create_application().openapi()
    paths = schema["paths"]
    jobs_path = "/api/v1/satellite-images/downloads"
    job_path = "/api/v1/satellite-images/downloads/{job_id}"
    acquire_path = "/api/v1/satellite-images/forest/{forest_area_id}/download"

    assert "get" in paths[jobs_path]
    assert "get" in paths[job_path]
    assert "post" in paths[acquire_path]
    assert "202" in paths[acquire_path]["post"]["responses"]
    assert "SatelliteDownloadJobResponse" in schema["components"]["schemas"]


def test_missing_download_job_migration_returns_actionable_503_without_sql_details():
    database_error = OperationalError(
        "select from satellite_download_jobs",
        {},
        Exception('relation "satellite_download_jobs" does not exist'),
    )

    class FakeDb:
        rolled_back = False

        def rollback(self):
            self.rolled_back = True

    db = FakeDb()
    with pytest.raises(HTTPException) as error:
        _raise_if_download_job_table_missing(database_error, db)

    assert error.value.status_code == 503
    assert "migration has not been applied" in error.value.detail
    assert "relation" not in error.value.detail
    assert db.rolled_back is True


def test_unknown_download_job_returns_404():
    class EmptyDb:
        def get(self, _model, job_id):
            assert job_id == "missing-job"
            return None

    with pytest.raises(HTTPException) as error:
        satellite_images_api.get_satellite_download_job(
            "missing-job",
            EmptyDb(),
            SimpleNamespace(id=3),
        )

    assert error.value.status_code == 404


def test_failed_download_can_be_retried_with_a_new_job(download_job_session):
    service = SatelliteDownloadJobService(download_job_session)
    first, created = service.create_or_get_active(
        forest_area_id=7,
        product_id="failed-then-retry",
        product_name="Product",
        started_by=3,
    )
    assert created is True
    service.fail(first.job_id, "Copernicus credentials were rejected.")

    retry, retry_created = service.create_or_get_active(
        forest_area_id=7,
        product_id="failed-then-retry",
        product_name="Product",
        started_by=3,
    )
    assert retry_created is True
    assert retry.job_id != first.job_id
    assert retry.status == "PREPARING"


def test_progress_endpoint_hides_jobs_outside_the_users_forest_scope(monkeypatch):
    job = SimpleNamespace(job_id="job-id", forest_area_id=11)

    class FakeDb:
        def get(self, model, key):
            assert model is SatelliteDownloadJob
            assert key == "job-id"
            return job

    class ScopedForestRepository:
        def __init__(self, _db):
            pass

        def get_by_id_for_user(self, *, forest_area_id, user):
            assert forest_area_id == 11
            assert user.id == 3
            return None

    monkeypatch.setattr(
        satellite_images_api,
        "ForestAreaRepository",
        ScopedForestRepository,
    )

    with pytest.raises(HTTPException) as error:
        satellite_images_api.get_satellite_download_job(
            "job-id",
            FakeDb(),
            SimpleNamespace(id=3),
        )

    assert getattr(error.value, "status_code", None) == 404

    class AuthorisedForestRepository:
        def __init__(self, _db):
            pass

        def get_by_id_for_user(self, *, forest_area_id, user):
            return SimpleNamespace(id=forest_area_id)

    monkeypatch.setattr(
        satellite_images_api,
        "ForestAreaRepository",
        AuthorisedForestRepository,
    )
    assert satellite_images_api.get_satellite_download_job(
        "job-id",
        FakeDb(),
        SimpleNamespace(id=3),
    ) is job


def test_acquisition_route_queues_once_for_repeated_clicks(monkeypatch):
    forest = SimpleNamespace(id=7)

    class FakeDb:
        pass

    class FakeForestRepository:
        def __init__(self, _db):
            pass

        def get_by_id_for_user(self, *, forest_area_id, user):
            assert user.id == 3
            return forest if forest_area_id == forest.id else None

    class FakeImageRepository:
        def __init__(self, _db):
            pass

        def get_by_product_id(self, _product_id):
            return None

    active_jobs = {}

    class FakeDownloadJobService:
        def __init__(self, _db):
            pass

        def create_or_get_active(self, **values):
            key = (values["forest_area_id"], values["product_id"])
            if key in active_jobs:
                return active_jobs[key], False
            job = SimpleNamespace(
                job_id="stable-job-id",
                product_id=values["product_id"],
                status="PREPARING",
            )
            active_jobs[key] = job
            return job, True

    monkeypatch.setattr(
        satellite_images_api,
        "ForestAreaRepository",
        FakeForestRepository,
    )
    monkeypatch.setattr(
        satellite_images_api,
        "SatelliteImageRepository",
        FakeImageRepository,
    )
    monkeypatch.setattr(
        satellite_images_api,
        "SatelliteDownloadJobService",
        FakeDownloadJobService,
    )

    request = satellite_images_api.SatelliteDownloadRequest(
        product_id="S2-PRODUCT-0001",
        product_name="Sentinel Product",
        tile_id="35KPV",
        acquisition_date="2025-07-12",
        cloud_cover=5,
    )

    def request_download():
        background_tasks = BackgroundTasks()
        response = Response()
        result = satellite_images_api.download_sentinel_product(
            7,
            request,
            background_tasks,
            response,
            FakeDb(),
            SimpleNamespace(id=3),
        )
        return result, background_tasks, response

    first_job, first_tasks, first_response = request_download()
    repeated_job, repeated_tasks, repeated_response = request_download()

    assert first_job.job_id == repeated_job.job_id
    assert len(first_tasks.tasks) == 1
    assert len(repeated_tasks.tasks) == 0
    assert first_response.status_code == 202
    assert repeated_response.status_code == 200


def test_downloads_path_is_not_shadowed_by_the_numeric_image_route(monkeypatch):
    """Guard the symptom a stale FastAPI process produced.

    A build that registers ``/{image_id}`` ahead of ``/downloads`` answers a
    status request with a 422 naming ``image_id`` instead of listing jobs.
    The page can only report that as a backend it cannot use, so the ordering
    is pinned here rather than left to the order of the decorators.
    """

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.deps import get_current_active_user
    from app.database.session import get_db

    forest = SimpleNamespace(id=4)
    job = SimpleNamespace(
        job_id="job-for-forest-4",
        forest_area_id=forest.id,
        product_id="S2-PRODUCT-0009",
        product_name="Sentinel Product",
        status="DOWNLOADING",
        downloaded_bytes=2048,
        total_bytes=8192,
        progress_percentage=25.0,
        satellite_image_id=None,
        error_message=None,
        created_at=datetime(2025, 7, 1, 8, 0, 0, tzinfo=UTC),
        updated_at=datetime(2025, 7, 1, 8, 1, 0, tzinfo=UTC),
        completed_at=None,
    )

    class FakeQuery:
        def filter(self, *_args):
            return self

        def order_by(self, *_args):
            return self

        def limit(self, _count):
            return self

        def all(self):
            return [job]

    class FakeDb:
        def query(self, _model):
            return FakeQuery()

    class FakeForestRepository:
        def __init__(self, _db):
            pass

        def get_by_id_for_user(self, *, forest_area_id, user):
            assert user.id == 11
            return forest if forest_area_id == forest.id else None

    monkeypatch.setattr(
        satellite_images_api,
        "ForestAreaRepository",
        FakeForestRepository,
    )

    app = FastAPI()
    app.include_router(satellite_images_api.router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: FakeDb()
    app.dependency_overrides[get_current_active_user] = lambda: SimpleNamespace(
        id=11
    )

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/satellite-images/downloads",
            params={"forest_area_id": forest.id},
        )

    assert response.status_code == 200
    payload = response.json()
    assert [item["job_id"] for item in payload] == ["job-for-forest-4"]
    assert payload[0]["progress_percentage"] == 25.0
    assert payload[0]["total_bytes"] == 8192
