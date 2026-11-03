import importlib.util
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import support as support_api
from app.api.deps import get_current_active_user
from app.database.session import Base, get_db
from app.models.audit_log import AuditLog
from app.models.district import District
from app.models.enums import UserRole
from app.models.province import Province
from app.models.support_query import (
    SupportNotification,
    SupportQuery,
    SupportQueryAssignment,
    SupportQueryAttachment,
    SupportQueryMessage,
    SupportQueryStatusHistory,
)
from app.models.user import User


def make_client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    tables = [
        Province.__table__, District.__table__, User.__table__, AuditLog.__table__,
        SupportQuery.__table__, SupportQueryMessage.__table__, SupportQueryAttachment.__table__,
        SupportQueryAssignment.__table__, SupportQueryStatusHistory.__table__, SupportNotification.__table__,
    ]
    Base.metadata.create_all(engine, tables=tables)
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    province = Province(name="Copperbelt", code="CB", is_active=True)
    db.add(province)
    db.flush()
    district = District(name="Kitwe", code="KIT", province_id=province.id, is_active=True)
    db.add(district)
    db.flush()
    admin = User(full_name="Support Admin", email="admin@forestwatch.zm", password_hash="x", role=UserRole.ADMIN, is_active=True, must_change_password=False)
    second_admin = User(full_name="Technical Administrator", email="admin2@forestwatch.zm", password_hash="x", role=UserRole.ADMIN, is_active=True, must_change_password=False)
    officer = User(full_name="District Officer", email="officer@forestwatch.zm", password_hash="x", role=UserRole.DISTRICT_FORESTRY_OFFICER, district_id=district.id, is_active=True, must_change_password=False)
    other = User(full_name="Other Officer", email="other@forestwatch.zm", password_hash="x", role=UserRole.PROVINCIAL_FORESTRY_OFFICER, is_active=True, must_change_password=False)
    db.add_all([admin, second_admin, officer, other])
    db.commit()

    class Settings:
        support_attachment_directory = "unused-in-test"
        support_attachment_max_bytes = 1024 * 1024

    monkeypatch.setattr(support_api, "get_settings", lambda: Settings())

    def record_uploads(db, query, uploader, files, message_id=None):
        for _, filename, extension, data in files:
            db.add(SupportQueryAttachment(
                query_id=query.id,
                message_id=message_id,
                uploader_id=uploader.id,
                original_filename=filename,
                storage_key=f"test-{query.id}-{filename}",
                content_type=support_api.CONTENT_TYPES[extension],
                size_bytes=len(data),
            ))
        return []

    # The sandbox does not allow test processes to create attachment files.
    # Keep API and metadata behavior real while replacing only the disk write.
    monkeypatch.setattr(support_api, "_save_files", record_uploads)
    actor = {"user": officer}
    app = FastAPI()
    app.include_router(support_api.router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_active_user] = lambda: actor["user"]
    return TestClient(app), actor, db, (admin, second_admin, officer, other), (engine, db)


def test_support_query_workflow_rbac_attachments_and_notifications(monkeypatch):
    client, actor, db, (admin, second_admin, officer, other), resources = make_client(monkeypatch)
    engine, session = resources
    png = b"\x89PNG\r\n\x1a\n" + b"fake-image-data"
    response = client.post(
        "/api/v1/support/queries",
        data={
            "subject": "Satellite preview is blank",
            "category": "SATELLITE_IMAGE_ISSUES",
            "description": "The image viewer is blank after selecting the latest scene.",
            "priority": "HIGH",
        },
        files=[("attachments", ("screen.png", png, "image/png"))],
    )
    assert response.status_code == 201, response.text
    submitted = response.json()
    query_id = submitted["id"]
    assert submitted["reference"].startswith("FWQ-")
    assert submitted["district_name"] == "Kitwe"
    assert submitted["attachments"][0]["filename"] == "screen.png"
    actor["user"] = admin
    admin_notices = client.get("/api/v1/support/notifications").json()
    assert admin_notices[0]["title"].startswith("New support query")
    assert client.put(f"/api/v1/support/notifications/{admin_notices[0]['id']}/read").status_code == 200

    # Officers cannot read or download another officer's query.
    actor["user"] = other
    assert client.get(f"/api/v1/support/queries/{query_id}").status_code == 404
    assert client.get("/api/v1/support/queries").json() == []
    assert client.put(f"/api/v1/support/notifications/{admin_notices[0]['id']}/read").status_code == 404
    assert client.post(f"/api/v1/support/queries/{query_id}/assign", data={"administrator_id": admin.id}).status_code == 403
    assert client.patch(f"/api/v1/support/queries/{query_id}/status", data={"new_status": "RESOLVED"}).status_code == 403
    actor["user"] = officer
    assert len(client.get("/api/v1/support/queries", params={"category": "SATELLITE_IMAGE_ISSUES", "priority": "HIGH", "status": "PENDING"}).json()) == 1
    assert client.get("/api/v1/support/queries", params={"category": "OTHER"}).json() == []
    # Another officer cannot download the file, even when given its ID.
    actor["user"] = other
    assert client.get(f"/api/v1/support/attachments/{submitted['attachments'][0]['id']}/download").status_code == 404
    actor["user"] = officer

    actor["user"] = admin
    assert client.get("/api/v1/support/queries/stats").json() == {
        "total": 1, "pending": 1, "under_review": 0, "in_progress": 0, "resolved": 0, "urgent": 0,
    }
    assert client.get("/api/v1/support/filters").json()["administrators"]
    assigned = client.post(f"/api/v1/support/queries/{query_id}/assign", data={"administrator_id": second_admin.id})
    assert assigned.status_code == 200 and assigned.json()["assigned_admin_id"] == second_admin.id
    assert session.scalar(select(func.count()).select_from(SupportQueryAssignment)) == 1

    # Internal notes are visible to admins, but never included in officer details or downloads.
    note = client.post(f"/api/v1/support/queries/{query_id}/messages", data={"message": "Check the imagery service logs.", "internal_note": "true"})
    assert note.status_code == 201
    assert any(entry["is_internal_note"] for entry in client.get(f"/api/v1/support/queries/{query_id}").json()["messages"])
    actor["user"] = officer
    assert client.post(f"/api/v1/support/queries/{query_id}/messages", data={"message": "Should be private", "internal_note": "true"}).status_code == 403
    officer_view = client.get(f"/api/v1/support/queries/{query_id}").json()
    assert all(not entry["is_internal_note"] for entry in officer_view["messages"])
    assert len(client.get("/api/v1/support/notifications").json()) == 1

    # Public administrator responses and state changes notify the submitting officer.
    actor["user"] = admin
    reply = client.post(f"/api/v1/support/queries/{query_id}/messages", data={"message": "We are investigating the scene preview."})
    assert reply.status_code == 201
    assert client.patch(f"/api/v1/support/queries/{query_id}/status", data={"new_status": "RESOLVED"}).status_code == 200
    resolved = client.get(f"/api/v1/support/queries/{query_id}").json()
    assert resolved["status"] == "RESOLVED" and resolved["resolved_at"]
    assert session.scalar(select(func.count()).select_from(SupportQueryStatusHistory)) == 2
    actor["user"] = officer
    assert len(client.get("/api/v1/support/notifications").json()) == 3  # assignment, public reply, status update
    assert client.post(f"/api/v1/support/queries/{query_id}/messages", data={"message": "Thanks"}).status_code == 409
    actor["user"] = admin
    assert client.patch(f"/api/v1/support/queries/{query_id}/status", data={"new_status": "IN_PROGRESS"}).status_code == 200
    assert session.get(SupportQuery, query_id).resolved_at is None
    reopened = client.get("/api/v1/support/queries", params={"district_id": officer.district_id, "officer_id": officer.id, "category": "SATELLITE_IMAGE_ISSUES", "priority": "HIGH", "status": "IN_PROGRESS"})
    assert len(reopened.json()) == 1

    # Assignment and private file retrieval enforce their own access and validation rules.
    assert client.post(f"/api/v1/support/queries/{query_id}/assign", data={"administrator_id": officer.id}).status_code == 422
    assert client.get(f"/api/v1/support/attachments/999/download").status_code == 404
    actor["user"] = officer
    assert client.post(
        "/api/v1/support/queries",
        data={"subject": "Bad attachment", "category": "OTHER", "description": "This file is not an image.", "priority": "LOW"},
        files=[("attachments", ("spoof.png", b"%PDF-pretend", "image/png"))],
    ).status_code == 400
    assert client.post(
        "/api/v1/support/queries",
        data={"subject": "Oversized attachment", "category": "OTHER", "description": "This file exceeds the configured maximum.", "priority": "LOW"},
        files=[("attachments", ("large.txt", b"a" * (1024 * 1024 + 1), "text/plain"))],
    ).status_code == 413
    assert session.scalar(select(func.count()).select_from(SupportQuery)) == 1

    client.close()
    session.close()
    engine.dispose()


def test_support_migration_creates_all_tables_and_single_active_assignment_index():
    migration_path = Path(__file__).parents[1] / "alembic" / "versions" / "b7a4c19d2e63_add_query_and_support_management.py"
    spec = importlib.util.spec_from_file_location("support_migration", migration_path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE users (id INTEGER PRIMARY KEY)")
        connection.exec_driver_sql("CREATE TABLE districts (id INTEGER PRIMARY KEY)")
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            migration.upgrade()
        table_names = set(inspect(connection).get_table_names())
        assert {
            "support_queries", "support_query_messages", "support_query_attachments",
            "support_query_assignments", "support_query_status_history", "support_notifications",
        } <= table_names
        assignment_indexes = {item["name"] for item in inspect(connection).get_indexes("support_query_assignments")}
        assert "uq_support_query_assignment_active" in assignment_indexes
    engine.dispose()
