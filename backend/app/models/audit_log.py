"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Audit Log Model

Purpose:
    Records an immutable trail of the actions performed
    in the system.

Responsibilities:
    - Record user logins.
    - Record analysis executions.
    - Record alert status changes.
    - Record detection verification decisions.
    - Preserve the user and timestamp of every action.

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

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)

from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)

from app.database.session import Base


if TYPE_CHECKING:
    from app.models.user import User


class AuditLog(Base):
    """
    One recorded action, satisfying requirement FR-19.

    Audit records are WRITE-ONCE. There is deliberately no
    update method and no updated_at column: a trail that can
    be edited after the fact is not evidence of anything.
    Corrections are made by appending a new record, never by
    altering an existing one.

    This model does not use AuditMixin, because that mixin
    provides an updated_at column with an onupdate rule,
    which would imply these rows are mutable.
    """

    # =========================================================
    # DATABASE TABLE
    # =========================================================

    __tablename__ = "audit_logs"

    # =========================================================
    # PRIMARY KEY
    # =========================================================

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    # =========================================================
    # ACTOR
    #
    # Nullable because some actions are performed by the
    # system itself, such as a scheduled analysis run, and a
    # failed login attempt may not correspond to a real
    # account. A null actor is meaningful, not missing data.
    # =========================================================

    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        index=True,
        comment=(
            "Officer who performed the action, or null "
            "when performed by the system."
        ),
    )

    # =========================================================
    # ACTION
    # =========================================================

    action: Mapped[str] = mapped_column(
        String(60),
        nullable=False,
        index=True,
        comment=(
            "Action performed, for example LOGIN, "
            "ANALYSIS_RUN or ALERT_STATUS_CHANGE."
        ),
    )

    # =========================================================
    # SUBJECT OF THE ACTION
    #
    # Stored as a type plus an identifier rather than as a
    # foreign key, because the audit trail must outlive the
    # records it describes. A deleted detection must not take
    # the evidence of its own deletion with it.
    # =========================================================

    entity_type: Mapped[str | None] = mapped_column(
        String(60),
        nullable=True,
        index=True,
        comment=(
            "Type of record acted upon, for example "
            "Detection or AnalysisJob."
        ),
    )

    entity_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        index=True,
        comment="Identifier of the record acted upon.",
    )

    # =========================================================
    # DETAIL
    # =========================================================

    detail: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment=(
            "Human-readable description of what changed, "
            "including previous and new values where "
            "a status was altered."
        ),
    )

    ip_address: Mapped[str | None] = mapped_column(
        String(45),
        nullable=True,
        comment=(
            "Origin address of the request. Sized for a "
            "full IPv6 address."
        ),
    )

    # =========================================================
    # TIMESTAMP
    #
    # Recorded once, when the row is created. There is no
    # updated_at counterpart by design.
    # =========================================================

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
        comment="Date and time the action was performed.",
    )

    # =========================================================
    # RELATIONSHIPS
    # =========================================================

    user: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[user_id],
        lazy="joined",
    )

    # =========================================================
    # STRING REPRESENTATION
    # =========================================================

    def __repr__(self) -> str:
        """
        Return a readable representation of the AuditLog.
        """

        return (
            f"AuditLog("
            f"id={self.id}, "
            f"action='{self.action}', "
            f"user_id={self.user_id}, "
            f"at={self.created_at})"
        )
