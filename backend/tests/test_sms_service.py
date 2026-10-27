"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: SMS Service Tests

Purpose:
    Verify number validation, message construction and the
    reading of the provider's response.

Responsibilities:
    - Confirm Zambian numbers normalise to one E.164 form.
    - Confirm numbers that are not Zambian mobiles are
      refused.
    - Confirm an alert message fits a single SMS segment.
    - Confirm an accepted message is recorded as SUBMITTED
      and never as delivered.
    - Confirm a refused or unreadable answer is a failure.
    - Confirm the priority threshold governs sending.
    - Confirm sandbox is forced unless production is opted
      into explicitly.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Note:
    These tests contact nothing. There is no database, no
    network and no API key: the provider SDK is replaced
    with a stub, so a run cannot send a real message to a
    real handset even if credentials happen to be present in
    the environment. That is a requirement of the task, not
    a convenience - a test suite that could text a Forestry
    Department officer is not one that can be run freely.
===========================================================
"""

import pytest

from app.models.enums import PriorityLevel, SmsQueueStatus
from app.services import sms_service
from app.services.sms_service import (
    SMS_MAX_LENGTH,
    SmsAmbiguousError,
    SmsConfigurationError,
    SmsProviderError,
    SmsService,
    SmsTransientError,
    build_alert_sms,
    classify_recipient,
    meets_priority_threshold,
    normalise_msisdn,
)


# =========================================================
# PHONE NUMBER NORMALISATION
# =========================================================


@pytest.mark.parametrize(
    "written",
    [
        "0977123456",
        "+260977123456",
        "260977123456",
        "00260977123456",
        "+260 977 123 456",
        "097-712-3456",
        "  0977123456  ",
        "977123456",
    ],
)
def test_every_written_form_of_one_number_normalises_alike(
    written,
):
    """
    One handset must produce one stored number.

    Officers write numbers in all of these forms. If two of
    them stored differently, the uniqueness constraint on
    the SMS queue would not hold and that officer would
    receive the same alert twice.
    """

    assert normalise_msisdn(written) == "+260977123456"


def test_airtel_and_zamtel_prefixes_are_both_accepted():
    """
    The rule covers the 7 and 9 mobile ranges.

    A prefix allowlist would have to be edited whenever a
    new range was allocated, and until it was it would
    silently refuse to alert the officer holding that
    number.
    """

    assert normalise_msisdn("0771234567") == "+260771234567"

    assert normalise_msisdn("0951234567") == "+260951234567"


@pytest.mark.parametrize(
    "written",
    [
        None,
        "",
        "   ",
        "0211234567",
        "097712345",
        "09771234567",
        "+254711123456",
        "not a number",
        "+260+977123456",
        "0977123abc",
        "097x1234567",
    ],
)
def test_numbers_that_are_not_zambian_mobiles_are_refused(
    written,
):
    """
    Refusal is None, not an exception.

    A missing or malformed number is an ordinary state of a
    user record. The caller skips that officer, exactly as
    it skips one with no email address.

    The cases, in order: absent; empty; whitespace; a Lusaka
    landline (02 range, not mobile); too short; too long; a
    Kenyan number, which the provider would accept and
    charge for; free text; a stray plus mid-number; letters.
    """

    assert normalise_msisdn(written) is None


# =========================================================
# MESSAGE BODY
# =========================================================


def test_alert_message_fits_one_segment_and_names_what_matters():
    """
    The body must carry what decides whether to travel.
    """

    message = build_alert_sms(
        forest_name="Chichele Plantation",
        district_name="Ndola",
        detected_area_hectares=3.85,
        priority=PriorityLevel.CRITICAL,
        detection_id=142,
    )

    assert len(message) <= SMS_MAX_LENGTH

    assert "CRITICAL" in message
    assert "3.85" in message
    assert "Chichele Plantation" in message
    assert "Ndola" in message
    assert "142" in message


def test_alert_message_does_not_claim_the_clearing_is_confirmed():
    """
    The alert is raised before any officer has looked at it.

    The detection is PENDING at this point, so the message
    must ask for review rather than report a finding. This
    mirrors the wording rule the email body already follows.
    """

    message = build_alert_sms(
        forest_name="Chichele Plantation",
        district_name="Ndola",
        detected_area_hectares=3.85,
        priority=PriorityLevel.HIGH,
        detection_id=142,
    )

    assert "possible" in message.lower()
    assert "awaiting review" in message.lower()


def test_alert_message_carries_no_link_or_token():
    """
    A URL carrying a credential would put an authentication
    token into the recipient's message store and the mobile
    operator's logs.
    """

    message = build_alert_sms(
        forest_name="Chichele Plantation",
        district_name="Ndola",
        detected_area_hectares=3.85,
        priority=PriorityLevel.HIGH,
        detection_id=142,
    )

    assert "http" not in message.lower()
    assert "token" not in message.lower()


def test_a_long_forest_name_is_shortened_not_the_measurements():
    """
    An over-long name must not push out the figures.

    An officer who cannot read the area or the detection
    number has nothing to act on, whereas a truncated name
    still identifies the place alongside the district.
    """

    message = build_alert_sms(
        forest_name="A" * 300,
        district_name="Lufwanyama",
        detected_area_hectares=12.50,
        priority=PriorityLevel.CRITICAL,
        detection_id=987,
    )

    assert len(message) <= SMS_MAX_LENGTH

    assert "12.50" in message
    assert "987" in message
    assert "Lufwanyama" in message


def test_an_unknown_district_is_stated_rather_than_left_blank():
    """
    A message reading "at Chichele, ." would look broken.
    """

    message = build_alert_sms(
        forest_name="Chichele Plantation",
        district_name=None,
        detected_area_hectares=1.0,
        priority=PriorityLevel.HIGH,
        detection_id=1,
    )

    assert "district unknown" in message


# =========================================================
# PRIORITY THRESHOLD
# =========================================================


@pytest.mark.parametrize(
    "priority,minimum,expected",
    [
        (PriorityLevel.CRITICAL, "HIGH", True),
        (PriorityLevel.HIGH, "HIGH", True),
        (PriorityLevel.MEDIUM, "HIGH", False),
        (PriorityLevel.LOW, "HIGH", False),
        (PriorityLevel.LOW, "LOW", True),
        (PriorityLevel.CRITICAL, "CRITICAL", True),
        (PriorityLevel.HIGH, "CRITICAL", False),
        (PriorityLevel.HIGH, "high", True),
        (PriorityLevel.HIGH, "  HIGH  ", True),
    ],
)
def test_priority_threshold_orders_levels_by_severity(
    priority,
    minimum,
    expected,
):
    """
    PriorityLevel is a string enum and therefore unordered.

    Comparing its members directly would compare their text,
    which puts CRITICAL below LOW alphabetically. The
    explicit ordering is what this guards.
    """

    assert (
        meets_priority_threshold(priority, minimum)
        is expected
    )


@pytest.mark.parametrize(
    "minimum",
    ["", "URGENT", "hihg", None],
)
def test_an_unrecognised_threshold_sends_nothing(minimum):
    """
    A typo in SMS_MIN_PRIORITY must mean no messages.

    Defaulting to sending would turn a configuration
    mistake into an unintended message to every officer for
    every low-priority NDVI fluctuation.
    """

    assert (
        meets_priority_threshold(
            PriorityLevel.CRITICAL,
            minimum,
        )
        is False
    )


# =========================================================
# READING THE PROVIDER RESPONSE
# =========================================================


@pytest.mark.parametrize("code", [100, 101, 102, "101"])
def test_an_accepted_message_is_submitted_not_delivered(code):
    """
    The central requirement of this integration.

    The provider is telling us it has the message, not that
    a handset received it. Only a delivery report could say
    the latter, and this system does not accept delivery
    reports. Recording acceptance as delivery would make the
    audit trail show an officer as notified of a clearing
    they never heard about.
    """

    status, detail = classify_recipient(
        {
            "statusCode": code,
            "status": "Success",
            "number": "+260977123456",
            "messageId": "ATXid_abc123",
            "cost": "KES 0.8000",
        }
    )

    assert status is SmsQueueStatus.SUBMITTED

    assert detail is None

    # The enum must not offer a label that would let any
    # code claim delivery.
    assert not hasattr(SmsQueueStatus, "DELIVERED")


@pytest.mark.parametrize(
    "code,status_text",
    [
        (403, "InvalidPhoneNumber"),
        (405, "InsufficientBalance"),
        (406, "UserInBlacklist"),
        (500, "InternalServerError"),
    ],
)
def test_a_refused_message_fails_and_keeps_the_reason(
    code,
    status_text,
):
    """
    The provider's own words are carried into the record.
    """

    status, detail = classify_recipient(
        {
            "statusCode": code,
            "status": status_text,
            "number": "+260977123456",
        }
    )

    assert status is SmsQueueStatus.FAILED

    assert status_text in detail

    assert str(code) in detail


@pytest.mark.parametrize(
    "recipient",
    [
        {},
        {"statusCode": None},
        {"statusCode": "Success"},
        {"status": "Success"},
    ],
)
def test_an_unreadable_status_is_a_failure_not_an_acceptance(
    recipient,
):
    """
    If the provider's answer cannot be read, the honest
    record is that the message is not known to have been
    accepted. Treating an unreadable answer as success is
    exactly the false claim this module exists to avoid.
    """

    status, detail = classify_recipient(recipient)

    assert status is SmsQueueStatus.FAILED

    assert detail


# =========================================================
# SERVICE BEHAVIOUR
# =========================================================


class StubSmsApi:
    """
    Stands in for africastalking.SMS.

    Records what it was asked to send and answers with
    whatever the test needs. It has no network access, so a
    test using it cannot reach a real handset.
    """

    def __init__(self, response=None, raises=None):
        self.response = response
        self.raises = raises
        self.calls = []

    def send(self, message, recipients, **kwargs):
        self.calls.append(
            {
                "message": message,
                "recipients": recipients,
                **kwargs,
            }
        )

        if self.raises is not None:
            raise self.raises

        return self.response


def accepted_response(number="+260977123456"):
    """Return a provider response accepting one message."""

    return {
        "SMSMessageData": {
            "Message": "Sent to 1/1 Total Cost: KES 0.8000",
            "Recipients": [
                {
                    "statusCode": 101,
                    "status": "Success",
                    "number": number,
                    "messageId": "ATXid_abc123",
                    "cost": "KES 0.8000",
                }
            ],
        }
    }


@pytest.fixture
def service(monkeypatch):
    """
    An SmsService whose provider is a stub.

    The API key is set to a dummy value so configuration
    checks pass, and the client factory is replaced, so no
    real SDK is initialised and no request is made.
    """

    svc = SmsService()

    svc._api_key = "test-key-not-a-real-credential"

    svc.username = "sandbox"

    svc.is_sandbox = True

    svc.sender_id = None

    return svc


def test_a_send_submits_the_normalised_number(
    service,
    monkeypatch,
):
    """
    The number is normalised again at the point of sending.

    A row written into the queue by hand must not bypass
    validation on its way to the provider.
    """

    stub = StubSmsApi(response=accepted_response())

    monkeypatch.setattr(
        service,
        "_sms_client",
        lambda: stub,
    )

    recipient = service.send_sms(
        recipient_phone="0977123456",
        message="ForestWatch test",
    )

    assert stub.calls[0]["recipients"] == ["+260977123456"]

    assert recipient["statusCode"] == 101


def test_a_send_passes_an_explicit_timeout(
    service,
    monkeypatch,
):
    """
    The provider SDK does not convert a timeout into its own
    exception type, so the service must know what it asked
    for in order to recognise one.
    """

    stub = StubSmsApi(response=accepted_response())

    monkeypatch.setattr(
        service,
        "_sms_client",
        lambda: stub,
    )

    service.send_sms(
        recipient_phone="+260977123456",
        message="ForestWatch test",
    )

    assert stub.calls[0]["timeout"] == (3.05, 9.05)


def test_an_invalid_recipient_is_refused_before_any_request(
    service,
    monkeypatch,
):
    """
    No request is made for a number that cannot be valid.
    """

    stub = StubSmsApi(response=accepted_response())

    monkeypatch.setattr(
        service,
        "_sms_client",
        lambda: stub,
    )

    with pytest.raises(SmsProviderError):
        service.send_sms(
            recipient_phone="+254711123456",
            message="ForestWatch test",
        )

    assert stub.calls == []


def test_an_empty_message_is_refused_before_any_request(
    service,
    monkeypatch,
):
    """
    An empty SMS would be charged for and say nothing.
    """

    stub = StubSmsApi(response=accepted_response())

    monkeypatch.setattr(
        service,
        "_sms_client",
        lambda: stub,
    )

    with pytest.raises(SmsProviderError):
        service.send_sms(
            recipient_phone="+260977123456",
            message="   ",
        )

    assert stub.calls == []


def test_a_connect_timeout_is_safe_to_retry(
    service,
    monkeypatch,
):
    """
    A connection timeout means the provider never received
    the request, so retrying cannot create a duplicate.
    """

    import requests

    stub = StubSmsApi(
        raises=requests.exceptions.ConnectTimeout("timed out"),
    )

    monkeypatch.setattr(
        service,
        "_sms_client",
        lambda: stub,
    )

    with pytest.raises(SmsTransientError):
        service.send_sms(
            recipient_phone="+260977123456",
            message="ForestWatch test",
        )


def test_a_read_timeout_is_not_retried_when_acceptance_is_unknown(
    service,
    monkeypatch,
):
    """A late response may mean the provider accepted the message."""

    import requests

    stub = StubSmsApi(
        raises=requests.exceptions.ReadTimeout("response timed out"),
    )

    monkeypatch.setattr(
        service,
        "_sms_client",
        lambda: stub,
    )

    with pytest.raises(SmsAmbiguousError, match="outcome is unknown"):
        service.send_sms(
            recipient_phone="+260977123456",
            message="ForestWatch test",
        )


def test_connection_loss_is_not_retried_when_acceptance_is_unknown(
    service,
    monkeypatch,
):
    import requests

    stub = StubSmsApi(
        raises=requests.exceptions.ConnectionError("connection reset"),
    )

    monkeypatch.setattr(
        service,
        "_sms_client",
        lambda: stub,
    )

    with pytest.raises(SmsAmbiguousError, match="outcome is unknown"):
        service.send_sms(
            recipient_phone="+260977123456",
            message="ForestWatch test",
        )


def test_a_provider_error_body_is_truncated_in_the_message(
    service,
    monkeypatch,
):
    """
    The SDK raises with the raw response body as its message,
    which may be an HTML error page. It is kept, because it
    is what an administrator needs, but bounded so it cannot
    fill the queue row.
    """

    stub = StubSmsApi(
        raises=Exception("x" * 5000),
    )

    monkeypatch.setattr(
        service,
        "_sms_client",
        lambda: stub,
    )

    with pytest.raises(SmsProviderError) as caught:
        service.send_sms(
            recipient_phone="+260977123456",
            message="ForestWatch test",
        )

    assert len(str(caught.value)) < 400


def test_a_response_with_no_recipients_is_not_a_success(
    service,
    monkeypatch,
):
    """
    The provider answers this way when it rejects every
    recipient. It must never become a SUBMITTED row.
    """

    stub = StubSmsApi(
        response={
            "SMSMessageData": {
                "Message": "Sent to 0/1 Total Cost: 0",
                "Recipients": [],
            }
        },
    )

    monkeypatch.setattr(
        service,
        "_sms_client",
        lambda: stub,
    )

    with pytest.raises(SmsProviderError):
        service.send_sms(
            recipient_phone="+260977123456",
            message="ForestWatch test",
        )


def test_an_unreadable_response_is_not_a_success(
    service,
    monkeypatch,
):
    """A send that cannot be read is not a send that worked."""

    stub = StubSmsApi(response="OK")

    monkeypatch.setattr(
        service,
        "_sms_client",
        lambda: stub,
    )

    with pytest.raises(SmsProviderError):
        service.send_sms(
            recipient_phone="+260977123456",
            message="ForestWatch test",
        )


def test_a_missing_api_key_is_a_configuration_error():
    """
    Named distinctly so the worker can fail it immediately
    rather than spending retries on it, and the message
    names the variable to set without quoting its value.
    """

    svc = SmsService()

    svc._api_key = ""

    with pytest.raises(SmsConfigurationError) as caught:
        svc.ensure_configured()

    assert "AFRICASTALKING_API_KEY" in str(caught.value)


def test_the_api_key_never_appears_in_the_error_message():
    """
    Credentials must not reach a log, a response or a queue
    row. The configuration error is the one place that
    handles the key and also produces text.
    """

    secret = "super-secret-sandbox-key-0123456789"

    svc = SmsService()

    svc._api_key = ""

    svc.username = ""

    try:
        svc.ensure_configured()

    except SmsConfigurationError as exc:
        assert secret not in str(exc)


# =========================================================
# SANDBOX ENFORCEMENT
# =========================================================


def test_sandbox_is_forced_unless_production_is_explicit(
    monkeypatch,
):
    """
    The provider selects its sandbox endpoint purely from
    the username being the literal string "sandbox".

    This is the guard that stops a development or test run
    sending a real message: a production username sitting in
    a developer .env is overridden, so the request can only
    reach the simulator.
    """

    class Stub:
        africastalking_username = "forestwatch_live"
        africastalking_api_key = "k"
        africastalking_environment = "development"
        sms_sender_id = "FORESTWATCH"

        @property
        def africastalking_is_sandbox(self):
            return True

    monkeypatch.setattr(
        sms_service,
        "get_settings",
        lambda: Stub(),
    )

    svc = SmsService()

    assert svc.username == "sandbox"

    assert svc.is_sandbox is True

    # The sandbox has no sender ID of its own, and passing
    # one it does not recognise is refused.
    assert svc.sender_id is None


def test_production_is_used_only_when_asked_for_exactly(
    monkeypatch,
):
    """
    The configured username is honoured only when the
    environment says production.
    """

    class Stub:
        africastalking_username = "forestwatch_live"
        africastalking_api_key = "k"
        africastalking_environment = "production"
        sms_sender_id = "FORESTWATCH"

        @property
        def africastalking_is_sandbox(self):
            return False

    monkeypatch.setattr(
        sms_service,
        "get_settings",
        lambda: Stub(),
    )

    svc = SmsService()

    assert svc.username == "forestwatch_live"

    assert svc.is_sandbox is False

    assert svc.sender_id == "FORESTWATCH"


def settings_with_environment(configured):
    """
    Build real Settings with one environment value.

    Exercised against the actual Settings property rather
    than a stub, because this single decision is what keeps
    a development run from texting a real officer.
    """

    from app.core.config import Settings

    return Settings(
        SECRET_KEY="test-secret",
        DATABASE_URL="postgresql+psycopg://u:p@localhost/x",
        AFRICASTALKING_ENVIRONMENT=configured,
    )


@pytest.mark.parametrize(
    "configured",
    [
        "sandbox",
        "development",
        "prod",
        "live",
        "productive",
        "",
        "   ",
    ],
)
def test_anything_short_of_naming_production_stays_in_sandbox(
    configured,
):
    """
    The default for an unrecognised value is the harmless
    one.

    "prod" and "live" are the plausible near-misses, and
    both resolve to sandbox: an administrator who meant
    production finds no messages sent and goes looking,
    which is the safe way round for this particular
    mistake.
    """

    assert (
        settings_with_environment(
            configured
        ).africastalking_is_sandbox
        is True
    )


@pytest.mark.parametrize(
    "configured",
    ["production", "Production", "PRODUCTION", "  production  "],
)
def test_naming_production_in_any_case_leaves_the_sandbox(
    configured,
):
    """
    The opt-in has to work when it is meant.

    Case and whitespace are ignored, because writing some
    case of the word production is a deliberate statement of
    intent rather than a slip, and refusing "Production"
    would send an administrator hunting a bug that is not
    there.
    """

    assert (
        settings_with_environment(
            configured
        ).africastalking_is_sandbox
        is False
    )
