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
    One administrative district within a province of Zambia.

    Districts are the unit jurisdiction is enforced against.
    A District Forestry Officer is assigned exactly one, and
    may retrieve only records whose forest area lies in it.
    A Provincial Forestry Officer is assigned a province
    instead, which covers every district within it, so their
    reach is derived by joining through province_id rather
    than by listing districts on the account.

    The Copperbelt has ten districts, which are seeded
    rather than created by officers: they are fixed
    administrative boundaries, not data the system owns.
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
        comment=(
            "District name as officers know it, for example "
            "Kitwe. Shown in place of the identifier "
            "wherever a jurisdiction is displayed."
        ),
    )

    code: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        nullable=False,
        index=True,
        comment=(
            "Short official abbreviation, for example KIT. "
            "Unique, so a district can be cited without "
            "ambiguity in reports."
        ),
    )

    # =====================================================
    # PROVINCE REFERENCE
    # =====================================================

    province_id: Mapped[int] = mapped_column(
        ForeignKey("provinces.id"),
        nullable=False,
        index=True,
        comment=(
            "Province containing this district. Not null, "
            "because a provincial officer's reach is "
            "resolved by joining through this column; a "
            "district without one would be invisible to "
            "the officer responsible for it."
        ),
    )

    # =====================================================
    # STATUS
    # =====================================================

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment=(
            "Whether the district is current. Kept rather "
            "than deleted if boundaries are reorganised, "
            "because forest areas and officer assignments "
            "still reference it."
        ),
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