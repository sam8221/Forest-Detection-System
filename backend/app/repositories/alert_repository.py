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
- Count alerts for dashboard statistics.

Author:
Samuel Bikiloni

Project:
Web-Based Deforestation Detection and Alert System
Using Sentinel-2 Imagery in the Copperbelt, Zambia
"""

from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.enums import AlertStatus


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
        