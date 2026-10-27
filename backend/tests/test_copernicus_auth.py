from __future__ import annotations

from types import SimpleNamespace

import pytest
import requests

from app.services import copernicus_service as copernicus_module
from app.services.copernicus_service import (
    CopernicusAuthenticationError,
    CopernicusAuthenticationServiceError,
    CopernicusService,
)


class FakeOAuthResponse:
    def __init__(self, status_code=200, payload=None, body=""):
        self.status_code = status_code
        self.payload = payload or {}
        self.text = body

    def json(self):
        return self.payload


class FakeDownloadResponse:
    def __init__(self, status_code, content=b"product"):
        self.status_code = status_code
        self.headers = {"Content-Length": str(len(content))}
        self.content = content

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def iter_content(self, chunk_size):
        yield self.content


def configure_credentials(monkeypatch, username="service-user", password="service-password"):
    monkeypatch.setattr(
        copernicus_module,
        "settings",
        SimpleNamespace(
            copernicus_username=username,
            copernicus_password=password,
        ),
    )


def test_authentication_uses_supported_password_grant_and_stores_token(monkeypatch):
    configure_credentials(monkeypatch)
    observed = {}

    def fake_post(url, **kwargs):
        observed["url"] = url
        observed.update(kwargs)
        return FakeOAuthResponse(
            payload={
                "access_token": "test-access-token",
                "refresh_token": "test-refresh-token",
                "expires_in": 300,
            }
        )

    monkeypatch.setattr(copernicus_module.requests, "post", fake_post)
    service = CopernicusService()

    assert service.authenticate() == "test-access-token"
    assert observed["url"] == service.TOKEN_URL
    assert observed["data"]["client_id"] == "cdse-public"
    assert observed["data"]["grant_type"] == "password"
    assert observed["data"]["username"] == "service-user"
    assert observed["data"]["password"] == "service-password"
    assert service.session.headers["Authorization"] == "Bearer test-access-token"
    assert service._refresh_token == "test-refresh-token"
    assert service._token_expires_at is not None


def test_missing_credentials_fail_safely_without_requesting_a_token(monkeypatch):
    configure_credentials(monkeypatch, username="", password="")
    monkeypatch.setattr(
        copernicus_module.requests,
        "post",
        lambda *_args, **_kwargs: pytest.fail("unexpected auth request"),
    )

    with pytest.raises(CopernicusAuthenticationError) as error:
        CopernicusService().authenticate()

    assert "COPERNICUS_USERNAME" in str(error.value)
    assert "service-password" not in str(error.value)


def test_invalid_credentials_do_not_expose_provider_body_or_credentials(monkeypatch):
    configure_credentials(monkeypatch)
    monkeypatch.setattr(
        copernicus_module.requests,
        "post",
        lambda *_args, **_kwargs: FakeOAuthResponse(
            status_code=401,
            payload={"error_description": "invalid account password"},
            body="sensitive provider response",
        ),
    )

    with pytest.raises(CopernicusAuthenticationError) as error:
        CopernicusService().authenticate()

    assert "COPERNICUS_USERNAME" in str(error.value)
    assert "sensitive" not in str(error.value)
    assert "service-password" not in str(error.value)


def test_temporary_identity_failure_is_retryable_and_sanitized(monkeypatch):
    configure_credentials(monkeypatch)
    monkeypatch.setattr(
        copernicus_module.requests,
        "post",
        lambda *_args, **_kwargs: FakeOAuthResponse(
            status_code=503,
            body="provider internal error details",
        ),
    )

    with pytest.raises(CopernicusAuthenticationServiceError) as error:
        CopernicusService().authenticate()

    assert "temporarily unavailable" in str(error.value)
    assert "provider internal" not in str(error.value)


def test_expiring_access_token_uses_refresh_grant(monkeypatch):
    configure_credentials(monkeypatch)
    observed = []

    def fake_post(_url, **kwargs):
        observed.append(kwargs["data"])
        return FakeOAuthResponse(
            payload={"access_token": "refreshed-access", "expires_in": 600}
        )

    monkeypatch.setattr(copernicus_module.requests, "post", fake_post)
    service = CopernicusService()
    service._access_token = "old-access"
    service._refresh_token = "refresh-value"
    service._token_expires_at = 0
    service.session.headers["Authorization"] = "Bearer old-access"

    service._ensure_authenticated()

    assert observed == [
        {
            "client_id": "cdse-public",
            "grant_type": "refresh_token",
            "refresh_token": "refresh-value",
        }
    ]
    assert service.session.headers["Authorization"] == "Bearer refreshed-access"


def test_auth_transport_errors_are_classified_without_exception_text(monkeypatch):
    configure_credentials(monkeypatch)

    def fail_connection(*_args, **_kwargs):
        raise requests.exceptions.ConnectionError("private endpoint details")

    monkeypatch.setattr(copernicus_module.requests, "post", fail_connection)

    with pytest.raises(CopernicusAuthenticationServiceError) as error:
        CopernicusService().authenticate()

    assert "Unable to connect" in str(error.value)
    assert "private endpoint" not in str(error.value)


def test_download_uses_bearer_token_and_recovers_once_from_expired_token(
    monkeypatch,
    tmp_path,
):
    service = CopernicusService()
    service._ensure_authenticated = lambda: None

    class SequenceSession:
        def __init__(self):
            self.headers = {"Authorization": "Bearer expired-token"}
            self.responses = [
                FakeDownloadResponse(401),
                FakeDownloadResponse(200),
            ]
            self.auth_headers = []

        def get(self, *_args, **_kwargs):
            self.auth_headers.append(self.headers.get("Authorization"))
            return self.responses.pop(0)

    session = SequenceSession()
    service.session = session

    def refresh():
        service.session.headers["Authorization"] = "Bearer renewed-token"

    monkeypatch.setattr(service, "_refresh_or_authenticate", refresh)
    destination = tmp_path / "download.zip"

    assert service.download_file("https://example.invalid/product", destination) == destination
    assert destination.read_bytes() == b"product"
    assert session.auth_headers == [
        "Bearer expired-token",
        "Bearer renewed-token",
    ]


def test_download_authentication_failure_is_permanent_and_leaves_no_partial_file(
    monkeypatch,
    tmp_path,
):
    service = CopernicusService()
    service._ensure_authenticated = lambda: None

    class SequenceSession:
        def __init__(self):
            self.headers = {}
            self.responses = [
                FakeDownloadResponse(401),
                FakeDownloadResponse(401),
            ]

        def get(self, *_args, **_kwargs):
            return self.responses.pop(0)

    service.session = SequenceSession()
    monkeypatch.setattr(service, "_refresh_or_authenticate", lambda: None)
    destination = tmp_path / "rejected.zip"

    with pytest.raises(CopernicusAuthenticationError):
        service.download_file("https://example.invalid/product", destination)

    assert not destination.exists()
    assert not (tmp_path / "rejected.zip.part").exists()
