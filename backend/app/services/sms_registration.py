"""
An officer's own SMS registration.

Registering a number is how an officer asks to be told about
suspected clearing in the district they are responsible for.
This module holds the three things that belong to that act:
reading the current settings, changing them, and sending the
one test message that proves the channel works.

Kept apart from sms_service, which talks to the provider, and
from alert_service, which decides who an alert concerns.
Nothing here decides whether an alert warrants a message.

Why the test message is sent here and now rather than queued:

    The officer is waiting for an answer. A queued message
    would return "accepted for sending" and tell them nothing
    about whether their number works, which is the entire
    point of pressing the button. It is submitted during the
    request and the provider's answer is reported.

    This does not affect the alert pipeline. Automatic alert
    messages are still queued and sent by the background
    worker, so image processing and analysis never wait on a
    provider.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models.enums import SmsQueueStatus
from app.models.sms_queue import SmsQueue
from app.models.user import User
from app.schemas.user import SmsSettingsUpdate
from app.services.sms_recipients import (
    PREFERENCE_IS_MAPPED,
    officer_accepts_alert_sms,
    sms_phone_skip_reason,
)
from app.services.sms_service import SmsService, sms_system_status
from app.services.sms_worker import (
    apply_outcome,
    log_unrecorded_attempt,
    submit_message,
)


logger = logging.getLogger(__name__)


#: The message sent when an officer registers a number.
#:
#: Fixed wording, and deliberately not passed through the
#: length trimming that alert messages use. An alert is
#: shortened so the facts that decide a field visit survive;
#: this message carries no such facts, is sent once, only
#: when asked for, and reads as a confirmation. Trimming it
#: would damage the one thing it has to do, which is read as
#: a complete and official confirmation.
#:
#: It is longer than one 160-character segment, so a provider
#: will charge for two. That is accepted for a one-off
#: registration confirmation.
WELCOME_SMS = (
    "Welcome to ForestWatch Zambia! Your mobile number has "
    "been successfully registered for forest monitoring "
    "notifications. You will automatically receive SMS "
    "alerts when potential deforestation is detected in "
    "your assigned monitoring areas."
)


#: Marker for a queue row that is a registration test.
#:
#: A test belongs to no alert, so its alert_id is NULL. That
#: is the only thing distinguishing it from a notification in
#: the record, which is why it is named here rather than left
#: as an unexplained NULL for a later reader to interpret.
TEST_MESSAGE_HAS_NO_ALERT = None


class SmsRegistrationError(Exception):
    """A registration request that cannot be carried out."""


def sms_settings_for(
    user: User,
    sms_service: SmsService | None = None,
) -> dict:
    """
    Describe an officer's current SMS settings.

    Args:
        user:
            The signed-in officer.
        sms_service:
            Service to check the provider through. Injected
            so a test can answer without a network.

    Returns:
        Fields for SmsSettingsResponse.

    The system half of this answer comes from
    sms_system_status, which asks the provider rather than
    inferring a working channel from a key being present in
    the configuration. An officer reading "Active" is being
    told the provider accepted these credentials, not that
    somebody typed something into AFRICASTALKING_API_KEY.
    """

    check = sms_system_status(sms_service=sms_service)

    return {
        "phone_number": user.phone_number,
        "sms_notifications_enabled": officer_accepts_alert_sms(user),
        "preference_supported": PREFERENCE_IS_MAPPED,
        "automatic_sending_enabled": check.can_send,
        "system_status": check.status.value,
        "system_detail": check.detail,
    }


def update_sms_settings(
    db: Session,
    user: User,
    changes: SmsSettingsUpdate,
) -> User:
    """
    Apply an officer's change to their own SMS settings.

    Args:
        db:
            Database session.
        user:
            The signed-in officer, who is also the subject.
        changes:
            Fields to change. An omitted field is left alone,
            so saving a number does not silently re-enable
            notifications the officer had switched off.

    Returns:
        The updated officer.

    Raises:
        SmsRegistrationError:
            The preference was asked for but the column that
            stores it does not exist yet.

    The number has already been validated and normalised to
    E.164 by SmsSettingsUpdate. Storing one written form
    means the same handset cannot be reached twice as two
    different-looking numbers.
    """

    fields = changes.model_dump(exclude_unset=True)

    if "phone_number" in fields:
        user.phone_number = fields["phone_number"]

    if "sms_notifications_enabled" in fields:
        if not PREFERENCE_IS_MAPPED:
            raise SmsRegistrationError(
                "The notification preference cannot be saved "
                "yet because the database is missing the "
                "column that stores it. Apply migration "
                "d9f4a7c1e835 and restart the backend."
            )

        user.sms_notifications_enabled = bool(
            fields["sms_notifications_enabled"]
        )

    db.commit()
    db.refresh(user)

    return user


def send_registration_test_sms(
    db: Session,
    user: User,
    sms_service: SmsService | None = None,
) -> dict:
    """
    Send the welcome message to an officer's saved number.

    Args:
        db:
            Database session.
        user:
            The signed-in officer, who is also the recipient.
            An officer can only test their own number, so no
            account can be used to send messages to a number
            its holder never registered.
        sms_service:
            Service to submit through. Injected so tests can
            supply one that never touches a network.

    Returns:
        Fields for SmsTestResponse.

    Raises:
        SmsRegistrationError:
            No usable number is saved.

    Deliberately not gated on SMS_ENABLED. That switch stops
    the system sending alerts on its own; this message is
    sent because an officer pressed a button, and testing the
    channel before enabling automatic sending is the order
    the deployment notes describe. The response reports the
    switch separately so the page cannot imply that alerts
    will now flow.
    """

    phone_reason = sms_phone_skip_reason(user.phone_number)

    if phone_reason == "missing_phone_number":
        raise SmsRegistrationError(
            "Save a mobile number before sending a test "
            "message."
        )

    if phone_reason is not None:
        raise SmsRegistrationError(
            "The saved number is not a valid Zambian mobile "
            "number. Save a corrected number and try again."
        )

    outcome = submit_message(
        sms_service or SmsService(),
        recipient_phone=user.phone_number,
        message=WELCOME_SMS,
        reference=f"Registration test for user {user.id}",
    )

    recorded = _record_test_message(db, user, outcome)

    return {
        "submitted": outcome.status is SmsQueueStatus.SUBMITTED,
        "status": outcome.status.value,
        "detail": outcome.detail,
        "recipient_phone": user.phone_number,
        "recorded": recorded,
    }


def _record_test_message(
    db: Session,
    user: User,
    outcome,
) -> bool:
    """
    Write the test attempt into the SMS record.

    Args:
        db:
            Database session.
        user:
            Recipient.
        outcome:
            What the attempt produced.

    Returns:
        True when the attempt was stored.

    The row is written with the attempt's final status and
    never as PENDING, so the background worker cannot pick it
    up and send the officer a second copy. max_retries is
    zero for the same reason: a test the officer watched fail
    is theirs to repeat, not the system's.

    Until migration d9f4a7c1e835 makes sms_queue.alert_id
    nullable, a test cannot be stored at all: the column
    requires an alert and this message has none. Inventing an
    alert reference would put a message into that alert's
    record that was never sent for it, corrupting the
    notification trail FR-19 depends on. So the attempt goes
    unrecorded and the caller is told, which is a smaller
    failure than a false record.
    """

    row = SmsQueue(
        alert_id=TEST_MESSAGE_HAS_NO_ALERT,
        recipient_user_id=user.id,
        recipient_phone=user.phone_number,
        recipient_name=user.full_name,
        message=WELCOME_SMS,
        status=SmsQueueStatus.PENDING,
        retry_count=0,
        max_retries=0,
    )

    apply_outcome(row, outcome)

    try:
        db.add(row)
        db.commit()

        return True

    except Exception as exc:
        db.rollback()

        logger.exception(
            "The registration test for user %s was sent but "
            "could not be recorded.",
            user.id,
        )

        # The attempt itself, in full, so that a message the
        # provider accepted and charged for is not lost from
        # the record merely because the row would not store.
        #
        # Not described as expected. It was expected while
        # sms_queue.alert_id was still NOT NULL, and saying
        # so in the log was a mistake: once that is fixed
        # the same line would make a real fault read as
        # routine.
        log_unrecorded_attempt(
            row,
            reason=exc,
            context=f"registration test for user {user.id}",
        )

        return False
