"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Email Scheduler

Purpose:
    Automatically processes pending email notifications.

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

from app.database.session import SessionLocal
from app.services.email_worker import EmailWorker


logger = logging.getLogger(__name__)


class EmailScheduler:
    """
    Runs the email worker automatically in the background.
    """

    def __init__(self, interval_seconds: int = 30) -> None:
        self.interval_seconds = interval_seconds
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def _run(self) -> None:
        """
        Process the email queue periodically.
        """

        while not self._stop_event.is_set():

            db = SessionLocal()

            try:
                EmailWorker(db).run_once()

            except Exception:
                # One bad cycle must not kill the thread.
                # Logged rather than printed so the entry
                # carries a timestamp and the traceback,
                # which a bare message did not.
                logger.exception(
                    "The email worker cycle failed."
                )

            finally:
                db.close()

            self._stop_event.wait(
                self.interval_seconds
            )

    def start(self) -> None:
        """
        Start the background email scheduler.
        """

        if (
            self._thread is not None
            and self._thread.is_alive()
        ):
            return

        self._stop_event.clear()

        self._thread = threading.Thread(
            target=self._run,
            name="forestwatch-email-worker",
            daemon=True,
        )

        self._thread.start()

        logger.info(
            "Email scheduler started (interval=%ss).",
            self.interval_seconds,
        )

    def stop(self) -> None:
        """
        Stop the background email scheduler.
        """

        self._stop_event.set()

        if self._thread is not None:
            self._thread.join(
                timeout=5
            )

        logger.info(
            "Email scheduler stopped."
        )