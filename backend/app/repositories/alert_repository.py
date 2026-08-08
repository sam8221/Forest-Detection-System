"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Alert Repository

Purpose:
    Provides database operations for alerts.

Responsibilities:
    - Create alerts.
    - Retrieve alerts.
    - Update alerts.
    - Delete alerts.
    - Retrieve alerts by status.
    - Count alerts for dashboard statistics.

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

    # ---------------------------------------------------------
    # Create
    # ---------------------------------------------------------
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

    # ---------------------------------------------------------
    # Get by ID
    # ---------------------------------------------------------
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

    # ---------------------------------------------------------
    # Get All
    # ---------------------------------------------------------
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

    # ---------------------------------------------------------
    # Get Recent
    # ---------------------------------------------------------
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

    # ---------------------------------------------------------
    # Get by Status
    # ---------------------------------------------------------
    def get_by_status(
        self,
        status: AlertStatus,
    ) -> list[Alert]:
        """
        Retrieve alerts by status.
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

    # ---------------------------------------------------------
    # Get Pending
    # ---------------------------------------------------------
    def get_pending(
        self,
    ) -> list[Alert]:
        return self.get_by_status(
            AlertStatus.PENDING,
        )

    # ---------------------------------------------------------
    # Get Sent
    # ---------------------------------------------------------
    def get_sent(
        self,
    ) -> list[Alert]:
        return self.get_by_status(
            AlertStatus.SENT,
        )

    # ---------------------------------------------------------
    # Get Failed
    # ---------------------------------------------------------
    def get_failed(
        self,
    ) -> list[Alert]:
        return self.get_by_status(
            AlertStatus.FAILED,
        )

    # ---------------------------------------------------------
    # Get Read
    # ---------------------------------------------------------
    def get_read(
        self,
    ) -> list[Alert]:
        return self.get_by_status(
            AlertStatus.READ,
        )

    # ---------------------------------------------------------
    # Count All
    # ---------------------------------------------------------
    def count(
        self,
    ) -> int:
        """
        Return total number of alerts.
        """

        return (
            self.db.query(Alert)
            .count()
        )

    # ---------------------------------------------------------
    # Count Pending
    # ---------------------------------------------------------
    def count_pending(
        self,
    ) -> int:
        return (
            self.db.query(Alert)
            .filter(
                Alert.status == AlertStatus.PENDING,
            )
            .count()
        )

    # ---------------------------------------------------------
    # Count Sent
    # ---------------------------------------------------------
    def count_sent(
        self,
    ) -> int:
        return (
            self.db.query(Alert)
            .filter(
                Alert.status == AlertStatus.SENT,
            )
            .count()
        )

    # ---------------------------------------------------------
    # Count Failed
    # ---------------------------------------------------------
    def count_failed(
        self,
    ) -> int:
        return (
            self.db.query(Alert)
            .filter(
                Alert.status == AlertStatus.FAILED,
            )
            .count()
        )

    # ---------------------------------------------------------
    # Count Read
    # ---------------------------------------------------------
    def count_read(
        self,
    ) -> int:
        return (
            self.db.query(Alert)
            .filter(
                Alert.status == AlertStatus.READ,
            )
            .count()
        )

    # ---------------------------------------------------------
    # Count Resolved
    # ---------------------------------------------------------
    def count_resolved(
        self,
    ) -> int:
        return (
            self.db.query(Alert)
            .filter(
                Alert.is_resolved.is_(True),
            )
            .count()
        )

    # ---------------------------------------------------------
    # Update
    # ---------------------------------------------------------
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

    # ---------------------------------------------------------
    # Delete
    # ---------------------------------------------------------
    def delete(
        self,
        alert: Alert,
    ) -> None:
        """
        Permanently delete an alert.
        """

        self.db.delete(alert)
        self.db.commit()