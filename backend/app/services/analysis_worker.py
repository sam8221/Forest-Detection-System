"""Claim and execute persistent analysis jobs from the database queue."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database.session import SessionLocal, engine
from app.models.analysis_job import AnalysisJob
from app.models.enums import AnalysisJobStatus
from app.services.analysis_service import AnalysisService


logger = logging.getLogger(__name__)

# A two-key PostgreSQL advisory lock uniquely identifies a job without adding
# another column or requiring a schema migration. The lock connection stays
# open for the entire run; PostgreSQL releases the lock if its worker exits.
_LOCK_NAMESPACE = 1_179_860_570
DEFAULT_PENDING_TIMEOUT = timedelta(minutes=30)
ABANDONED_RUNNING_MESSAGE = (
    "The analysis worker stopped before this run finished. Start a new analysis to retry."
)
ABANDONED_PENDING_MESSAGE = (
    "The analysis was not claimed by a worker within 30 minutes and was closed as abandoned. "
    "Start a new analysis to retry."
)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _try_job_lock(connection, job_id: int, database_engine=engine) -> bool:
    """Return True when this connection acquired the job's advisory lock."""

    if database_engine.dialect.name != "postgresql":
        return False

    acquired = bool(
        connection.execute(
            text("SELECT pg_try_advisory_lock(:namespace, :job_id)"),
            {"namespace": _LOCK_NAMESPACE, "job_id": int(job_id)},
        ).scalar_one()
    )
    connection.commit()
    return acquired


def _release_job_lock(connection, job_id: int, database_engine=engine) -> None:
    if connection is None:
        return
    try:
        if database_engine.dialect.name == "postgresql":
            connection.execute(
                text("SELECT pg_advisory_unlock(:namespace, :job_id)"),
                {"namespace": _LOCK_NAMESPACE, "job_id": int(job_id)},
            )
            connection.commit()
    except Exception:
        logger.exception("Could not release analysis worker lock for job %s", job_id)
        connection.rollback()
    finally:
        connection.close()


def _job_lock_is_free(connection, job_id: int, database_engine=engine) -> bool:
    """Check whether a worker still owns a job, without changing job data."""

    if database_engine.dialect.name != "postgresql":
        # The deployed database is PostgreSQL. Other dialects have no
        # cross-process lock, so RUNNING records cannot be proven live.
        return True

    acquired = _try_job_lock(connection, job_id, database_engine)
    if acquired:
        connection.execute(
            text("SELECT pg_advisory_unlock(:namespace, :job_id)"),
            {"namespace": _LOCK_NAMESPACE, "job_id": int(job_id)},
        )
        connection.commit()
    return acquired


def recover_abandoned_analysis_jobs(
    *,
    pending_timeout: timedelta = DEFAULT_PENDING_TIMEOUT,
    session_factory=SessionLocal,
    database_engine=engine,
) -> int:
    """Fail queue records that have no live worker or have waited too long.

    RUNNING jobs are only closed when their PostgreSQL advisory lock is free.
    PENDING jobs stay queued for 30 minutes; a worker that owns one keeps it
    alive even during the short interval before it changes the state to RUNNING.
    """

    db: Session = session_factory()
    connection = None
    now = datetime.now(UTC)
    recovered = 0

    try:
        if database_engine.dialect.name == "postgresql":
            connection = database_engine.connect()
        jobs = (
            db.query(AnalysisJob)
            .filter(
                AnalysisJob.status.in_(
                    [AnalysisJobStatus.PENDING, AnalysisJobStatus.RUNNING]
                )
            )
            .with_for_update(skip_locked=True, of=AnalysisJob)
            .all()
        )

        for job in jobs:
            lock_free = (
                True
                if connection is None
                else _job_lock_is_free(connection, job.id, database_engine)
            )
            if not lock_free:
                continue

            if job.status == AnalysisJobStatus.RUNNING:
                message = ABANDONED_RUNNING_MESSAGE
            elif _utc(job.created_at) <= now - pending_timeout:
                message = ABANDONED_PENDING_MESSAGE
            else:
                continue

            job.status = AnalysisJobStatus.FAILED
            job.completed_at = now
            job.error_message = message[:500]
            if job.started_at is not None:
                job.duration_seconds = (
                    now - _utc(job.started_at)
                ).total_seconds()
            recovered += 1

        if recovered:
            db.commit()
        else:
            db.rollback()
    except Exception:
        db.rollback()
        raise
    finally:
        if connection is not None:
            connection.close()
        db.close()

    if recovered:
        logger.warning("Closed %s abandoned analysis job(s)", recovered)
    return recovered


class AnalysisWorker:
    """Execute one database-queued job at a time per worker thread."""

    def __init__(
        self,
        *,
        session_factory=SessionLocal,
        database_engine=engine,
        service_factory=AnalysisService,
    ) -> None:
        self.session_factory = session_factory
        self.database_engine = database_engine
        self.service_factory = service_factory

    def _claim_next(self):
        lock_connection = None
        job_id = None
        db: Session = self.session_factory()
        try:
            candidates = (
                db.query(AnalysisJob)
                .filter(AnalysisJob.status == AnalysisJobStatus.PENDING)
                .order_by(AnalysisJob.created_at.asc(), AnalysisJob.id.asc())
                .limit(25)
                .with_for_update(skip_locked=True, of=AnalysisJob)
                .all()
            )
            for job in candidates:
                candidate_lock = self.database_engine.connect()
                try:
                    acquired = _try_job_lock(
                        candidate_lock,
                        job.id,
                        self.database_engine,
                    )
                except Exception:
                    candidate_lock.close()
                    raise
                if not acquired:
                    candidate_lock.close()
                    continue

                lock_connection = candidate_lock
                job_id = job.id
                break

            # Releasing row locks before the potentially long processing step
            # lets API readers and other workers inspect unrelated jobs.
            db.commit()
        except Exception:
            db.rollback()
            if lock_connection is not None:
                _release_job_lock(lock_connection, job_id, self.database_engine)
            raise
        finally:
            db.close()

        if job_id is None:
            return None
        return job_id, lock_connection

    def run_once(self) -> bool:
        """Claim and process one pending job; return whether work was found."""

        claim = self._claim_next()
        if claim is None:
            return False

        job_id, lock_connection = claim
        try:
            with self.session_factory() as db:
                job = db.get(AnalysisJob, job_id)
                if job is None or job.status != AnalysisJobStatus.PENDING:
                    return True

                try:
                    self.service_factory(db).execute(job)
                except Exception:
                    # AnalysisService records its own failure. This log keeps
                    # a worker traceback without changing a terminal result.
                    logger.exception("Analysis worker failed for job %s", job_id)
                finally:
                    db.expire_all()
                    final_job = db.get(AnalysisJob, job_id)
                    if final_job is not None and final_job.status in (
                        AnalysisJobStatus.PENDING,
                        AnalysisJobStatus.RUNNING,
                    ):
                        try:
                            self.service_factory(db).fail_analysis(
                                final_job,
                                "The analysis worker exited before recording a final result.",
                            )
                        except Exception:
                            db.rollback()
                            logger.exception(
                                "Could not record worker exit for job %s", job_id
                            )
            return True
        finally:
            _release_job_lock(lock_connection, job_id, self.database_engine)

