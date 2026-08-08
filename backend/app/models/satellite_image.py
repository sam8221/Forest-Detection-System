"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Satellite Image Model

Purpose:
    Stores metadata about Sentinel-2 satellite images
    used by the Forest Detection System.

Responsibilities:
    - Link images to forest areas.
    - Store Sentinel product information.
    - Store acquisition details.
    - Store cloud coverage.
    - Store image location.
    - Support future NDVI analysis.

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

if TYPE_CHECKING:
    from app.models.analysis_job import AnalysisJob
    from app.models.detection import Detection
    from app.models.forest_area import ForestArea

from datetime import date

from sqlalchemy import (
    Boolean,
    Date,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)

from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)

from app.database.session import Base
from app.models.base_model import AuditMixin


class SatelliteImage(AuditMixin, Base):
    """
    Represents one Sentinel-2 image downloaded
    for a monitored forest area.
    """

    # ---------------------------------------------------------
    # Database Table
    # ---------------------------------------------------------
    __tablename__ = "satellite_images"

    __table_args__ = (
        UniqueConstraint(
            "forest_area_id",
            "product_id",
            name="uq_satellite_image_product",
        ),
    )

    # ---------------------------------------------------------
    # Primary Key
    # ---------------------------------------------------------
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    # ---------------------------------------------------------
    # Forest Area
    # ---------------------------------------------------------
    forest_area_id: Mapped[int] = mapped_column(
        ForeignKey("forest_areas.id"),
        nullable=False,
        index=True,
        comment="Forest area associated with this image.",
    )

    # ---------------------------------------------------------
    # Sentinel Information
    # ---------------------------------------------------------
    product_id: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        index=True,
        comment="Unique Sentinel product identifier.",
    )

    tile_id: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        comment="Sentinel tile identifier.",
    )

    satellite_name: Mapped[str] = mapped_column(
        String(20),
        default="Sentinel-2",
        nullable=False,
        comment="Satellite platform.",
    )

    acquisition_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
        comment="Image acquisition date.",
    )

    processing_level: Mapped[str] = mapped_column(
        String(10),
        default="L2A",
        nullable=False,
        comment="Sentinel processing level.",
    )

    cloud_cover_percentage: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
        comment="Cloud cover percentage.",
    )

    # ---------------------------------------------------------
    # Storage
    # ---------------------------------------------------------
    file_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Stored image filename.",
    )

    storage_path: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Location where the image is stored.",
    )

    file_size_mb: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="File size in MB.",
    )

    checksum: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        comment="SHA256 checksum.",
    )

    # ---------------------------------------------------------
    # Status
    # ---------------------------------------------------------
    is_downloaded: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Indicates whether the image has been downloaded.",
    )

    is_processed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Indicates whether NDVI analysis has been completed.",
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Soft delete flag.",
    )

         # ---------------------------------------------------------
    # Relationships
    # ---------------------------------------------------------

    forest_area: Mapped["ForestArea"] = relationship(
        "ForestArea",
        back_populates="satellite_images",
        lazy="joined",
    )

    analysis_jobs: Mapped[list["AnalysisJob"]] = relationship(
        "AnalysisJob",
        back_populates="satellite_image",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    detections: Mapped[list["Detection"]] = relationship(
        "Detection",
        back_populates="satellite_image",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    # ---------------------------------------------------------
    # String Representation
    # ---------------------------------------------------------
    def __repr__(self) -> str:
        return (
            f"SatelliteImage("
            f"id={self.id}, "
            f"product_id='{self.product_id}', "
            f"tile_id='{self.tile_id}')"
        )
       