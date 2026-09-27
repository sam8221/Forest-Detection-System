"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Alert Service

Purpose:
    Handles creation and management of deforestation alerts.

Responsibilities:
    - Create decision-support alerts.
    - Determine alert priority.
    - Assign active Forestry Officers.
    - Queue email notifications.
    - Prevent duplicate alerts.
    - Mark alerts as sent or failed.
    - Mark recipient alerts as read.
    - Resolve alerts.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Version:
    1.1.0
===========================================================
"""

from datetime import UTC, datetime

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.alert_recipient import AlertRecipient
from app.models.detection import Detection
from app.models.district import District
from app.models.email_queue import EmailQueue
from app.models.enums import (
    AlertStatus,
    AlertType,
    EmailQueueStatus,
    PriorityLevel,
    UserRole,
)
from app.models.forest_area import ForestArea
from app.models.user import User
from app.repositories.alert_repository import AlertRepository


class AlertService:
    """
    Handles deforestation alerts and notifications.
    """

    def __init__(
        self,
        db: Session,
    ):
        self.db = db
        self.repository = AlertRepository(db)

    # =========================================================
    # DETERMINE PRIORITY
    # =========================================================

    def determine_priority(
        self,
        vegetation_loss_percentage: float,
    ) -> PriorityLevel:
        """
        Determine alert priority from vegetation loss.

        Rules:
            < 30%  -> LOW
            30-50% -> MEDIUM
            50-70% -> HIGH
            >=70%  -> CRITICAL

        These thresholds are used for alert prioritisation.
        """

        if vegetation_loss_percentage >= 70.0:
            return PriorityLevel.CRITICAL

        if vegetation_loss_percentage >= 50.0:
            return PriorityLevel.HIGH

        if vegetation_loss_percentage >= 30.0:
            return PriorityLevel.MEDIUM

        return PriorityLevel.LOW

    # =========================================================
    # DETERMINE SEVERITY LABEL
    # =========================================================

    def determine_severity(
        self,
        vegetation_loss_percentage: float,
    ) -> str:
        """
        Convert vegetation loss into a readable severity label.
        """

        if vegetation_loss_percentage >= 50.0:
            return "SEVERE"

        if vegetation_loss_percentage >= 40.0:
            return "MODERATE"

        return "LOW"

    # =========================================================
    # CREATE ALERT
    # =========================================================

    def create_alert(
        self,
        detection: Detection,
    ) -> Alert:
        """
        Create an alert from a verified detection.

        Prevents duplicate alerts for the same detection.
        """

        existing_alert = (
            self.db.query(Alert)
            .filter(
                Alert.detection_id == detection.id,
            )
            .first()
        )

        if existing_alert is not None:
            return existing_alert

        priority = self.determine_priority(
            detection.vegetation_loss_percentage,
        )

        severity = self.determine_severity(
            detection.vegetation_loss_percentage,
        )

        forest_name = (
            detection.forest_area.name
            if detection.forest_area
            else f"Forest Area {detection.forest_area_id}"
        )

        # -----------------------------------------------------
        # Where the clearing is
        #
        # An officer receiving this has to decide whether to
        # travel, so the district matters as much as the
        # measurements.
        # -----------------------------------------------------

        district_name = None

        if (
            detection.forest_area is not None
            and detection.forest_area.district is not None
        ):
            district_name = (
                detection.forest_area.district.name
            )

        location_line = (
            f"District: {district_name}\n"
            if district_name
            else ""
        )

        title = (
            f"{priority.value} Deforestation Alert - "
            f"{forest_name}"
        )

        # -----------------------------------------------------
        # What this alert claims
        #
        # The alert is raised when the analysis confirms a
        # clearing, BEFORE any officer has looked at it. The
        # detection is PENDING at this point, so the message
        # must ask for review rather than report a conclusion.
        #
        # Saying it had already been verified would invert
        # the workflow this system exists to support, and
        # would present an automated measurement as a
        # confirmed finding.
        # -----------------------------------------------------

        message = (
            "ForestWatch Zambia Deforestation Alert\n"
            "\n"
            "Possible deforestation has been detected from "
            "Sentinel-2 imagery and is awaiting review.\n"
            "\n"
            f"Forest Area: {forest_name}\n"
            f"{location_line}"
            f"Detection ID: {detection.id}\n"
            f"Severity: {severity}\n"
            f"Priority: {priority.value}\n"
            f"Affected Area: "
            f"{detection.detected_area_hectares:.2f} hectares\n"
            f"Confidence: "
            f"{detection.confidence_score:.2f}%\n"
            f"NDVI Before: "
            f"{detection.ndvi_before:.6f}\n"
            f"NDVI After: "
            f"{detection.ndvi_after:.6f}\n"
            f"Vegetation Loss: "
            f"{detection.vegetation_loss_percentage:.2f}%\n"
            "\n"
            "This is an automated measurement, not a "
            "confirmed finding. Sign in to ForestWatch "
            "Zambia to view the affected area on the map "
            "and record your assessment.\n"
            "\n"
            "The confidence figure combines how much of the "
            "area could be measured with the severity of "
            "the vegetation decline. It is not a "
            "probability."
        )

        alert = Alert(
            detection_id=detection.id,
            title=title,
            message=message,
            alert_type=AlertType.EMAIL,
            priority=priority,
            status=AlertStatus.PENDING,
        )

        return self.repository.create(alert)

    # =========================================================
    # CREATE RECIPIENTS
    # =========================================================

    def create_alert_recipients(
        self,
        alert: Alert,
    ) -> None:
        """
        Assign the alert to the active Forestry Officers
        whose jurisdiction covers the affected forest area.

        A district officer receives the alert when the forest
        area lies in their district; a provincial officer
        receives it when the area lies anywhere in their
        province.

        Administrators are deliberately excluded. They
        provision accounts and configure thresholds but hold
        no operational alert duties, which is what keeps the
        audit trail independent of the officers it records.

        Existing recipients are not duplicated.
        """

        # -----------------------------------------------------
        # Locate the affected forest area
        # -----------------------------------------------------

        forest_area = (
            self.db.query(ForestArea)
            .join(
                Detection,
                Detection.forest_area_id
                == ForestArea.id,
            )
            .filter(
                Detection.id
                == alert.detection_id,
            )
            .first()
        )

        if forest_area is None:
            raise ValueError(
                "Alert is not linked to a forest area, "
                "so its recipients cannot be determined."
            )

        # -----------------------------------------------------
        # Resolve the province containing that district
        # -----------------------------------------------------

        district = (
            self.db.query(District)
            .filter(
                District.id
                == forest_area.district_id,
            )
            .first()
        )

        if district is None:
            raise ValueError(
                "Forest area is not linked to a district, "
                "so its recipients cannot be determined."
            )

        # -----------------------------------------------------
        # Select officers whose jurisdiction covers the area
        # -----------------------------------------------------

        officers = (
            self.db.query(User)
            .filter(
                User.is_active.is_(True),

                or_(
                    and_(
                        User.role
                        == UserRole.DISTRICT_FORESTRY_OFFICER,

                        User.district_id
                        == forest_area.district_id,
                    ),

                    and_(
                        User.role
                        == UserRole.PROVINCIAL_FORESTRY_OFFICER,

                        User.province_id
                        == district.province_id,
                    ),
                ),
            )
            .all()
        )

        for officer in officers:

            existing = (
                self.db.query(AlertRecipient)
                .filter(
                    AlertRecipient.alert_id == alert.id,
                    AlertRecipient.user_id == officer.id,
                )
                .first()
            )

            if existing is not None:
                continue

            recipient = AlertRecipient(
                alert_id=alert.id,
                user_id=officer.id,
                is_read=False,
            )

            self.db.add(recipient)

        self.db.commit()

    # =========================================================
    # QUEUE EMAIL
    # =========================================================

    def queue_email_notifications(
        self,
        alert: Alert,
    ) -> None:
        """
        Queue email notifications for alert recipients.

        Prevents duplicate pending email messages.
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

            if not user or not user.email:
                continue

            existing_email = (
                self.db.query(EmailQueue)
                .filter(
                    EmailQueue.alert_id == alert.id,
                    EmailQueue.recipient_email == user.email,
                    EmailQueue.status == EmailQueueStatus.PENDING,
                )
                .first()
            )

            if existing_email is not None:
                continue

            email = EmailQueue(
                alert_id=alert.id,
                recipient_email=user.email,
                recipient_name=user.full_name,
                subject=alert.title,
                body=alert.message,
                status=EmailQueueStatus.PENDING,
            )

            self.db.add(email)

        self.db.commit()

    # =========================================================
    # PROCESS DETECTION
    # =========================================================

    def process_detection(
        self,
        detection: Detection,
    ) -> Alert:
        """
        Execute the complete alert workflow.

        Workflow:
            1. Create or retrieve alert.
            2. Assign Forestry Officers.
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

    # =========================================================
    # MARK ALERT AS SENT
    # =========================================================

    def mark_as_sent(
        self,
        alert: Alert,
    ) -> Alert:
        """
        Mark alert as successfully sent.
        """

        alert.status = AlertStatus.SENT
        alert.sent_at = datetime.now(UTC)

        return self.repository.update(alert)

    # =========================================================
    # MARK ALERT AS FAILED
    # =========================================================

    def mark_as_failed(
        self,
        alert: Alert,
    ) -> Alert:
        """
        Mark alert as failed.
        """

        alert.status = AlertStatus.FAILED

        return self.repository.update(alert)

    # =========================================================
    # MARK RECIPIENT AS READ
    # =========================================================

    def mark_alert_as_read(
        self,
        recipient: AlertRecipient,
    ) -> AlertRecipient:
        """
        Mark an alert as read by a recipient.
        """

        recipient.is_read = True
        recipient.read_at = datetime.now(UTC)

        self.db.commit()
        self.db.refresh(recipient)

        return recipient

    # =========================================================
    # RESOLVE ALERT
    # =========================================================

    def resolve_alert(
        self,
        alert: Alert,
        notes: str | None = None,
    ) -> Alert:
        """
        Resolve an alert.
        """

        alert.is_resolved = True
        alert.status = AlertStatus.RESOLVED
        alert.resolution_notes = notes
        alert.resolved_at = datetime.now(UTC)

        return self.repository.update(alert)