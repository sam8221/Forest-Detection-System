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

Version:
    1.0.0
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
from app.services.sentinel_service import SentinelService


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

        self.sentinel_service = SentinelService(db)

        self.alert_service = AlertService(db)

    # ---------------------------------------------------------
    # Create Analysis Job
    # ---------------------------------------------------------
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

    # ---------------------------------------------------------
    # Start Analysis
    # ---------------------------------------------------------
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

    # ---------------------------------------------------------
    # Complete Analysis
    # ---------------------------------------------------------
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

    # ---------------------------------------------------------
    # Fail Analysis
    # ---------------------------------------------------------
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

            job.duration_seconds = (
                completed_at - job.started_at
            ).total_seconds()

        self.db.commit()

    # ---------------------------------------------------------
    # Execute Analysis
    # ---------------------------------------------------------
    def execute(
        self,
        job: AnalysisJob,
    ) -> None:
        """
        Execute the complete analysis workflow.

        Workflow:

        1. Start analysis
        2. Retrieve Sentinel-2 imagery
        3. Perform NDVI analysis
        4. Detect vegetation loss
        5. Generate alerts
        6. Complete analysis
        """

        try:

            # -----------------------------------------
            # Mark job as running
            # -----------------------------------------
            self.start_analysis(job)

            # -----------------------------------------
            # Future Workflow
            # -----------------------------------------
            #
            # latest_image =
            # self.sentinel_service.get_latest_image(
            #     job.forest_area_id,
            # )
            #
            # NDVIService.calculate(...)
            #
            # DetectionService.detect(...)
            #
            # AlertService.send(...)
            #
            # These services will be connected
            # in the next implementation phase.
            #
            # -----------------------------------------

            self.complete_analysis(
                job=job,
                cloud_cover=5.4,
                vegetation_change=0.0,
                ndvi_threshold=0.30,
            )

        except Exception as ex:

            self.fail_analysis(
                job=job,
                error_message=str(ex),
            )

            raise