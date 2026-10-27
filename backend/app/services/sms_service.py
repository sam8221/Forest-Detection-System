"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: SMS Service

Purpose:
    Sends deforestation alert SMS messages to Forestry
    Officers through Africa's Talking.

Responsibilities:
    - Normalise and validate Zambian mobile numbers.
    - Build a short alert message that fits one SMS.
    - Submit messages to the provider.
    - Classify the provider's answer honestly.
    - Separate configuration faults from transport faults.

What this module will not do:
    It will not report a message as delivered. The provider
    answers whether it accepted a message for delivery,
    which is a different claim, and the two are kept
    distinct throughout. See classify_recipient.

Security:
    The API key is read from configuration and passed to the
    provider SDK, which sends it in a request header. It is
    never logged, never formatted into an error message and
    never returned to a caller. Nothing in this module puts
    it in a string.

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

import logging
import re

from app.core.config import get_settings
from app.models.enums import PriorityLevel, SmsQueueStatus


logger = logging.getLogger(__name__)


# =========================================================
# ERRORS
#
# Four types, because the worker must treat them
# differently. Collapsing them into one would mean either
# retrying a missing API key three times or giving up on a
# network blip at the first attempt.
# =========================================================


class SmsError(Exception):
    """Base class for SMS failures."""


class SmsConfigurationError(SmsError):
    """
    The service is not configured, or is misconfigured.

    Not transient. Retrying changes nothing, so the worker
    fails the message immediately rather than consuming
    attempts writing the same error three times.
    """


class SmsTransientError(SmsError):
    """
    The provider could not be reached this time.

    A connection timeout before a connection was established.
    The request could not have been accepted, so a retry is safe.
    """


class SmsAmbiguousError(SmsError):
    """The request may have been accepted, so retrying could duplicate it."""


class SmsProviderError(SmsError):
    """
    The provider was reached and refused the message.

    An invalid number, a rejected sender ID, an exhausted
    balance. Retrying the same message will be refused the
    same way, so the worker treats this as terminal.
    """


# =========================================================
# PRIORITY ORDERING
#
# PriorityLevel is a string enum and therefore unordered;
# comparing its members directly would compare their text,
# which would make CRITICAL < LOW. The ordering is declared
# here because this module is where it is needed.
# =========================================================

PRIORITY_ORDER: dict[PriorityLevel, int] = {
    PriorityLevel.LOW: 0,
    PriorityLevel.MEDIUM: 1,
    PriorityLevel.HIGH: 2,
    PriorityLevel.CRITICAL: 3,
}


def meets_priority_threshold(
    priority: PriorityLevel,
    minimum: str,
) -> bool:
    """
    Decide whether an alert priority earns an SMS.

    Args:
        priority:
            The alert's priority.
        minimum:
            Configured minimum, as the name of a
            PriorityLevel member. Case and surrounding
            whitespace are ignored.

    Returns:
        True when the alert is at or above the configured
        minimum.

    An unrecognised minimum returns False rather than
    defaulting to sending everything. A typo in
    SMS_MIN_PRIORITY should mean no messages and a log line
    to find, not an unintended message to every officer for
    every low-priority NDVI fluctuation.
    """

    try:
        floor = PriorityLevel(minimum.strip().upper())

    except (AttributeError, ValueError):
        logger.warning(
            "SMS_MIN_PRIORITY is not a valid priority "
            "level, so no alert SMS will be queued. "
            "Expected one of: %s",
            ", ".join(level.value for level in PriorityLevel),
        )

        return False

    return (
        PRIORITY_ORDER[priority]
        >= PRIORITY_ORDER[floor]
    )


# =========================================================
# PHONE NUMBERS
# =========================================================

# Zambia is country code 260. A subscriber number is nine
# digits, and mobile ranges begin 7 or 9 (for example 097,
# 096, 095, 077, 076).
#
# The rule is deliberately the broad "9 or 7 then eight
# digits" rather than a list of current operator prefixes.
# An allowlist would have to be edited whenever ZICTA
# allocated a new range, and until it was it would silently
# refuse to alert the officer holding that number. The cost
# of being broad is accepting a number that is well formed
# but unallocated, which the provider then rejects and the
# queue records.
_ZAMBIAN_SUBSCRIBER = re.compile(r"^[79][0-9]{8}$")

_NON_DIGITS = re.compile(r"[^\d+]")
_ALLOWED_WRITTEN_FORM = re.compile(r"^[+0-9\s().-]+$")


def normalise_msisdn(raw: str | None) -> str | None:
    """
    Convert a written Zambian mobile number to E.164.

    Args:
        raw:
            Number as entered, in any of the forms officers
            write them: "0977123456", "260977123456",
            "+260 977 123 456", "097-712-3456".

    Returns:
        The number as "+260977123456", or None when it is
        not a well-formed Zambian mobile number.

    Why normalisation happens before storage:
        The same handset written two ways would otherwise
        defeat the uniqueness constraint on the SMS queue
        and the officer would receive one alert twice.

    Returning None rather than raising:
        A missing or malformed number is an ordinary state
        of a user record, not an exceptional one. The caller
        skips that officer, exactly as it skips one with no
        email address.
    """

    if not raw:
        return None

    written = raw.strip()

    # Permit common separators and an optional international
    # prefix, but do not turn embedded letters or other text
    # into a different, valid number by silently stripping it.
    if not _ALLOWED_WRITTEN_FORM.fullmatch(written):
        return None

    digits = _NON_DIGITS.sub("", written)

    # A plus is only meaningful at the front.
    if "+" in digits[1:]:
        return None

    digits = digits.lstrip("+")

    if digits.startswith("00"):
        digits = digits[2:]

    if digits.startswith("260"):
        subscriber = digits[3:]

    elif digits.startswith("0"):
        subscriber = digits[1:]

    elif _ZAMBIAN_SUBSCRIBER.match(digits):
        # Written without any prefix at all.
        subscriber = digits

    else:
        return None

    if not _ZAMBIAN_SUBSCRIBER.match(subscriber):
        return None

    return f"+260{subscriber}"


# =========================================================
# MESSAGE BODY
# =========================================================

# A GSM-7 segment is 160 characters. Longer messages are
# split and charged per segment, so the body is built to
# fit one.
SMS_MAX_LENGTH = 160


def build_alert_sms(
    forest_name: str,
    district_name: str | None,
    detected_area_hectares: float,
    priority: PriorityLevel,
    detection_id: int,
) -> str:
    """
    Build the body of an alert SMS.

    Args:
        forest_name:
            Forest area the detection falls in.
        district_name:
            District, or None when it cannot be resolved.
        detected_area_hectares:
            Measured area of the suspected clearing.
        priority:
            Alert priority.
        detection_id:
            Detection the officer should open.

    Returns:
        A message of at most SMS_MAX_LENGTH characters.

    Why this is not Alert.message:
        Alert.message is a multi-line email body carrying
        NDVI figures, a confidence note and an explanation
        of what confidence means. Submitted as an SMS it
        would be six charged segments of mostly context an
        officer cannot act on from a handset.

        The SMS carries only what decides whether to travel:
        how serious, how large, where, and which record to
        open. The detail stays in the email and the
        dashboard.

    Why there is no link and no token:
        A URL carrying a credential would put an
        authentication token into the recipient's message
        store and the operator's logs. The officer signs in
        the usual way.
    """

    location = district_name or "district unknown"

    # Named as awaiting review on purpose: the alert is
    # raised before any officer has looked at it, so the
    # message must not read as a confirmed finding.
    message = (
        f"ForestWatch {priority.value}: possible clearing "
        f"of {detected_area_hectares:.2f} ha at "
        f"{forest_name}, {location}. "
        f"Detection {detection_id} awaiting review. "
        f"Sign in to assess."
    )

    if len(message) <= SMS_MAX_LENGTH:
        return message

    # Too long, which in practice means a long forest area
    # name. The forest name is shortened rather than the
    # measurements, because an officer who cannot read the
    # area or the detection number has nothing to act on,
    # whereas a truncated name still identifies the place
    # alongside the district.
    overflow = len(message) - SMS_MAX_LENGTH

    trimmed = forest_name[: max(0, len(forest_name) - overflow - 1)]

    return (
        f"ForestWatch {priority.value}: possible clearing "
        f"of {detected_area_hectares:.2f} ha at "
        f"{trimmed}…, {location}. "
        f"Detection {detection_id} awaiting review. "
        f"Sign in to assess."
    )[:SMS_MAX_LENGTH]


# =========================================================
# PROVIDER RESPONSE
# =========================================================

# Status codes that mean the provider took responsibility
# for the message.
#
#   100 Processed
#   101 Sent
#   102 Queued
#
# Everything else is treated as a refusal.
#
# A caveat worth stating plainly: the provider's numeric
# table could not be retrieved from its documentation while
# this was written, so these three are taken from its
# published examples and from the SDK's own usage. That is
# why every row stores the code and status text verbatim
# (SmsQueue.provider_status_code, provider_status). If a
# code outside this set turns out to mean acceptance, this
# tuple is the only thing that changes and no record is
# lost.
ACCEPTED_STATUS_CODES = (100, 101, 102)


def classify_recipient(
    recipient: dict,
) -> tuple[SmsQueueStatus, str | None]:
    """
    Read one per-recipient result from the provider.

    Args:
        recipient:
            One entry of SMSMessageData.Recipients, with the
            provider's keys: statusCode, status, number,
            messageId, cost.

    Returns:
        The status to record, and a reason when it failed.

    The important line in this module:

        An accepted message is recorded as SUBMITTED, never
        as delivered or sent. The provider is telling us it
        has the message, not that a handset received it.
        Only a delivery report could say the latter, and
        this system does not yet accept delivery reports.

        Recording acceptance as delivery would mean the
        audit trail showed an officer as notified of a
        clearing they never heard about, which is the one
        claim this record must not make falsely.

    An unparseable or absent status code is a failure, not
    an acceptance. If the provider's answer cannot be read,
    the honest record is that the message is not known to
    have been accepted.
    """

    raw_code = recipient.get("statusCode")

    status_text = str(
        recipient.get("status") or ""
    ).strip()

    try:
        code = int(raw_code)

    except (TypeError, ValueError):
        return (
            SmsQueueStatus.FAILED,
            (
                "The provider did not return a readable "
                f"status code (received {raw_code!r})."
            ),
        )

    if code in ACCEPTED_STATUS_CODES:
        return (SmsQueueStatus.SUBMITTED, None)

    return (
        SmsQueueStatus.FAILED,
        (
            f"The provider refused the message: "
            f"{status_text or 'no reason given'} "
            f"(code {code})."
        ),
    )


# =========================================================
# SMS SERVICE
# =========================================================


class SmsService:
    """
    Submits alert messages to Africa's Talking.

    Mirrors EmailService: configuration is read once at
    construction, sending raises on failure, and the service
    holds no database session. The worker owns the queue.

    Sandbox by default, and by construction:

        The provider selects its sandbox endpoint purely
        from the username being the literal string
        "sandbox". This service therefore overrides the
        configured username to "sandbox" unless
        AFRICASTALKING_ENVIRONMENT is exactly "production".

        That ordering matters. It means a production
        username and a production key sitting in a developer
        .env still cannot reach a real handset, so running
        the application or its tests cannot send a real
        message by accident.
    """

    SANDBOX_USERNAME = "sandbox"

    # (connect, read) in seconds, the SDK's own default.
    # Stated explicitly because the SDK does not convert a
    # timeout into its own exception type, so this service
    # has to know what it asked for.
    TIMEOUT_SECONDS = (3.05, 9.05)

    def __init__(self) -> None:
        settings = get_settings()

        self.is_sandbox = settings.africastalking_is_sandbox

        self.username = (
            self.SANDBOX_USERNAME
            if self.is_sandbox
            else settings.africastalking_username
        )

        # Held only to hand to the SDK. Never logged, never
        # formatted into a message, never returned.
        self._api_key = settings.africastalking_api_key

        # The sandbox has no sender ID of its own, and
        # passing one it does not recognise is refused.
        self.sender_id = (
            None
            if self.is_sandbox
            else (settings.sms_sender_id or None)
        )

    # ---------------------------------------------------------
    # Configuration
    # ---------------------------------------------------------

    def ensure_configured(self) -> None:
        """
        Confirm the service can reach the provider.

        Raises:
            SmsConfigurationError:
                A required credential is absent.

        The message names the environment variable to set
        and never includes its value.
        """

        if not self._api_key:
            raise SmsConfigurationError(
                "AFRICASTALKING_API_KEY is not set, so no "
                "SMS can be sent. Add it to the backend "
                ".env file."
            )

        if not self.username:
            raise SmsConfigurationError(
                "AFRICASTALKING_USERNAME is not set, so no "
                "SMS can be sent. The sandbox username is "
                "always the literal value sandbox."
            )

    # ---------------------------------------------------------
    # Provider client
    # ---------------------------------------------------------

    def _sms_client(self):
        """
        Initialise the provider SDK and return its SMS API.

        The SDK keeps its credentials in module-level state
        and is initialised by calling africastalking
        .initialize(). That is its supported interface, so
        it is called here rather than worked around, but it
        means the last initialise in the process wins. This
        service therefore initialises immediately before
        each send rather than once at import, so a send
        always uses this instance's configuration.

        The import is local so that the application, its
        migrations and its tests all start without the
        package installed. Only an actual send needs it.
        """

        self.ensure_configured()

        try:
            import africastalking

        except ImportError as exc:
            raise SmsConfigurationError(
                "The africastalking package is not "
                "installed, so no SMS can be sent. Install "
                "the backend requirements."
            ) from exc

        africastalking.initialize(
            self.username,
            self._api_key,
        )

        return africastalking.SMS

    # ---------------------------------------------------------
    # Send
    # ---------------------------------------------------------

    def send_sms(
        self,
        recipient_phone: str,
        message: str,
    ) -> dict:
        """
        Submit one message and return the provider's result.

        Args:
            recipient_phone:
                Recipient in E.164 form. Normalised here as
                well as at the point of queueing, so a
                number written directly into the queue by
                hand cannot bypass validation.
            message:
                Body to send.

        Returns:
            The provider's per-recipient result dictionary,
            with its keys unchanged. Interpreting it is
            classify_recipient's job, not this method's.

        Raises:
            SmsConfigurationError:
                Credentials or the package are missing.
            SmsTransientError:
                A connection could not be established, so a
                retry cannot duplicate an accepted request.
            SmsAmbiguousError:
                The request may have reached the provider but
                no conclusive response was received.
            SmsProviderError:
                The provider refused the request outright,
                or answered in a shape this code cannot
                read.
        """

        normalised = normalise_msisdn(recipient_phone)

        if normalised is None:
            raise SmsProviderError(
                "The recipient number is not a valid "
                "Zambian mobile number, so no message was "
                "submitted."
            )

        if not message or not message.strip():
            raise SmsProviderError(
                "The message body is empty, so no message "
                "was submitted."
            )

        client = self._sms_client()

        # Imported here for the same reason as the SDK: the
        # application must start without either installed.
        import requests

        try:
            response = client.send(
                message,
                [normalised],
                sender_id=self.sender_id,
                timeout=self.TIMEOUT_SECONDS,
            )

        except requests.exceptions.ConnectTimeout as exc:
            # The connection was never established, so the
            # provider cannot have accepted this request.
            raise SmsTransientError(
                "A connection to the SMS provider could not "
                "be established. The message will be retried."
            ) from exc

        except (
            requests.exceptions.Timeout,
            requests.exceptions.ConnectionError,
        ) as exc:
            # A read timeout or connection loss can happen
            # after the provider accepted the message. Stop
            # here rather than risk charging and texting a
            # duplicate on the next worker cycle.
            raise SmsAmbiguousError(
                "The provider outcome is unknown after the "
                "connection was interrupted. Automatic retry "
                "was stopped to avoid a duplicate message."
            ) from exc

        except ValueError as exc:
            # The SDK validates recipients itself and raises
            # ValueError for one it rejects.
            raise SmsProviderError(
                "The SMS provider rejected the recipient "
                "number."
            ) from exc

        except Exception as exc:
            # Everything else, including the SDK's own
            # AfricasTalkingException, whose message is the
            # raw response body.
            #
            # The provider's words are kept because they are
            # what an administrator needs, but truncated:
            # an HTML error page would otherwise fill
            # last_error. The API key travels in a header,
            # so it is not in this text.
            detail = str(exc).strip().replace("\n", " ")

            raise SmsProviderError(
                "The SMS provider refused the request: "
                f"{detail[:300]}"
            ) from exc

        return self._extract_recipient(response, normalised)

    # ---------------------------------------------------------
    # Response reading
    # ---------------------------------------------------------

    @staticmethod
    def _extract_recipient(
        response: object,
        normalised_phone: str,
    ) -> dict:
        """
        Pull this recipient's result out of the response.

        The provider answers a bulk-capable endpoint even
        for one recipient, so the result arrives as

            {"SMSMessageData": {"Recipients": [ {...} ]}}

        Raises:
            SmsProviderError:
                The response is not in that shape, or
                carries no recipient. A send that cannot be
                read is not treated as a success: the point
                of this method is that an unreadable answer
                must never become a SUBMITTED row.
        """

        if not isinstance(response, dict):
            raise SmsProviderError(
                "The SMS provider returned an unreadable "
                "response, so the message cannot be "
                "recorded as submitted."
            )

        data = response.get("SMSMessageData") or {}

        recipients = data.get("Recipients") or []

        if not recipients:
            # The provider answers this way when it rejects
            # every recipient outright. Its summary line
            # usually says why.
            summary = str(
                data.get("Message") or ""
            ).strip()

            raise SmsProviderError(
                "The SMS provider accepted no recipients: "
                f"{summary[:200] or 'no reason given'}"
            )

        for entry in recipients:
            if not isinstance(entry, dict):
                continue

            number = str(entry.get("number") or "").strip()

            if number in ("", normalised_phone):
                return entry

        raise SmsProviderError(
            "The SMS provider returned a result for a "
            "different recipient than the one submitted."
        )
