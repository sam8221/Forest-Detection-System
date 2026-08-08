"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Forest Area Model

Purpose:
    Represents monitored forest areas (Areas of Interest)
    within the ForestWatch Zambia system.

Responsibilities:
    - Store forest boundaries.
    - Store protection status.
    - Configure monitoring settings.
    - Link forests to satellite images,
      analysis jobs and detections.

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

from geoalchemy2 import Geometry
from sqlalchemy import (
    Boolean,
    Enum as SqlEnum,
    Float,
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
    MonitoringFrequency,
    PriorityLevel,
    ProtectedStatus,
)

if TYPE_CHECKING:
    from app.models.analysis_job import AnalysisJob
    from app.models.detection import Detection
    from app.models.district import District
    from app.models.satellite_image import SatelliteImage
    from app.models.user import User


class ForestArea(AuditMixin, Base):
    """
    Represents one monitored forest area (AOI).
    """

    # ---------------------------------------------------------
    # Database Table
    # ---------------------------------------------------------
    __tablename__ = "forest_areas"

    # ---------------------------------------------------------
    # Primary Key
    # ---------------------------------------------------------
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    # ---------------------------------------------------------
    # Forest Information
    # ---------------------------------------------------------
    forest_code: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
        index=True,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # ---------------------------------------------------------
    # Location
    # ---------------------------------------------------------
    district_id: Mapped[int] = mapped_column(
        ForeignKey("districts.id"),
        nullable=False,
        index=True,
    )

    geometry: Mapped[str] = mapped_column(
        Geometry(
            geometry_type="POLYGON",
            srid=4326,
        ),
        nullable=False,
    )

    area_hectares: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    # ---------------------------------------------------------
    # Monitoring Configuration
    # ---------------------------------------------------------
    protected_status: Mapped[ProtectedStatus] = mapped_column(
        SqlEnum(ProtectedStatus),
        default=ProtectedStatus.PROTECTED_FOREST,
        nullable=False,
    )

    monitoring_frequency: Mapped[MonitoringFrequency] = mapped_column(
        SqlEnum(MonitoringFrequency),
        default=MonitoringFrequency.DAILY,
        nullable=False,
    )

    priority_level: Mapped[PriorityLevel] = mapped_column(
        SqlEnum(PriorityLevel),
        default=PriorityLevel.MEDIUM,
        nullable=False,
    )

    monitoring_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # ---------------------------------------------------------
    # Audit
    # ---------------------------------------------------------
    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    # ---------------------------------------------------------
    # Relationships
    # ---------------------------------------------------------
    district: Mapped["District"] = relationship(
        "District",
        back_populates="forest_areas",
        lazy="joined",
    )

    creator: Mapped["User"] = relationship(
        "User",
        back_populates="forest_areas",
        foreign_keys=[created_by],
        lazy="joined",
    )

    satellite_images: Mapped[list["SatelliteImage"]] = relationship(
        "SatelliteImage",
        back_populates="forest_area",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    analysis_jobs: Mapped[list["AnalysisJob"]] = relationship(
        "AnalysisJob",
        back_populates="forest_area",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    detections: Mapped[list["Detection"]] = relationship(
        "Detection",
        back_populates="forest_area",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    # ---------------------------------------------------------
    # String Representation
    # ---------------------------------------------------------
    def __repr__(self) -> str:
        """
        Return a readable representation of the forest area.
        """

        return (
            f"ForestArea("
            f"id={self.id}, "
            f"forest_code='{self.forest_code}', "
            f"name='{self.name}')"
        )