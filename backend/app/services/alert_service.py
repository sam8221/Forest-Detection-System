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

import logging
from datetime import UTC, datetime

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.alert_recipient import AlertRecipient
from app.models.detection import Detection
from app.models.district import District
from app.models.email_queue import EmailQueue
from app.core.config import get_settings
from app.models.enums import (
    AlertStatus,
    AlertType,
    EmailQueueStatus,
    PriorityLevel,
    SmsQueueStatus,
)
from app.models.forest_area import ForestArea
from app.models.sms_queue import SmsQueue
from app.repositories.alert_repository import AlertRepository
from app.services.sms_service import (
    build_alert_sms,
    meets_priority_threshold,
    normalise_msisdn,
)
from app.services.sms_recipients import (
    eligible_sms_officers_query,
    sms_phone_skip_reason,
    sms_recipient_authorization_reason,
)


logger = logging.getLogger(__name__)


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

        officers = eligible_sms_officers_query(
            self.db,
            forest_area,
            district,
        ).all()

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
    # QUEUE SMS
    # =========================================================

    def queue_sms_notifications(
        self,
        alert: Alert,
    ) -> None:
        """
        Queue alert SMS messages for the alert's recipients.

        Args:
            alert:
                The alert to notify about. Its recipients
                must already exist; this method does not
                create them.

        Why this walks AlertRecipient rather than querying
        officers again:

            create_alert_recipients has already decided who
            covers this forest area, applying the district
            and province rules of FR-04. Repeating that
            query here would be a second copy of the
            jurisdiction logic, free to drift from the first,
            and SMS would then reach officers email did not.

        Why not every alert gets one:

            SMS interrupts an officer and costs money per
            message, so it is reserved for alerts serious
            enough to warrant a field response. The floor is
            configuration (SMS_MIN_PRIORITY, default HIGH),
            not a literal. Email still goes out for every
            alert, so nothing is lost below the threshold.

        Skips are recorded in sms_queue with a controlled,
        non-sensitive reason. The recipient's number is never
        included in the log message. A unique database index
        and INSERT ... ON CONFLICT DO NOTHING make queueing
        idempotent across repeated or concurrent alert runs.
        """

        settings = get_settings()

        if not settings.sms_enabled:
            return

        if not meets_priority_threshold(
            alert.priority,
            settings.sms_min_priority,
        ):
            return

        detection = alert.detection

        if detection is None:
            # Nothing to describe, so nothing is sent. The
            # email already queued still carries the alert.
            return

        forest_area = detection.forest_area

        if forest_area is None or forest_area.district is None:
            logger.warning(
                "SMS recipients skipped for alert_id=%s: "
                "forest area or district is unavailable.",
                alert.id,
            )
            return

        forest_name = (
            forest_area.name
            if forest_area is not None
            else f"Forest Area {detection.forest_area_id}"
        )

        district_name = (
            forest_area.district.name
            if forest_area is not None
            and forest_area.district is not None
            else None
        )

        message = build_alert_sms(
            forest_name=forest_name,
            district_name=district_name,
            detected_area_hectares=(
                detection.detected_area_hectares
            ),
            priority=alert.priority,
            detection_id=detection.id,
        )

        recipients = (
            self.db.query(AlertRecipient)
            .filter(
                AlertRecipient.alert_id == alert.id,
            )
            .all()
        )

        existing_rows = (
            self.db.query(SmsQueue)
            .filter(SmsQueue.alert_id == alert.id)
            .all()
        )

        existing_user_ids = {
            row.recipient_user_id
            for row in existing_rows
            if row.recipient_user_id is not None
        }
        existing_phones = {
            row.recipient_phone
            for row in existing_rows
            if row.recipient_phone is not None
        }

        queue_values = []

        for recipient in recipients:

            user = recipient.user

            if user is None:
                continue

            authorization_reason = sms_recipient_authorization_reason(
                user,
                forest_area,
            )

            if authorization_reason is not None:
                logger.info(
                    "SMS recipient skipped alert_id=%s user_id=%s "
                    "reason=%s",
                    alert.id,
                    user.id,
                    authorization_reason,
                )
                continue

            if user.id in existing_user_ids:
                continue

            # A number is normalised before it is compared
            # or stored, so one handset written two ways
            # cannot become two messages.
            phone = normalise_msisdn(user.phone_number)

            skip_reason = sms_phone_skip_reason(user.phone_number)

            if phone is not None and phone in existing_phones:
                logger.info(
                    "SMS recipient skipped alert_id=%s user_id=%s "
                    "reason=duplicate_recipient_number",
                    alert.id,
                    user.id,
                )
                continue

            queue_values.append(
                {
                    "alert_id": alert.id,
                    "recipient_phone": (
                        phone if skip_reason is None else None
                    ),
                    "recipient_user_id": user.id,
                    "recipient_name": user.full_name,
                    "message": message,
                    "status": (
                        SmsQueueStatus.SKIPPED
                        if skip_reason is not None
                        else SmsQueueStatus.PENDING
                    ),
                    "skip_reason": skip_reason,
                    "retry_count": 0,
                    "max_retries": 3,
                }
            )

            existing_user_ids.add(user.id)

            if phone is not None:
                existing_phones.add(phone)

            if skip_reason is not None:
                logger.info(
                    "SMS recipient skipped alert_id=%s user_id=%s "
                    "reason=%s",
                    alert.id,
                    user.id,
                    skip_reason,
                )

        if queue_values:
            statement = (
                pg_insert(SmsQueue)
                .values(queue_values)
                .on_conflict_do_nothing()
            )
            self.db.execute(statement)

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
            4. Queue SMS notifications for serious alerts.

        Every step is idempotent, so running this twice for
        one detection produces one alert, one set of
        recipients, one email per recipient and one SMS per
        recipient.
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

        # Queued after email, and deliberately not instead
        # of it: SMS is an additional channel for alerts
        # warranting a field response, not a replacement for
        # the record an officer reads in full.
        self.queue_sms_notifications(
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
