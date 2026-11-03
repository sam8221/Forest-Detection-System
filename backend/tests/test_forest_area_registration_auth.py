"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Tests: Authentication on forest area registration

Why these exist:
    Registration failed in the interface with "Could not
    validate credentials." The endpoint and the role check
    were both correct; the token presented had expired. The
    message gave the officer nothing to act on, because it
    described a credential problem rather than the thing
    that had actually happened to them.

    These tests pin down the whole matrix for the one
    endpoint an officer uses to add a forest area: who gets
    in, who does not, and what each is told. They run
    against the real dependency chain — the actual JWT
    decode in app.api.deps — rather than an override, so a
    change that quietly admitted an expired token would
    fail here.

No network and no database: the session is an in-memory
SQLite one and the user repository is a double.
===========================================================
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.api.deps as deps
from app.api.forest_areas import router as forest_areas_router
from app.core.security import (
    create_access_token,
    hash_password,
    password_fingerprint,
)
from app.database.session import get_db
from app.models.enums import UserRole
from app.models.user import User


OFFICER_EMAIL = "kitwe.officer@forestwatch.zm"


ACCOUNT_PASSWORD = "OfficerPassword#2026"


def make_user(role=UserRole.DISTRICT_FORESTRY_OFFICER, is_active=True):
    return User(
        id=3,
        email=OFFICER_EMAIL,
        full_name="Kitwe Officer",
        role=role,
        district_id=8,
        is_active=is_active,
        password_hash=hash_password(ACCOUNT_PASSWORD),
        must_change_password=False,
    )


def issued_token(user, **claims):
    """
    A token as the login endpoint issues it.

    The pwd claim ties the token to the password it was
    issued under, so that a reset invalidates it. A token
    without one is refused, which is what the dedicated test
    in test_password_reset.py establishes.
    """

    payload = {
        "sub": user.email,
        "role": user.role.value,
        "pwd": password_fingerprint(user.password_hash),
    }

    payload.update(claims)

    return create_access_token(payload, **{})


class FakeUserRepository:
    """Returns the one account these tests care about."""

    def __init__(self, user):
        self.user = user

    def get_by_email(self, email):
        if self.user is not None and email == self.user.email:
            return self.user
        return None


class RecordingSession:
    """
    Enough of a Session for the endpoint's happy path.

    The registration endpoint adds, commits and refreshes.
    None of that needs a real database to establish who is
    allowed to reach it, which is what these tests are about.
    """

    def __init__(self):
        self.added = []
        self.committed = False

    def add(self, instance):
        self.added.append(instance)

    def commit(self):
        self.committed = True

    def refresh(self, instance):
        # Stand in for the values the database assigns on
        # insert. Without them the response model cannot be
        # built, and the endpoint would appear to fail for a
        # reason that has nothing to do with authentication.
        instance.id = 101
        instance.is_active = True
        instance.created_at = datetime.now(UTC)
        instance.updated_at = datetime.now(UTC)

    def rollback(self):
        pass


@pytest.fixture
def context(monkeypatch):
    """An app wired to the real auth dependencies."""

    state = {
        "user": make_user(),
        "session": RecordingSession(),
    }

    monkeypatch.setattr(
        deps,
        "UserRepository",
        lambda db: FakeUserRepository(state["user"]),
    )

    # The boundary is parsed against PostGIS in production.
    # These tests are about who may reach the endpoint, so
    # the geometry step is stood in for.
    import app.api.forest_areas as forest_areas_module

    monkeypatch.setattr(
        forest_areas_module,
        "parse_and_validate_boundary",
        lambda db, geometry_wkt: geometry_wkt,
    )

    app = FastAPI()
    app.include_router(forest_areas_router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: state["session"]

    state["client"] = TestClient(app, raise_server_exceptions=False)
    return state


def registration_payload():
    return {
        "name": "Chichele Plantation",
        "forest_code": "CB-KIT-014",
        "district_id": 8,
        "area_hectares": 42.5,
        "protected_status": "PROTECTED_FOREST",
        "monitoring_frequency": "MONTHLY",
        "priority_level": "MEDIUM",
        "description": "Registered during authentication testing.",
        "geometry": (
            "POLYGON((28.2 -12.8, 28.3 -12.8, "
            "28.3 -12.7, 28.2 -12.7, 28.2 -12.8))"
        ),
    }


def register(client, token=None):
    headers = {}

    if token is not None:
        headers["Authorization"] = f"Bearer {token}"

    return client.post(
        "/api/v1/forest-areas",
        json=registration_payload(),
        headers=headers,
    )


# =========================================================
# THE OFFICER WHO SHOULD GET IN
# =========================================================


def test_an_authenticated_officer_can_register_a_forest_area(context):
    """The case that was failing in the interface."""

    token = issued_token(context["user"])

    response = register(context["client"], token)

    assert response.status_code == 201, response.text
    assert context["session"].committed is True

    created = context["session"].added[0]
    assert created.name == "Chichele Plantation"
    # Authorship is taken from the token, never from the body.
    assert created.created_by == 3


@pytest.mark.parametrize(
    "role",
    [
        UserRole.ADMIN,
        UserRole.PROVINCIAL_FORESTRY_OFFICER,
        UserRole.DISTRICT_FORESTRY_OFFICER,
    ],
)
def test_every_forestry_role_may_register(context, role):
    context["user"] = make_user(role=role)

    response = register(
        context["client"],
        issued_token(context["user"]),
    )

    assert response.status_code == 201, response.text


# =========================================================
# WHO STAYS OUT, AND WHAT THEY ARE TOLD
# =========================================================


def test_a_request_without_a_token_is_refused(context):
    response = register(context["client"])

    assert response.status_code == 401
    assert context["session"].committed is False


def test_an_expired_token_asks_the_officer_to_sign_in_again(context):
    """
    The failure behind the reported fault.

    The officer is told their session ended, not that their
    credentials could not be validated: the first is
    something they can act on, the second describes a
    problem they did not know they had.
    """

    token = create_access_token(
        {
            "sub": OFFICER_EMAIL,
            "pwd": password_fingerprint(
                context["user"].password_hash
            ),
        },
        expires_delta=timedelta(minutes=-1),
    )

    response = register(context["client"], token)

    assert response.status_code == 401
    assert response.json()["detail"] == deps.SESSION_EXPIRED_DETAIL
    assert "expired" in response.json()["detail"].lower()
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert context["session"].committed is False


def test_a_token_signed_with_another_key_is_refused(context):
    """
    Forging a token must not be told apart from any other
    invalid one, so a forger learns nothing from the reply.
    """

    from jose import jwt

    token = jwt.encode(
        {"sub": OFFICER_EMAIL},
        "not-the-application-secret",
        algorithm="HS256",
    )

    response = register(context["client"], token)

    assert response.status_code == 401
    assert response.json()["detail"] == deps.INVALID_CREDENTIALS_DETAIL
    assert context["session"].committed is False


def test_a_malformed_token_is_refused(context):
    response = register(context["client"], "not-a-jwt-at-all")

    assert response.status_code == 401
    assert response.json()["detail"] == deps.INVALID_CREDENTIALS_DETAIL
    assert context["session"].committed is False


def test_a_token_naming_no_account_is_refused(context):
    """
    The token verifies but the account is gone. The caller
    is told no more than for any other invalid token.
    """

    context["user"] = None

    response = register(
        context["client"],
        create_access_token({"sub": "removed@forestwatch.zm"}),
    )

    assert response.status_code == 401
    assert response.json()["detail"] == deps.INVALID_CREDENTIALS_DETAIL
    assert context["session"].committed is False


def test_a_deactivated_account_is_refused(context):
    """
    A valid token for an account an administrator has
    disabled. Refused as forbidden rather than
    unauthenticated: the credentials are genuine, the
    account is not permitted to act.
    """

    context["user"] = make_user(is_active=False)

    response = register(
        context["client"],
        issued_token(context["user"]),
    )

    assert response.status_code == 403
    assert context["session"].committed is False


def test_an_expired_token_is_refused_before_the_body_is_considered(
    context,
):
    """
    Authentication comes first. A request that would fail
    validation anyway must still be refused as
    unauthenticated, so a rejected body can never reveal
    that an endpoint was reached.
    """

    token = create_access_token(
        {
            "sub": OFFICER_EMAIL,
            "pwd": password_fingerprint(
                context["user"].password_hash
            ),
        },
        expires_delta=timedelta(minutes=-1),
    )

    response = context["client"].post(
        "/api/v1/forest-areas",
        json={"name": ""},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401
    assert response.status_code != 422
