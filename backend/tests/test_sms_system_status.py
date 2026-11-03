"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Tests: SMS system status

What these protect:

    The system must not report SMS as working because an
    API key is present in its configuration. That was the
    original fault, and it was not theoretical: a truncated
    key sat in .env, the Settings page reported the channel
    as configured, and every message was refused by the
    provider with "The supplied authentication is invalid".
    Nothing in the system said so until an officer pressed
    Send Test SMS and read the error.

    So "Active" now means one thing only: the provider was
    asked and accepted these credentials. Every test here
    exists to keep some other condition from being mistaken
    for that.

No test here contacts Africa's Talking. The SDK is stubbed
in each one, which is what the sms_credential_check marker
declares.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia
===========================================================
"""

from types import SimpleNamespace

import pytest
import requests

from app.services import sms_service as sms_service_module
from app.services.sms_registration import sms_settings_for
from app.services.sms_service import (
    ProviderCheck,
    SmsService,
    SmsSystemStatus,
    reset_sms_system_status_cache,
    sms_system_status,
)


pytestmark = pytest.mark.sms_credential_check


REAL_LOOKING_KEY = "atsk_0123456789abcdef0123456789abcdef"


# =========================================================
# STUBS
# =========================================================


class StubSms:
    """
    Stands in for africastalking.SMS.

    Records what it was asked so a test can assert that the
    check used a timeout and did not send anything, and
    answers with either a result or an exception.
    """

    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []
        self.sends = []

    def fetch_messages(self, last_received_id=None, timeout=None):
        self.calls.append(
            {
                "last_received_id": last_received_id,
                "timeout": timeout,
            }
        )

        if self.error is not None:
            raise self.error

        return self.result

    def send(self, *args, **kwargs):
        # Recorded so a test can prove the check never
        # sends a message. Nothing should ever call this.
        self.sends.append({"args": args, "kwargs": kwargs})

        raise AssertionError(
            "The credential check must not send an SMS."
        )


def messaging_response():
    """A successful answer from the messaging endpoint."""

    return {"SMSMessageData": {"Messages": []}}


def settings_stub(
    sms_enabled=True,
    api_key=REAL_LOOKING_KEY,
    username="sandbox",
    environment="sandbox",
):
    """Configuration for one test, without reading .env."""

    return SimpleNamespace(
        sms_enabled=sms_enabled,
        africastalking_username=username,
        africastalking_api_key=api_key,
        africastalking_environment=environment,
        africastalking_is_sandbox=environment != "production",
        sms_sender_id="",
    )


@pytest.fixture
def provider(monkeypatch):
    """
    Install a stubbed provider SDK.

    Returns a function that takes the StubSms to
    answer with. initialize is replaced as well, so no real
    credentials are ever handed to the SDK and no network
    call is possible.
    """

    import africastalking

    monkeypatch.setattr(
        africastalking,
        "initialize",
        lambda username, api_key: None,
    )

    def install(sms):
        monkeypatch.setattr(
            africastalking,
            "SMS",
            sms,
        )

        return sms

    return install


@pytest.fixture(autouse=True)
def clean_status_cache():
    """No remembered answer leaks between these tests."""

    reset_sms_system_status_cache()

    yield

    reset_sms_system_status_cache()


def configured(monkeypatch, **kwargs):
    """Point the service at a stubbed configuration."""

    stub = settings_stub(**kwargs)

    monkeypatch.setattr(
        sms_service_module,
        "get_settings",
        lambda: stub,
    )

    return stub


# =========================================================
# THE FIVE STATES
# =========================================================


def test_accepted_credentials_are_reported_as_active(
    monkeypatch,
    provider,
):
    """The one case that may be called Active."""

    configured(monkeypatch)

    provider(StubSms(result=messaging_response()))

    check = SmsService().check_credentials()

    assert check.status is SmsSystemStatus.ACTIVE

    assert check.can_send is True

    # Active is a claim about what the provider said, so it
    # may only be made when the provider actually answered.
    assert check.verified_with_provider is True


def test_an_absent_key_is_missing_credentials(
    monkeypatch,
    provider,
):
    """Nothing was configured, so nothing was asked."""

    configured(monkeypatch, api_key="")

    stub = provider(StubSms(result=messaging_response()))

    check = SmsService().check_credentials()

    assert check.status is SmsSystemStatus.MISSING_CREDENTIALS

    assert check.can_send is False

    # No request is made when there is nothing to send.
    assert stub.calls == []

    # The variable to set is named; its value never is.
    assert "AFRICASTALKING_API_KEY" in check.detail


def test_a_rejected_key_is_invalid_credentials(
    monkeypatch,
    provider,
):
    """
    The failure this whole module exists for.

    A key is present, so every check short of asking the
    provider would call this channel configured. The
    provider refuses it.
    """

    import africastalking

    configured(monkeypatch)

    provider(
        StubSms(
            error=africastalking.Service.AfricasTalkingException(
                "The supplied authentication is invalid"
            )
        )
    )

    check = SmsService().check_credentials()

    assert check.status is SmsSystemStatus.INVALID_CREDENTIALS

    assert check.can_send is False

    # The provider's own words survive, because they are
    # what tells an administrator which key is wrong.
    assert "authentication is invalid" in check.detail


def test_an_unreachable_provider_is_a_provider_error(
    monkeypatch,
    provider,
):
    """A connection fault is not a credential fault."""

    configured(monkeypatch)

    provider(
        StubSms(
            error=requests.exceptions.ConnectionError(
                "connection refused"
            )
        )
    )

    check = SmsService().check_credentials()

    assert check.status is SmsSystemStatus.PROVIDER_ERROR

    assert check.can_send is False

    assert "could not be reached" in check.detail


def test_a_timeout_is_a_provider_error(
    monkeypatch,
    provider,
):
    """The provider did not answer in time."""

    configured(monkeypatch)

    provider(
        StubSms(
            error=requests.exceptions.Timeout("too slow")
        )
    )

    check = SmsService().check_credentials()

    assert check.status is SmsSystemStatus.PROVIDER_ERROR


def test_an_unrecognised_fault_is_never_reported_as_active(
    monkeypatch,
    provider,
):
    """
    A fault whose wording this code does not know.

    It is reported as a provider error rather than guessed
    at. The safe direction for an unknown answer is "we
    cannot say messages are being sent", never "Active".
    """

    import africastalking

    configured(monkeypatch)

    provider(
        StubSms(
            error=africastalking.Service.AfricasTalkingException(
                "Service temporarily unavailable"
            )
        )
    )

    check = SmsService().check_credentials()

    assert check.status is SmsSystemStatus.PROVIDER_ERROR

    assert check.can_send is False


def test_the_switch_being_off_is_reported_without_asking(
    monkeypatch,
    provider,
):
    """
    SMS_ENABLED off means nothing is sent to anybody.

    There is nothing to ask the provider in that case, and
    an installation that has never configured SMS should
    make no outbound request at all.
    """

    configured(monkeypatch, sms_enabled=False)

    stub = provider(StubSms(result=messaging_response()))

    check = sms_system_status()

    assert check.status is SmsSystemStatus.DISABLED

    assert check.can_send is False

    assert stub.calls == []

    assert check.verified_with_provider is False


def test_the_check_asks_the_messaging_endpoint_not_the_account(
    monkeypatch,
    provider,
):
    """
    The regression that reported a working channel as broken.

    The first version of this check asked the account
    endpoint, which reports the balance. On this project's
    own production account that endpoint answers 401 to a
    key that sends SMS perfectly well, so the Settings page
    showed INVALID_CREDENTIALS while a real message went
    out, was accepted and was charged for.

    A permission on the account endpoint is not the
    permission being asked about. The check belongs in the
    same endpoint family as sending.
    """

    import africastalking

    configured(monkeypatch)

    stub = provider(StubSms(result=messaging_response()))

    # The account endpoint refuses this key, as the real one
    # did. It must make no difference.
    class RefusingApplication:
        def fetch_application_data(self, timeout=None):
            raise africastalking.Service.AfricasTalkingException(
                "The supplied authentication is invalid"
            )

    monkeypatch.setattr(
        africastalking,
        "Application",
        RefusingApplication(),
    )

    check = SmsService().check_credentials()

    assert check.status is SmsSystemStatus.ACTIVE

    # It asked the messaging endpoint...
    assert len(stub.calls) == 1

    # ...as a read, for nothing in particular, and sent no
    # message in the process.
    assert stub.calls[0]["last_received_id"] == 0

    assert stub.sends == []


# =========================================================
# DIAGNOSTICS
#
# "The supplied authentication is invalid" is the same
# sentence whether no key was loaded, a key was loaded
# under a name nothing reads, or a good key was paired
# with the wrong username. These make the difference
# visible without printing the key.
# =========================================================


def test_the_summary_names_the_configuration_without_the_key(
    monkeypatch,
):
    configured(monkeypatch, environment="production", username="forestwatchzambia")

    summary = SmsService().configuration_summary()

    assert "forestwatchzambia" in summary

    assert "production" in summary

    assert "api.africastalking.com" in summary

    # A length, which distinguishes a key that was never
    # loaded from one truncated in copying, but never the
    # key itself.
    assert str(len(REAL_LOOKING_KEY)) in summary

    assert REAL_LOOKING_KEY not in summary


def test_the_summary_says_plainly_when_no_key_was_loaded(
    monkeypatch,
):
    """
    The fault that produced no key at all: credentials
    present in .env under a name the application does not
    read, ignored in silence by the settings loader.
    """

    configured(monkeypatch, api_key="")

    summary = SmsService().configuration_summary()

    assert "NOT LOADED" in summary


def test_a_key_stored_under_the_wrong_name_is_called_out(
    monkeypatch,
):
    configured(monkeypatch, api_key="")

    warnings = SmsService().configuration_warnings()

    assert any("AFRICASTALKING_API_KEY" in w for w in warnings)

    assert any("any other name is ignored" in w for w in warnings)


def test_a_username_silently_overridden_to_sandbox_is_called_out(
    monkeypatch,
):
    """
    A production username and key with the environment
    still naming sandbox. The service overrides the
    username to 'sandbox' by design, the provider refuses
    the pair, and nothing said that the username in .env
    was not the one being used.
    """

    configured(
        monkeypatch,
        username="forestwatchzambia",
        environment="sandbox",
    )

    warnings = SmsService().configuration_warnings()

    overrides = [w for w in warnings if "overridden" in w]

    assert overrides

    assert "forestwatchzambia" in overrides[0]

    assert "AFRICASTALKING_ENVIRONMENT=production" in overrides[0]


def test_the_sandbox_username_on_production_is_called_out(
    monkeypatch,
):
    configured(
        monkeypatch,
        username="sandbox",
        environment="production",
    )

    warnings = SmsService().configuration_warnings()

    assert any("does not accept the sandbox username" in w for w in warnings)


def test_an_environment_that_is_neither_word_is_called_out(
    monkeypatch,
):
    """
    Only the exact word production selects production. A
    value like 'prod' or 'live' resolves to sandbox, which
    is the safe default but a surprising one.
    """

    configured(
        monkeypatch,
        username="forestwatchzambia",
        environment="live",
    )

    warnings = SmsService().configuration_warnings()

    assert any("not 'production'" in w for w in warnings)


def test_a_sound_configuration_raises_no_warnings(
    monkeypatch,
):
    configured(
        monkeypatch,
        username="forestwatchzambia",
        environment="production",
    )

    assert SmsService().configuration_warnings() == []


def test_no_warning_ever_contains_the_key(
    monkeypatch,
):
    for environment in ("sandbox", "production", "live"):
        for username in ("sandbox", "forestwatchzambia"):
            configured(
                monkeypatch,
                username=username,
                environment=environment,
            )

            service = SmsService()

            joined = " ".join(
                service.configuration_warnings()
            ) + service.configuration_summary()

            assert REAL_LOOKING_KEY not in joined


# =========================================================
# WHAT MUST NEVER LEAK
# =========================================================


def test_the_api_key_never_appears_in_a_reported_detail(
    monkeypatch,
    provider,
):
    """
    A credential on a web page outlives the page.

    The provider sends the key in a header and does not
    echo it, so this should never trigger. It is checked
    because the cost of being wrong is a working credential
    rendered in a browser.
    """

    import africastalking

    configured(monkeypatch)

    provider(
        StubSms(
            error=africastalking.Service.AfricasTalkingException(
                f"Rejected key {REAL_LOOKING_KEY} for sandbox"
            )
        )
    )

    check = SmsService().check_credentials()

    assert REAL_LOOKING_KEY not in check.detail

    assert "***" in check.detail


def test_the_check_asks_with_a_timeout(
    monkeypatch,
    provider,
):
    """
    An officer is waiting on a page while this runs.

    Without an explicit timeout the SDK's default read
    timeout would hold the Settings page for nine seconds
    on an unreachable provider.
    """

    configured(monkeypatch)

    stub = provider(StubSms(result=messaging_response()))

    SmsService().check_credentials()

    assert stub.calls[0]["timeout"] == SmsService.CHECK_TIMEOUT_SECONDS


# =========================================================
# CACHING
#
# The check runs whenever an officer opens the Settings
# page. Without a cache that is one request to a third
# party per page load, and the page waits for each.
# =========================================================


def test_a_recent_answer_is_reused_rather_than_asked_again(
    monkeypatch,
    provider,
):
    configured(monkeypatch)

    stub = provider(StubSms(result=messaging_response()))

    first = sms_system_status()

    second = sms_system_status()

    assert first.status is SmsSystemStatus.ACTIVE

    assert second.status is SmsSystemStatus.ACTIVE

    assert len(stub.calls) == 1


def test_a_forced_check_asks_again(
    monkeypatch,
    provider,
):
    """
    What the scheduler uses at startup.

    An administrator restarting after correcting a key must
    see the real answer, not one remembered from before the
    correction.
    """

    configured(monkeypatch)

    stub = provider(StubSms(result=messaging_response()))

    sms_system_status()

    sms_system_status(force=True)

    assert len(stub.calls) == 2


def test_a_failure_is_remembered_for_less_time_than_a_success(
):
    """
    An administrator who has just fixed a key should see the
    status recover within a minute, not wait five.
    """

    assert (
        sms_service_module.FAILED_STATUS_CACHE_SECONDS
        < sms_service_module.STATUS_CACHE_SECONDS
    )


# =========================================================
# WHAT THE OFFICER'S PAGE IS TOLD
# =========================================================


def officer(phone_number="+260977123456"):
    return SimpleNamespace(
        id=3,
        full_name="Kitwe Officer",
        phone_number=phone_number,
        sms_notifications_enabled=True,
    )


def test_the_page_is_told_sending_is_off_when_a_key_is_rejected(
    monkeypatch,
):
    """
    The end-to-end point of the change.

    A key is configured. The provider refuses it. The page
    must not describe this as a working channel.
    """

    configured(monkeypatch)

    monkeypatch.setattr(
        SmsService,
        "check_credentials",
        lambda self: ProviderCheck(
            status=SmsSystemStatus.INVALID_CREDENTIALS,
            detail="The SMS provider rejected the credentials.",
            verified_with_provider=True,
        ),
    )

    reported = sms_settings_for(officer())

    assert reported["automatic_sending_enabled"] is False

    assert reported["system_status"] == "INVALID_CREDENTIALS"

    assert "rejected" in reported["system_detail"]


def test_the_page_reports_sending_on_only_for_an_active_check(
    monkeypatch,
):
    configured(monkeypatch)

    monkeypatch.setattr(
        SmsService,
        "check_credentials",
        lambda self: ProviderCheck(
            status=SmsSystemStatus.ACTIVE,
            detail="The SMS provider accepted the credentials.",
            verified_with_provider=True,
        ),
    )

    reported = sms_settings_for(officer())

    assert reported["automatic_sending_enabled"] is True

    assert reported["system_status"] == "ACTIVE"


def test_every_non_active_state_reports_sending_as_off(
    monkeypatch,
):
    """
    No state other than ACTIVE may report the channel as
    sending. Stated as one test over all of them so a state
    added later cannot quietly default to True.
    """

    # SMS switched on, so the switch cannot short-circuit
    # the answer and make every state read as DISABLED on a
    # machine whose .env has it off.
    configured(monkeypatch)

    for status in SmsSystemStatus:
        if status is SmsSystemStatus.ACTIVE:
            continue

        monkeypatch.setattr(
            SmsService,
            "check_credentials",
            lambda self, status=status: ProviderCheck(
                status=status,
                detail="stubbed",
            ),
        )

        reset_sms_system_status_cache()

        reported = sms_settings_for(officer())

        assert reported["automatic_sending_enabled"] is False, status

        assert reported["system_status"] == status.value
