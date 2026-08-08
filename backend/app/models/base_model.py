"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Base Model

Purpose:
    Provides reusable audit fields for all database models.

Responsibilities:
    - Store record creation time.
    - Store last update time.
    - Automatically update timestamps.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Version:
    1.0.0
===========================================================
"""

from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column


class AuditMixin:
    """
    Reusable audit fields for all database models.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        comment="Date and time the record was created.",
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
        comment="Date and time the record was last updated.",
    )