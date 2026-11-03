"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Tests: What the SMS scheduler reports

What these protect:

    Until now the backend console said nothing about SMS.
    The scheduler reported its start, its shutdown and its
    failures through a logger that had no handler, so an
    administrator deploying the system had no way to learn
    that messages were not being sent other than asking an
    officer to press Send Test SMS and read the error.

    These tests keep the scheduler saying, in the console,
    whether SMS can be sent and what each cycle did.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia
===========================================================
"""

import logging

from app.services import sms_scheduler as sms_scheduler_module
from app.services.sms_scheduler import SmsScheduler
from app.services.sms_service import ProviderCheck, SmsSystemStatus
from app.services.sms_worker import CycleResult


def answering(check, monkeypatch):
    """Make the status check return a fixed answer."""

    monkeypatch.setattr(
        sms_scheduler_module,
        "sms_system_status",
        lambda force=False: check,
    )


# =========================================================
# THE STARTUP REPORT
# =========================================================


def test_a_working_channel_is_reported_as_active(
    monkeypatch,
    caplog,
):
    answering(
        ProviderCheck(
            status=SmsSystemStatus.ACTIVE,
            detail="The SMS provider accepted the credentials.",
            verified_with_provider=True,
        ),
        monkeypatch,
    )

    with caplog.at_level(logging.INFO):
        SmsScheduler()._report_provider_status()

    assert "SMS is active" in caplog.text


def test_a_rejected_credential_is_reported_as_an_error(
    monkeypatch,
    caplog,
):
    """
    Logged as an error, not a warning.

    SMS switched on but unable to send means alerts the
    system accepted responsibility for are reaching nobody.
    That does not belong in the quieter half of a log.
    """

    answering(
        ProviderCheck(
            status=SmsSystemStatus.INVALID_CREDENTIALS,
            detail=(
                "The SMS provider rejected the configured "
                "credentials: The supplied authentication "
                "is invalid"
            ),
            verified_with_provider=True,
        ),
        monkeypatch,
    )

    with caplog.at_level(logging.INFO):
        SmsScheduler()._report_provider_status()

    errors = [
        record
        for record in caplog.records
        if record.levelno >= logging.ERROR
    ]

    assert errors

    # The state and the provider's reason both appear, so
    # the console says which fault it is and why.
    assert "INVALID_CREDENTIALS" in caplog.text

    assert "authentication is invalid" in caplog.text


def test_a_failing_status_check_does_not_stop_the_worker(
    monkeypatch,
    caplog,
):
    """
    Reporting the status must never be the reason the queue
    stops being processed. A message already queued for an
    officer is more important than knowing why.
    """

    def explode(force=False):
        raise RuntimeError("the provider check itself broke")

    monkeypatch.setattr(
        sms_scheduler_module,
        "sms_system_status",
        explode,
    )

    with caplog.at_level(logging.INFO):
        SmsScheduler()._report_provider_status()

    assert "could not be determined" in caplog.text


def test_the_startup_check_is_not_answered_from_the_cache(
    monkeypatch,
):
    """
    An administrator restarting after correcting a key must
    see the current answer.
    """

    asked = []

    monkeypatch.setattr(
        sms_scheduler_module,
        "sms_system_status",
        lambda force=False: (
            asked.append(force),
            ProviderCheck(
                status=SmsSystemStatus.ACTIVE,
                detail="ok",
            ),
        )[1],
    )

    SmsScheduler()._report_provider_status()

    assert asked == [True]


# =========================================================
# WHAT A CYCLE DID
# =========================================================


def test_an_unchanged_status_is_not_repeated_every_cycle(
    monkeypatch,
    caplog,
):
    """
    The refresh runs every thirty seconds. Reporting the
    same fault each time would bury everything else in the
    console.
    """

    answering(
        ProviderCheck(
            status=SmsSystemStatus.INVALID_CREDENTIALS,
            detail="rejected",
            verified_with_provider=True,
        ),
        monkeypatch,
    )

    scheduler = SmsScheduler()

    with caplog.at_level(logging.INFO):
        scheduler._refresh_provider_status()

        scheduler._refresh_provider_status()

        scheduler._refresh_provider_status()

    reported = [
        record
        for record in caplog.records
        if "INVALID_CREDENTIALS" in record.getMessage()
    ]

    assert len(reported) == 1


def test_a_recovery_is_reported(
    monkeypatch,
    caplog,
):
    """
    An administrator who corrects a key sees the system say
    so, without restarting the application.
    """

    scheduler = SmsScheduler()

    answering(
        ProviderCheck(
            status=SmsSystemStatus.INVALID_CREDENTIALS,
            detail="rejected",
        ),
        monkeypatch,
    )

    scheduler._refresh_provider_status()

    answering(
        ProviderCheck(
            status=SmsSystemStatus.ACTIVE,
            detail="accepted",
        ),
        monkeypatch,
    )

    with caplog.at_level(logging.INFO):
        scheduler._refresh_provider_status()

    assert "SMS is active again" in caplog.text


def test_the_recurring_refresh_does_not_force_a_request(
    monkeypatch,
):
    """
    The refresh exists partly to keep the remembered answer
    warm so the Settings page never waits on the provider.
    Forcing every cycle would make it a request to a third
    party every thirty seconds instead.
    """

    asked = []

    monkeypatch.setattr(
        sms_scheduler_module,
        "sms_system_status",
        lambda force=False: (
            asked.append(force),
            ProviderCheck(
                status=SmsSystemStatus.ACTIVE,
                detail="ok",
            ),
        )[1],
    )

    SmsScheduler()._refresh_provider_status()

    assert asked == [False]


def test_a_cycle_result_counts_every_outcome_apart():
    result = CycleResult(
        submitted=2,
        failed=1,
        skipped=3,
        retrying=1,
    )

    assert result.total == 7

    summary = result.describe()

    assert "2 submitted" in summary

    assert "1 failed" in summary

    assert "3 skipped" in summary

    assert "1 awaiting retry" in summary


def test_an_empty_cycle_is_distinguishable_from_a_busy_one():
    """
    The scheduler logs an empty cycle at DEBUG and a busy
    one at INFO, so a console at INFO does not fill with a
    line every thirty seconds saying nothing happened.
    """

    assert CycleResult().total == 0

    assert CycleResult(submitted=1).total == 1
