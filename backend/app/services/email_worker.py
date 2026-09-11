"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Email Worker

Purpose:
    Processes queued deforestation alert emails.

Responsibilities:
    - Read pending emails.
    - Send emails through SMTP.
    - Mark successfully sent emails as SENT.
    - Mark the related alert as SENT.
    - Retry failed emails.
    - Mark alerts as FAILED after maximum retries.

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

from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.email_queue import EmailQueue
from app.models.enums import (
    AlertStatus,
    EmailQueueStatus,
)
from app.services.email_service import EmailService


class EmailWorker:
    """
    Processes pending emails in the email queue.
    """

    def __init__(
        self,
        db: Session,
    ):
        """
        Initialize the email worker.
        """

        self.db = db
        self.email_service = EmailService()

    # =========================================================
    # PROCESS EMAIL QUEUE
    # =========================================================

    def process_queue(self) -> None:
        """
        Process all pending emails.

        Successful email:
            EmailQueue -> SENT
            Alert -> SENT

        Failed email:
            retry_count increases.

        Maximum retries reached:
            EmailQueue -> FAILED
            Alert -> FAILED
        """

        pending_emails = (
            self.db.query(EmailQueue)
            .filter(
                EmailQueue.status
                == EmailQueueStatus.PENDING
            )
            .order_by(
                EmailQueue.created_at.asc(),
            )
            .all()
        )

        for email in pending_emails:

            try:
                # -------------------------------------------------
                # Send email through SMTP
                # -------------------------------------------------

                self.email_service.send_email(
                    recipient_email=email.recipient_email,
                    subject=email.subject,
                    html_body=email.body,
                )

                # -------------------------------------------------
                # Mark email as sent
                # -------------------------------------------------

                email.status = EmailQueueStatus.SENT

                email.sent_at = datetime.now(UTC)

                email.last_error = None

                # -------------------------------------------------
                # Update related alert
                # -------------------------------------------------

                alert = (
                    self.db.query(Alert)
                    .filter(
                        Alert.id == email.alert_id,
                    )
                    .first()
                )

                if alert is not None:

                    alert.status = AlertStatus.SENT

                    alert.sent_at = datetime.now(UTC)

                self.db.commit()

                self.db.refresh(email)

            except Exception as ex:

                # -------------------------------------------------
                # Record failure
                # -------------------------------------------------

                email.retry_count += 1

                email.last_error = str(ex)

                # -------------------------------------------------
                # Maximum retry limit
                # -------------------------------------------------

                if (
                    email.retry_count
                    >= email.max_retries
                ):

                    email.status = (
                        EmailQueueStatus.FAILED
                    )

                    alert = (
                        self.db.query(Alert)
                        .filter(
                            Alert.id == email.alert_id,
                        )
                        .first()
                    )

                    if alert is not None:
                        alert.status = (
                            AlertStatus.FAILED
                        )

                self.db.commit()

                self.db.refresh(email)

    # =========================================================
    # RUN ONCE
    # =========================================================

    def run_once(self) -> None:
        """
        Execute one email-processing cycle.

        This method can later be called by:

            - FastAPI BackgroundTasks
            - APScheduler
            - Celery
            - Cron
            - Another scheduled worker
        """

        self.process_queue()