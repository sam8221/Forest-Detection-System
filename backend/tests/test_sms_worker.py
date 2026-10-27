"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: SMS Worker Tests

Purpose:
    Verify how an attempt's outcome is recorded against a
    queued message.

Responsibilities:
    - Confirm an accepted message is terminal and keeps the
      provider's identifiers.
    - Confirm a transport failure retries, then fails.
    - Confirm a configuration fault fails without spending
      retries.
    - Confirm a provider refusal is terminal.
    - Confirm the provider's answer is recorded even on a
      failure.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Note:
    These tests drive the worker's decision function
    against a plain stub row. There is no database session,
    no provider and no network, which is what lets the
    whole transition table be exercised cheaply - including
    the exhausted-retry path, which would otherwise need
    three real failed sends to reach.
===========================================================
"""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app.models.enums import SmsQueueStatus
from app.services.sms_service import (
    SmsAmbiguousError,
    SmsConfigurationError,
    SmsProviderError,
    SmsTransientError,
)
from app.services.sms_worker import (
    SendOutcome,
    SmsWorker,
    apply_outcome,
    pending_sms_claim_query,
)


# =========================================================
# HELPERS
# =========================================================


class StubRow:
    """
    Stands in for an SmsQueue row.

    Carries the same attributes apply_outcome writes, with
    no mapper and no session behind them.
    """

    def __init__(self, retry_count=0, max_retries=3, phone="+260977123456"):
        self.id = 1
        self.recipient_phone = phone
        self.recipient_name = "Kitwe Officer"
        self.message = "ForestWatch test"
        self.status = SmsQueueStatus.PROCESSING
        self.skip_reason = None
        self.retry_count = retry_count
        self.max_retries = max_retries
        self.last_error = None
        self.provider_message_id = None
        self.provider_status_code = None
        self.provider_status = None
        self.provider_cost = None
        self.submitted_at = None
        self.recipient_user = None
        self.alert = None


class StubService:
    """
    Stands in for SmsService.

    Returns a provider recipient dictionary, or raises, with
    no network access of any kind.
    """

    def __init__(self, recipient=None, raises=None):
        self.recipient = recipient
        self.raises = raises
        self.calls = 0

    def send_sms(self, recipient_phone, message):
        self.calls += 1

        if self.raises is not None:
            raise self.raises

        return self.recipient


FIXED_TIME = datetime(2026, 5, 20, 8, 30, tzinfo=UTC)


# =========================================================
# ACCEPTED
# =========================================================


def test_an_accepted_message_records_the_provider_identifiers():
    """
    The provider's answer is the record, so every part of it
    that identifies the message is kept.
    """

    row = StubRow()

    apply_outcome(
        row,
        SendOutcome(
            status=SmsQueueStatus.SUBMITTED,
            provider_message_id="ATXid_abc123",
            provider_status_code=101,
            provider_status="Success",
            provider_cost="KES 0.8000",
        ),
        now=FIXED_TIME,
    )

    assert row.status is SmsQueueStatus.SUBMITTED
    assert row.submitted_at == FIXED_TIME
    assert row.provider_message_id == "ATXid_abc123"
    assert row.provider_status_code == 101
    assert row.provider_status == "Success"
    assert row.provider_cost == "KES 0.8000"

    # A previous attempt's error must not linger beside a
    # successful submission.
    assert row.last_error is None


def test_an_accepted_message_does_not_consume_a_retry():
    """
    Acceptance is terminal: retry_count has no further
    meaning once the provider holds the message.
    """

    row = StubRow(retry_count=1)

    apply_outcome(
        row,
        SendOutcome(status=SmsQueueStatus.SUBMITTED),
        now=FIXED_TIME,
    )

    assert row.retry_count == 1


def test_a_previous_error_is_cleared_on_acceptance():
    """
    A row that failed once and then succeeded must not still
    read as failed.
    """

    row = StubRow(retry_count=1)

    row.last_error = "The SMS provider could not be reached."

    apply_outcome(
        row,
        SendOutcome(status=SmsQueueStatus.SUBMITTED),
        now=FIXED_TIME,
    )

    assert row.last_error is None


# =========================================================
# TRANSPORT FAILURE
# =========================================================


def test_a_transport_failure_returns_the_message_to_pending():
    """
    The officer should still be told, so the message waits
    for the next cycle rather than being abandoned.
    """

    row = StubRow()

    apply_outcome(
        row,
        SendOutcome(
            status=SmsQueueStatus.FAILED,
            detail="The SMS provider could not be reached.",
            retryable=True,
        ),
        now=FIXED_TIME,
    )

    assert row.status is SmsQueueStatus.PENDING
    assert row.retry_count == 1
    assert row.submitted_at is None
    assert "could not be reached" in row.last_error


def test_a_transport_failure_fails_once_the_retries_are_used():
    """
    The third attempt against max_retries=3 is the last.
    """

    row = StubRow(retry_count=2, max_retries=3)

    apply_outcome(
        row,
        SendOutcome(
            status=SmsQueueStatus.FAILED,
            detail="The SMS provider could not be reached.",
            retryable=True,
        ),
        now=FIXED_TIME,
    )

    assert row.retry_count == 3
    assert row.status is SmsQueueStatus.FAILED


def test_an_unknown_provider_outcome_is_terminal_to_avoid_duplicates():
    row = StubRow()

    outcome = SmsWorker(
        db=None,
        sms_service=StubService(
            raises=SmsAmbiguousError("outcome unknown")
        ),
    ).attempt(row)

    assert outcome.status is SmsQueueStatus.FAILED
    assert outcome.retryable is False


def test_a_missing_phone_is_skipped_without_calling_provider():
    service = StubService(
        recipient={
            "statusCode": 101,
            "status": "Success",
        }
    )
    worker = SmsWorker(db=None, sms_service=service)

    outcome = worker.attempt(StubRow(phone=None))

    assert outcome.status is SmsQueueStatus.SKIPPED
    assert outcome.skip_reason == "missing_phone_number"
    assert service.calls == 0


def test_a_deactivated_officer_is_skipped_before_submission():
    service = StubService(
        recipient={
            "statusCode": 101,
            "status": "Success",
        }
    )
    row = StubRow()
    row.recipient_user = SimpleNamespace(
        is_active=False,
        role="DISTRICT_FORESTRY_OFFICER",
        district_id=7,
        province_id=None,
        phone_number="+260977123456",
    )
    row.alert = SimpleNamespace(
        detection=SimpleNamespace(
            forest_area=SimpleNamespace(
                district_id=7,
                district=SimpleNamespace(province_id=3),
            )
        )
    )

    outcome = SmsWorker(db=None, sms_service=service).attempt(row)

    assert outcome.status is SmsQueueStatus.SKIPPED
    assert outcome.skip_reason == "recipient_inactive"
    assert service.calls == 0


def test_worker_claim_query_skips_rows_locked_by_another_worker():
    query = pending_sms_claim_query(Session())
    sql = str(
        query.statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert "FOR UPDATE OF sms_queue SKIP LOCKED" in sql


def test_transient_retries_reuse_one_row_until_provider_accepts():
    class SequenceService:
        def __init__(self):
            self.outcomes = [
                SmsTransientError("connect timeout"),
                SmsTransientError("connect timeout"),
                {
                    "statusCode": 101,
                    "status": "Success",
                    "messageId": "provider-id-1",
                },
            ]
            self.calls = 0

        def send_sms(self, recipient_phone, message):
            self.calls += 1
            result = self.outcomes.pop(0)
            if isinstance(result, Exception):
                raise result
            return result

    service = SequenceService()
    worker = SmsWorker(db=None, sms_service=service)
    row = StubRow()

    for _ in range(3):
        outcome = worker.attempt(row)
        apply_outcome(row, outcome, now=FIXED_TIME)

    assert service.calls == 3
    assert row.retry_count == 2
    assert row.status is SmsQueueStatus.SUBMITTED
    assert row.provider_message_id == "provider-id-1"


def test_the_retry_sequence_runs_pending_then_fails():
    """
    Walk the whole sequence, which is the behaviour an
    administrator sees in the queue over three cycles.
    """

    row = StubRow(max_retries=3)

    outcome = SendOutcome(
        status=SmsQueueStatus.FAILED,
        detail="The SMS provider could not be reached.",
        retryable=True,
    )

    seen = []

    for _ in range(3):
        apply_outcome(row, outcome, now=FIXED_TIME)

        seen.append((row.retry_count, row.status))

    assert seen == [
        (1, SmsQueueStatus.PENDING),
        (2, SmsQueueStatus.PENDING),
        (3, SmsQueueStatus.FAILED),
    ]


# =========================================================
# TERMINAL FAILURE
# =========================================================


def test_a_configuration_fault_fails_without_spending_retries():
    """
    An unset API key fails identically every time.

    Counting attempts against it would write the same error
    three times and delay the moment an administrator sees
    what is actually wrong.
    """

    row = StubRow()

    apply_outcome(
        row,
        SendOutcome(
            status=SmsQueueStatus.FAILED,
            detail="AFRICASTALKING_API_KEY is not set.",
            retryable=False,
        ),
        now=FIXED_TIME,
    )

    assert row.status is SmsQueueStatus.FAILED
    assert row.retry_count == 0
    assert "AFRICASTALKING_API_KEY" in row.last_error


def test_a_provider_refusal_keeps_the_code_it_refused_with():
    """
    A refusal code is the most useful thing in the row when
    working out why an officer was not reached, so it is
    recorded on a failure as well as on a success.
    """

    row = StubRow()

    apply_outcome(
        row,
        SendOutcome(
            status=SmsQueueStatus.FAILED,
            detail="The provider refused: InvalidPhoneNumber (code 403).",
            retryable=False,
            provider_status_code=403,
            provider_status="InvalidPhoneNumber",
        ),
        now=FIXED_TIME,
    )

    assert row.status is SmsQueueStatus.FAILED
    assert row.provider_status_code == 403
    assert row.provider_status == "InvalidPhoneNumber"
    assert row.submitted_at is None


def test_a_failed_message_is_never_marked_submitted():
    """
    submitted_at is the evidence the provider took the
    message. A failure must leave no such evidence.
    """

    row = StubRow()

    for outcome in (
        SendOutcome(
            status=SmsQueueStatus.FAILED,
            detail="x",
            retryable=True,
        ),
        SendOutcome(
            status=SmsQueueStatus.FAILED,
            detail="x",
            retryable=False,
        ),
    ):
        apply_outcome(row, outcome, now=FIXED_TIME)

        assert row.submitted_at is None


# =========================================================
# ATTEMPT CLASSIFICATION
# =========================================================


def worker_with(service):
    """
    Build a worker around a stub service and no session.

    process_queue is not called in these tests, so the
    session is never touched; passing None keeps the test
    free of a database.
    """

    return SmsWorker(db=None, sms_service=service)


def test_an_accepted_send_becomes_a_submitted_outcome():
    """End to end through attempt(), with no network."""

    worker = worker_with(
        StubService(
            recipient={
                "statusCode": 101,
                "status": "Success",
                "number": "+260977123456",
                "messageId": "ATXid_abc123",
                "cost": "KES 0.8000",
            }
        )
    )

    outcome = worker.attempt(StubRow())

    assert outcome.status is SmsQueueStatus.SUBMITTED
    assert outcome.retryable is False
    assert outcome.provider_message_id == "ATXid_abc123"
    assert outcome.provider_status_code == 101
    assert outcome.provider_cost == "KES 0.8000"


def test_a_refused_send_becomes_a_terminal_outcome():
    """
    A message the provider refused will be refused again, so
    it is not retried.
    """

    worker = worker_with(
        StubService(
            recipient={
                "statusCode": 403,
                "status": "InvalidPhoneNumber",
                "number": "+260977123456",
            }
        )
    )

    outcome = worker.attempt(StubRow())

    assert outcome.status is SmsQueueStatus.FAILED
    assert outcome.retryable is False
    assert outcome.provider_status_code == 403


@pytest.mark.parametrize(
    "error,retryable",
    [
        (SmsTransientError("unreachable"), True),
        (SmsConfigurationError("no key"), False),
        (SmsProviderError("refused"), False),
    ],
)
def test_each_error_type_maps_to_the_right_retry_decision(
    error,
    retryable,
):
    """
    The three error types exist precisely so the worker can
    tell these cases apart.
    """

    worker = worker_with(StubService(raises=error))

    outcome = worker.attempt(StubRow())

    assert outcome.status is SmsQueueStatus.FAILED
    assert outcome.retryable is retryable


def test_an_unexpected_fault_does_not_escape_the_attempt():
    """
    One bad row must not stop the queue, so attempt()
    returns an outcome for every failure mode rather than
    raising.
    """

    worker = worker_with(
        StubService(raises=RuntimeError("a bug")),
    )

    outcome = worker.attempt(StubRow())

    assert outcome.status is SmsQueueStatus.FAILED
    assert outcome.retryable is False

    # A bug repeats, so it is not retried, and its detail
    # points at the log rather than leaking a traceback.
    assert "internal fault" in outcome.detail


def test_an_unreadable_status_code_is_recorded_as_absent():
    """
    A code that is not a number must not be coerced into
    one, and must not become a success.
    """

    worker = worker_with(
        StubService(
            recipient={
                "statusCode": "not-a-number",
                "status": "Odd",
                "number": "+260977123456",
            }
        )
    )

    outcome = worker.attempt(StubRow())

    assert outcome.status is SmsQueueStatus.FAILED
    assert outcome.provider_status_code is None
