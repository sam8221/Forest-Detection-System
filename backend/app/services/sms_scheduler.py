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
from app.services.sms_service import (
    SmsService,
    SmsSystemStatus,
    sms_system_status,
)
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

        # The last state written to the log, so that a
        # recurring check reports a change rather than
        # repeating itself every cycle.
        self._last_reported_status: SmsSystemStatus | None = None

    def _run(self) -> None:
        """
        Process the SMS queue periodically.

        The provider check happens here, on the first cycle,
        rather than in start(). start() is called while the
        application is still starting up, and a provider
        that does not answer would hold the whole API behind
        a network timeout. In this thread the same check
        costs nothing anybody is waiting for.
        """

        self._report_provider_status()

        while not self._stop_event.is_set():

            # Refreshed here rather than only at startup, for
            # two reasons. An administrator who corrects a
            # key sees the status recover without restarting
            # the application. And because this thread keeps
            # the remembered answer fresh, the Settings page
            # is served from it and no officer ever waits on
            # a request to the provider.
            self._refresh_provider_status()

            db = SessionLocal()

            try:
                result = SmsWorker(db).run_once()

                if result.total:
                    logger.info(
                        "SMS cycle: %s.",
                        result.describe(),
                    )

                else:
                    # Nothing to do is the ordinary case,
                    # every thirty seconds. At DEBUG so an
                    # administrator can confirm the thread
                    # is alive without an INFO console
                    # filling with empty cycles.
                    logger.debug(
                        "SMS cycle: queue empty."
                    )

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

    def _report_configuration(self) -> None:
        """
        Write the resolved SMS configuration to the console.

        Logged before the credential check, because when the
        check fails this is what says why. "The supplied
        authentication is invalid" is the same sentence
        whether no key was loaded, a key was loaded under
        the wrong name, or a good key was paired with the
        wrong username, and on its own it distinguishes
        none of them.

        Contains the username, the environment, the endpoint
        and whether a key was loaded. It does not contain
        the key.
        """

        try:
            service = SmsService()

            logger.info(
                "SMS configuration: %s",
                service.configuration_summary(),
            )

            for warning in service.configuration_warnings():
                logger.warning(
                    "SMS configuration: %s",
                    warning,
                )

        except Exception:
            logger.exception(
                "The SMS configuration could not be "
                "described. The queue will still be "
                "processed."
            )

    def _refresh_provider_status(self) -> None:
        """
        Keep the remembered provider answer current.

        Asks without forcing, so the provider is contacted
        only when the remembered answer has expired. A
        change is reported; an unchanged state is not, so a
        console does not fill with the same line every
        minute.
        """

        try:
            check = sms_system_status()

        except Exception:
            logger.exception(
                "The SMS provider status could not be "
                "refreshed. The queue will still be "
                "processed."
            )

            return

        if check.status is self._last_reported_status:
            return

        self._last_reported_status = check.status

        if check.status is SmsSystemStatus.ACTIVE:
            logger.info(
                "SMS is active again: %s",
                check.detail,
            )

        else:
            logger.error(
                "SMS cannot be sent (%s): %s",
                check.status.value,
                check.detail,
            )

    def _report_provider_status(self) -> None:
        """
        Log whether SMS can actually be sent.

        Written to the console at startup because this is
        the question an administrator has when they deploy
        the system, and until now the only way to find the
        answer was for an officer to press Send Test SMS and
        read the error.

        A fault is logged as an error rather than a warning:
        SMS switched on but unable to send means alerts the
        system accepted responsibility for are not reaching
        anybody, which is not a condition to leave in the
        quieter half of a log.
        """

        self._report_configuration()

        try:
            check = sms_system_status(force=True)

        except Exception:
            # Reporting the status must never be the reason
            # the queue stops being processed.
            logger.exception(
                "The SMS provider status could not be "
                "determined. The queue will still be "
                "processed."
            )

            return

        self._last_reported_status = check.status

        if check.status is SmsSystemStatus.ACTIVE:
            logger.info(
                "SMS is active: %s",
                check.detail,
            )

            return

        logger.error(
            "SMS cannot be sent (%s): %s",
            check.status.value,
            check.detail,
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
            "SMS scheduler started (interval=%ss). "
            "Checking the provider credentials.",
            self.interval_seconds,
        )

    def stop(self) -> None:
        """
        Stop the background SMS scheduler.

        Reports whether the thread actually ended. A worker
        still running after a shutdown holds a database
        session, and a stop that silently timed out would
        look identical to a clean one.
        """

        if self._thread is None:
            return

        self._stop_event.set()

        self._thread.join(
            timeout=5
        )

        if self._thread.is_alive():
            logger.warning(
                "The SMS scheduler did not stop within 5 "
                "seconds. It is a daemon thread and will "
                "end with the process."
            )

        else:
            logger.info(
                "SMS scheduler stopped."
            )

        self._thread = None
