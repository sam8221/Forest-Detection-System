"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: SMS Worker

Purpose:
    Processes queued deforestation alert SMS messages.

Responsibilities:
    - Claim pending messages one at a time.
    - Submit them through the SMS service.
    - Record the provider's answer against each row.
    - Retry transport failures, within a limit.
    - Fail configuration faults immediately.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Version:
    1.0.0
===========================================================
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import logging

from sqlalchemy.orm import Session

from app.models.enums import SmsQueueStatus
from app.models.sms_queue import SmsQueue
from app.services.sms_service import (
    SmsAmbiguousError,
    SmsConfigurationError,
    SmsProviderError,
    SmsService,
    SmsTransientError,
    classify_recipient,
)
from app.services.sms_recipients import (
    sms_phone_skip_reason,
    sms_queue_skip_reason,
)


logger = logging.getLogger(__name__)


# =========================================================
# OUTCOME OF ONE ATTEMPT
# =========================================================


@dataclass(frozen=True)
class SendOutcome:
    """
    What one attempt at one message produced.

    A plain value, carrying no database session and no
    provider client, so the decision about what it means for
    a queue row is testable on its own.
    """

    status: SmsQueueStatus

    detail: str | None = None

    # True only for a failure worth attempting again.
    retryable: bool = False

    provider_message_id: str | None = None

    provider_status_code: int | None = None

    provider_status: str | None = None

    provider_cost: str | None = None

    skip_reason: str | None = None


def log_unrecorded_attempt(
    row,
    reason: Exception | None = None,
    context: str = "",
) -> None:
    """
    Write an SMS attempt to the log when the database refused it.

    Args:
        row:
            The SmsQueue row that could not be stored. Read
            attribute by attribute so a partially built row
            still produces a line.
        reason:
            The database error, when there was one.
        context:
            Where this happened, for the reader.

    FR-19 requires every notification logged with the user
    and the time. A message the provider accepted has been
    sent and charged for whether or not the row committed,
    so a failure to store it is the one moment when the
    trail is most at risk of losing an event that really
    happened.

    This is the fallback, not the record: the log is not a
    substitute for the table and the line says so. But an
    event written somewhere can be reconciled later, and an
    event written nowhere cannot be recovered at all.

    Deliberately not a debug line and never silent. It is
    logged at ERROR with everything the row would have
    held, so that the attempt survives in the console and
    in whatever collects it.
    """

    def field(name):
        try:
            return getattr(row, name, None)

        except Exception:
            return None

    logger.error(
        "SMS ATTEMPT NOT RECORDED%s. This message was "
        "submitted to the provider but could not be written "
        "to sms_queue, so it is missing from the "
        "notification record and is reported here instead. "
        "user_id=%s recipient=%s alert_id=%s status=%s "
        "provider_message_id=%s provider_status=%s "
        "provider_status_code=%s cost=%s submitted_at=%s "
        "error=%s",
        f" ({context})" if context else "",
        field("recipient_user_id"),
        field("recipient_phone"),
        field("alert_id"),
        getattr(field("status"), "value", field("status")),
        field("provider_message_id"),
        field("provider_status"),
        field("provider_status_code"),
        field("provider_cost"),
        field("submitted_at"),
        f"{type(reason).__name__}: {reason}" if reason else "unknown",
    )


@dataclass(frozen=True)
class CycleResult:
    """
    What one pass over the SMS queue did.

    Returned so the scheduler can say what happened rather
    than only that it ran. A console that reports "SMS
    scheduler started" and then nothing cannot distinguish a
    worker quietly keeping up with the queue from one that
    stopped doing anything at all.
    """

    submitted: int = 0

    failed: int = 0

    skipped: int = 0

    #: Rows returned to PENDING for another attempt. Counted
    #: apart from failures: a transport blip that will be
    #: retried is not the same event as a message abandoned.
    retrying: int = 0

    @property
    def total(self) -> int:
        """How many rows the cycle handled."""

        return (
            self.submitted
            + self.failed
            + self.skipped
            + self.retrying
        )

    def describe(self) -> str:
        """A one-line summary for a log entry."""

        return (
            f"{self.submitted} submitted, "
            f"{self.failed} failed, "
            f"{self.skipped} skipped, "
            f"{self.retrying} awaiting retry"
        )


def pending_sms_claim_query(db):
    """Select one pending row with a PostgreSQL worker lock."""

    return (
        db.query(SmsQueue)
        .filter(SmsQueue.status == SmsQueueStatus.PENDING)
        .order_by(SmsQueue.created_at.asc())
        .with_for_update(of=SmsQueue, skip_locked=True)
    )


def apply_outcome(
    row,
    outcome: SendOutcome,
    now: datetime | None = None,
) -> None:
    """
    Write an attempt's result onto a queue row.

    Args:
        row:
            The SmsQueue row, or anything carrying the same
            attributes. Deliberately untyped so the tests
            can drive every transition with a plain stub and
            no database.
        outcome:
            What the attempt produced.
        now:
            Timestamp to record, for tests that need a
            fixed one.

    The rules, and why each is what it is:

        SUBMITTED is terminal. The provider has the message.
        Attempting it again would charge for and deliver a
        second copy of the same alert, so a submitted row is
        never retried, whatever happens afterwards.

        A retryable failure goes back to PENDING and
        increments retry_count, becoming FAILED once the
        attempts are used up. Only transport failures
        qualify.

        A non-retryable failure is FAILED at once and does
        NOT increment retry_count. An unset API key or a
        malformed number fails identically every time;
        counting attempts against it would only write the
        same error three times and delay the moment an
        administrator sees it.
    """

    stamp = now or datetime.now(UTC)

    if outcome.status is SmsQueueStatus.SKIPPED:
        row.status = SmsQueueStatus.SKIPPED
        row.skip_reason = outcome.skip_reason
        row.last_error = None
        return

    if outcome.status is SmsQueueStatus.SUBMITTED:
        row.status = SmsQueueStatus.SUBMITTED

        row.submitted_at = stamp

        row.last_error = None

        row.provider_message_id = outcome.provider_message_id

        row.provider_status_code = outcome.provider_status_code

        row.provider_status = outcome.provider_status

        row.provider_cost = outcome.provider_cost

        return

    # Whatever the provider did say is kept even on a
    # failure: a refusal code is the most useful thing in
    # the row when working out why an officer was not
    # reached.
    if outcome.provider_status_code is not None:
        row.provider_status_code = outcome.provider_status_code

    if outcome.provider_status is not None:
        row.provider_status = outcome.provider_status

    row.last_error = outcome.detail

    if not outcome.retryable:
        row.status = SmsQueueStatus.FAILED

        return

    row.retry_count = (row.retry_count or 0) + 1

    if row.retry_count >= row.max_retries:
        row.status = SmsQueueStatus.FAILED

    else:
        row.status = SmsQueueStatus.PENDING


def submit_message(
    sms_service: "SmsService",
    recipient_phone: str,
    message: str,
    reference: str,
) -> SendOutcome:
    """
    Submit one message and turn every outcome into a record.

    Args:
        sms_service:
            Service to submit through.
        recipient_phone:
            Recipient in E.164 form.
        message:
            Body to send.
        reference:
            How to name this message in the log. A queued
            message uses its row id; the registration test
            names itself, because it has no row until this
            has returned.

    Returns:
        The outcome, for apply_outcome to record. This
        function raises nothing: every failure mode is
        returned as an outcome, so one bad message can stop
        neither the queue nor a request.

    Shared by the queue worker and the registration test so
    that a provider refusal, a dead connection and an
    unreadable answer are judged identically whichever asked.
    A test message reporting success where a real alert would
    have failed would be worse than no test at all.
    """

    try:
        recipient = sms_service.send_sms(
            recipient_phone=recipient_phone,
            message=message,
        )

    except SmsConfigurationError as exc:
        # Not the message's fault and not transient.
        logger.error(
            "%s cannot be sent: %s",
            reference,
            exc,
        )

        return SendOutcome(
            status=SmsQueueStatus.FAILED,
            detail=str(exc),
            retryable=False,
        )

    except SmsTransientError as exc:
        logger.warning(
            "%s could not reach the provider: %s",
            reference,
            exc,
        )

        return SendOutcome(
            status=SmsQueueStatus.FAILED,
            detail=str(exc),
            retryable=True,
        )

    except SmsAmbiguousError as exc:
        logger.error(
            "%s has an unknown provider outcome; it will "
            "not be retried to avoid a duplicate.",
            reference,
        )

        return SendOutcome(
            status=SmsQueueStatus.FAILED,
            detail=str(exc),
            retryable=False,
        )

    except SmsProviderError as exc:
        logger.warning(
            "%s was refused: %s",
            reference,
            exc,
        )

        return SendOutcome(
            status=SmsQueueStatus.FAILED,
            detail=str(exc),
            retryable=False,
        )

    except Exception:
        # A fault in this code rather than the provider's.
        # Logged in full, recorded briefly, and not retried,
        # because a bug repeats.
        logger.exception(
            "%s failed unexpectedly",
            reference,
        )

        return SendOutcome(
            status=SmsQueueStatus.FAILED,
            detail=(
                "The message could not be sent because of "
                "an internal fault. See the server log."
            ),
            retryable=False,
        )

    # -----------------------------------------------------
    # The provider answered. What it said decides the
    # status, and it is recorded verbatim either way.
    # -----------------------------------------------------

    status, detail = classify_recipient(recipient)

    raw_code = recipient.get("statusCode")

    try:
        code = int(raw_code)

    except (TypeError, ValueError):
        code = None

    return SendOutcome(
        status=status,
        detail=detail,
        # A refusal is the provider's decision about this
        # message, so repeating it changes nothing.
        retryable=False,
        provider_message_id=(
            str(recipient.get("messageId"))
            if recipient.get("messageId")
            else None
        ),
        provider_status_code=code,
        provider_status=(
            str(recipient.get("status"))[:50]
            if recipient.get("status")
            else None
        ),
        provider_cost=(
            str(recipient.get("cost"))[:30]
            if recipient.get("cost")
            else None
        ),
    )


# =========================================================
# SMS WORKER
# =========================================================


class SmsWorker:
    """
    Processes pending messages in the SMS queue.

    Mirrors EmailWorker, with two deliberate differences.

    The row is claimed before the provider is called:

        The worker sets PROCESSING and commits before
        submitting. If the process dies mid-send, the row is
        left in PROCESSING rather than PENDING, so the next
        run does not pick it up and send a message the
        provider may already have accepted. A message stuck
        in PROCESSING is visible and can be decided on; a
        duplicate SMS to an officer cannot be undone.

    The parent alert's status is not changed:

        EmailWorker marks the Alert SENT when its email
        goes out. This worker leaves Alert.status alone.
        Email is the channel every alert uses, so it owns
        that transition; an SMS marking an alert sent while
        its email was still queued would misreport the
        alert's progress. The SMS record lives in its own
        rows.
    """

    def __init__(
        self,
        db: Session,
        sms_service: SmsService | None = None,
    ):
        """
        Initialise the worker.

        Args:
            db:
                Database session.
            sms_service:
                Service to send through. Injected so tests
                can supply one that never touches a network.
        """

        self.db = db

        self.sms_service = sms_service or SmsService()

    # =========================================================
    # ATTEMPT ONE MESSAGE
    # =========================================================

    def attempt(self, row: SmsQueue) -> SendOutcome:
        """
        Submit one queued message.

        Args:
            row:
                The queue row to send.

        Returns:
            The outcome, for apply_outcome to record. This
            method raises nothing: every failure mode is
            returned as an outcome, so one bad row cannot
            stop the queue.
        """

        phone_reason = sms_phone_skip_reason(row.recipient_phone)

        if phone_reason is not None:
            return SendOutcome(
                status=SmsQueueStatus.SKIPPED,
                detail=phone_reason,
                skip_reason=phone_reason,
            )

        skip_reason = sms_queue_skip_reason(row)

        if skip_reason is not None:
            return SendOutcome(
                status=SmsQueueStatus.SKIPPED,
                detail=skip_reason,
                skip_reason=skip_reason,
            )

        return submit_message(
            self.sms_service,
            recipient_phone=row.recipient_phone,
            message=row.message,
            reference=f"SMS queue row {row.id}",
        )

    # =========================================================
    # PROCESS QUEUE
    # =========================================================

    def process_queue(self) -> "CycleResult":
        """
        Process every pending message.

        Returns:
            What the cycle did, for the scheduler to report.
            A cycle that found nothing is not the same event
            as a cycle that sent four messages, and a
            console showing only "started" cannot tell them
            apart.

        Each row is committed on its own, so one failure
        neither rolls back a message already submitted nor
        stops the rest of the queue.
        """

        submitted = 0

        failed = 0

        skipped = 0

        retrying = 0

        while True:
            row = pending_sms_claim_query(self.db).first()

            if row is None:
                break

            # Claim it first. See the class docstring: a
            # process that dies after this point leaves the row
            # in PROCESSING rather than offering it again. The
            # row lock also prevents another worker from claiming
            # it before this status commit.
            row.status = SmsQueueStatus.PROCESSING

            self.db.commit()

            outcome = self.attempt(row)

            apply_outcome(row, outcome)

            # Counted from the row rather than the outcome,
            # because apply_outcome is what decides between
            # them: a retryable failure with attempts left
            # becomes PENDING again, and reporting that as a
            # failure would overstate what happened.
            if row.status is SmsQueueStatus.SUBMITTED:
                submitted += 1

            elif row.status is SmsQueueStatus.SKIPPED:
                skipped += 1

            elif row.status is SmsQueueStatus.PENDING:
                retrying += 1

            else:
                failed += 1

            try:
                self.db.commit()

            except Exception as exc:
                # The send already happened; failing to
                # record it must not crash the worker and
                # leave the row claimed for ever.
                self.db.rollback()

                logger.exception(
                    "Could not record the outcome of SMS "
                    "queue row %s",
                    row.id,
                )

                # The traceback above says what went wrong.
                # This says what was lost, which is the part
                # the notification record needs back.
                log_unrecorded_attempt(
                    row,
                    reason=exc,
                    context="alert message, queue worker",
                )

        return CycleResult(
            submitted=submitted,
            failed=failed,
            skipped=skipped,
            retrying=retrying,
        )

    # =========================================================
    # RUN ONCE
    # =========================================================

    def run_once(self) -> "CycleResult":
        """
        Execute one SMS-processing cycle.

        Returns:
            What the cycle did.

        Called by SmsScheduler, and usable from a management
        command or a cron entry without change.
        """

        return self.process_queue()
