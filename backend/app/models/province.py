"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Province Model

Purpose:
    Defines the Province entity, the top level of the
    administrative hierarchy the system is organised around.

Responsibilities:
    - Store a Zambian province and its official code.
    - Own the districts within it.

How it works:
    Province sits above District, which in turn owns the
    forest areas. That chain is what jurisdiction-scoped
    access is enforced along:

        Province -> District -> ForestArea -> Detection

    A Provincial Forestry Officer is assigned a province and
    may see every district inside it. A District Forestry
    Officer is assigned a district and sees only that one.
    The repository layer walks this chain to decide what a
    query may return, which is why the relationship matters
    beyond simple record-keeping.

    Provinces are deactivated rather than deleted. Forest
    areas, detections and alerts reference them, and removing
    a province would orphan records that alerts have already
    been raised against.

Note on scope:
    The dissertation studies the Copperbelt Province, but the
    model is not limited to it. Zambia has ten provinces and
    the schema holds any of them, so the system can be
    extended beyond the pilot without a schema change.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia
===========================================================
"""

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base
from app.models.base_model import AuditMixin


# Imported for type checking only. At runtime SQLAlchemy resolves
# the string "District" through its model registry, and importing
# the module here for real would create a circular import, since
# District refers back to Province.
if TYPE_CHECKING:
    from app.models.district import District


class Province(AuditMixin, Base):
    """
    Represents a Zambian province.
    """

    __tablename__ = "provinces"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
        comment="Province name.",
    )

    code: Mapped[str] = mapped_column(
        String(10),
        unique=True,
        nullable=False,
        comment="Province code.",
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # Relationships
    districts: Mapped[list["District"]] = relationship(
        "District",
        back_populates="province",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"Province(id={self.id}, name='{self.name}')"