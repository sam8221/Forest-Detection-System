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
    - Queue email notifications.
    - Resolve alerts.
    - Mark alerts as read.

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
from app.repositories.alert_repository import (
    AlertRepository,
)


class AlertService:
    """
    Handles alert creation and notification.
    """

    def __init__(
        self,
        db: Session,
    ):
        """
        Initialize the alert service.
        """

        self.db = db

        self.repository = AlertRepository(db)

    # ---------------------------------------------------------
    # Create Alert
    # ---------------------------------------------------------
    def create_alert(
        self,
        detection: Detection,
    ) -> Alert:
        """
        Create a new alert
        from a verified detection.
        """

        title = (
            f"Deforestation Detected - "
            f"{detection.forest_area.name}"
        )

        message = (
            f"Potential deforestation detected in "
            f"{detection.forest_area.name}.\n"
            f"Estimated affected area: "
            f"{detection.detected_area_hectares:.2f} hectares.\n"
            f"Confidence Score: "
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

        return self.repository.create(
            alert,
        )

    # ---------------------------------------------------------
    # Create Alert Recipients
    # ---------------------------------------------------------
    def create_alert_recipients(
        self,
        alert: Alert,
    ) -> None:
        """
        Create recipients for every
        active Forestry Officer.
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

    # ---------------------------------------------------------
    # Queue Email Notifications
    # ---------------------------------------------------------
    def queue_email_notifications(
        self,
        alert: Alert,
    ) -> None:
        """
        Queue email notifications
        for all recipients.
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
            # ---------------------------------------------------------
    # Mark Alert as Read
    # ---------------------------------------------------------
    def mark_alert_as_read(
        self,
        recipient: AlertRecipient,
    ) -> AlertRecipient:
        """
        Mark an alert as read by a recipient.
        """

        recipient.is_read = True

        recipient.read_at = datetime.now(
            UTC,
        )

        self.db.commit()
        self.db.refresh(recipient)

        return recipient

    # ---------------------------------------------------------
    # Resolve Alert
    # ---------------------------------------------------------
    def resolve_alert(
        self,
        alert: Alert,
        notes: str | None = None,
    ) -> Alert:
        """
        Resolve an alert.
        """

        alert.is_resolved = True

        alert.status = AlertStatus.READ

        alert.resolution_notes = notes

        alert.resolved_at = datetime.now(
            UTC,
        )

        alert = self.repository.update(
            alert,
        )

        return alert

    # ---------------------------------------------------------
    # Process Detection
    # ---------------------------------------------------------
    def process_detection(
        self,
        detection: Detection,
    ) -> Alert:
        """
        Execute the complete alert workflow.

        Workflow
        --------
        1. Create alert.
        2. Create recipients.
        3. Queue email notifications.
        """

        alert = self.create_alert(
            detection,
        )

        self.create_alert_recipients(
            alert,
        )

        self.queue_email_notifications(
            alert,
        )

        return alert

    # ---------------------------------------------------------
    # Mark Alert as Sent
    # ---------------------------------------------------------
    def mark_as_sent(
        self,
        alert: Alert,
    ) -> Alert:
        """
        Mark an alert as successfully sent.
        """

        alert.status = AlertStatus.SENT

        alert.sent_at = datetime.now(
            UTC,
        )

        return self.repository.update(
            alert,
        )

    # ---------------------------------------------------------
    # Mark Alert as Failed
    # ---------------------------------------------------------
    def mark_as_failed(
        self,
        alert: Alert,
    ) -> Alert:
        """
        Mark an alert as failed.
        """

        alert.status = AlertStatus.FAILED

        return self.repository.update(
            alert,
        )