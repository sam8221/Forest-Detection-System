"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Detection Repository

Purpose:
    Provides database operations for deforestation
    detections.

Responsibilities:
    - Create detections.
    - Retrieve detections.
    - Update detections.
    - Delete detections.
    - Retrieve pending, verified and rejected detections.
    - Count detections for dashboard statistics.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Version:
    1.0.0
===========================================================
"""

from sqlalchemy.orm import Session

from app.models.detection import Detection
from app.models.enums import DetectionStatus


class DetectionRepository:
    """
    Handles database operations for detections.
    """

    def __init__(
        self,
        db: Session,
    ):
        self.db = db

    # ---------------------------------------------------------
    # Create
    # ---------------------------------------------------------
    def create(
        self,
        detection: Detection,
    ) -> Detection:
        """
        Save a new detection.
        """

        self.db.add(detection)
        self.db.commit()
        self.db.refresh(detection)

        return detection

    # ---------------------------------------------------------
    # Get by ID
    # ---------------------------------------------------------
    def get_by_id(
        self,
        detection_id: int,
    ) -> Detection | None:
        """
        Retrieve a detection by ID.
        """

        return (
            self.db.query(Detection)
            .filter(
                Detection.id == detection_id,
            )
            .first()
        )

    # ---------------------------------------------------------
    # Get All
    # ---------------------------------------------------------
    def get_all(
        self,
    ) -> list[Detection]:
        """
        Retrieve all detections.
        """

        return (
            self.db.query(Detection)
            .order_by(
                Detection.created_at.desc(),
            )
            .all()
        )

    # ---------------------------------------------------------
    # Get Recent
    # ---------------------------------------------------------
    def get_recent(
        self,
        limit: int = 5,
    ) -> list[Detection]:
        """
        Retrieve the most recent detections.
        """

        return (
            self.db.query(Detection)
            .order_by(
                Detection.created_at.desc(),
            )
            .limit(limit)
            .all()
        )

    # ---------------------------------------------------------
    # Get by Forest Area
    # ---------------------------------------------------------
    def get_by_forest_area(
        self,
        forest_area_id: int,
    ) -> list[Detection]:
        """
        Retrieve detections for a forest area.
        """

        return (
            self.db.query(Detection)
            .filter(
                Detection.forest_area_id == forest_area_id,
            )
            .order_by(
                Detection.created_at.desc(),
            )
            .all()
        )

    # ---------------------------------------------------------
    # Get by Status
    # ---------------------------------------------------------
    def get_by_status(
        self,
        status: DetectionStatus,
    ) -> list[Detection]:
        """
        Retrieve detections by status.
        """

        return (
            self.db.query(Detection)
            .filter(
                Detection.status == status,
            )
            .order_by(
                Detection.created_at.desc(),
            )
            .all()
        )

    # ---------------------------------------------------------
    # Get Pending
    # ---------------------------------------------------------
    def get_pending(
        self,
    ) -> list[Detection]:
        """
        Retrieve pending detections.
        """

        return self.get_by_status(
            DetectionStatus.PENDING,
        )

    # ---------------------------------------------------------
    # Get Verified
    # ---------------------------------------------------------
    def get_verified(
        self,
    ) -> list[Detection]:
        """
        Retrieve verified detections.
        """

        return self.get_by_status(
            DetectionStatus.VERIFIED,
        )

    # ---------------------------------------------------------
    # Get Rejected
    # ---------------------------------------------------------
    def get_rejected(
        self,
    ) -> list[Detection]:
        """
        Retrieve rejected detections.
        """

        return self.get_by_status(
            DetectionStatus.REJECTED,
        )

    # ---------------------------------------------------------
    # Count
    # ---------------------------------------------------------
    def count(
        self,
    ) -> int:
        """
        Return total number of detections.
        """

        return (
            self.db.query(Detection)
            .count()
        )

    # ---------------------------------------------------------
    # Count Pending
    # ---------------------------------------------------------
    def count_pending(
        self,
    ) -> int:
        """
        Return total pending detections.
        """

        return (
            self.db.query(Detection)
            .filter(
                Detection.status == DetectionStatus.PENDING,
            )
            .count()
        )

    # ---------------------------------------------------------
    # Count Verified
    # ---------------------------------------------------------
    def count_verified(
        self,
    ) -> int:
        """
        Return total verified detections.
        """

        return (
            self.db.query(Detection)
            .filter(
                Detection.status == DetectionStatus.VERIFIED,
            )
            .count()
        )

    # ---------------------------------------------------------
    # Count Rejected
    # ---------------------------------------------------------
    def count_rejected(
        self,
    ) -> int:
        """
        Return total rejected detections.
        """

        return (
            self.db.query(Detection)
            .filter(
                Detection.status == DetectionStatus.REJECTED,
            )
            .count()
        )

    # ---------------------------------------------------------
    # Update
    # ---------------------------------------------------------
    def update(
        self,
        detection: Detection,
    ) -> Detection:
        """
        Update an existing detection.
        """

        self.db.commit()
        self.db.refresh(detection)

        return detection

    # ---------------------------------------------------------
    # Delete
    # ---------------------------------------------------------
    def delete(
        self,
        detection: Detection,
    ) -> None:
        """
        Permanently delete a detection.
        """

        self.db.delete(detection)
        self.db.commit()