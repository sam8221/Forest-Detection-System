"""
What a completed analysis reports as having measured.

The Analysis page used to display the affected area and the
confidence from response fields the analysis API has never
sent, so every completed analysis showed 0.00 ha at 0.00%
confidence however much clearing it had found. The figures
are now measured from the detections the job itself produced.

These tests fix the distinction that made the defect worth
fixing: an area of zero and no area at all are different
findings, and the response has to keep them apart.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

import app.api.analysis as analysis_api
from app.models.enums import AnalysisJobStatus
from app.repositories.detection_repository import DetectionRepository


# =========================================================
# THE AGGREGATE
# =========================================================

class FakeAggregateQuery:
    """Stands in for the count, sum and avg query over detections."""

    def __init__(self, row):
        self._row = row

    def filter(self, *_args, **_kwargs):
        return self

    def one(self):
        return self._row


class FakeAggregateSession:
    def __init__(self, row):
        self._row = row

    def query(self, *_args, **_kwargs):
        return FakeAggregateQuery(self._row)


def totals_from(row):
    return DetectionRepository(
        FakeAggregateSession(row)
    ).measured_totals_for_job(analysis_job_id=87)


def test_a_job_that_found_nothing_reports_no_area_rather_than_zero():
    """
    The shape PostgreSQL returns for a job with no
    detections: a count of zero, and NULL for both
    aggregates because there were no rows to aggregate.
    """

    totals = totals_from((0, None, None))

    assert totals["detection_count"] == 0

    # None, not 0.0. Zero hectares would read as a measured
    # area; there was no area to measure.
    assert totals["detected_area_hectares"] is None
    assert totals["mean_confidence_score"] is None


def test_a_job_that_found_clearing_reports_its_measured_totals():
    totals = totals_from((16, 59.75, 94.181875))

    assert totals == {
        "detection_count": 16,
        "detected_area_hectares": 59.75,
        "mean_confidence_score": 94.181875,
    }


def test_a_single_detection_reports_its_own_area_and_confidence():
    """
    Matches analysis job 14, whose execution log recorded
    0.9800 ha at 94.78 percent confidence.
    """

    totals = totals_from((1, 0.98, 94.78))

    assert totals["detection_count"] == 1
    assert totals["detected_area_hectares"] == pytest.approx(0.98)
    assert totals["mean_confidence_score"] == pytest.approx(94.78)


def test_aggregates_are_returned_as_plain_floats():
    """
    PostgreSQL returns sum() as a Decimal through some
    drivers. The response is serialised as JSON, so the
    values are converted rather than passed through.
    """

    totals = totals_from((2, Decimal("1.50"), Decimal("88.25")))

    assert isinstance(totals["detected_area_hectares"], float)
    assert isinstance(totals["mean_confidence_score"], float)
    assert totals["detected_area_hectares"] == pytest.approx(1.5)


def test_a_counted_detection_with_no_recorded_area_is_not_reported_as_zero():
    """
    Defensive: a detection row whose area was never written
    makes sum() NULL while count() is non-zero. That is a
    missing measurement, not an area of zero.
    """

    totals = totals_from((3, None, None))

    assert totals["detection_count"] == 3
    assert totals["detected_area_hectares"] is None
    assert totals["mean_confidence_score"] is None


# =========================================================
# THE RESPONSE
# =========================================================

def job_detail_response(monkeypatch, job, measured):
    """Call the endpoint with its repositories stubbed out."""

    monkeypatch.setattr(
        analysis_api,
        "AnalysisRepository",
        lambda _db: SimpleNamespace(
            get_by_id_for_user=lambda job_id, user: job
        ),
    )
    monkeypatch.setattr(
        analysis_api,
        "DetectionRepository",
        lambda _db: SimpleNamespace(
            measured_totals_for_job=lambda job_id: measured
        ),
    )
    # Whether the output rasters are on disk is not what
    # these tests are about; that has its own suite.
    monkeypatch.setattr(
        analysis_api,
        "_verified_completed_result",
        lambda job, db: (True, None),
    )

    return analysis_api.get_analysis_job(
        job_id=job.id,
        request=SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace())
        ),
        db=object(),
        current_user=SimpleNamespace(id=3),
    )


def completed_job(**changes):
    values = {
        "id": 87,
        "forest_area_id": 69,
        "satellite_image_id": 46,
        "previous_satellite_image_id": 47,
        "status": AnalysisJobStatus.COMPLETED,
        "job_type": SimpleNamespace(value="MANUAL"),
        "started_by": 3,
        "started_at": "2026-10-26T20:35:20Z",
        "completed_at": "2026-10-26T20:35:27Z",
        "duration_seconds": 6.76,
        "cloud_cover_percentage": 4.540487,
        "vegetation_change_percentage": 0.0,
        "ndvi_threshold": 0.3,
        "error_message": None,
        "execution_log": None,
        "created_at": None,
        "updated_at": None,
    }
    values.update(changes)
    return SimpleNamespace(**values)


def test_the_response_carries_the_measured_totals(monkeypatch):
    response = job_detail_response(
        monkeypatch,
        completed_job(vegetation_change_percentage=86.96),
        {
            "detection_count": 1,
            "detected_area_hectares": 0.98,
            "mean_confidence_score": 94.78,
        },
    )

    assert response["detection_count"] == 1
    assert response["detected_area_hectares"] == pytest.approx(0.98)
    assert response["mean_confidence_score"] == pytest.approx(94.78)
    assert response["vegetation_change_percentage"] == pytest.approx(86.96)


def test_a_zero_detection_response_sends_null_not_zero(monkeypatch):
    """
    The interface decides between "none detected" and "not
    available" from these values, so the response must not
    flatten an absent area into 0.0.
    """

    response = job_detail_response(
        monkeypatch,
        completed_job(),
        {
            "detection_count": 0,
            "detected_area_hectares": None,
            "mean_confidence_score": None,
        },
    )

    assert response["detection_count"] == 0
    assert response["detected_area_hectares"] is None
    assert response["mean_confidence_score"] is None

    # The measured vegetation change of zero is still a real
    # reading and is reported as one.
    assert response["vegetation_change_percentage"] == 0.0


def test_the_response_does_not_carry_the_fields_the_page_used_to_read(monkeypatch):
    """
    Guards the other half of the defect. The page read
    loss_area_hectares, deforestation_area_hectares,
    deforested_area_hectares, confidence_percentage and
    confidence. Naming them here records that this response
    has never provided them, so nobody reinstates a frontend
    fallback onto fields that will always be absent.
    """

    response = job_detail_response(
        monkeypatch,
        completed_job(),
        {
            "detection_count": 0,
            "detected_area_hectares": None,
            "mean_confidence_score": None,
        },
    )

    for absent in (
        "loss_area_hectares",
        "deforestation_area_hectares",
        "deforested_area_hectares",
        "confidence_percentage",
        "confidence",
    ):
        assert absent not in response
