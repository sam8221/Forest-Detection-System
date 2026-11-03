"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Tests: Administrator password reset

What this covers:
    An officer who cannot sign in has their password reset
    by an administrator. The system generates it; the
    administrator never chooses one. These tests establish
    the properties that make that safe to do:

        the generated password is random, strong, and
        satisfies the policy the system enforces elsewhere;

        what is stored is a bcrypt hash, never the password;

        the previous password stops working, and so does
        every token issued under it;

        the officer must replace the temporary password
        before the account can do anything else, and once
        they have, the temporary one is dead;

        only an administrator can ask for any of this;

        the audit trail names both parties and does not
        contain the password.

The database is a real one — SQLite, in memory — so the
hash that is asserted on is the hash that was written. No
network is used.
===========================================================
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.api.deps as deps
from app.api.users import router as users_router
from app.core.security import (
    TEMPORARY_PASSWORD_LENGTH,
    create_access_token,
    generate_temporary_password,
    hash_password,
    password_fingerprint,
    verify_password,
)
from app.database.session import Base, get_db
from app.models.audit_log import AuditLog
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.user import validate_password_strength
from app.services.auth_service import AuthService


ADMIN_EMAIL = "admin@forestwatch.zm"
OFFICER_EMAIL = "ndola.officer@forestwatch.zm"
OFFICER_ORIGINAL_PASSWORD = "OfficerOriginal#2026"


# =========================================================
# FIXTURES
# =========================================================


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    Base.metadata.create_all(
        engine,
        tables=[User.__table__, AuditLog.__table__],
    )

    session = sessionmaker(bind=engine)()

    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def accounts(db):
    admin = User(
        full_name="System Administrator",
        email=ADMIN_EMAIL,
        password_hash=hash_password("AdminPassword#2026"),
        role=UserRole.ADMIN,
        is_active=True,
        must_change_password=False,
    )

    officer = User(
        full_name="Ndola Forestry Officer",
        email=OFFICER_EMAIL,
        password_hash=hash_password(OFFICER_ORIGINAL_PASSWORD),
        role=UserRole.DISTRICT_FORESTRY_OFFICER,
        is_active=True,
        must_change_password=False,
    )

    db.add_all([admin, officer])
    db.commit()
    db.refresh(admin)
    db.refresh(officer)

    return {"admin": admin, "officer": officer}


@pytest.fixture
def client(db, accounts):
    """An app wired to the real authentication dependencies."""

    app = FastAPI()
    app.include_router(users_router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: db

    return TestClient(app, raise_server_exceptions=False)


def token_for(user):
    """A token as the login endpoint would issue it."""

    return create_access_token(
        {
            "sub": user.email,
            "role": user.role.value,
            "pwd": password_fingerprint(user.password_hash),
        }
    )


def auth(user):
    return {"Authorization": f"Bearer {token_for(user)}"}


# =========================================================
# THE ROUTE ITSELF
# =========================================================

def test_the_reset_route_is_registered_on_the_application():
    """
    Regression test for the way this feature first failed.

    Everything below passed while the feature did not work
    in the browser, because every one of those tests mounts
    the users router itself. The interface does not: it
    posts to a path on the assembled application, and the
    server that was running had been started before the
    endpoint existed, so that path returned FastAPI's own
    404 and the button reported "Not Found".

    This asserts the path as the interface spells it,
    prefix included, against the real application object. It
    cannot detect a server that has not been restarted — no
    test can — but it does fail if the endpoint is ever
    dropped from the router, renamed, or mounted under a
    prefix the interface does not use.
    """

    from app.main import app

    # The schema rather than app.routes: routers are
    # included lazily in this version of FastAPI, so the
    # route objects do not exist until the application is
    # built. This is also the exact view the interface and
    # any client of the API sees.
    paths = app.openapi()["paths"]

    path = "/api/v1/users/{user_id}/reset-password"

    assert path in paths, (
        "The interface posts to this path. Registered user "
        "paths are: "
        + ", ".join(sorted(p for p in paths if "/users" in p))
    )

    assert "post" in paths[path]


def test_the_reset_route_is_administrator_only():
    """
    The guard travels with the endpoint, so a future
    refactor cannot move it and leave it open.
    """

    import inspect

    from app.api.deps import get_admin_user
    from app.api.users import reset_user_password

    dependencies = [
        parameter.default.dependency
        for parameter in inspect.signature(
            reset_user_password
        ).parameters.values()
        if hasattr(parameter.default, "dependency")
    ]

    assert get_admin_user in dependencies


# =========================================================
# THE GENERATED PASSWORD
# =========================================================


def test_generated_passwords_satisfy_the_password_policy():
    """
    The generator must not be able to produce a password the
    system would refuse if it were typed in.
    """

    for _ in range(500):
        password = generate_temporary_password()

        # Raises if any class is missing.
        validate_password_strength(password)

        assert len(password) == TEMPORARY_PASSWORD_LENGTH


def test_generated_passwords_do_not_repeat():
    """
    A generator that repeats itself would let an
    administrator who has seen one reset anticipate another.
    """

    passwords = {generate_temporary_password() for _ in range(1000)}

    assert len(passwords) == 1000


def test_a_password_too_short_for_the_policy_is_refused():
    with pytest.raises(ValueError):
        generate_temporary_password(length=6)


# =========================================================
# THE RESET ITSELF
# =========================================================


def test_an_administrator_can_reset_an_officers_password(
    client, accounts
):
    response = client.post(
        f"/api/v1/users/{accounts['officer'].id}/reset-password",
        headers=auth(accounts["admin"]),
    )

    assert response.status_code == 200, response.text

    body = response.json()

    assert body["email"] == OFFICER_EMAIL
    assert body["full_name"] == "Ndola Forestry Officer"
    assert body["must_change_password"] is True
    assert len(body["temporary_password"]) == TEMPORARY_PASSWORD_LENGTH

    validate_password_strength(body["temporary_password"])


def test_the_password_is_stored_only_as_a_bcrypt_hash(
    client, db, accounts
):
    """
    The plain password is returned once and never written.
    """

    officer = accounts["officer"]

    response = client.post(
        f"/api/v1/users/{officer.id}/reset-password",
        headers=auth(accounts["admin"]),
    )

    issued = response.json()["temporary_password"]

    db.refresh(officer)

    assert officer.password_hash != issued
    assert officer.password_hash.startswith("$2")
    assert issued not in officer.password_hash
    assert verify_password(issued, officer.password_hash)


def test_the_generated_password_authenticates_the_officer(
    client, db, accounts
):
    officer = accounts["officer"]

    issued = client.post(
        f"/api/v1/users/{officer.id}/reset-password",
        headers=auth(accounts["admin"]),
    ).json()["temporary_password"]

    db.refresh(officer)

    assert (
        AuthService(db).authenticate_user(OFFICER_EMAIL, issued)
        is not None
    )


def test_the_previous_password_stops_working(
    client, db, accounts
):
    officer = accounts["officer"]

    client.post(
        f"/api/v1/users/{officer.id}/reset-password",
        headers=auth(accounts["admin"]),
    )

    db.refresh(officer)

    assert (
        AuthService(db).authenticate_user(
            OFFICER_EMAIL, OFFICER_ORIGINAL_PASSWORD
        )
        is None
    )


def test_a_reset_for_an_account_that_does_not_exist_is_refused(
    client, accounts
):
    response = client.post(
        "/api/v1/users/99999/reset-password",
        headers=auth(accounts["admin"]),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "User not found."


# =========================================================
# WHO MAY RESET A PASSWORD
# =========================================================


@pytest.mark.parametrize(
    "role",
    [
        UserRole.DISTRICT_FORESTRY_OFFICER,
        UserRole.PROVINCIAL_FORESTRY_OFFICER,
    ],
)
def test_an_officer_cannot_reset_a_password(
    client, db, accounts, role
):
    """
    Resetting passwords is administration. An officer who
    could do it could take over a colleague's account.
    """

    officer = accounts["officer"]
    officer.role = role
    db.commit()
    db.refresh(officer)

    response = client.post(
        f"/api/v1/users/{accounts['admin'].id}/reset-password",
        headers=auth(officer),
    )

    assert response.status_code == 403

    db.refresh(accounts["admin"])

    assert verify_password(
        "AdminPassword#2026", accounts["admin"].password_hash
    )


def test_an_unauthenticated_request_cannot_reset_a_password(
    client, db, accounts
):
    response = client.post(
        f"/api/v1/users/{accounts['officer'].id}/reset-password"
    )

    assert response.status_code == 401

    db.refresh(accounts["officer"])

    assert verify_password(
        OFFICER_ORIGINAL_PASSWORD,
        accounts["officer"].password_hash,
    )


def test_a_deactivated_administrator_cannot_reset_a_password(
    client, db, accounts
):
    admin = accounts["admin"]
    admin.is_active = False
    db.commit()
    db.refresh(admin)

    response = client.post(
        f"/api/v1/users/{accounts['officer'].id}/reset-password",
        headers=auth(admin),
    )

    assert response.status_code == 403


# =========================================================
# THE FORCED CHANGE
# =========================================================


def test_the_officer_must_change_the_temporary_password(
    client, db, accounts
):
    """
    Until the officer replaces it, the administrator who
    issued it can act as them, and the audit trail cannot
    tell the two apart. The account is therefore refused
    everything else.
    """

    officer = accounts["officer"]

    client.post(
        f"/api/v1/users/{officer.id}/reset-password",
        headers=auth(accounts["admin"]),
    )

    db.refresh(officer)

    assert officer.must_change_password is True

    # Any ordinary request is now refused.
    blocked = client.get(
        "/api/v1/users",
        headers=auth(officer),
    )

    assert blocked.status_code == 403
    assert blocked.json()["detail"] == (
        deps.PASSWORD_CHANGE_REQUIRED_DETAIL
    )


def test_the_officer_can_still_reach_the_password_endpoints(
    client, db, accounts
):
    """
    The forced change must not lock the account out of the
    one action being demanded of it.
    """

    officer = accounts["officer"]

    issued = client.post(
        f"/api/v1/users/{officer.id}/reset-password",
        headers=auth(accounts["admin"]),
    ).json()["temporary_password"]

    db.refresh(officer)

    profile = client.get(
        "/api/v1/users/profile",
        headers=auth(officer),
    )

    assert profile.status_code == 200

    changed = client.put(
        "/api/v1/users/profile/password",
        headers=auth(officer),
        json={
            "current_password": issued,
            "new_password": "OfficerChosen#2026",
        },
    )

    assert changed.status_code == 200, changed.text


def test_the_temporary_password_dies_when_it_is_replaced(
    client, db, accounts
):
    """
    Requirement: the temporary password cannot be reused
    once changed. The administrator's knowledge of it
    expires with first use.
    """

    officer = accounts["officer"]

    issued = client.post(
        f"/api/v1/users/{officer.id}/reset-password",
        headers=auth(accounts["admin"]),
    ).json()["temporary_password"]

    db.refresh(officer)

    client.put(
        "/api/v1/users/profile/password",
        headers=auth(officer),
        json={
            "current_password": issued,
            "new_password": "OfficerChosen#2026",
        },
    )

    db.refresh(officer)

    service = AuthService(db)

    assert officer.must_change_password is False
    assert service.authenticate_user(OFFICER_EMAIL, issued) is None
    assert (
        service.authenticate_user(
            OFFICER_EMAIL, "OfficerChosen#2026"
        )
        is not None
    )


# =========================================================
# EXISTING SESSIONS
# =========================================================


def test_a_reset_ends_a_session_already_open_on_the_account(
    client, db, accounts
):
    """
    A reset is often performed because an account may be in
    someone else's hands. A token issued before it must stop
    working at once rather than lasting out its hour.
    """

    officer = accounts["officer"]

    token_before = token_for(officer)

    assert (
        client.get(
            "/api/v1/users/profile",
            headers={"Authorization": f"Bearer {token_before}"},
        ).status_code
        == 200
    )

    client.post(
        f"/api/v1/users/{officer.id}/reset-password",
        headers=auth(accounts["admin"]),
    )

    after = client.get(
        "/api/v1/users/profile",
        headers={"Authorization": f"Bearer {token_before}"},
    )

    assert after.status_code == 401
    assert after.json()["detail"] == deps.PASSWORD_CHANGED_DETAIL


def test_a_token_carrying_no_password_fingerprint_is_refused(
    client, accounts
):
    """
    A token issued before this binding existed. Accepting it
    would leave a way to hold a token that no reset revokes.
    """

    legacy = create_access_token(
        {
            "sub": OFFICER_EMAIL,
            "role": UserRole.DISTRICT_FORESTRY_OFFICER.value,
        }
    )

    response = client.get(
        "/api/v1/users/profile",
        headers={"Authorization": f"Bearer {legacy}"},
    )

    assert response.status_code == 401


# =========================================================
# THE AUDIT TRAIL
# =========================================================


def test_the_reset_is_recorded_without_the_password(
    client, db, accounts
):
    """
    FR-19: the administrator, the officer, the action and
    the time. An audit table is read by people who are not
    entitled to the account, so the password is not in it.
    """

    officer = accounts["officer"]

    issued = client.post(
        f"/api/v1/users/{officer.id}/reset-password",
        headers=auth(accounts["admin"]),
    ).json()["temporary_password"]

    entry = (
        db.query(AuditLog)
        .filter(AuditLog.action == "PASSWORD_RESET")
        .one()
    )

    assert entry.user_id == accounts["admin"].id
    assert entry.entity_type == "User"
    assert entry.entity_id == officer.id
    assert entry.created_at is not None

    assert OFFICER_EMAIL in entry.detail
    assert ADMIN_EMAIL in entry.detail

    # The password appears nowhere in the record.
    assert issued not in (entry.detail or "")

    for row in db.query(AuditLog).all():
        assert issued not in (row.detail or "")


def test_the_password_is_not_written_to_the_application_log(
    client, accounts, caplog
):
    """
    A password in a log file outlives the reset, in a place
    nobody thinks of as holding credentials.
    """

    with caplog.at_level("DEBUG"):
        issued = client.post(
            f"/api/v1/users/{accounts['officer'].id}/reset-password",
            headers=auth(accounts["admin"]),
        ).json()["temporary_password"]

    assert issued not in caplog.text


# =========================================================
# WHAT MUST NOT HAVE CHANGED
# =========================================================


def test_an_ordinary_account_is_unaffected_by_the_feature(
    client, db, accounts
):
    """
    An officer who has never had a reset signs in and works
    exactly as before.
    """

    service = AuthService(db)

    assert (
        service.authenticate_user(
            OFFICER_EMAIL, OFFICER_ORIGINAL_PASSWORD
        )
        is not None
    )

    assert (
        client.get(
            "/api/v1/users/profile",
            headers=auth(accounts["officer"]),
        ).status_code
        == 200
    )

    # And administration still works for the administrator.
    assert (
        client.get(
            "/api/v1/users",
            headers=auth(accounts["admin"]),
        ).status_code
        == 200
    )
