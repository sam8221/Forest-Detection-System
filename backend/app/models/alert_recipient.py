"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Alert Recipient Model

Purpose:
    Associates alerts with users who should receive
    notifications.

Responsibilities:
    - Link alerts to users.
    - Track whether a user has viewed an alert.
    - Support multiple recipients per alert.

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
    ForeignKey,
    Integer,
)

from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)

from app.database.session import Base
from app.models.base_model import AuditMixin

if TYPE_CHECKING:
    from app.models.alert import Alert
    from app.models.user import User


class AlertRecipient(AuditMixin, Base):
    """
    Represents one recipient of an alert.
    """

    # ---------------------------------------------------------
    # Database Table
    # ---------------------------------------------------------
    __tablename__ = "alert_recipients"

    # ---------------------------------------------------------
    # Primary Key
    # ---------------------------------------------------------
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    # ---------------------------------------------------------
    # Foreign Keys
    # ---------------------------------------------------------
    alert_id: Mapped[int] = mapped_column(
        ForeignKey("alerts.id"),
        nullable=False,
        index=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    # ---------------------------------------------------------
    # Status
    # ---------------------------------------------------------
    is_read: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # ---------------------------------------------------------
    # Relationships
    # ---------------------------------------------------------
    alert: Mapped["Alert"] = relationship(
        "Alert",
        back_populates="recipients",
        lazy="joined",
    )

    user: Mapped["User"] = relationship(
        "User",
        back_populates="alert_recipients",
        lazy="joined",
    )