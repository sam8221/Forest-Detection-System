"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: District Model

Purpose:
    Represents administrative districts within Zambia
    and their relationship with provinces and monitored
    forest areas.

Responsibilities:
    - Store district information.
    - Associate districts with provinces.
    - Associate districts with monitored forest areas.
    - Support active/inactive district records.

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

from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Integer,
    String,
)

from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)

from app.database.session import Base
from app.models.base_model import AuditMixin


if TYPE_CHECKING:
    from app.models.forest_area import ForestArea
    from app.models.province import Province


class District(AuditMixin, Base):
    """
    Represents an administrative district within a
    province of Zambia.
    """

    __tablename__ = "districts"

    # =====================================================
    # PRIMARY KEY
    # =====================================================

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    # =====================================================
    # DISTRICT INFORMATION
    # =====================================================

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    code: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        nullable=False,
        index=True,
    )

    # =====================================================
    # PROVINCE REFERENCE
    # =====================================================

    province_id: Mapped[int] = mapped_column(
        ForeignKey("provinces.id"),
        nullable=False,
        index=True,
    )

    # =====================================================
    # STATUS
    # =====================================================

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # =====================================================
    # RELATIONSHIPS
    # =====================================================

    province: Mapped["Province"] = relationship(
        "Province",
        back_populates="districts",
        lazy="joined",
    )

    forest_areas: Mapped[list["ForestArea"]] = relationship(
        "ForestArea",
        back_populates="district",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    # =====================================================
    # STRING REPRESENTATION
    # =====================================================

    def __repr__(self) -> str:
        return (
            f"District("
            f"id={self.id}, "
            f"name='{self.name}', "
            f"code='{self.code}'"
            f")"
        )