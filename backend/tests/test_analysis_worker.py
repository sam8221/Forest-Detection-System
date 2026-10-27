from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.api.analysis import _verified_completed_result
from app.models.enums import AnalysisJobStatus
from app.services.analysis_worker import (
    ABANDONED_PENDING_MESSAGE,
    ABANDONED_RUNNING_MESSAGE,
    recover_abandoned_analysis_jobs,
)


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *_args, **_kwargs):
        return self

    def with_for_update(self, **_kwargs):
        return self

    def all(self):
        return self.rows


class FakeSession:
    def __init__(self, jobs):
        self.jobs = jobs
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def query(self, _model):
        return FakeQuery(self.jobs)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


class FakeResult:
    def __init__(self, value):
        self.value = value

    def scalar_one(self):
        return self.value


class FakeConnection:
    def __init__(self, available_by_job):
        self.available_by_job = available_by_job
        self.commits = 0
        self.closed = False

    def execute(self, statement, params):
        if "pg_try_advisory_lock" in str(statement):
            value = self.available_by_job.get(params["job_id"], True)
            return FakeResult(value)
        return FakeResult(True)

    def commit(self):
        self.commits += 1

    def close(self):
        self.closed = True

    def rollback(self):
        pass


class FakeEngine:
    dialect = SimpleNamespace(name="postgresql")

    def __init__(self, connection):
        self.connection = connection

    def connect(self):
        return self.connection


def make_job(job_id, status, created_at, started_at=None):
    return SimpleNamespace(
        id=job_id,
        status=status,
        created_at=created_at,
        started_at=started_at,
        completed_at=None,
        duration_seconds=None,
        error_message=None,
    )


def test_stale_pending_job_is_failed_but_a_recent_queue_entry_is_preserved():
    now = datetime.now(UTC)
    stale = make_job(101, AnalysisJobStatus.PENDING, now - timedelta(hours=3))
    recent = make_job(102, AnalysisJobStatus.PENDING, now - timedelta(seconds=10))
    session = FakeSession([stale, recent])
    connection = FakeConnection({101: True, 102: True})

    recovered = recover_abandoned_analysis_jobs(
        session_factory=lambda: session,
        database_engine=FakeEngine(connection),
    )

    assert recovered == 1
    assert stale.status == AnalysisJobStatus.FAILED
    assert stale.error_message == ABANDONED_PENDING_MESSAGE
    assert recent.status == AnalysisJobStatus.PENDING
    assert session.commits == 1
    assert session.closed
    assert connection.closed


def test_running_job_is_failed_only_when_its_worker_lock_is_gone():
    now = datetime.now(UTC)
    abandoned = make_job(
        201,
        AnalysisJobStatus.RUNNING,
        now - timedelta(minutes=5),
        started_at=now - timedelta(minutes=4),
    )
    live = make_job(
        202,
        AnalysisJobStatus.RUNNING,
        now - timedelta(minutes=5),
        started_at=now - timedelta(minutes=4),
    )
    session = FakeSession([abandoned, live])
    connection = FakeConnection({201: True, 202: False})

    recovered = recover_abandoned_analysis_jobs(
        session_factory=lambda: session,
        database_engine=FakeEngine(connection),
    )

    assert recovered == 1
    assert abandoned.status == AnalysisJobStatus.FAILED
    assert abandoned.error_message == ABANDONED_RUNNING_MESSAGE
    assert abandoned.completed_at is not None
    assert abandoned.duration_seconds == pytest.approx(240, abs=0.01)
    assert live.status == AnalysisJobStatus.RUNNING


def test_completed_record_without_execution_timestamps_has_unverified_results():
    job = SimpleNamespace(
        status=AnalysisJobStatus.COMPLETED,
        started_at=None,
        completed_at=None,
    )

    verified, message = _verified_completed_result(job, db=None)

    assert verified is False
    assert "no complete execution timestamps" in message

