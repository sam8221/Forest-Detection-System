"""Database operations and byte-progress math for downloads."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import logging

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.models.satellite_download_job import (
    ACTIVE_DOWNLOAD_STATUSES,
    SatelliteDownloadJob,
)


logger = logging.getLogger(__name__)


def calculate_download_percentage(
    downloaded_bytes: int,
    total_bytes: int | None,
    *,
    transfer_complete: bool = False,
) -> float | None:
    """Calculate a bounded percentage from measured bytes only."""

    if transfer_complete:
        return 100.0

    if total_bytes is None or total_bytes <= 0:
        return None

    downloaded = max(0, downloaded_bytes)
    percentage = (downloaded / total_bytes) * 100

    # The response body may yield its final chunk before the HTTP
    # transfer has been cleanly closed and the temporary file saved.
    return min(99.9, max(0.0, percentage))


class SatelliteDownloadJobService:
    """Creates and updates persisted download-job records."""

    def __init__(self, db: Session):
        self.db = db

    def get_active_for_product(
        self,
        forest_area_id: int,
        product_id: str,
    ) -> SatelliteDownloadJob | None:
        return (
            self.db.query(SatelliteDownloadJob)
            .filter(
                SatelliteDownloadJob.forest_area_id == forest_area_id,
                SatelliteDownloadJob.product_id == product_id,
                SatelliteDownloadJob.status.in_(ACTIVE_DOWNLOAD_STATUSES),
            )
            .order_by(SatelliteDownloadJob.created_at.desc())
            .first()
        )

    def create_or_get_active(
        self,
        *,
        forest_area_id: int,
        product_id: str,
        product_name: str,
        started_by: int | None,
    ) -> tuple[SatelliteDownloadJob, bool]:
        existing = self.get_active_for_product(forest_area_id, product_id)
        if existing is not None:
            return existing, False

        job = SatelliteDownloadJob(
            job_id=str(uuid4()),
            forest_area_id=forest_area_id,
            product_id=product_id,
            product_name=product_name,
            started_by=started_by,
            status="PREPARING",
            downloaded_bytes=0,
            progress_percentage=None,
        )
        self.db.add(job)

        try:
            self.db.commit()
            self.db.refresh(job)
            return job, True
        except IntegrityError:
            # The partial unique index arbitrates duplicate requests
            # across workers/processes. Return the job created by the
            # competing request instead of starting a second transfer.
            self.db.rollback()
            existing = self.get_active_for_product(forest_area_id, product_id)
            if existing is None:
                raise
            return existing, False

    @staticmethod
    def record_progress(
        job_id: str,
        *,
        status: str,
        downloaded_bytes: int,
        total_bytes: int | None,
        transfer_complete: bool = False,
        session_factory=SessionLocal,
    ) -> None:
        """
        Record transfer progress on its own database session.

        Args:
            job_id:
                The job to update, by identifier rather than by
                ORM instance: an instance belongs to the session
                that loaded it, and this does not run there.

        Why a session of its own:

            The members of a product are transferred
            concurrently, so progress is reported from several
            threads while the main thread is still inside the
            download. Writing it through the session the
            download itself uses means one SQLAlchemy Session is
            operated on by several threads, which it refuses:

                IllegalStateChangeError
                ResourceClosedError

            Both were observed against this code, and both
            killed a transfer that had otherwise succeeded, with
            the bytes already on disk. A short session per write
            shares no state to corrupt.

        A failure here is logged and swallowed. Progress
        reporting must never be the reason an acquisition fails;
        the worst outcome is a percentage that stops advancing.
        """

        percentage = calculate_download_percentage(
            max(0, downloaded_bytes),
            total_bytes if total_bytes and total_bytes > 0 else None,
            transfer_complete=transfer_complete,
        )

        db: Session = session_factory()

        try:
            db.execute(
                update(SatelliteDownloadJob)
                .where(SatelliteDownloadJob.job_id == job_id)
                .values(
                    status=status,
                    downloaded_bytes=max(0, downloaded_bytes),
                    total_bytes=(
                        total_bytes
                        if total_bytes and total_bytes > 0
                        else None
                    ),
                    progress_percentage=percentage,
                )
            )
            db.commit()
        except SQLAlchemyError:
            db.rollback()
            logger.exception(
                "Could not record progress for satellite download job %s",
                job_id,
            )
        finally:
            db.close()

    def report_progress(
        self,
        job: SatelliteDownloadJob,
        *,
        status: str,
        downloaded_bytes: int,
        total_bytes: int | None,
        transfer_complete: bool = False,
    ) -> None:
        job.status = status
        job.downloaded_bytes = max(0, downloaded_bytes)
        job.total_bytes = total_bytes if total_bytes and total_bytes > 0 else None
        job.progress_percentage = calculate_download_percentage(
            job.downloaded_bytes,
            job.total_bytes,
            transfer_complete=transfer_complete,
        )
        self.db.commit()

    def complete(
        self,
        job: SatelliteDownloadJob,
        satellite_image_id: int,
    ) -> None:
        job.status = "COMPLETED"
        job.progress_percentage = 100.0
        job.satellite_image_id = satellite_image_id
        job.error_message = None
        job.completed_at = datetime.now(UTC)
        self.db.commit()
        self.db.refresh(job)

    def fail(
        self,
        job_id: str,
        message: str,
    ) -> None:
        self.db.rollback()
        job = self.db.get(SatelliteDownloadJob, job_id)
        if job is None:
            return
        job.status = "FAILED"
        job.error_message = message[:500]
        job.completed_at = datetime.now(UTC)
        self.db.commit()

    def fail_abandoned(self) -> int:
        """Mark downloads left active by a stopped server as failed."""

        jobs = (
            self.db.query(SatelliteDownloadJob)
            .filter(SatelliteDownloadJob.status.in_(ACTIVE_DOWNLOAD_STATUSES))
            .all()
        )
        for job in jobs:
            job.status = "FAILED"
            job.error_message = (
                "The server stopped during this download. "
                "Retry the acquisition."
            )
            job.completed_at = datetime.now(UTC)
        if jobs:
            self.db.commit()
        return len(jobs)
