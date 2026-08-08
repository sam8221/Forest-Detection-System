"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Email Queue Model

Purpose:
    Stores outgoing emails waiting to be sent.

Responsibilities:
    - Queue outgoing emails.
    - Support automatic retries.
    - Record sending status.
    - Store SMTP responses.
    - Ensure reliable email delivery.

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

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    Enum as SqlEnum,
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
from app.models.base_model import AuditMixin
from app.models.enums import EmailQueueStatus

if TYPE_CHECKING:
    from app.models.alert import Alert


class EmailQueue(AuditMixin, Base):
    """
    Represents an email waiting to be sent.
    """

    # ---------------------------------------------------------
    # Database Table
    # ---------------------------------------------------------
    __tablename__ = "email_queue"

    # ---------------------------------------------------------
    # Primary Key
    # ---------------------------------------------------------
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    # ---------------------------------------------------------
    # Alert
    # ---------------------------------------------------------
    alert_id: Mapped[int] = mapped_column(
        ForeignKey("alerts.id"),
        nullable=False,
        index=True,
        comment="Alert associated with this email.",
    )

    # ---------------------------------------------------------
    # Recipient
    # ---------------------------------------------------------
    recipient_email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    recipient_name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    # ---------------------------------------------------------
    # Email Content
    # ---------------------------------------------------------
    subject: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    body: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # ---------------------------------------------------------
    # Sending Status
    # ---------------------------------------------------------
    status: Mapped[EmailQueueStatus] = mapped_column(
        SqlEnum(EmailQueueStatus),
        default=EmailQueueStatus.PENDING,
        nullable=False,
    )

    retry_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    max_retries: Mapped[int] = mapped_column(
        Integer,
        default=5,
        nullable=False,
    )

    last_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # ---------------------------------------------------------
    # Relationships
    # ---------------------------------------------------------
    alert: Mapped["Alert"] = relationship(
        "Alert",
        back_populates="email_queue",
        lazy="joined",
    )
    