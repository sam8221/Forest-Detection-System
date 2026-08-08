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
===========================================================
"""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.email_queue import EmailQueue
from app.models.enums import EmailQueueStatus
from app.services.email_service import EmailService


class EmailWorker:
    """
    Processes pending emails.
    """

    def __init__(self, db: Session):
        self.db = db
        self.email_service = EmailService()

    def process_queue(self) -> None:
        """
        Process every pending email.
        """

        pending_emails = (
            self.db.query(EmailQueue)
            .filter(
                EmailQueue.status == EmailQueueStatus.PENDING
            )
            .all()
        )

        for email in pending_emails:

            try:

                self.email_service.send_email(
                    recipient_email=email.recipient_email,
                    subject=email.subject,
                    html_body=email.body,
                )

                email.status = EmailQueueStatus.SENT
                email.sent_at = datetime.now(UTC)

                self.db.commit()

            except Exception as ex:

                email.retry_count += 1

                email.last_error = str(ex)
                 if email.retry_count >= email.max_retries:

                    email.status = EmailQueueStatus.FAILED

                self.db.commit()

        # Finished processing all pending emails.

    def run_once(self) -> None:
        """
        Execute one email processing cycle.

        This method can be called by:
            - A scheduler
            - FastAPI BackgroundTasks
            - APScheduler
            - Celery
        """

        self.process_queue()               