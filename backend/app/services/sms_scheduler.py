"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: SMS Scheduler

Purpose:
    Automatically processes pending alert SMS messages.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia
===========================================================
"""

from __future__ import annotations

import logging
import threading

from app.core.config import get_settings
from app.database.session import SessionLocal
from app.services.sms_worker import SmsWorker


logger = logging.getLogger(__name__)


class SmsScheduler:
    """
    Runs the SMS worker automatically in the background.

    Mirrors EmailScheduler: a daemon thread in the
    application process, not a separate deployed service.
    That keeps the deployment to one process, which is the
    same reason this project does not use Celery and Redis.

    The loop exits immediately when SMS is disabled, so the
    thread costs nothing on an installation that has not
    configured a provider.
    """

    def __init__(self, interval_seconds: int = 30) -> None:
        self.interval_seconds = interval_seconds
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def _run(self) -> None:
        """
        Process the SMS queue periodically.
        """

        while not self._stop_event.is_set():

            db = SessionLocal()

            try:
                SmsWorker(db).run_once()

            except Exception:
                # One bad cycle must not kill the thread:
                # the queue would then stay unprocessed
                # silently until the application restarted.
                logger.exception(
                    "The SMS worker cycle failed."
                )

            finally:
                db.close()

            self._stop_event.wait(
                self.interval_seconds
            )

    def start(self) -> None:
        """
        Start the background SMS scheduler.

        Does nothing when SMS is disabled, so enabling the
        feature is a configuration change rather than a code
        change, and a system with no provider configured
        runs no SMS thread at all.
        """

        if not get_settings().sms_enabled:
            logger.info(
                "SMS notifications are disabled "
                "(SMS_ENABLED), so the SMS scheduler was "
                "not started."
            )

            return

        if (
            self._thread is not None
            and self._thread.is_alive()
        ):
            return

        self._stop_event.clear()

        self._thread = threading.Thread(
            target=self._run,
            name="forestwatch-sms-worker",
            daemon=True,
        )

        self._thread.start()

        logger.info(
            "SMS scheduler started (interval=%ss).",
            self.interval_seconds,
        )

    def stop(self) -> None:
        """
        Stop the background SMS scheduler.
        """

        self._stop_event.set()

        if self._thread is not None:
            self._thread.join(
                timeout=5
            )

            self._thread = None
