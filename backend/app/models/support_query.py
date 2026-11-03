"""Database records for officer support conversations."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class SupportQuery(Base):
    __tablename__ = "support_queries"
    __table_args__ = (
        CheckConstraint(
            "category IN ('TECHNICAL_PROBLEM','SATELLITE_IMAGE_ISSUES',"
            "'ANALYSIS_NDVI_ISSUES','DETECTION_ALERT_ISSUES',"
            "'SMS_NOTIFICATION_ISSUES','ACCOUNT_LOGIN_ISSUES',"
            "'DATA_ACCURACY_ISSUES','GENERAL_ENQUIRIES','OTHER')",
            name="ck_support_queries_category",
        ),
        CheckConstraint(
            "priority IN ('LOW','MEDIUM','HIGH','URGENT')",
            name="ck_support_queries_priority",
        ),
        CheckConstraint(
            "status IN ('PENDING','UNDER_REVIEW','IN_PROGRESS','RESOLVED')",
            name="ck_support_queries_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reference: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    officer_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False)
    assigned_admin_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    district_id: Mapped[int | None] = mapped_column(ForeignKey("districts.id", ondelete="SET NULL"), index=True)
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    priority: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    officer: Mapped["User"] = relationship("User", foreign_keys=[officer_id], lazy="select")
    assigned_admin: Mapped["User | None"] = relationship("User", foreign_keys=[assigned_admin_id], lazy="select")
    district: Mapped["District | None"] = relationship("District", lazy="select")
    messages: Mapped[list["SupportQueryMessage"]] = relationship(
        "SupportQueryMessage", back_populates="query", cascade="all, delete-orphan", lazy="select"
    )
    attachments: Mapped[list["SupportQueryAttachment"]] = relationship(
        "SupportQueryAttachment", back_populates="query", foreign_keys="SupportQueryAttachment.query_id",
        cascade="all, delete-orphan", lazy="select",
    )
    assignments: Mapped[list["SupportQueryAssignment"]] = relationship(
        "SupportQueryAssignment", back_populates="query", cascade="all, delete-orphan", lazy="select"
    )
    status_history: Mapped[list["SupportQueryStatusHistory"]] = relationship(
        "SupportQueryStatusHistory", back_populates="query", cascade="all, delete-orphan", lazy="select"
    )
    notifications: Mapped[list["SupportNotification"]] = relationship(
        "SupportNotification", back_populates="query", cascade="all, delete-orphan", lazy="select"
    )


class SupportQueryMessage(Base):
    __tablename__ = "support_query_messages"
    __table_args__ = (
        CheckConstraint("sender_role IN ('ADMIN','PROVINCIAL_FORESTRY_OFFICER','DISTRICT_FORESTRY_OFFICER')", name="ck_support_message_sender_role"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    query_id: Mapped[int] = mapped_column(ForeignKey("support_queries.id", ondelete="CASCADE"), index=True, nullable=False)
    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False)
    sender_role: Mapped[str] = mapped_column(String(40), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_internal_note: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)

    query: Mapped["SupportQuery"] = relationship("SupportQuery", back_populates="messages")
    sender: Mapped["User"] = relationship("User", foreign_keys=[sender_id], lazy="select")
    attachments: Mapped[list["SupportQueryAttachment"]] = relationship(
        "SupportQueryAttachment", back_populates="message", foreign_keys="SupportQueryAttachment.message_id",
        cascade="all, delete-orphan", lazy="select",
    )


class SupportQueryAttachment(Base):
    __tablename__ = "support_query_attachments"
    __table_args__ = (
        UniqueConstraint("storage_key", name="uq_support_attachment_storage_key"),
        CheckConstraint("size_bytes > 0", name="ck_support_attachment_size_positive"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    query_id: Mapped[int] = mapped_column(ForeignKey("support_queries.id", ondelete="CASCADE"), index=True, nullable=False)
    message_id: Mapped[int | None] = mapped_column(ForeignKey("support_query_messages.id", ondelete="CASCADE"), index=True)
    uploader_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(80), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    query: Mapped["SupportQuery"] = relationship(
        "SupportQuery", back_populates="attachments", foreign_keys=[query_id]
    )
    message: Mapped["SupportQueryMessage | None"] = relationship(
        "SupportQueryMessage", back_populates="attachments", foreign_keys=[message_id]
    )
    uploader: Mapped["User"] = relationship("User", foreign_keys=[uploader_id], lazy="select")


class SupportQueryAssignment(Base):
    __tablename__ = "support_query_assignments"
    __table_args__ = (
        Index(
            "uq_support_query_assignment_active",
            "query_id",
            unique=True,
            postgresql_where=text("ended_at IS NULL"),
            sqlite_where=text("ended_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    query_id: Mapped[int] = mapped_column(ForeignKey("support_queries.id", ondelete="CASCADE"), index=True, nullable=False)
    assigned_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    assigned_to_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    query: Mapped["SupportQuery"] = relationship("SupportQuery", back_populates="assignments")
    assigned_by: Mapped["User"] = relationship("User", foreign_keys=[assigned_by_id], lazy="select")
    assigned_to: Mapped["User"] = relationship("User", foreign_keys=[assigned_to_id], lazy="select")


class SupportQueryStatusHistory(Base):
    __tablename__ = "support_query_status_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    query_id: Mapped[int] = mapped_column(ForeignKey("support_queries.id", ondelete="CASCADE"), index=True, nullable=False)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(20))
    to_status: Mapped[str] = mapped_column(String(20), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)

    query: Mapped["SupportQuery"] = relationship("SupportQuery", back_populates="status_history")
    actor: Mapped["User"] = relationship("User", foreign_keys=[actor_id], lazy="select")


class SupportNotification(Base):
    __tablename__ = "support_notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recipient_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    query_id: Mapped[int | None] = mapped_column(ForeignKey("support_queries.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    recipient: Mapped["User"] = relationship("User", foreign_keys=[recipient_id], lazy="select")
    actor: Mapped["User | None"] = relationship("User", foreign_keys=[actor_id], lazy="select")
    query: Mapped["SupportQuery | None"] = relationship("SupportQuery", back_populates="notifications")
