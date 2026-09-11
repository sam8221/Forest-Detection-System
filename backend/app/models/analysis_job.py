"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Analysis Job Model

Purpose:
    Records every forest-change analysis performed
    by the system.

Responsibilities:
    - Track manual and scheduled analyses.
    - Link forest areas with previous and latest
      satellite images.
    - Record execution details.
    - Store processing statistics.
    - Record processing errors.
    - Support multi-date forest change detection.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Version:
    1.1.0
===========================================================
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
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
    AnalysisJobStatus,
    AnalysisJobType,
)


if TYPE_CHECKING:
    from app.models.detection import Detection
    from app.models.forest_area import ForestArea
    from app.models.satellite_image import SatelliteImage
    from app.models.user import User


class AnalysisJob(AuditMixin, Base):
    """
    Represents one execution of the forest-change
    analysis engine.

    The analysis compares a previous Sentinel-2
    image against a latest Sentinel-2 image.
    """

    # =========================================================
    # DATABASE TABLE
    # =========================================================

    __tablename__ = "analysis_jobs"

    # =========================================================
    # PRIMARY KEY
    # =========================================================

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    # =========================================================
    # FOREST AREA
    # =========================================================

    forest_area_id: Mapped[int] = mapped_column(
        ForeignKey("forest_areas.id"),
        nullable=False,
        index=True,
        comment="Forest area being analysed.",
    )

    # =========================================================
    # PREVIOUS SATELLITE IMAGE
    # =========================================================

    previous_satellite_image_id: Mapped[int | None] = mapped_column(
        ForeignKey("satellite_images.id"),
        nullable=True,
        index=True,
        comment=(
            "Previous Sentinel-2 image used as the "
            "baseline for change detection."
        ),
    )

    # =========================================================
    # LATEST SATELLITE IMAGE
    # =========================================================

    satellite_image_id: Mapped[int] = mapped_column(
        ForeignKey("satellite_images.id"),
        nullable=False,
        index=True,
        comment=(
            "Latest Sentinel-2 image used for "
            "change detection."
        ),
    )

    # =========================================================
    # USER WHO STARTED ANALYSIS
    # =========================================================

    started_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        index=True,
        comment=(
            "User that started the analysis. "
            "Null when started automatically."
        ),
    )

    # =========================================================
    # ANALYSIS INFORMATION
    # =========================================================

    job_type: Mapped[AnalysisJobType] = mapped_column(
        SqlEnum(AnalysisJobType),
        nullable=False,
        default=AnalysisJobType.AUTOMATIC,
    )

    status: Mapped[AnalysisJobStatus] = mapped_column(
        SqlEnum(AnalysisJobStatus),
        nullable=False,
        default=AnalysisJobStatus.PENDING,
    )

    # =========================================================
    # EXECUTION TIMES
    # =========================================================

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    duration_seconds: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Total analysis execution time in seconds.",
    )

    # =========================================================
    # ANALYSIS STATISTICS
    # =========================================================

    cloud_cover_percentage: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Cloud cover considered during analysis.",
    )

    ndvi_threshold: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="NDVI change threshold used.",
    )

    vegetation_change_percentage: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Estimated vegetation change.",
    )

    # =========================================================
    # ERROR INFORMATION
    # =========================================================

    error_message: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    execution_log: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Detailed analysis execution log.",
    )

    # =========================================================
    # RELATIONSHIPS
    # =========================================================

    forest_area: Mapped["ForestArea"] = relationship(
        "ForestArea",
        back_populates="analysis_jobs",
        lazy="joined",
    )

    # Previous image used as baseline.
    previous_satellite_image: Mapped["SatelliteImage | None"] = relationship(
        "SatelliteImage",
        foreign_keys=[previous_satellite_image_id],
        lazy="joined",
    )

    # Latest image used in the analysis.
    satellite_image: Mapped["SatelliteImage"] = relationship(
        "SatelliteImage",
        foreign_keys=[satellite_image_id],
        back_populates="analysis_jobs",
        lazy="joined",
    )

    started_by_user: Mapped["User | None"] = relationship(
        "User",
        back_populates="analysis_jobs",
        foreign_keys=[started_by],
        lazy="joined",
    )

    detections: Mapped[list["Detection"]] = relationship(
        "Detection",
        back_populates="analysis_job",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    # =========================================================
    # STRING REPRESENTATION
    # =========================================================

    def __repr__(self) -> str:
        """
        Return a readable representation of the
        AnalysisJob object.
        """

        return (
            f"AnalysisJob("
            f"id={self.id}, "
            f"status='{self.status.value}', "
            f"job_type='{self.job_type.value}')"
        )