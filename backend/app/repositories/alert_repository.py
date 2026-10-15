"""
ForestWatch Zambia

Module: Alert Repository

Purpose:
Provides database operations for alerts.

Responsibilities:
- Create alerts.
- Retrieve alerts.
- Update alerts.
- Delete alerts.
- Retrieve alerts by status.
- Retrieve resolved alerts.
- Restrict results to an officer's jurisdiction.
- Count alerts for dashboard statistics.

Note:
Methods whose name ends in _for_user apply jurisdiction
scoping (requirement FR-04) and are what the API layer
calls. The unscoped methods remain for system-level work,
such as the email worker dispatching queued alerts, where
every alert must be considered regardless of who is
eventually notified.

Author:
Samuel Bikiloni

Project:
Web-Based Deforestation Detection and Alert System
Using Sentinel-2 Imagery in the Copperbelt, Zambia
"""

from sqlalchemy import false
from sqlalchemy.orm import Query, Session

from app.models.alert import Alert
from app.models.detection import Detection
from app.models.district import District
from app.models.enums import AlertStatus, UserRole
from app.models.forest_area import ForestArea
from app.models.user import User


class AlertRepository:
    """
    Handles database operations for alerts.
    """

    def __init__(
        self,
        db: Session,
    ):
        self.db = db

    # =========================================================
    # JURISDICTION SCOPING
    # =========================================================

    def scope_to_jurisdiction(
        self,
        query: Query,
        user: User,
    ) -> Query:
        """
        Restrict an alert query to a user's jurisdiction.

        Args:
            query:
                Query selecting Alert rows.

            user:
                Officer whose jurisdiction applies.

        Returns:
            The query with the jurisdiction filter applied.

        An alert is raised about a detection, so its
        jurisdiction is the jurisdiction of that detection:
        the detection belongs to a forest area, which
        belongs to a district, which belongs to a province.
        Scoping therefore joins through all three.

        This is the enforcement point for requirement FR-04.
        Filtering here rather than in the endpoint means an
        out-of-jurisdiction alert cannot be returned by any
        caller of these methods, whatever the request asked
        for. An alert names the forest area and the location
        of suspected clearing, so leaking one tells an
        officer where the department is watching in a
        district they do not cover.

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
                Detection,
                Detection.id
                == Alert.detection_id,
            )
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
        alert_id: int,
        user: User,
    ) -> Alert | None:
        """
        Retrieve an alert only if the user may see it.

        Returns None when the alert does not exist OR lies
        outside the user's jurisdiction. The two cases are
        deliberately indistinguishable to the caller, so
        that probing for record IDs reveals nothing about
        alerts in other districts.
        """

        query = self.db.query(Alert).filter(
            Alert.id == alert_id,
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
    ) -> list[Alert]:
        """
        Retrieve all alerts the user may see.
        """

        query = self.db.query(Alert)

        return (
            self.scope_to_jurisdiction(query, user)
            .order_by(
                Alert.created_at.desc(),
            )
            .all()
        )

    # ---------------------------------------------------------
    # Get by Status within Jurisdiction
    # ---------------------------------------------------------

    def get_by_status_for_user(
        self,
        status: AlertStatus,
        user: User,
    ) -> list[Alert]:
        """
        Retrieve alerts of one status the user may see.
        """

        query = self.db.query(Alert).filter(
            Alert.status == status,
        )

        return (
            self.scope_to_jurisdiction(query, user)
            .order_by(
                Alert.created_at.desc(),
            )
            .all()
        )

    # ---------------------------------------------------------
    # Get Resolved within Jurisdiction
    # ---------------------------------------------------------

    def get_resolved_for_user(
        self,
        user: User,
    ) -> list[Alert]:
        """
        Retrieve resolved alerts the user may see.

        Resolution is tracked using the is_resolved field,
        matching the unscoped get_resolved. It is not read
        from the status column: an alert carries a review
        status and a resolution flag separately, and the two
        can disagree where a resolution was only partly
        written.
        """

        query = self.db.query(Alert).filter(
            Alert.is_resolved.is_(True),
        )

        return (
            self.scope_to_jurisdiction(query, user)
            .order_by(
                Alert.created_at.desc(),
            )
            .all()
        )

    # =========================================================
    # CREATE
    # =========================================================

    def create(
        self,
        alert: Alert,
    ) -> Alert:
        """
        Save a new alert.
        """

        self.db.add(alert)
        self.db.commit()
        self.db.refresh(alert)

        return alert

    # =========================================================
    # GET BY ID
    # =========================================================

    def get_by_id(
        self,
        alert_id: int,
    ) -> Alert | None:
        """
        Retrieve an alert by ID.
        """

        return (
            self.db.query(Alert)
            .filter(
                Alert.id == alert_id,
            )
            .first()
        )

    # =========================================================
    # GET ALL
    # =========================================================

    def get_all(
        self,
    ) -> list[Alert]:
        """
        Retrieve all alerts.
        """

        return (
            self.db.query(Alert)
            .order_by(
                Alert.created_at.desc(),
            )
            .all()
        )

    # =========================================================
    # GET RECENT
    # =========================================================

    def get_recent(
        self,
        limit: int = 5,
    ) -> list[Alert]:
        """
        Retrieve the most recent alerts.
        """

        return (
            self.db.query(Alert)
            .order_by(
                Alert.created_at.desc(),
            )
            .limit(limit)
            .all()
        )

    # =========================================================
    # GET BY STATUS
    # =========================================================

    def get_by_status(
        self,
        status: AlertStatus,
    ) -> list[Alert]:
        """
        Retrieve alerts by processing status.
        """

        return (
            self.db.query(Alert)
            .filter(
                Alert.status == status,
            )
            .order_by(
                Alert.created_at.desc(),
            )
            .all()
        )

    # =========================================================
    # GET PENDING
    # =========================================================

    def get_pending(
        self,
    ) -> list[Alert]:
        """
        Retrieve pending alerts.
        """

        return self.get_by_status(
            AlertStatus.PENDING,
        )

    # =========================================================
    # GET SENT
    # =========================================================

    def get_sent(
        self,
    ) -> list[Alert]:
        """
        Retrieve sent alerts.
        """

        return self.get_by_status(
            AlertStatus.SENT,
        )

    # =========================================================
    # GET FAILED
    # =========================================================

    def get_failed(
        self,
    ) -> list[Alert]:
        """
        Retrieve failed alerts.
        """

        return self.get_by_status(
            AlertStatus.FAILED,
        )

    # =========================================================
    # GET READ
    # =========================================================

    def get_read(
        self,
    ) -> list[Alert]:
        """
        Retrieve read alerts.
        """

        return self.get_by_status(
            AlertStatus.READ,
        )

    # =========================================================
    # GET RESOLVED
    # =========================================================

    def get_resolved(
        self,
    ) -> list[Alert]:
        """
        Retrieve resolved alerts.

        Resolution is tracked using the
        is_resolved field.
        """

        return (
            self.db.query(Alert)
            .filter(
                Alert.is_resolved.is_(True),
            )
            .order_by(
                Alert.created_at.desc(),
            )
            .all()
        )

    # =========================================================
    # COUNT ALL
    # =========================================================

    def count(
        self,
    ) -> int:
        """
        Return the total number of alerts.
        """

        return (
            self.db.query(Alert)
            .count()
        )

    # =========================================================
    # COUNT PENDING
    # =========================================================

    def count_pending(
        self,
    ) -> int:
        """
        Return the number of pending alerts.
        """

        return (
            self.db.query(Alert)
            .filter(
                Alert.status == AlertStatus.PENDING,
                Alert.is_resolved.is_(False),
            )
            .count()
        )

    # =========================================================
    # COUNT SENT
    # =========================================================

    def count_sent(
        self,
    ) -> int:
        """
        Return the number of sent alerts.
        """

        return (
            self.db.query(Alert)
            .filter(
                Alert.status == AlertStatus.SENT,
                Alert.is_resolved.is_(False),
            )
            .count()
        )

    # =========================================================
    # COUNT FAILED
    # =========================================================

    def count_failed(
        self,
    ) -> int:
        """
        Return the number of failed alerts.
        """

        return (
            self.db.query(Alert)
            .filter(
                Alert.status == AlertStatus.FAILED,
                Alert.is_resolved.is_(False),
            )
            .count()
        )

    # =========================================================
    # COUNT READ
    # =========================================================

    def count_read(
        self,
    ) -> int:
        """
        Return the number of read alerts.
        """

        return (
            self.db.query(Alert)
            .filter(
                Alert.status == AlertStatus.READ,
                Alert.is_resolved.is_(False),
            )
            .count()
        )

    # =========================================================
    # COUNT RESOLVED
    # =========================================================

    def count_resolved(
        self,
    ) -> int:
        """
        Return the number of resolved alerts.
        """

        return (
            self.db.query(Alert)
            .filter(
                Alert.is_resolved.is_(True),
            )
            .count()
        )

    # =========================================================
    # UPDATE
    # =========================================================

    def update(
        self,
        alert: Alert,
    ) -> Alert:
        """
        Update an existing alert.
        """

        self.db.commit()
        self.db.refresh(alert)

        return alert

    # =========================================================
    # DELETE
    # =========================================================

    def delete(
        self,
        alert: Alert,
    ) -> None:
        """
        Permanently delete an alert.
        """

        self.db.delete(alert)
        self.db.commit()
        