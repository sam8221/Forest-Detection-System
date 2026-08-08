"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Alert Service

Purpose:
    Handles creation and management of alerts.

Responsibilities:
    - Create alerts.
    - Assign recipients.
    - Queue emails.
    - Resolve alerts.
    - Mark alerts as read.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia
===========================================================
"""

from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.alert_recipient import AlertRecipient
from app.models.detection import Detection
from app.models.email_queue import EmailQueue
from app.models.enums import (
    AlertStatus,
    AlertType,
    PriorityLevel,
    UserRole,
)
from app.models.user import User


class AlertService:
    """
    Handles alert creation and notification.
    """

    def __init__(self, db: Session):
        self.db = db

    def create_alert(
        self,
        detection: Detection,
    ) -> Alert:
        """
        Create a new alert from a detection.
        """

        title = (
            f"Deforestation Detected - "
            f"{detection.forest_area.name}"
        )

        message = (
            f"Potential deforestation detected in "
            f"{detection.forest_area.name}.\n"
            f"Estimated area affected: "
            f"{detection.detected_area_hectares:.2f} hectares.\n"
            f"Confidence: "
            f"{detection.confidence_score:.2f}%."
        )

        alert = Alert(
            detection_id=detection.id,
            title=title,
            message=message,
            alert_type=AlertType.EMAIL,
            priority=PriorityLevel.HIGH,
            status=AlertStatus.PENDING,
        )

        self.db.add(alert)
        self.db.commit()
        self.db.refresh(alert)

        return alert

    def create_alert_recipients(
        self,
        alert: Alert,
    ) -> None:
        """
        Create recipients for every active
        Forestry Officer.
        """

        officers = (
            self.db.query(User)
            .filter(
                User.role == UserRole.FORESTRY_OFFICER,
                User.is_active.is_(True),
            )
            .all()
        )

        for officer in officers:

            recipient = AlertRecipient(
                alert_id=alert.id,
                user_id=officer.id,
            )

            self.db.add(recipient)

        self.db.commit()

        def queue_email_notifications(
        self,
        alert: Alert,
    ) -> None:
        """
        Create email queue records for all
        alert recipients.
        """

        recipients = (
            self.db.query(AlertRecipient)
            .filter(
                AlertRecipient.alert_id == alert.id,
            )
            .all()
        )

        for recipient in recipients:

            user = recipient.user

            email = EmailQueue(
                alert_id=alert.id,
                recipient_email=user.email,
                recipient_name=user.full_name,
                subject=alert.title,
                body=alert.message,
            )

            self.db.add(email)

        self.db.commit()

    def mark_alert_as_read(
        self,
        recipient: AlertRecipient,
    ) -> None:
        """
        Mark an alert as read.
        """

        from datetime import datetime, UTC

        recipient.is_read = True
        recipient.read_at = datetime.now(UTC)

        self.db.commit()

    def resolve_alert(
        self,
        alert: Alert,
        notes: str | None = None,
    ) -> None:
        """
        Mark an alert as resolved.
        """

        from datetime import datetime, UTC

        alert.is_resolved = True
        alert.resolution_notes = notes
        alert.status = AlertStatus.READ
        alert.resolved_at = datetime.now(UTC)

        self.db.commit()

    def process_detection(
        self,
        detection: Detection,
    ) -> Alert:
        """
        Complete workflow after a verified
        detection.

        1. Create Alert
        2. Create Alert Recipients
        3. Queue Email Notifications
        """

        alert = self.create_alert(detection)

        self.create_alert_recipients(alert)

        self.queue_email_notifications(alert)

        return alert