"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Detection Service

Purpose:
    Performs forest change detection and creates
    detection records.

Responsibilities:
    - Execute NDVI-based analysis.
    - Compare satellite imagery.
    - Create detections.
    - Trigger alerts.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia
===========================================================
"""

from sqlalchemy.orm import Session

from app.models.analysis_job import AnalysisJob
from app.models.detection import Detection
from app.models.enums import DetectionStatus
from app.services.alert_service import AlertService


class DetectionService:
    """
    Handles deforestation detection.
    """

    def __init__(self, db: Session):
        self.db = db
        self.alert_service = AlertService(db)

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

        self.db.add(detection)
        self.db.commit()
        self.db.refresh(detection)

        return detection

    def verify_detection(
        self,
        detection: Detection,
        verified_by: int,
    ) -> Detection:
        
        """
        Verify a detection and trigger alerts.
        """

        from datetime import UTC, datetime

        detection.status = DetectionStatus.VERIFIED
        detection.verified_by = verified_by
        detection.verified_at = datetime.now(UTC)

        self.db.commit()

        self.alert_service.process_detection(
            detection
        )

        return detection
    def reject_detection(
        self,
        detection: Detection,
        verified_by: int,
        notes: str,
    ) -> Detection:
        """
        Reject a detection.
        """

        from datetime import UTC, datetime

        detection.status = DetectionStatus.REJECTED
        detection.verified_by = verified_by
        detection.verified_at = datetime.now(UTC)
        detection.verification_notes = notes

        self.db.commit()

        return detection

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

        self.db.commit()

        return detection

    def execute_detection(
        self,
        job: AnalysisJob,
    ) -> Detection | None:
        """
        Execute the complete detection workflow.

        NOTE:
        This currently contains placeholder values.
        Later it will call the NDVI engine and compare
        Sentinel-2 imagery.
        """

        # -------------------------------------------------
        # Future NDVI Processing
        #
        # 1. Load current Sentinel-2 image
        # 2. Load previous image
        # 3. Calculate NDVI
        # 4. Detect vegetation change
        # -------------------------------------------------

        vegetation_loss = 3.85
        confidence = 97.4

        # Ignore insignificant changes
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

        self.verify_detection(
            detection=detection,
            verified_by=1,
        )

        return detection