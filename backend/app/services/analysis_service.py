"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Analysis Service

Purpose:
    Coordinates the complete intelligent deforestation
    detection workflow using Sentinel-2 imagery.

Workflow:

    Forest Area
        ↓
    Copernicus Sentinel-2 search
        ↓
    Newest suitable image
        ↓
    Download/register if new
        ↓
    Select previous + latest image
        ↓
    NDVI analysis
        ↓
    Vegetation change detection
        ↓
    Deforestation detection
        ↓
    Alert generation
        ↓
    Analysis completed

Author:
    Samuel Bikiloni

Project:
    Intelligent Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Version:
    2.0.0
===========================================================
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.analysis_job import AnalysisJob
from app.models.enums import (
    AnalysisJobStatus,
    AnalysisJobType,
)
from app.models.forest_area import ForestArea

from app.services.alert_service import AlertService
from app.services.detection_service import DetectionService
from app.services.satellite_image_selection_service import (
    SatelliteImageSelectionService,
)
from app.services.sentinel_service import SentinelService


class AnalysisService:
    """
    Coordinates the complete Sentinel-2 deforestation
    detection workflow.
    """

    def __init__(
        self,
        db: Session,
    ) -> None:
        """
        Initialize the analysis service.
        """

        self.db = db

        self.detection_service = (
            DetectionService(db)
        )

        self.alert_service = (
            AlertService(db)
        )

        self.image_selection_service = (
            SatelliteImageSelectionService(db)
        )

        self.sentinel_service = (
            SentinelService(db)
        )

    # =========================================================
    # CREATE ANALYSIS JOB
    # =========================================================

    def create_analysis_job(
        self,
        forest_area_id: int,
        satellite_image_id: int,
        started_by: int | None,
        job_type: AnalysisJobType,
        previous_satellite_image_id: int | None = None,
    ) -> AnalysisJob:
        """
        Create a new analysis job.
        """

        job = AnalysisJob(
            forest_area_id=forest_area_id,

            previous_satellite_image_id=(
                previous_satellite_image_id
            ),

            satellite_image_id=(
                satellite_image_id
            ),

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
        Mark analysis job as running.
        """

        job.status = (
            AnalysisJobStatus.RUNNING
        )

        job.started_at = (
            datetime.now(UTC)
        )

        self.db.commit()

        self.db.refresh(job)

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
        Mark analysis job as completed.
        """

        completed_at = (
            datetime.now(UTC)
        )

        job.completed_at = completed_at

        job.status = (
            AnalysisJobStatus.COMPLETED
        )

        if job.started_at is not None:

            job.duration_seconds = (
                completed_at
                - job.started_at
            ).total_seconds()

        job.cloud_cover_percentage = (
            cloud_cover
        )

        job.vegetation_change_percentage = (
            vegetation_change
        )

        job.ndvi_threshold = (
            ndvi_threshold
        )

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
        Mark analysis job as failed.
        """

        completed_at = (
            datetime.now(UTC)
        )

        job.completed_at = completed_at

        job.status = (
            AnalysisJobStatus.FAILED
        )

        job.error_message = (
            str(error_message)[:500]
        )

        if job.started_at is not None:

            job.duration_seconds = (
                completed_at
                - job.started_at
            ).total_seconds()

        self.db.commit()

        self.db.refresh(job)

    # =========================================================
    # AUTOMATIC SENTINEL ACQUISITION
    # =========================================================

    def acquire_latest_satellite_image(
        self,
        forest_area_id: int,
    ):
        """
        Search Copernicus for the newest suitable
        Sentinel-2 image.

        If a new image exists, it is downloaded and
        registered automatically.

        If the newest image already exists locally,
        the existing database record is returned.
        """

        forest = (
            self.db.query(ForestArea)
            .filter(
                ForestArea.id
                == forest_area_id,

                ForestArea.is_active.is_(True),
            )
            .first()
        )

        if forest is None:

            raise ValueError(
                "Forest area not found."
            )

        image = (
            self.sentinel_service
            .discover_latest_image(
                forest_area=forest,

                max_cloud_cover=30.0,

                search_days=30,
            )
        )

        if image is None:

            raise ValueError(
                "No suitable Sentinel-2 image was "
                "found for this forest area."
            )

        return image

    # =========================================================
    # SELECT CURRENT IMAGE PAIR
    # =========================================================

    def select_current_image_pair(
        self,
        forest_area_id: int,
    ):
        """
        Select the previous and latest compatible
        Sentinel-2 images.
        """

        (
            previous_image,
            latest_image,
        ) = (
            self.image_selection_service
            .select_image_pair(
                forest_area_id=forest_area_id
            )
        )

        return (
            previous_image,
            latest_image,
        )

    # =========================================================
    # RUN COMPLETE ANALYSIS
    # =========================================================

    def run_analysis(
        self,
        forest_area_id: int,
        started_by: int | None = None,
    ) -> AnalysisJob:
        """
        Create and execute an automatic analysis.

        This method performs:

            1. Copernicus image discovery.
            2. New image download if required.
            3. Previous/latest image selection.
            4. Analysis job creation.
            5. NDVI/detection processing.
            6. Alert generation.
        """

        # -----------------------------------------------------
        # Acquire newest Sentinel-2 image
        # -----------------------------------------------------

        self.acquire_latest_satellite_image(
            forest_area_id=forest_area_id
        )

        # -----------------------------------------------------
        # Select compatible image pair
        # -----------------------------------------------------

        (
            previous_image,
            latest_image,
        ) = self.select_current_image_pair(
            forest_area_id=forest_area_id
        )

        # -----------------------------------------------------
        # Create job
        # -----------------------------------------------------

        job = self.create_analysis_job(
            forest_area_id=forest_area_id,

            previous_satellite_image_id=(
                previous_image.id
            ),

            satellite_image_id=(
                latest_image.id
            ),

            started_by=started_by,

            job_type=(
                AnalysisJobType.AUTOMATIC
            ),
        )

        # -----------------------------------------------------
        # Execute
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
        Execute the analysis job.

        This method is designed to run in the background.

        It will:

            1. Find the forest.
            2. Check Copernicus again.
            3. Download newest imagery if available.
            4. Select previous/latest images.
            5. Update the analysis job.
            6. Run detection.
            7. Generate alert.
            8. Complete the job.
        """

        try:

            # -------------------------------------------------
            # Get forest
            # -------------------------------------------------

            forest = (
                self.db.query(ForestArea)
                .filter(
                    ForestArea.id
                    == job.forest_area_id
                )
                .first()
            )

            if forest is None:

                raise ValueError(
                    "Forest area associated with "
                    "analysis job was not found."
                )

            # -------------------------------------------------
            # Start analysis
            # -------------------------------------------------

            self.start_analysis(job)

            # -------------------------------------------------
            # Check Copernicus for newest image
            # -------------------------------------------------

            latest_available = (
                self.sentinel_service
                .discover_latest_image(
                    forest_area=forest,

                    max_cloud_cover=30.0,

                    search_days=30,
                )
            )

            if latest_available is None:

                raise ValueError(
                    "No suitable Sentinel-2 image "
                    "is available."
                )

            # -------------------------------------------------
            # Refresh database state
            # -------------------------------------------------

            self.db.expire_all()

            # -------------------------------------------------
            # Select previous/latest images
            # -------------------------------------------------

            (
                previous_image,
                latest_image,
            ) = (
                self.image_selection_service
                .select_image_pair(
                    forest_area_id=job.forest_area_id
                )
            )

            # -------------------------------------------------
            # Update job with actual image pair
            # -------------------------------------------------

            job.previous_satellite_image_id = (
                previous_image.id
            )

            job.satellite_image_id = (
                latest_image.id
            )

            self.db.commit()

            self.db.refresh(job)

            # -------------------------------------------------
            # Execute deforestation detection
            # -------------------------------------------------

            detection = (
                self.detection_service
                .execute_detection(
                    job
                )
            )

            # -------------------------------------------------
            # Generate alert
            # -------------------------------------------------

            if detection is not None:

                self.alert_service.process_detection(
                    detection
                )

            # -------------------------------------------------
            # Calculate vegetation change
            # -------------------------------------------------

            vegetation_change = 0.0

            if detection is not None:

                vegetation_change = (
                    detection
                    .vegetation_loss_percentage
                    or 0.0
                )

            # -------------------------------------------------
            # Cloud coverage
            # -------------------------------------------------

            cloud_cover = (
                latest_image
                .cloud_cover_percentage
                or 0.0
            )

            # -------------------------------------------------
            # Complete analysis
            # -------------------------------------------------

            self.complete_analysis(
                job=job,

                cloud_cover=cloud_cover,

                vegetation_change=(
                    vegetation_change
                ),

                ndvi_threshold=0.30,
            )

        except Exception as exc:

            # -------------------------------------------------
            # Rollback failed database transaction
            # -------------------------------------------------

            self.db.rollback()

            try:

                # Refresh job after rollback

                job = (
                    self.db.query(
                        AnalysisJob
                    )
                    .filter(
                        AnalysisJob.id
                        == job.id
                    )
                    .first()
                )

                if job is not None:

                    self.fail_analysis(
                        job=job,

                        error_message=str(
                            exc
                        ),
                    )

            except Exception:

                self.db.rollback()

            # -------------------------------------------------
            # Re-raise
            # -------------------------------------------------

            raise