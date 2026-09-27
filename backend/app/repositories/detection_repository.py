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
    - Restrict results to an officer's jurisdiction.
    - Count detections for dashboard statistics.

Note:
    Methods whose name ends in _for_user apply
    jurisdiction scoping (requirement FR-04) and are what
    the API layer calls. The unscoped methods remain for
    system-level work, such as dispatching alerts, where
    every detection must be considered regardless of who
    is eventually notified.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Version:
    1.0.0
===========================================================
"""

from sqlalchemy import false
from sqlalchemy.orm import Query, Session

from app.models.detection import Detection
from app.models.district import District
from app.models.enums import DetectionStatus, UserRole
from app.models.forest_area import ForestArea
from app.models.user import User


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
    # Jurisdiction Scoping
    # ---------------------------------------------------------
    def scope_to_jurisdiction(
        self,
        query: Query,
        user: User,
    ) -> Query:
        """
        Restrict a detection query to a user's jurisdiction.

        Args:
            query:
                Query selecting Detection rows.

            user:
                Officer whose jurisdiction applies.

        Returns:
            The query with the jurisdiction filter applied.

        A detection belongs to a forest area, which belongs
        to a district, which belongs to a province. Scoping
        therefore joins through both.

        This is the enforcement point for requirement FR-04.
        Filtering here rather than in the endpoint means an
        out-of-jurisdiction detection cannot be returned by
        any caller of these methods, whatever the request
        asked for. A user interface that merely hides rows
        is not access control.

        An officer with no jurisdiction assigned matches
        nothing. That case is rejected explicitly rather
        than left to a NULL comparison: SQLAlchemy renders
        `column == None` as `IS NULL`, which would match
        rows whose district is unset instead of matching
        none. An unassigned account is treated as not yet
        authorised.
        """

        # -----------------------------------------------------
        # Administrators are unrestricted
        # -----------------------------------------------------

        if user.role == UserRole.ADMIN:
            return query

        query = (
            query
            .join(
                ForestArea,
                ForestArea.id
                == Detection.forest_area_id,
            )
            .join(
                District,
                District.id
                == ForestArea.district_id,
            )
        )

        # -----------------------------------------------------
        # Provincial officers: every district in the province
        # -----------------------------------------------------

        if user.role == UserRole.PROVINCIAL_FORESTRY_OFFICER:

            if user.province_id is None:
                return query.filter(false())

            return query.filter(
                District.province_id
                == user.province_id,
            )

        # -----------------------------------------------------
        # District officers: their district only
        # -----------------------------------------------------

        if user.role == UserRole.DISTRICT_FORESTRY_OFFICER:

            if user.district_id is None:
                return query.filter(false())

            return query.filter(
                ForestArea.district_id
                == user.district_id,
            )

        # -----------------------------------------------------
        # Unknown role: return nothing
        # -----------------------------------------------------

        return query.filter(false())

    # ---------------------------------------------------------
    # Get by ID within Jurisdiction
    # ---------------------------------------------------------
    def get_by_id_for_user(
        self,
        detection_id: int,
        user: User,
    ) -> Detection | None:
        """
        Retrieve a detection only if the user may see it.

        Returns None when the detection does not exist OR
        lies outside the user's jurisdiction. The two cases
        are deliberately indistinguishable to the caller, so
        that probing for record IDs reveals nothing about
        detections in other districts.
        """

        query = self.db.query(Detection).filter(
            Detection.id == detection_id,
        )

        return (
            self.scope_to_jurisdiction(query, user)
            .first()
        )

    # ---------------------------------------------------------
    # Get All within Jurisdiction
    # ---------------------------------------------------------
    def get_all_for_user(
        self,
        user: User,
    ) -> list[Detection]:
        """
        Retrieve all detections the user may see.
        """

        query = self.db.query(Detection)

        return (
            self.scope_to_jurisdiction(query, user)
            .order_by(
                Detection.created_at.desc(),
            )
            .all()
        )

    # ---------------------------------------------------------
    # Get by Status within Jurisdiction
    # ---------------------------------------------------------
    def get_by_status_for_user(
        self,
        status: DetectionStatus,
        user: User,
    ) -> list[Detection]:
        """
        Retrieve detections by status the user may see.
        """

        query = self.db.query(Detection).filter(
            Detection.status == status,
        )

        return (
            self.scope_to_jurisdiction(query, user)
            .order_by(
                Detection.created_at.desc(),
            )
            .all()
        )

    # ---------------------------------------------------------
    # Get by Forest Area within Jurisdiction
    # ---------------------------------------------------------
    def get_by_forest_area_for_user(
        self,
        forest_area_id: int,
        user: User,
    ) -> list[Detection]:
        """
        Retrieve a forest area's detections the user may see.
        """

        query = self.db.query(Detection).filter(
            Detection.forest_area_id == forest_area_id,
        )

        return (
            self.scope_to_jurisdiction(query, user)
            .order_by(
                Detection.created_at.desc(),
            )
            .all()
        )

    # ---------------------------------------------------------
    # Count within Jurisdiction
    # ---------------------------------------------------------
    def count_for_user(
        self,
        user: User,
        status: DetectionStatus | None = None,
    ) -> int:
        """
        Count detections the user may see.

        Args:
            user:
                Officer whose jurisdiction applies.

            status:
                Optional status to count. All statuses are
                counted when omitted.
        """

        query = self.db.query(Detection)

        if status is not None:
            query = query.filter(
                Detection.status == status,
            )

        return (
            self.scope_to_jurisdiction(query, user)
            .count()
        )

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