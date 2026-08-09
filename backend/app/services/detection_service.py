"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
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
from app.models.detection import Detection
from app.models.enums import DetectionStatus
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

    # ---------------------------------------------------------
    # Create Detection
    # ---------------------------------------------------------
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

    # ---------------------------------------------------------
    # Verify Detection
    # ---------------------------------------------------------
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

    # ---------------------------------------------------------
    # Reject Detection
    # ---------------------------------------------------------
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

    # ---------------------------------------------------------
    # Close Detection
    # ---------------------------------------------------------
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

    # ---------------------------------------------------------
    # Execute Detection
    # ---------------------------------------------------------
    def execute_detection(
        self,
        job: AnalysisJob,
    ) -> Detection | None:
        """
        Execute the complete detection workflow.

        Future workflow:

        1. Load latest Sentinel-2 image.
        2. Load previous Sentinel-2 image.
        3. Calculate NDVI.
        4. Compare NDVI.
        5. Measure vegetation loss.
        6. Create detection.

        Returns
        -------
        Detection | None
        """

        # -------------------------------------------------
        # Placeholder values
        # Replace with NDVI results later.
        # -------------------------------------------------

        vegetation_loss = 3.85

        confidence = 97.40

        if vegetation_loss < 0.50:

            return None

        detection = self.create_detection(
            job=job,
            detected_area=vegetation_loss,
            confidence=confidence,
            ndvi_before=0.81,
            ndvi_after=0.42,
            vegetation_loss=48.15,
        )

        # -------------------------------------------------
        # Detection remains PENDING.
        #
        # A Forestry Officer will verify it using:
        #
        # PUT /detections/{id}/verify
        # -------------------------------------------------

        return detection