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
    - Generate alerts.
    - Record analysis results.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia
===========================================================
"""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.analysis_job import AnalysisJob
from app.models.enums import (
    AnalysisJobStatus,
    AnalysisJobType,
)
from app.services.alert_service import AlertService


class AnalysisService:
    """
    Handles the complete forest analysis process.
    """

    def __init__(self, db: Session):
        self.db = db
        self.alert_service = AlertService(db)

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

    def start_analysis(
        self,
        job: AnalysisJob,
    ) -> None:
        """
        Mark the analysis as running.
        """

        job.status = AnalysisJobStatus.RUNNING
        job.started_at = datetime.now(UTC)

        self.db.commit()
    def complete_analysis(
        self,
        job: AnalysisJob,
        cloud_cover: float,
        vegetation_change: float,
        ndvi_threshold: float,
    ) -> None:
        """
        Mark an analysis job as successfully completed.
        """

        completed_at = datetime.now(UTC)

        job.completed_at = completed_at
        job.status = AnalysisJobStatus.COMPLETED

        if job.started_at is not None:
            duration = (
                completed_at - job.started_at
            ).total_seconds()

            job.duration_seconds = duration

        job.cloud_cover_percentage = cloud_cover
        job.vegetation_change_percentage = vegetation_change
        job.ndvi_threshold = ndvi_threshold

        self.db.commit()

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
        job.error_message = error_message

        if job.started_at is not None:
            duration = (
                completed_at - job.started_at
            ).total_seconds()

            job.duration_seconds = duration

        self.db.commit()

    def execute(
        self,
        job: AnalysisJob,
    ) -> None:
        """
        Execute the complete analysis workflow.

        NOTE:
        DetectionService will be connected here after
        it is implemented.
        """

        try:

            self.start_analysis(job)

            # ---------------------------------------
            # TODO:
            # Download Sentinel-2 image
            # Calculate NDVI
            # Compare previous image
            # Create Detection
            # Trigger AlertService
            # ---------------------------------------

            self.complete_analysis(
                job=job,
                cloud_cover=5.4,
                vegetation_change=0.0,
                ndvi_threshold=0.30,
            )

        except Exception as ex:

            self.fail_analysis(
                job,
                str(ex),
            )

            raise