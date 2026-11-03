"""An officer registering their own number and testing it.

These cover the scenarios the SMS notification requirement
lists for registration: a valid number saved, an invalid one
refused, the welcome message sent only on request, acceptance
never reported as delivery, failures reported usefully, and
the preference respected once it can be stored.

Nothing here connects to PostgreSQL or to Africa's Talking.
"""

from types import SimpleNamespace

import pytest

from app.models.enums import SmsQueueStatus, UserRole
from app.schemas.user import SmsSettingsUpdate
from app.services import sms_registration
from app.services.sms_recipients import (
    officer_accepts_alert_sms,
    sms_recipient_authorization_reason,
)
from app.services.sms_registration import (
    WELCOME_SMS,
    SmsRegistrationError,
    send_registration_test_sms,
    sms_settings_for,
    update_sms_settings,
)
from app.services.sms_service import (
    SmsProviderError,
    SmsTransientError,
)


class MemoryDb:
    """Just enough session for the registration service."""

    def __init__(self, *, accepts_rows=True):
        self.added = []
        self.commits = 0
        self.rollbacks = 0
        self.accepts_rows = accepts_rows

    def add(self, row):
        self.added.append(row)

    def commit(self):
        if not self.accepts_rows and self.added:
            # Stands in for the NOT NULL constraint on
            # sms_queue.alert_id before the migration.
            raise RuntimeError("null value in column alert_id")

        self.commits += 1

    def rollback(self):
        self.rollbacks += 1
        self.added.clear()

    def refresh(self, _):
        return None


class StubSms:
    """An SMS service that never reaches a network."""

    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.sent = []

    def send_sms(self, recipient_phone, message):
        self.sent.append((recipient_phone, message))

        if self.error is not None:
            raise self.error

        return self.result


def officer(phone="+260977123456", enabled=None):
    user = SimpleNamespace(
        id=7,
        full_name="Kitwe Officer",
        phone_number=phone,
        is_active=True,
    )

    if enabled is not None:
        user.sms_notifications_enabled = enabled

    return user


def accepted(message_id="ATXid_1"):
    return {
        "statusCode": 101,
        "status": "Success",
        "number": "+260977123456",
        "messageId": message_id,
        "cost": "KES 0.8000",
    }


# =========================================================
# REGISTERING A NUMBER
# =========================================================

@pytest.mark.parametrize(
    "written,stored",
    [
        ("0977123456", "+260977123456"),
        ("+260977123456", "+260977123456"),
        ("260977123456", "+260977123456"),
        ("00260977123456", "+260977123456"),
        ("+260 977 123 456", "+260977123456"),
        ("0961234567", "+260961234567"),
    ],
)
def test_a_valid_zambian_number_is_stored_in_one_form(written, stored):
    """Every accepted spelling reaches the handset as one number."""

    changes = SmsSettingsUpdate(phone_number=written)

    assert changes.phone_number == stored


@pytest.mark.parametrize(
    "written",
    [
        "12345",
        "097712345",            # one digit short
        "09771234567",          # one digit long
        "+2547012345678",       # not Zambian
        "0877123456",           # not a mobile prefix
        "not a number",
    ],
)
def test_an_invalid_number_is_refused_before_it_is_stored(written):
    """An invalid number never reaches the database."""

    with pytest.raises(ValueError):
        SmsSettingsUpdate(phone_number=written)


def test_saving_a_number_does_not_change_the_preference():
    """An omitted field is left alone."""

    user = officer(phone=None, enabled=False)
    db = MemoryDb()

    update_sms_settings(
        db=db,
        user=user,
        changes=SmsSettingsUpdate(phone_number="0977123456"),
    )

    assert user.phone_number == "+260977123456"
    assert user.sms_notifications_enabled is False


def test_an_empty_number_clears_the_saved_one():
    """Clearing is explicit, not an accident of a blank form."""

    user = officer()
    db = MemoryDb()

    update_sms_settings(
        db=db,
        user=user,
        changes=SmsSettingsUpdate(phone_number=""),
    )

    assert user.phone_number is None


def test_the_preference_cannot_be_saved_before_its_column_exists(monkeypatch):
    """The officer is told why, rather than the switch doing nothing."""

    monkeypatch.setattr(
        sms_registration,
        "PREFERENCE_IS_MAPPED",
        False,
    )

    with pytest.raises(SmsRegistrationError) as raised:
        update_sms_settings(
            db=MemoryDb(),
            user=officer(),
            changes=SmsSettingsUpdate(sms_notifications_enabled=False),
        )

    assert "d9f4a7c1e835" in str(raised.value)


def test_the_preference_is_saved_once_the_column_exists(monkeypatch):
    monkeypatch.setattr(
        sms_registration,
        "PREFERENCE_IS_MAPPED",
        True,
    )

    user = officer(enabled=True)

    update_sms_settings(
        db=MemoryDb(),
        user=user,
        changes=SmsSettingsUpdate(sms_notifications_enabled=False),
    )

    assert user.sms_notifications_enabled is False


def test_settings_report_an_unmigrated_preference_as_unsupported(monkeypatch):
    monkeypatch.setattr(
        sms_registration,
        "PREFERENCE_IS_MAPPED",
        False,
    )

    reported = sms_settings_for(officer())

    assert reported["preference_supported"] is False

    # Treated as opted in, which is what happened before the
    # preference existed.
    assert reported["sms_notifications_enabled"] is True


# =========================================================
# THE TEST MESSAGE
# =========================================================

def test_the_welcome_message_is_the_registration_wording():
    """The officer is told what registering actually means."""

    assert WELCOME_SMS.startswith("Welcome to ForestWatch Zambia!")
    assert "successfully registered" in WELCOME_SMS
    assert "automatically receive SMS alerts" in WELCOME_SMS


def test_a_test_message_needs_a_saved_number():
    """Nothing is submitted when there is nowhere to send it."""

    service = StubSms(result=accepted())

    with pytest.raises(SmsRegistrationError) as raised:
        send_registration_test_sms(
            db=MemoryDb(),
            user=officer(phone=None),
            sms_service=service,
        )

    assert "Save a mobile number" in str(raised.value)
    assert service.sent == []


def test_an_accepted_test_message_is_recorded_as_submitted():
    """Accepted by the provider, and recorded as exactly that."""

    db = MemoryDb()
    service = StubSms(result=accepted())

    result = send_registration_test_sms(
        db=db,
        user=officer(),
        sms_service=service,
    )

    assert result["submitted"] is True

    # Never "DELIVERED" or "SENT": no delivery report exists.
    assert result["status"] == "SUBMITTED"
    assert result["recorded"] is True

    assert service.sent == [("+260977123456", WELCOME_SMS)]

    row = db.added[0]

    assert row.status is SmsQueueStatus.SUBMITTED
    assert row.message == WELCOME_SMS
    assert row.recipient_user_id == 7

    # A test belongs to no alert; that is what marks it.
    assert row.alert_id is None

    # Terminal, so the background worker cannot send a
    # second copy of a message the officer already has.
    assert row.max_retries == 0


def test_a_refused_test_message_reports_the_reason():
    """A failure says what went wrong, and is not called success."""

    db = MemoryDb()
    service = StubSms(
        error=SmsProviderError("The provider refused the message.")
    )

    result = send_registration_test_sms(
        db=db,
        user=officer(),
        sms_service=service,
    )

    assert result["submitted"] is False
    assert result["status"] == "FAILED"
    assert "refused" in result["detail"]

    assert db.added[0].status is SmsQueueStatus.FAILED


def test_a_transport_failure_is_terminal_for_a_test():
    """A test the officer watched fail is theirs to repeat."""

    db = MemoryDb()
    service = StubSms(
        error=SmsTransientError("The provider could not be reached.")
    )

    result = send_registration_test_sms(
        db=db,
        user=officer(),
        sms_service=service,
    )

    assert result["status"] == "FAILED"

    # Not left PENDING, so the queue worker never picks it up.
    assert db.added[0].status is SmsQueueStatus.FAILED


def test_a_sent_message_is_still_reported_when_it_cannot_be_recorded():
    """Before the migration the record fails; the send still happened."""

    db = MemoryDb(accepts_rows=False)
    service = StubSms(result=accepted())

    result = send_registration_test_sms(
        db=db,
        user=officer(),
        sms_service=service,
    )

    assert result["submitted"] is True

    # Honest about the gap rather than claiming a record.
    assert result["recorded"] is False
    assert db.rollbacks == 1


# =========================================================
# WHETHER AN ALERT REACHES AN OFFICER
#
# The preference decides whether automatic alert messages go
# out. These check the decision itself, which is what stops
# and restarts the automatic notifications.
# =========================================================

def area_in(district_id=3, province_id=1):
    return SimpleNamespace(
        district_id=district_id,
        district=SimpleNamespace(province_id=province_id),
    )


def district_officer(district_id=3, enabled=None, phone="+260977123456"):
    user = SimpleNamespace(
        id=11,
        full_name="Kitwe Officer",
        phone_number=phone,
        is_active=True,
        role=UserRole.DISTRICT_FORESTRY_OFFICER,
        district_id=district_id,
        province_id=1,
    )

    if enabled is not None:
        user.sms_notifications_enabled = enabled

    return user


def test_an_officer_with_notifications_off_is_not_sent_an_alert():
    """Disabling stops automatic messages."""

    reason = sms_recipient_authorization_reason(
        district_officer(enabled=False),
        area_in(),
    )

    assert reason == "notifications_disabled"


def test_re_enabling_lets_future_alerts_through_again():
    """Re-enabling restores them, with no other change needed."""

    assert (
        sms_recipient_authorization_reason(
            district_officer(enabled=True),
            area_in(),
        )
        is None
    )


def test_an_officer_outside_the_district_is_never_sent_the_alert():
    """Jurisdiction is decided before any preference is consulted."""

    reason = sms_recipient_authorization_reason(
        district_officer(district_id=9, enabled=True),
        area_in(district_id=3),
    )

    assert reason == "outside_jurisdiction"


def test_notifications_are_on_for_an_account_predating_the_preference():
    """An unmigrated deployment keeps behaving as it did."""

    assert officer_accepts_alert_sms(district_officer()) is True

    assert (
        sms_recipient_authorization_reason(
            district_officer(),
            area_in(),
        )
        is None
    )
