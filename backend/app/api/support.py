"""Officer support queries, conversations and in-app notices."""

from __future__ import annotations

import io
import re
import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.core.config import get_settings
from app.database.session import get_db
from app.models.audit_log import AuditLog
from app.models.district import District
from app.models.enums import UserRole
from app.models.support_query import (
    SupportNotification,
    SupportQuery,
    SupportQueryAssignment,
    SupportQueryAttachment,
    SupportQueryMessage,
    SupportQueryStatusHistory,
    utc_now,
)
from app.models.user import User


router = APIRouter(prefix="/support", tags=["Queries & Support"])

CATEGORIES = {
    "TECHNICAL_PROBLEM", "SATELLITE_IMAGE_ISSUES", "ANALYSIS_NDVI_ISSUES",
    "DETECTION_ALERT_ISSUES", "SMS_NOTIFICATION_ISSUES", "ACCOUNT_LOGIN_ISSUES",
    "DATA_ACCURACY_ISSUES", "GENERAL_ENQUIRIES", "OTHER",
}
PRIORITIES = {"LOW", "MEDIUM", "HIGH", "URGENT"}
STATUSES = {"PENDING", "UNDER_REVIEW", "IN_PROGRESS", "RESOLVED"}
MAX_ATTACHMENTS = 5
ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".txt", ".csv", ".docx", ".xlsx"}
CONTENT_TYPES = {
    ".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg", ".txt": "text/plain", ".csv": "text/csv",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def _is_admin(user: User) -> bool:
    return user.role == UserRole.ADMIN


def _require_admin(user: User) -> None:
    if not _is_admin(user):
        raise HTTPException(status_code=403, detail="Administrator privileges required.")


def _require_officer(user: User) -> None:
    if user.role not in (UserRole.PROVINCIAL_FORESTRY_OFFICER, UserRole.DISTRICT_FORESTRY_OFFICER):
        raise HTTPException(status_code=403, detail="Forestry officer access required.")


def _get_query(db: Session, query_id: int, user: User) -> SupportQuery:
    query = db.get(SupportQuery, query_id)
    if query is None or (not _is_admin(user) and query.officer_id != user.id):
        # A 404 avoids disclosing whether another officer's query exists.
        raise HTTPException(status_code=404, detail="Support query not found.")
    return query


def _safe_filename(filename: str | None) -> tuple[str, str]:
    name = (filename or "attachment").replace("\\", "/").split("/")[-1]
    name = re.sub(r"[^A-Za-z0-9._ ()-]", "_", name).strip(" .")[:255]
    if not name:
        raise HTTPException(status_code=400, detail="Attachment filename is invalid.")
    extension = Path(name).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported attachment type: {extension or 'unknown'}.")
    return name, extension


async def _validated_files(files: list[UploadFile], max_bytes: int) -> list[tuple[UploadFile, str, str, bytes]]:
    if len(files) > MAX_ATTACHMENTS:
        raise HTTPException(status_code=400, detail=f"A maximum of {MAX_ATTACHMENTS} files may be attached at once.")
    result = []
    for upload in files:
        filename, extension = _safe_filename(upload.filename)
        data = await upload.read(max_bytes + 1)
        if not data:
            raise HTTPException(status_code=400, detail=f"{filename} is empty.")
        if len(data) > max_bytes:
            raise HTTPException(status_code=413, detail=f"{filename} exceeds the {max_bytes // (1024 * 1024)} MB file limit.")
        valid = (
            (extension == ".pdf" and data.startswith(b"%PDF-"))
            or (extension == ".png" and data.startswith(b"\x89PNG\r\n\x1a\n"))
            or (extension in {".jpg", ".jpeg"} and data.startswith(b"\xff\xd8\xff"))
        )
        if extension in {".docx", ".xlsx"}:
            try:
                with zipfile.ZipFile(io.BytesIO(data)) as document:
                    entries = set(document.namelist())
                marker = "word/document.xml" if extension == ".docx" else "xl/workbook.xml"
                valid = data.startswith(b"PK") and "[Content_Types].xml" in entries and marker in entries
            except (zipfile.BadZipFile, OSError):
                valid = False
        if extension in {".txt", ".csv"}:
            valid = b"\x00" not in data
            try:
                data.decode("utf-8-sig")
            except UnicodeDecodeError:
                valid = False
        if not valid:
            raise HTTPException(status_code=400, detail=f"{filename} does not match its file type.")
        result.append((upload, filename, extension, data))
    return result


def _save_files(
    db: Session,
    query: SupportQuery,
    uploader: User,
    files: list[tuple[UploadFile, str, str, bytes]],
    message_id: int | None = None,
) -> list[Path]:
    directory = Path(get_settings().support_attachment_directory).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    try:
        for _, filename, extension, data in files:
            storage_key = f"{uuid.uuid4().hex}{extension}"
            path = directory / storage_key
            path.write_bytes(data)
            written.append(path)
            db.add(SupportQueryAttachment(
                query_id=query.id,
                message_id=message_id,
                uploader_id=uploader.id,
                original_filename=filename,
                storage_key=storage_key,
                content_type=CONTENT_TYPES[extension],
                size_bytes=len(data),
            ))
    except Exception:
        for path in written:
            path.unlink(missing_ok=True)
        raise
    return written


def _audit(db: Session, user: User, action: str, query: SupportQuery, detail: str) -> None:
    db.add(AuditLog(
        user_id=user.id,
        action=action,
        entity_type="SupportQuery",
        entity_id=query.id,
        detail=detail,
    ))


def _notify(db: Session, recipient_id: int, actor_id: int | None, query: SupportQuery, title: str, message: str) -> None:
    db.add(SupportNotification(
        recipient_id=recipient_id,
        actor_id=actor_id,
        query_id=query.id,
        title=title[:180],
        message=message[:500],
    ))


def _notify_admins(db: Session, query: SupportQuery, actor_id: int, title: str, message: str) -> None:
    admin_ids = db.scalars(select(User.id).where(User.role == UserRole.ADMIN, User.is_active.is_(True))).all()
    for admin_id in admin_ids:
        _notify(db, admin_id, actor_id, query, title, message)


def _attachment_dict(attachment: SupportQueryAttachment) -> dict:
    return {
        "id": attachment.id,
        "filename": attachment.original_filename,
        "content_type": attachment.content_type,
        "size_bytes": attachment.size_bytes,
        "created_at": attachment.created_at,
    }


def _query_dict(
    db: Session,
    query: SupportQuery,
    include_private: bool,
    include_conversation: bool = True,
) -> dict:
    officer_name = db.scalar(select(User.full_name).where(User.id == query.officer_id))
    assigned_name = (
        db.scalar(select(User.full_name).where(User.id == query.assigned_admin_id))
        if query.assigned_admin_id else None
    )
    district_name = (
        db.scalar(select(District.name).where(District.id == query.district_id))
        if query.district_id else None
    )
    messages = db.scalars(
        select(SupportQueryMessage)
        .where(SupportQueryMessage.query_id == query.id)
        .order_by(SupportQueryMessage.created_at, SupportQueryMessage.id)
    ).all() if include_conversation else []
    visible_messages = [m for m in messages if include_private or not m.is_internal_note]
    attachments = db.scalars(
        select(SupportQueryAttachment)
        .where(SupportQueryAttachment.query_id == query.id)
        .order_by(SupportQueryAttachment.created_at, SupportQueryAttachment.id)
    ).all() if include_conversation else []
    visible_note_ids = {m.id for m in messages if m.is_internal_note}
    latest_response = db.scalar(
        select(func.max(SupportQueryMessage.created_at)).where(
            SupportQueryMessage.query_id == query.id,
            SupportQueryMessage.sender_role == UserRole.ADMIN.value,
            SupportQueryMessage.is_internal_note.is_(False),
        )
    )
    return {
        "id": query.id,
        "reference": query.reference,
        "officer_id": query.officer_id,
        "officer_name": officer_name or "Former user",
        "district_id": query.district_id,
        "district_name": district_name,
        "assigned_admin_id": query.assigned_admin_id,
        "assigned_admin_name": assigned_name,
        "subject": query.subject,
        "description": query.description,
        "category": query.category,
        "priority": query.priority,
        "status": query.status,
        "created_at": query.created_at,
        "updated_at": query.updated_at,
        "resolved_at": query.resolved_at,
        "last_response_at": latest_response,
        "messages": [
            {
                "id": m.id,
                "sender_id": m.sender_id,
                "sender_name": db.scalar(select(User.full_name).where(User.id == m.sender_id)) or "Former user",
                "sender_role": m.sender_role,
                "message": m.message,
                "is_internal_note": m.is_internal_note if include_private else False,
                "created_at": m.created_at,
                "attachments": [
                    _attachment_dict(a) for a in attachments
                    if a.message_id == m.id and (include_private or m.id not in visible_note_ids)
                ],
            }
            for m in visible_messages
        ],
        "attachments": [
            _attachment_dict(a) for a in attachments if a.message_id is None
        ],
    }


@router.get("/queries/stats")
def query_statistics(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    _require_admin(current_user)
    total = db.scalar(select(func.count()).select_from(SupportQuery)) or 0
    by_status = dict(db.execute(select(SupportQuery.status, func.count()).group_by(SupportQuery.status)).all())
    urgent = db.scalar(select(func.count()).select_from(SupportQuery).where(SupportQuery.priority == "URGENT")) or 0
    return {
        "total": total,
        "pending": by_status.get("PENDING", 0),
        "under_review": by_status.get("UNDER_REVIEW", 0),
        "in_progress": by_status.get("IN_PROGRESS", 0),
        "resolved": by_status.get("RESOLVED", 0),
        "urgent": urgent,
    }


@router.get("/filters")
def query_filter_options(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    _require_admin(current_user)
    districts = db.execute(select(District.id, District.name).order_by(District.name)).all()
    officers = db.execute(select(User.id, User.full_name).where(
        User.role.in_((UserRole.PROVINCIAL_FORESTRY_OFFICER, UserRole.DISTRICT_FORESTRY_OFFICER)),
    ).order_by(User.full_name)).all()
    return {
        "districts": [{"id": district_id, "name": name} for district_id, name in districts],
        "officers": [{"id": user_id, "name": name} for user_id, name in officers],
        "administrators": [
            {"id": user_id, "name": name}
            for user_id, name in db.execute(
                select(User.id, User.full_name).where(
                    User.role == UserRole.ADMIN, User.is_active.is_(True)
                ).order_by(User.full_name)
            ).all()
        ],
    }


@router.get("/queries")
def list_queries(
    search: str | None = None,
    district_id: int | None = None,
    officer_id: int | None = None,
    category: str | None = None,
    priority: str | None = None,
    query_status: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    statement = select(SupportQuery)
    if not _is_admin(current_user):
        _require_officer(current_user)
        statement = statement.where(SupportQuery.officer_id == current_user.id)
    else:
        if district_id is not None:
            statement = statement.where(SupportQuery.district_id == district_id)
        if officer_id is not None:
            statement = statement.where(SupportQuery.officer_id == officer_id)
        if search:
            pattern = f"%{search.strip()}%"
            statement = statement.join(User, User.id == SupportQuery.officer_id).where(
                or_(SupportQuery.reference.ilike(pattern), SupportQuery.subject.ilike(pattern), User.full_name.ilike(pattern))
            )
    if category:
        statement = statement.where(SupportQuery.category == category.upper())
    if priority:
        statement = statement.where(SupportQuery.priority == priority.upper())
    if query_status:
        statement = statement.where(SupportQuery.status == query_status.upper())
    queries = db.scalars(statement.order_by(SupportQuery.updated_at.desc(), SupportQuery.id.desc())).all()
    return [
        _query_dict(
            db,
            query,
            include_private=_is_admin(current_user),
            include_conversation=False,
        )
        for query in queries
    ]


@router.post("/queries", status_code=status.HTTP_201_CREATED)
async def submit_query(
    subject: str = Form(..., min_length=3, max_length=200),
    category: str = Form(...),
    description: str = Form(..., min_length=5, max_length=10000),
    priority: str = Form(...),
    attachments: list[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    _require_officer(current_user)
    category, priority = category.upper(), priority.upper()
    if category not in CATEGORIES or priority not in PRIORITIES:
        raise HTTPException(status_code=422, detail="Choose a valid query category and priority.")
    subject = subject.strip()
    description = description.strip()
    if len(subject) < 3 or len(description) < 5:
        raise HTTPException(status_code=422, detail="Enter a subject and description with meaningful detail.")
    files = await _validated_files(attachments, get_settings().support_attachment_max_bytes)
    now = utc_now()
    query = SupportQuery(
        reference=f"FWQ-TMP-{uuid.uuid4().hex}", officer_id=current_user.id, district_id=current_user.district_id,
        subject=subject, description=description, category=category,
        priority=priority, status="PENDING", created_at=now, updated_at=now,
    )
    db.add(query)
    db.flush()
    query.reference = f"FWQ-{now.year}-{query.id:06d}"
    first_message = SupportQueryMessage(
        query_id=query.id, sender_id=current_user.id, sender_role=current_user.role.value,
        message=description, is_internal_note=False,
    )
    db.add(first_message)
    db.flush()
    db.add(SupportQueryStatusHistory(
        query_id=query.id,
        actor_id=current_user.id,
        from_status=None,
        to_status="PENDING",
        note="Query submitted.",
    ))
    written = []
    try:
        written = _save_files(db, query, current_user, files)
        _notify_admins(db, query, current_user.id, f"New support query {query.reference}", query.subject)
        db.commit()
    except Exception:
        db.rollback()
        for path in written:
            path.unlink(missing_ok=True)
        raise
    db.refresh(query)
    return _query_dict(db, query, include_private=False)


@router.get("/queries/{query_id}")
def get_query(query_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    query = _get_query(db, query_id, current_user)
    return _query_dict(db, query, include_private=_is_admin(current_user))


@router.post("/queries/{query_id}/messages", status_code=status.HTTP_201_CREATED)
async def add_query_message(
    query_id: int,
    message: str = Form(..., min_length=1, max_length=10000),
    internal_note: bool = Form(default=False),
    attachments: list[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    query = _get_query(db, query_id, current_user)
    is_admin = _is_admin(current_user)
    if internal_note and not is_admin:
        raise HTTPException(status_code=403, detail="Only administrators may add internal notes.")
    if not is_admin:
        _require_officer(current_user)
        if query.status == "RESOLVED":
            raise HTTPException(status_code=409, detail="Reopen this query through an administrator before replying.")
    message = message.strip()
    if not message and not attachments:
        raise HTTPException(status_code=422, detail="Enter a message or attach a file.")
    if not message:
        message = "Please see the attached file."
    files = await _validated_files(attachments, get_settings().support_attachment_max_bytes)
    record = SupportQueryMessage(
        query_id=query.id, sender_id=current_user.id, sender_role=current_user.role.value,
        message=message, is_internal_note=internal_note,
    )
    db.add(record)
    query.updated_at = utc_now()
    db.flush()
    written = []
    try:
        written = _save_files(db, query, current_user, files, message_id=record.id)
        if not internal_note:
            if is_admin:
                _notify(db, query.officer_id, current_user.id, query, f"Response to {query.reference}", message[:160])
            elif query.assigned_admin_id:
                _notify(db, query.assigned_admin_id, current_user.id, query, f"Officer replied to {query.reference}", message[:160])
            else:
                _notify_admins(db, query, current_user.id, f"Officer replied to {query.reference}", message[:160])
        if is_admin:
            _audit(db, current_user, "SUPPORT_INTERNAL_NOTE" if internal_note else "SUPPORT_QUERY_RESPONSE", query, f"Message added to {query.reference}; internal={internal_note}.")
        db.commit()
    except Exception:
        db.rollback()
        for path in written:
            path.unlink(missing_ok=True)
        raise
    return {"id": record.id, "created_at": record.created_at}


@router.post("/queries/{query_id}/assign")
def assign_query(query_id: int, administrator_id: int = Form(...), db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    _require_admin(current_user)
    query = _get_query(db, query_id, current_user)
    assignee = db.get(User, administrator_id)
    if assignee is None or not assignee.is_active or assignee.role != UserRole.ADMIN:
        raise HTTPException(status_code=422, detail="Queries may be assigned to active administrators only.")
    now = utc_now()
    active_assignment = db.scalar(select(SupportQueryAssignment).where(
        SupportQueryAssignment.query_id == query.id, SupportQueryAssignment.ended_at.is_(None)
    ))
    if active_assignment:
        active_assignment.ended_at = now
    db.add(SupportQueryAssignment(query_id=query.id, assigned_by_id=current_user.id, assigned_to_id=assignee.id, assigned_at=now))
    old = query.assigned_admin_id
    query.assigned_admin_id = assignee.id
    query.updated_at = now
    _audit(db, current_user, "SUPPORT_QUERY_ASSIGNED", query, f"Assigned from {old} to administrator {assignee.id}.")
    _notify(db, query.officer_id, current_user.id, query, f"Query {query.reference} assigned", f"Your query is assigned to {assignee.full_name}.")
    db.commit()
    return _query_dict(db, query, include_private=True)


@router.patch("/queries/{query_id}/status")
def change_query_status(
    query_id: int,
    new_status: str = Form(...),
    note: str | None = Form(default=None, max_length=2000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    _require_admin(current_user)
    query = _get_query(db, query_id, current_user)
    new_status = new_status.upper()
    if new_status not in STATUSES:
        raise HTTPException(status_code=422, detail="Choose a valid query status.")
    previous = query.status
    if previous == new_status:
        return _query_dict(db, query, include_private=True)
    now = utc_now()
    query.status = new_status
    query.resolved_at = now if new_status == "RESOLVED" else None
    query.updated_at = now
    db.add(SupportQueryStatusHistory(query_id=query.id, actor_id=current_user.id, from_status=previous, to_status=new_status, note=note))
    _audit(db, current_user, "SUPPORT_QUERY_STATUS_CHANGE", query, f"{previous} -> {new_status}; {note or ''}".strip())
    _notify(db, query.officer_id, current_user.id, query, f"Query {query.reference} updated", f"Status changed to {new_status.replace('_', ' ').lower()}.")
    db.commit()
    return _query_dict(db, query, include_private=True)


@router.get("/attachments/{attachment_id}/download")
def download_attachment(attachment_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    attachment = db.get(SupportQueryAttachment, attachment_id)
    if attachment is None:
        raise HTTPException(status_code=404, detail="Attachment not found.")
    query = _get_query(db, attachment.query_id, current_user)
    if not _is_admin(current_user) and attachment.message_id is not None:
        message = db.get(SupportQueryMessage, attachment.message_id)
        if message is None or message.is_internal_note:
            raise HTTPException(status_code=404, detail="Attachment not found.")
    path = (Path(get_settings().support_attachment_directory).expanduser().resolve() / attachment.storage_key).resolve()
    if path.parent != Path(get_settings().support_attachment_directory).expanduser().resolve() or not path.is_file():
        raise HTTPException(status_code=404, detail="Attachment file not found.")
    return FileResponse(path, media_type=attachment.content_type, filename=attachment.original_filename, content_disposition_type="attachment")


@router.get("/notifications")
def list_support_notifications(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    records = db.scalars(select(SupportNotification).where(
        SupportNotification.recipient_id == current_user.id,
    ).order_by(SupportNotification.created_at.desc()).limit(50)).all()
    return [{
        "id": r.id, "title": r.title, "message": r.message, "query_id": r.query_id,
        "created_at": r.created_at, "read_at": r.read_at,
    } for r in records]


@router.put("/notifications/{notification_id}/read")
def mark_support_notification_read(notification_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    record = db.get(SupportNotification, notification_id)
    if record is None or record.recipient_id != current_user.id:
        raise HTTPException(status_code=404, detail="Notification not found.")
    if record.read_at is None:
        record.read_at = datetime.now(UTC)
        db.commit()
    return {"id": record.id, "read_at": record.read_at}
