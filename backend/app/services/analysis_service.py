"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Analysis Service

Purpose:
    Coordinates the complete forest analysis workflow.

Responsibilities:
    - Create analysis jobs.
    - Execute satellite image analysis.
    - Trigger detection engine.
    - Record analysis results.
    - Handle analysis failures.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Version:
    1.0.0
===========================================================
"""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.analysis_job import AnalysisJob
from app.models.satellite_image import SatelliteImage
from app.models.enums import (
    AnalysisJobStatus,
    AnalysisJobType,
)
from app.services.detection_service import DetectionService


class AnalysisService:
    """
    Coordinates the complete forest analysis workflow.
    """

    def __init__(
        self,
        db: Session,
    ):
        """
        Initialize the analysis service.
        """

        self.db = db

        self.detection_service = DetectionService(db)

    # =========================================================
    # CREATE ANALYSIS JOB
    # =========================================================

    def create_analysis_job(
        self,
        forest_area_id: int,
        satellite_image_id: int,
        started_by: int | None,
        job_type: AnalysisJobType,
    ) -> AnalysisJob:
        """
        Create a new analysis job.
        """

        job = AnalysisJob(
            forest_area_id=forest_area_id,
            satellite_image_id=satellite_image_id,
            started_by=started_by,
            job_type=job_type,
            status=AnalysisJobStatus.PENDING,
        )

        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)

        return job

    # =========================================================
    # START ANALYSIS
    # =========================================================

    def start_analysis(
        self,
        job: AnalysisJob,
    ) -> None:
        """
        Mark an analysis job as running.
        """

        job.status = AnalysisJobStatus.RUNNING
        job.started_at = datetime.now(UTC)

        self.db.commit()

    # =========================================================
    # COMPLETE ANALYSIS
    # =========================================================

    def complete_analysis(
        self,
        job: AnalysisJob,
        cloud_cover: float,
        vegetation_change: float,
        ndvi_threshold: float,
    ) -> None:
        """
        Mark an analysis job as completed.
        """

        completed_at = datetime.now(UTC)

        job.completed_at = completed_at
        job.status = AnalysisJobStatus.COMPLETED

        if job.started_at is not None:
            job.duration_seconds = (
                completed_at - job.started_at
            ).total_seconds()

        job.cloud_cover_percentage = cloud_cover

        job.vegetation_change_percentage = (
            vegetation_change
        )

        job.ndvi_threshold = ndvi_threshold

        self.db.commit()
        self.db.refresh(job)

    # =========================================================
    # FAIL ANALYSIS
    # =========================================================

    def fail_analysis(
        self,
        job: AnalysisJob,
        error_message: str,
    ) -> None:
        """
        Mark an analysis job as failed.
        """

        completed_at = datetime.now(UTC)

        job.completed_at = completed_at
        job.status = AnalysisJobStatus.FAILED

        job.error_message = error_message[:500]

        if job.started_at is not None:
            job.duration_seconds = (
                completed_at - job.started_at
            ).total_seconds()

        self.db.commit()
        self.db.refresh(job)

    # =========================================================
    # RUN ANALYSIS
    # =========================================================

    def run_analysis(
        self,
        forest_area_id: int,
        started_by: int | None = None,
    ) -> AnalysisJob:
        """
        Create and execute an analysis job for a forest area.

        Workflow:

        1. Find the latest Sentinel-2 image.
        2. Create an analysis job.
        3. Start the analysis.
        4. Execute detection.
        5. Calculate vegetation change.
        6. Complete the analysis job.
        7. Return the completed job.
        """

        # -----------------------------------------------------
        # Find latest satellite image
        # -----------------------------------------------------

        satellite_image = (
            self.db.query(SatelliteImage)
            .filter(
                SatelliteImage.forest_area_id
                == forest_area_id
            )
            .order_by(
                SatelliteImage.acquisition_date.desc()
            )
            .first()
        )

        if satellite_image is None:
            raise ValueError(
                "No satellite image is available "
                "for this forest area."
            )

        # -----------------------------------------------------
        # Create analysis job
        # -----------------------------------------------------

        job = self.create_analysis_job(
            forest_area_id=forest_area_id,
            satellite_image_id=satellite_image.id,
            started_by=started_by,
            job_type=AnalysisJobType.AUTOMATIC,
        )

        # -----------------------------------------------------
        # Execute analysis
        # -----------------------------------------------------

        self.execute(job)

        return job

    # =========================================================
    # EXECUTE ANALYSIS
    # =========================================================

    def execute(
        self,
        job: AnalysisJob,
    ) -> None:
        """
        Execute the complete analysis workflow.
        """

        try:

            # -------------------------------------------------
            # Start analysis
            # -------------------------------------------------

            self.start_analysis(job)

            # -------------------------------------------------
            # Execute detection
            # -------------------------------------------------

            detection = (
                self.detection_service.execute_detection(
                    job
                )
            )

            # -------------------------------------------------
            # Determine vegetation change
            # -------------------------------------------------

            if detection is not None:

                vegetation_change = (
                    detection.vegetation_loss_percentage
                    or 0.0
                )

            else:

                vegetation_change = 0.0

            # -------------------------------------------------
            # Complete analysis
            # -------------------------------------------------

            self.complete_analysis(
                job=job,
                cloud_cover=5.4,
                vegetation_change=vegetation_change,
                ndvi_threshold=0.30,
            )

        except Exception as exc:

            # Make sure the current transaction is clean
            self.db.rollback()

            try:

                self.fail_analysis(
                    job=job,
                    error_message=str(exc),
                )

            except Exception:

                self.db.rollback()

            raise