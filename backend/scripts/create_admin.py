"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Create First Administrator

Purpose:
    Creates the first administrator account, so that the
    system can be administered at all.

Responsibilities:
    - Refuse to run once an administrator exists.
    - Collect the account details safely.
    - Validate them against the same rules the API applies.
    - Record the account's creation in the audit trail.

Why this is a command and not an endpoint:

    Every account in ForestWatch is provisioned by an
    administrator through POST /api/v1/users, which is
    restricted to administrators. On an empty database
    there is no administrator, so no account can be
    created and nobody can sign in.

    A "create the first administrator" HTTP route would
    resolve that, but it is by definition reachable without
    authentication: nobody can authenticate yet. It would
    therefore become a live account-creation hole on any
    database whose users table is empty - a fresh
    deployment, a restored backup, a dropped table.

    ForestWatch is not public-facing, and that restriction
    is a security control rather than a convenience:
    publishing the locations of suspected illegal clearing
    would inform the people responsible. Bootstrapping the
    system should require access to the server itself,
    which is a far stronger gate than an empty table.

Why it runs only once:

    Once an administrator exists, further accounts -
    including further administrators - are created through
    the API by a signed-in administrator, so each one is
    attributable to the person who created it. A command
    that could be run repeatedly would be a permanent way
    to mint an administrator with no such record, which is
    what FR-19 exists to prevent.

Usage:

    From the backend directory, with the virtual
    environment active:

        python -m scripts.create_admin

    The password is prompted for, and is not echoed. For an
    unattended install, supply the details as environment
    variables instead:

        FORESTWATCH_ADMIN_NAME
        FORESTWATCH_ADMIN_EMAIL
        FORESTWATCH_ADMIN_PASSWORD

    Never place these in a committed file.

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

import os
import sys
from getpass import getpass
from pathlib import Path

# ---------------------------------------------------------
# Import path
#
# Placed before the application imports so the command runs
# both as "python -m scripts.create_admin" and as
# "python scripts/create_admin.py". The second form finds
# no "app" package without this, and failing on the wording
# of the command rather than on anything real is a poor way
# to meet the system for the first time.
# ---------------------------------------------------------

sys.path.insert(
    0,
    str(Path(__file__).resolve().parent.parent),
)

from pydantic import ValidationError  # noqa: E402

from app.database.session import SessionLocal  # noqa: E402
from app.models.audit_log import AuditLog  # noqa: E402
from app.models.enums import UserRole  # noqa: E402
from app.models.user import User  # noqa: E402
from app.schemas.user import UserCreate  # noqa: E402
from app.services.auth_service import AuthService  # noqa: E402


# =========================================================
# INPUT COLLECTION
# =========================================================

def read_value(
    variable: str,
    prompt: str,
) -> str:
    """
    Read a value from the environment, or ask for it.

    Args:
        variable:
            Environment variable to read.

        prompt:
            Wording shown when it is not set.

    Returns:
        The value, with surrounding spaces removed.

    The environment is checked first so the command can run
    unattended during a deployment. When it is not set the
    value is asked for, which is the normal case.
    """

    value = os.environ.get(variable, "").strip()

    if value:
        return value

    return input(prompt).strip()


def read_password() -> str:
    """
    Read the administrator's password.

    Returns:
        The password as typed.

    Raises:
        ValueError:
            The two typed passwords do not match.

    Taken from the environment when set, otherwise asked
    for twice without echo. It is never defaulted: a
    password this command knows in advance is a password
    that lives in the source code, and the account it
    protects can provision every other account in the
    system.
    """

    supplied = os.environ.get(
        "FORESTWATCH_ADMIN_PASSWORD",
        "",
    )

    if supplied:
        return supplied

    first = getpass("Password: ")

    second = getpass("Confirm password: ")

    if first != second:
        raise ValueError(
            "The two passwords do not match."
        )

    return first


# =========================================================
# COMMAND
# =========================================================

def create_first_administrator() -> int:
    """
    Create the first administrator account.

    Returns:
        A process exit status: 0 on success, 1 on refusal
        or failure.
    """

    db = SessionLocal()

    try:
        # -------------------------------------------------
        # Refuse if the system is already administered
        #
        # Checked before anything is asked for, so the
        # refusal does not arrive after a password has
        # already been typed.
        # -------------------------------------------------

        existing_admin = (
            db.query(User)
            .filter(
                User.role == UserRole.ADMIN,
            )
            .first()
        )

        if existing_admin is not None:
            print(
                "An administrator account already exists "
                f"({existing_admin.email})."
            )

            print(
                "Further accounts are created by a "
                "signed-in administrator through the User "
                "Management page, so that each one is "
                "recorded against the person who created "
                "it."
            )

            return 1

        print("=" * 60)
        print(
            "ForestWatch Zambia - create first administrator"
        )
        print("=" * 60)

        full_name = read_value(
            "FORESTWATCH_ADMIN_NAME",
            "Full name: ",
        )

        email = read_value(
            "FORESTWATCH_ADMIN_EMAIL",
            "Email address: ",
        )

        password = read_password()

        # -------------------------------------------------
        # Validate through the API's own schema
        #
        # UserCreate carries the password policy and the
        # rule that an administrator holds no jurisdiction.
        # Validating through it means this command cannot
        # create an account the API would have refused, and
        # the two cannot drift apart later.
        # -------------------------------------------------

        account = UserCreate(
            full_name=full_name,
            email=email,
            password=password,
            role=UserRole.ADMIN,
        )

        auth_service = AuthService(db)

        user = auth_service.register_user(account)

        # -------------------------------------------------
        # Record the creation
        #
        # Attributed to no user, because at this moment
        # there is no account to attribute it to. That is
        # the reason for recording it: this is the only
        # account in the system that nobody provisioned,
        # and the trail should say so rather than leave its
        # appearance unexplained.
        # -------------------------------------------------

        db.add(
            AuditLog(
                user_id=None,
                action="ADMIN_BOOTSTRAP",
                entity_type="User",
                entity_id=user.id,
                detail=(
                    "First administrator account created "
                    "from the server console."
                ),
            )
        )

        db.commit()

        print()
        print("Administrator account created.")
        print(f"  Name  : {user.full_name}")
        print(f"  Email : {user.email}")
        print(f"  Role  : {user.role.value}")
        print()
        print(
            "Sign in at the ForestWatch interface and "
            "change this password."
        )

        return 0

    except ValidationError as error:

        # Pydantic reports every failed rule at once. Only
        # the messages are useful here; the field paths
        # repeat what was just typed.

        db.rollback()

        print()
        print("The account was not created:")

        for problem in error.errors():
            print(f"  - {problem['msg']}")

        return 1

    except ValueError as error:
        db.rollback()

        print()
        print(f"The account was not created: {error}")

        return 1

    except KeyboardInterrupt:
        db.rollback()

        print()
        print("Cancelled. No account was created.")

        return 1

    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(create_first_administrator())
