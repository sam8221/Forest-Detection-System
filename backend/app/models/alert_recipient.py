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
    One officer's copy of one alert.

    An alert is raised once against a detection, but several
    officers may need to see it. This table is the join
    between the two, holding the per-officer reading state
    so that one officer opening an alert does not mark it
    read for everyone.

    The rows are kept after an alert is resolved. Who was
    notified, and whether they opened it, is part of the
    record of how the department responded.
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
        comment="Alert this row delivers.",
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
        comment=(
            "Officer the alert was delivered to. Indexed "
            "because the usual query is an officer asking "
            "for their own alerts."
        ),
    )

    # ---------------------------------------------------------
    # Status
    # ---------------------------------------------------------
    is_read: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment=(
            "Whether this officer has opened the alert. "
            "Held per recipient, not on the alert, so one "
            "officer reading it does not hide it from the "
            "others it was sent to."
        ),
    )

    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment=(
            "When this officer opened the alert, or null if "
            "they have not. Timezone aware, so the interval "
            "between an alert being raised and being seen "
            "is measurable across sites."
        ),
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