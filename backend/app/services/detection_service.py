"""
ForestWatch Zambia

Module: Detection Service

Purpose:
Performs forest change detection and manages
detection records.

Responsibilities:
- Create detections.
- Verify detections.
- Reject detections.
- Close detections.
- Execute the detection workflow.
- Start analysis jobs.

Author:
Samuel Bikiloni

Project:
Web-Based Deforestation Detection and Alert System
Using Sentinel-2 Imagery in the Copperbelt, Zambia
"""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.analysis_job import AnalysisJob
from app.models.detection import Detection
from app.models.enums import DetectionStatus
from app.models.satellite_image import SatelliteImage

from app.repositories.detection_repository import (
    DetectionRepository,
)

from app.services.alert_service import AlertService


class DetectionService:
    """
    Handles forest change detection.
    """

    def __init__(
        self,
        db: Session,
    ):
        """
        Initialize the detection service.
        """

        self.db = db

        self.repository = DetectionRepository(db)

        self.alert_service = AlertService(db)

    # =====================================================
    # RUN ANALYSIS
    # =====================================================

    def run_analysis(
        self,
        forest_area_id: int,
    ) -> AnalysisJob:
        """
        Start a forest analysis.

        Workflow:
        1. Find the latest satellite image.
        2. Create an analysis job.
        3. Execute the detection workflow.
        4. Return the analysis job.
        """

        # -------------------------------------------------
        # Find latest satellite image
        # -------------------------------------------------

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

        # -------------------------------------------------
        # Create analysis job
        # -------------------------------------------------

        job = AnalysisJob(
            forest_area_id=forest_area_id,
            satellite_image_id=satellite_image.id,
        )

        self.db.add(job)

        try:
            self.db.commit()
            self.db.refresh(job)

        except Exception:
            self.db.rollback()
            raise

        # -------------------------------------------------
        # Execute detection
        # -------------------------------------------------

        try:

            self.execute_detection(
                job=job,
            )

            self.db.refresh(job)

        except Exception:
            self.db.rollback()
            raise

        return job

    # =====================================================
    # CREATE DETECTION
    # =====================================================

    def create_detection(
        self,
        job: AnalysisJob,
        detected_area: float,
        confidence: float,
        ndvi_before: float,
        ndvi_after: float,
        vegetation_loss: float,
    ) -> Detection:
        """
        Create a new detection record.
        """

        detection = Detection(
            forest_area_id=job.forest_area_id,
            satellite_image_id=job.satellite_image_id,
            analysis_job_id=job.id,
            detected_area_hectares=detected_area,
            confidence_score=confidence,
            ndvi_before=ndvi_before,
            ndvi_after=ndvi_after,
            vegetation_loss_percentage=vegetation_loss,
            status=DetectionStatus.PENDING,
        )

        return self.repository.create(
            detection,
        )

    # =====================================================
    # VERIFY DETECTION
    # =====================================================

    def verify_detection(
        self,
        detection: Detection,
        verified_by: int,
    ) -> Detection:
        """
        Verify a detection and trigger alerts.
        """

        detection.status = DetectionStatus.VERIFIED

        detection.verified_by = verified_by

        detection.verified_at = datetime.now(
            UTC,
        )

        detection = self.repository.update(
            detection,
        )

        self.alert_service.process_detection(
            detection,
        )

        return detection

    # =====================================================
    # REJECT DETECTION
    # =====================================================

    def reject_detection(
        self,
        detection: Detection,
        verified_by: int,
        notes: str,
    ) -> Detection:
        """
        Reject a detection.
        """

        detection.status = DetectionStatus.REJECTED

        detection.verified_by = verified_by

        detection.verified_at = datetime.now(
            UTC,
        )

        detection.verification_notes = notes

        return self.repository.update(
            detection,
        )

    # =====================================================
    # CLOSE DETECTION
    # =====================================================

    def close_detection(
        self,
        detection: Detection,
        notes: str | None = None,
    ) -> Detection:
        """
        Close a verified detection.
        """

        detection.status = DetectionStatus.CLOSED

        if notes:
            detection.verification_notes = notes

        return self.repository.update(
            detection,
        )

    # =====================================================
    # EXECUTE DETECTION
    # =====================================================

    def execute_detection(
        self,
        job: AnalysisJob,
    ) -> Detection | None:
        """
        Execute the complete detection workflow.

        Current workflow:

        1. Load latest Sentinel-2 image.
        2. Load previous Sentinel-2 image.
        3. Calculate NDVI.
        4. Compare NDVI.
        5. Measure vegetation loss.
        6. Create detection.

        NOTE:
        NDVI processing is currently represented by
        placeholder values and will be replaced by
        actual Sentinel-2 processing later.
        """

        # -------------------------------------------------
        # Temporary test values
        # -------------------------------------------------

        vegetation_loss_area = 3.85

        confidence = 97.40

        ndvi_before = 0.81

        ndvi_after = 0.42

        vegetation_loss_percentage = 48.15

        # -------------------------------------------------
        # Ignore insignificant changes
        # -------------------------------------------------

        if vegetation_loss_area < 0.50:
            return None

        # -------------------------------------------------
        # Create detection
        # -------------------------------------------------

        detection = self.create_detection(
            job=job,
            detected_area=vegetation_loss_area,
            confidence=confidence,
            ndvi_before=ndvi_before,
            ndvi_after=ndvi_after,
            vegetation_loss=vegetation_loss_percentage,
        )

        # -------------------------------------------------
        # Detection starts as PENDING.
        #
        # Forestry Officer can later verify it.
        # -------------------------------------------------

        return detection