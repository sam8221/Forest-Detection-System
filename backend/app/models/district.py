"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: District Model
===========================================================
"""

from sqlalchemy import Boolean, ForeignKey, Integer, String

from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base
from app.models.base_model import AuditMixin


class District(AuditMixin, Base):
    """
    Represents a district.
    """

    __tablename__ = "districts"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    code: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        nullable=False,
    )

    province_id: Mapped[int] = mapped_column(
        ForeignKey("provinces.id"),
        nullable=False,
        index=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # Relationships
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

    def __repr__(self) -> str:
        return f"District(id={self.id}, name='{self.name}')"