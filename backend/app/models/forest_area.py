"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Forest Area Model

Purpose:
    Represents monitored forest areas (Areas of Interest)
    within the ForestWatch Zambia system.

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Author:
    Samuel Bikiloni

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
    One monitored forest area, the unit an analysis runs over.

    A forest area is the area of interest an officer
    registers and the system then compares between two
    seasonal windows. Detections reference the job that
    produced them, and each job references one forest area,
    so this table is the root of the detection record.

    Coordinate systems:
        The boundary here is stored in EPSG:4326, degrees of
        latitude and longitude, because that is what a map
        client draws and what a shapefile of reserve
        boundaries normally arrives in.

        Detection.geometry is stored in EPSG:32735 instead,
        UTM zone 35S, whose unit is the metre. Detection
        areas are measured from their geometry, and an area
        computed in degrees varies with latitude and cannot
        be converted to hectares by a constant.

        The two therefore need reprojecting before they are
        compared, for example when testing whether a
        detection falls inside this boundary.

    NOTE: area_hectares is supplied by the client on create
    and update, and is never computed from the geometry or
    checked against it. The stored figure can therefore
    contradict the boundary in the same row. PostGIS can
    derive it from the geometry once reprojected to a metric
    CRS, which would make the column consistent by
    construction.
    """

    __tablename__ = "forest_areas"

    # =========================================================
    # PRIMARY KEY
    # =========================================================

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    # =========================================================
    # FOREST INFORMATION
    # =========================================================

    forest_code: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        nullable=False,
        index=True,
        comment=(
            "Departmental reference for the forest area. "
            "Unique, so officers can cite one area "
            "unambiguously in correspondence and field "
            "reports without quoting a database id."
        ),
    )

    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
        index=True,
        comment="Name of the forest area as officers know it.",
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Free description of the area and its vegetation.",
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Working notes kept by officers about the area.",
    )

    # =========================================================
    # LOCATION
    # =========================================================

    district_id: Mapped[int] = mapped_column(
        ForeignKey("districts.id"),
        nullable=False,
        index=True,
        comment=(
            "District the area lies in. This is what "
            "jurisdiction is enforced against: a district "
            "officer may retrieve only areas whose district "
            "matches their own, and the province follows "
            "from the district."
        ),
    )

    geometry: Mapped[object] = mapped_column(
        Geometry(
            geometry_type="POLYGON",
            srid=4326,
        ),
        nullable=False,
        comment=(
            "Boundary of the area in EPSG:4326, degrees. "
            "Reproject to a metric CRS such as EPSG:32735 "
            "before measuring area or distance; degrees "
            "give no usable unit of area."
        ),
    )

    area_hectares: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment=(
            "Stated size of the area in hectares. Supplied "
            "by the client, not derived from the geometry, "
            "so it may disagree with the boundary."
        ),
    )

    # =========================================================
    # MONITORING CONFIGURATION
    # =========================================================

    protected_status: Mapped[ProtectedStatus] = mapped_column(
        SqlEnum(ProtectedStatus),
        default=ProtectedStatus.PROTECTED_FOREST,
        nullable=False,
        comment=(
            "Legal protection class, which governs how a "
            "detection here is escalated."
        ),
    )

    monitoring_frequency: Mapped[MonitoringFrequency] = mapped_column(
        SqlEnum(MonitoringFrequency),
        default=MonitoringFrequency.WEEKLY,
        nullable=False,
        comment=(
            "How often the area is analysed. Bounded by the "
            "Sentinel-2 revisit interval of about five "
            "days, so no shorter period is offered."
        ),
    )

    priority_level: Mapped[PriorityLevel] = mapped_column(
        SqlEnum(PriorityLevel),
        default=PriorityLevel.MEDIUM,
        nullable=False,
        comment=(
            "Relative importance, used to order alerts when "
            "several areas report detections at once."
        ),
    )

    monitoring_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment=(
            "Whether scheduled analysis picks this area up. "
            "Distinct from is_active: an area can be "
            "current but temporarily not analysed, for "
            "example while its boundary is being corrected."
        ),
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment=(
            "Whether the area is current. Retired areas are "
            "kept rather than deleted, because detections "
            "and alerts remain attached to them."
        ),
    )

    # =========================================================
    # AUDIT
    # =========================================================

    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    # =========================================================
    # RELATIONSHIPS
    #
    # IMPORTANT:
    # Use lazy="select" so related records are loaded only
    # when the application actually accesses them.
    # This prevents the Forest Areas list from loading
    # satellite images, analysis jobs and detections.
    # =========================================================

    district: Mapped["District"] = relationship(
        "District",
        back_populates="forest_areas",
        lazy="select",
    )

    creator: Mapped["User"] = relationship(
        "User",
        back_populates="forest_areas",
        foreign_keys=[created_by],
        lazy="select",
    )

    satellite_images: Mapped[list["SatelliteImage"]] = relationship(
        "SatelliteImage",
        back_populates="forest_area",
        cascade="all, delete-orphan",
        lazy="select",
    )

    analysis_jobs: Mapped[list["AnalysisJob"]] = relationship(
        "AnalysisJob",
        back_populates="forest_area",
        cascade="all, delete-orphan",
        lazy="select",
    )

    detections: Mapped[list["Detection"]] = relationship(
        "Detection",
        back_populates="forest_area",
        cascade="all, delete-orphan",
        lazy="select",
    )

    # =========================================================
    # STRING REPRESENTATION
    # =========================================================

    def __repr__(self) -> str:
        return (
            f"ForestArea("
            f"id={self.id}, "
            f"forest_code='{self.forest_code}', "
            f"name='{self.name}')"
        )