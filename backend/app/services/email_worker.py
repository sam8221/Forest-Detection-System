"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Email Worker

Purpose:
    Processes queued emails and sends them automatically.

Responsibilities:
    - Read pending emails.
    - Send emails.
    - Update queue status.
    - Retry failed emails.

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

from app.models.email_queue import EmailQueue
from app.models.enums import EmailQueueStatus
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

    # ---------------------------------------------------------
    # Process Email Queue
    # ---------------------------------------------------------
    def process_queue(
        self,
    ) -> None:
        """
        Process all pending emails.
        """

        pending_emails = (
            self.db.query(EmailQueue)
            .filter(
                EmailQueue.status ==
                EmailQueueStatus.PENDING
            )
            .order_by(
                EmailQueue.created_at.asc(),
            )
            .all()
        )

        for email in pending_emails:

            try:

                # -------------------------------------
                # Send Email
                # -------------------------------------
                self.email_service.send_email(
                    recipient_email=email.recipient_email,
                    subject=email.subject,
                    html_body=email.body,
                )

                # -------------------------------------
                # Update Queue
                # -------------------------------------
                email.status = EmailQueueStatus.SENT

                email.sent_at = datetime.now(
                    UTC,
                )

                self.db.commit()

                self.db.refresh(email)

            except Exception as ex:

                # -------------------------------------
                # Retry
                # -------------------------------------
                email.retry_count += 1

                email.last_error = str(ex)

                if (
                    email.retry_count
                    >= email.max_retries
                ):

                    email.status = (
                        EmailQueueStatus.FAILED
                    )

                self.db.commit()

                self.db.refresh(email)

    # ---------------------------------------------------------
    # Run Worker Once
    # ---------------------------------------------------------
    def run_once(
        self,
    ) -> None:
        """
        Execute one email processing cycle.

        Can be called by:

        • APScheduler
        • Celery
        • FastAPI BackgroundTasks
        • Cron Jobs
        """

        self.process_queue()