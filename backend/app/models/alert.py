"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Alert Model

Purpose:
    Represents an alert generated after a confirmed
    or suspected deforestation detection.

Responsibilities:
    - Store alert information.
    - Link alerts to detections.
    - Track alert status.
    - Support dashboard and email notifications.

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
    Boolean,
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
from app.models.enums import (
    AlertStatus,
    AlertType,
    PriorityLevel,
)

if TYPE_CHECKING:
    from app.models.alert_recipient import AlertRecipient
    from app.models.detection import Detection
    from app.models.email_queue import EmailQueue


class Alert(AuditMixin, Base):
    """
    Represents a notification generated from a
    deforestation detection.
    """

    # ---------------------------------------------------------
    # Database Table
    # ---------------------------------------------------------
    __tablename__ = "alerts"

    # ---------------------------------------------------------
    # Primary Key
    # ---------------------------------------------------------
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    # ---------------------------------------------------------
    # Detection
    # ---------------------------------------------------------
    detection_id: Mapped[int] = mapped_column(
        ForeignKey("detections.id"),
        nullable=False,
        index=True,
        comment="Detection that generated this alert.",
    )

    # ---------------------------------------------------------
    # Alert Information
    # ---------------------------------------------------------
    title: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    alert_type: Mapped[AlertType] = mapped_column(
        SqlEnum(AlertType),
        default=AlertType.EMAIL,
        nullable=False,
    )

    priority: Mapped[PriorityLevel] = mapped_column(
        SqlEnum(PriorityLevel),
        default=PriorityLevel.MEDIUM,
        nullable=False,
    )

    status: Mapped[AlertStatus] = mapped_column(
        SqlEnum(AlertStatus),
        default=AlertStatus.PENDING,
        nullable=False,
    )

    is_resolved: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    resolution_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # ---------------------------------------------------------
    # Relationships
    # ---------------------------------------------------------
    detection: Mapped["Detection"] = relationship(
        "Detection",
        back_populates="alerts",
        lazy="joined",
    )

    recipients: Mapped[list["AlertRecipient"]] = relationship(
        "AlertRecipient",
        back_populates="alert",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    email_queue: Mapped[list["EmailQueue"]] = relationship(
        "EmailQueue",
        back_populates="alert",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    # ---------------------------------------------------------
    # String Representation
    # ---------------------------------------------------------
    def __repr__(self) -> str:
        """
        Return a readable representation
        of the Alert object.
        """

        return (
            f"Alert("
            f"id={self.id}, "
            f"status='{self.status.value}', "
            f"priority='{self.priority.value}')"
        )