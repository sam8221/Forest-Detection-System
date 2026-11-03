"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Tests: The SMS notification record

What these protect:

    FR-19 requires every notification logged with the user
    and the time. The moment that requirement is most at
    risk is the one where a message has already been sent
    and the database then refuses to store the row: the
    provider has delivered it and charged for it, and the
    only evidence left is whatever the application chose to
    write.

    That happened in production on this project. A real
    message went out at ZMW 0.48, sms_queue rejected the
    row because alert_id was NOT NULL, and the attempt was
    summarised in one line that called the failure
    "expected". The message was charged for and is in no
    record.

    These tests keep such an attempt visible, complete and
    impossible to mistake for routine.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia
===========================================================
"""

import logging

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.models.enums import SmsQueueStatus
from app.services.sms_worker import log_unrecorded_attempt


def sent_row():
    """A row for a message the provider accepted."""

    return SimpleNamespace(
        id=None,
        alert_id=None,
        recipient_user_id=3,
        recipient_phone="+260966993138",
        recipient_name="Kitwe Officer",
        message="Welcome to ForestWatch Zambia!",
        status=SmsQueueStatus.SUBMITTED,
        provider_message_id="ATXid_f77ca278afbb9b93d9531b4833cfe1b4",
        provider_status="Success",
        provider_status_code=100,
        provider_cost="ZMW 0.4800",
        submitted_at=datetime(2026, 11, 1, 20, 23, 4, tzinfo=UTC),
    )


def test_a_message_that_could_not_be_stored_is_logged_in_full(caplog):
    """
    Everything the row would have held reaches the log.

    A line naming only the row id would record that
    something was lost without recording what, which is of
    no use in reconstructing the trail.
    """

    with caplog.at_level(logging.ERROR):
        log_unrecorded_attempt(
            sent_row(),
            reason=RuntimeError("alert_id violates not-null constraint"),
            context="registration test for user 3",
        )

    written = caplog.text

    assert "3" in written                       # the officer
    assert "+260966993138" in written           # the recipient
    assert "SUBMITTED" in written               # the delivery status
    assert "ATXid_f77ca278afbb9b93d9531b4833cfe1b4" in written
    assert "Success" in written
    assert "ZMW 0.4800" in written              # what it cost
    assert "2026-11-01" in written              # when
    assert "not-null constraint" in written     # why it was lost


def test_the_failure_is_logged_as_an_error(caplog):
    """
    Not debug, not info, not "expected".

    A notification that was sent and charged for but never
    recorded is a gap in an audit trail, and an audit trail
    with an unreported gap is worse than one with a
    reported one.
    """

    with caplog.at_level(logging.DEBUG):
        log_unrecorded_attempt(sent_row(), reason=ValueError("no"))

    records = [
        record
        for record in caplog.records
        if "NOT RECORDED" in record.getMessage()
    ]

    assert records

    assert all(r.levelno >= logging.ERROR for r in records)


def test_the_line_says_the_message_was_sent_not_merely_failed(caplog):
    """
    The distinction that matters to whoever reads it. The
    message reached the recipient; only the record of it
    did not. Reading this as a failed send would under-count
    what was actually delivered.
    """

    with caplog.at_level(logging.ERROR):
        log_unrecorded_attempt(sent_row(), reason=ValueError("no"))

    assert "submitted to the provider" in caplog.text

    assert "missing from the notification record" in caplog.text


def test_logging_never_raises_on_an_incomplete_row(caplog):
    """
    This runs in a failure path, after a rollback, on a row
    that may be half built. It is the last chance to record
    the attempt, so it must not be the thing that throws.
    """

    class Awkward:
        recipient_phone = "+260977123456"

        @property
        def provider_cost(self):
            raise RuntimeError("detached from the session")

    with caplog.at_level(logging.ERROR):
        log_unrecorded_attempt(Awkward(), reason=None)

    assert "+260977123456" in caplog.text

    assert "NOT RECORDED" in caplog.text


def test_the_failure_is_not_described_as_expected(caplog):
    """
    The original wording said the failure was expected
    until a migration was applied. Once it is applied, that
    same sentence would make a real fault read as routine.
    """

    with caplog.at_level(logging.ERROR):
        log_unrecorded_attempt(sent_row(), reason=ValueError("no"))

    assert "expected" not in caplog.text.lower()


@pytest.mark.parametrize(
    "alert_id, description",
    [
        (None, "a registration test, which belongs to no alert"),
        (42, "an alert notification"),
    ],
)
def test_the_alert_is_recorded_where_there_is_one(
    alert_id,
    description,
    caplog,
):
    """
    Where a message belongs to an alert, the log says which.
    Where it does not, the absence is itself the fact: it
    is what distinguishes a test message from a
    notification in the record.
    """

    row = sent_row()

    row.alert_id = alert_id

    with caplog.at_level(logging.ERROR):
        log_unrecorded_attempt(row, reason=ValueError("no"))

    assert f"alert_id={alert_id}" in caplog.text, description
