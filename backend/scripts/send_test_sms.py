"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Send Test SMS

Purpose:
    Submits one message through the configured Africa's
    Talking account, to confirm the credentials and the
    sandbox simulator work before relying on alert SMS.

Responsibilities:
    - Refuse to run against production.
    - Submit one message to one number.
    - Print the provider's answer in full.
    - Say plainly that acceptance is not delivery.

Why this is a command and not an endpoint:

    A "send a test message" route would be a way for any
    authenticated officer to spend the department's SMS
    credit, and in production to text an arbitrary number
    from a government system. Confirming that credentials
    work is a deployment task, so it should require access
    to the server, not a session in the browser.

    It also keeps the API surface free of anything that
    handles the API key, which is what makes the "the key
    never reaches a response" claim easy to check.

Usage:

    python scripts/send_test_sms.py +260977123456

    The number must be registered in the Africa's Talking
    simulator, or the sandbox will refuse it. Open the
    simulator at https://developers.africastalking.com and
    add the number there first.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia
===========================================================
"""

from __future__ import annotations

import sys
from pathlib import Path


# ---------------------------------------------------------
# Make the application importable when this file is run
# directly, which is how a deployment task is run.
# ---------------------------------------------------------

BACKEND_ROOT = Path(__file__).resolve().parents[1]

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


from app.services.sms_service import (  # noqa: E402
    SmsConfigurationError,
    SmsError,
    SmsService,
    build_alert_sms,
    classify_recipient,
    normalise_msisdn,
)

from app.models.enums import PriorityLevel  # noqa: E402


def main(argv: list[str]) -> int:
    """
    Submit one test message and report what came back.

    Returns:
        A process exit code: 0 when the provider accepted
        the message, 1 otherwise.
    """

    if len(argv) != 2:
        print(
            "Usage: python scripts/send_test_sms.py "
            "+260977123456"
        )

        return 1

    phone = normalise_msisdn(argv[1])

    if phone is None:
        print(
            f"{argv[1]!r} is not a valid Zambian mobile "
            "number. Expected a form such as 0977123456 "
            "or +260977123456."
        )

        return 1

    service = SmsService()

    # -----------------------------------------------------
    # Never from this command against a live account
    #
    # The point of this script is to confirm a sandbox
    # setup. Pointed at production it would text a real
    # handset from a government system on the strength of a
    # command-line argument, which is not something a test
    # utility should be able to do.
    # -----------------------------------------------------

    if not service.is_sandbox:
        print(
            "AFRICASTALKING_ENVIRONMENT names production, "
            "so this command will not run: it exists to "
            "test the sandbox. Set it to sandbox and try "
            "again."
        )

        return 1

    message = build_alert_sms(
        forest_name="Chichele Plantation",
        district_name="Ndola",
        detected_area_hectares=3.85,
        priority=PriorityLevel.HIGH,
        detection_id=0,
    )

    print(f"Account:   {service.username} (sandbox)")
    print(f"Recipient: {phone}")
    print(f"Message:   {message}")
    print(f"Length:    {len(message)} characters")
    print()

    try:
        recipient = service.send_sms(
            recipient_phone=phone,
            message=message,
        )

    except SmsConfigurationError as exc:
        print(f"Not configured: {exc}")

        return 1

    except SmsError as exc:
        print(f"Failed: {exc}")

        return 1

    # -----------------------------------------------------
    # Print the answer verbatim
    #
    # This is the point of the exercise. The status code
    # table could not be confirmed from the provider's
    # documentation, so what a real sandbox send returns is
    # worth reading rather than assuming. Compare it against
    # ACCEPTED_STATUS_CODES in sms_service.
    # -----------------------------------------------------

    print("Provider returned:")

    for key in (
        "statusCode",
        "status",
        "number",
        "messageId",
        "cost",
    ):
        print(f"  {key}: {recipient.get(key)!r}")

    print()

    status, detail = classify_recipient(recipient)

    print(f"Recorded as: {status.value}")

    if detail:
        print(f"Reason:      {detail}")

    if status.value == "SUBMITTED":
        print()
        print(
            "SUBMITTED means the provider accepted the "
            "message. It does not mean a handset received "
            "it: this system does not accept delivery "
            "reports, so delivery is unconfirmed. Check the "
            "simulator to see the message arrive."
        )

        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
