"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Province Model

Purpose:
    Defines the Province entity.

Author:
    Samuel Bikiloni
===========================================================
"""

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base
from app.models.base_model import AuditMixin


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