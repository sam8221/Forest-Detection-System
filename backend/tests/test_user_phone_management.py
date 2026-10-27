"""Phone-number persistence, validation and account access tests."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.users import router as users_router
from app.api.deps import get_admin_user
from app.database.session import get_db
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.user import UserCreate, UserResponse, UserUpdate
from app.services.auth_service import AuthService


def user_create_payload(phone_number=...):
    payload = {
        "full_name": "Test Forestry Officer",
        "email": "officer@example.org",
        "password": "Strong#Password123",
        "role": UserRole.DISTRICT_FORESTRY_OFFICER,
        "district_id": 7,
    }

    if phone_number is not ...:
        payload["phone_number"] = phone_number

    return UserCreate(**payload)


class MemoryUserRepository:
    """Small repository double for AuthService's write paths."""

    def __init__(self, user=None):
        self.user = user
        self.created = None
        self.updated = None

    def get_by_email(self, email):
        return None

    def create(self, user):
        self.created = user
        return user

    def get_by_id(self, user_id):
        return self.user if self.user and self.user.id == user_id else None

    def update(self, user):
        self.updated = user
        return user


def service_with(repository):
    service = AuthService.__new__(AuthService)
    service.repository = repository
    return service


def admin_users_test_app():
    app = FastAPI()
    app.include_router(users_router)
    app.dependency_overrides[get_db] = lambda: None
    app.dependency_overrides[get_admin_user] = lambda: SimpleNamespace(
        role=UserRole.ADMIN
    )
    return app


def test_admin_service_creates_officer_with_normalized_phone():
    repository = MemoryUserRepository()
    service = service_with(repository)

    created = service.register_user(
        user_create_payload("+260 971 234 567")
    )

    assert repository.created is created
    assert created.phone_number == "+260971234567"


def test_admin_service_creates_officer_without_phone_as_null():
    repository = MemoryUserRepository()

    created = service_with(repository).register_user(
        user_create_payload()
    )

    assert created.phone_number is None


def test_admin_service_updates_and_clears_phone_number():
    existing = SimpleNamespace(
        id=12,
        phone_number=None,
    )
    repository = MemoryUserRepository(existing)
    service = service_with(repository)

    updated = service.update_user(
        12,
        UserUpdate(phone_number="0971-234-567"),
    )

    assert updated.phone_number == "+260971234567"

    cleared = service.update_user(
        12,
        UserUpdate(phone_number=None),
    )

    assert cleared.phone_number is None
    assert repository.updated is cleared


@pytest.mark.parametrize(
    "phone_number",
    [
        "0211234567",
        "09712345",
        "+254711123456",
        "not a phone number",
    ],
)
def test_create_and_update_reject_invalid_nonempty_numbers(phone_number):
    with pytest.raises(ValidationError, match="valid Zambian mobile"):
        user_create_payload(phone_number)

    with pytest.raises(ValidationError, match="valid Zambian mobile"):
        UserUpdate(phone_number=phone_number)


def test_user_response_includes_the_saved_phone_number():
    now = datetime.now(UTC)
    response = UserResponse(
        id=12,
        full_name="Test Forestry Officer",
        email="officer@example.org",
        phone_number="+260971234567",
        role=UserRole.DISTRICT_FORESTRY_OFFICER,
        is_active=True,
        must_change_password=False,
        last_login=None,
        province_id=None,
        district_id=7,
        province_name=None,
        district_name="Kitwe",
        created_at=now,
        updated_at=now,
    )

    assert response.phone_number == "+260971234567"


def test_district_officer_update_accepts_phone_and_district_fields():
    request = UserUpdate(
        full_name="Kitwe Officer",
        email="kitwe.officer@example.org",
        phone_number="+260971234567",
        role=UserRole.DISTRICT_FORESTRY_OFFICER,
        district_id=7,
        province_id=None,
    )

    assert request.phone_number == "+260971234567"
    assert request.district_id == 7


@pytest.mark.parametrize(
    ("phone_number", "expected_phone"),
    [
        (None, None),
        ("0971 234 567", "+260971234567"),
    ],
)
def test_create_endpoint_returns_user_with_nullable_or_saved_phone(
    monkeypatch,
    phone_number,
    expected_phone,
):
    now = datetime.now(UTC)

    def register_user(_service, user_data):
        return SimpleNamespace(
            id=21,
            full_name=user_data.full_name,
            email=str(user_data.email),
            phone_number=user_data.phone_number,
            role=user_data.role,
            is_active=True,
            must_change_password=True,
            last_login=None,
            province_id=user_data.province_id,
            district_id=user_data.district_id,
            province_name=None,
            district_name=None,
            created_at=now,
            updated_at=now,
        )

    monkeypatch.setattr(AuthService, "register_user", register_user)
    payload = {
        "full_name": "Test Forestry Officer",
        "email": "new-officer@example.org",
        "password": "Strong#Password123",
        "role": UserRole.DISTRICT_FORESTRY_OFFICER.value,
        "district_id": 7,
        "province_id": None,
    }
    if phone_number is not None:
        payload["phone_number"] = phone_number

    with TestClient(admin_users_test_app()) as client:
        response = client.post("/users", json=payload)

    assert response.status_code == 201
    assert response.json()["id"] == 21
    assert "phone_number" in response.json()
    assert response.json()["phone_number"] == expected_phone


def test_create_endpoint_returns_service_error_detail(monkeypatch):
    def reject_duplicate(_service, _user_data):
        raise ValueError("Email already exists.")

    monkeypatch.setattr(AuthService, "register_user", reject_duplicate)
    payload = {
        "full_name": "Test Forestry Officer",
        "email": "duplicate@example.org",
        "password": "Strong#Password123",
        "role": UserRole.DISTRICT_FORESTRY_OFFICER.value,
        "district_id": 7,
    }

    with TestClient(admin_users_test_app()) as client:
        response = client.post("/users", json=payload)

    assert response.status_code == 400
    assert response.json()["detail"] == "Email already exists."


def test_update_endpoint_returns_service_error_detail(monkeypatch):
    def reject_missing_user(_service, user_id, user_data):
        del user_id, user_data
        raise ValueError("User not found.")

    monkeypatch.setattr(AuthService, "update_user", reject_missing_user)

    with TestClient(admin_users_test_app()) as client:
        response = client.put(
            "/users/999",
            json={"phone_number": "+260971234567"},
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "User not found."


def test_update_endpoint_saves_and_returns_phone_number_on_readback():
    """Exercise PUT, SQLAlchemy persistence, and GET serialization."""

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    User.__table__.create(engine)
    session_factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )
    db = session_factory()

    officer = User(
        full_name="Test Forestry Officer",
        email="readback-officer@example.org",
        password_hash="not-used-in-this-test",
        role=UserRole.DISTRICT_FORESTRY_OFFICER,
    )
    db.add(officer)
    db.commit()
    officer_id = officer.id

    app = FastAPI()
    app.include_router(users_router)

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_admin_user] = lambda: SimpleNamespace(
        role=UserRole.ADMIN
    )

    try:
        with TestClient(app) as client:
            first_update = client.put(
                f"/users/{officer_id}",
                json={"phone_number": "0971 234 567"},
            )

            assert first_update.status_code == 200
            assert first_update.json()["phone_number"] == "+260971234567"

            first_read = client.get("/users")
            assert first_read.status_code == 200
            assert first_read.json()[0]["phone_number"] == "+260971234567"

            second_update = client.put(
                f"/users/{officer_id}",
                json={"phone_number": "+260961234567"},
            )

            assert second_update.status_code == 200
            assert second_update.json()["phone_number"] == "+260961234567"

            second_read = client.get("/users")
            assert second_read.status_code == 200
            assert second_read.json()[0]["phone_number"] == "+260961234567"

        db.refresh(officer)
        assert officer.phone_number == "+260961234567"
    finally:
        db.close()
        engine.dispose()


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/users"),
        ("PUT", "/users/{user_id}"),
    ],
)
def test_user_create_and_update_routes_keep_admin_dependency(method, path):
    route = next(
        route
        for route in users_router.routes
        if isinstance(route, APIRoute)
        and route.path == path
        and method in route.methods
    )

    assert any(
        dependency.call is get_admin_user
        for dependency in route.dependant.dependencies
    )

    ordinary_user = SimpleNamespace(
        role=UserRole.DISTRICT_FORESTRY_OFFICER,
    )

    with pytest.raises(HTTPException) as error:
        get_admin_user(ordinary_user)

    assert error.value.status_code == 403
