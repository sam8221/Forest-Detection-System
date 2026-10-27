"""Persistent progress for a Copernicus product download."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base
from app.models.base_model import AuditMixin


ACTIVE_DOWNLOAD_STATUSES = (
    "PREPARING",
    "DOWNLOADING",
    "VALIDATING",
)


class SatelliteDownloadJob(AuditMixin, Base):
    """Tracks one requested Copernicus download through validation."""

    __tablename__ = "satellite_download_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PREPARING', 'DOWNLOADING', 'VALIDATING', 'COMPLETED', 'FAILED')",
            name="ck_satellite_download_job_status",
        ),
        CheckConstraint(
            "progress_percentage IS NULL OR "
            "(progress_percentage >= 0 AND progress_percentage <= 100)",
            name="ck_satellite_download_job_progress",
        ),
        Index(
            "uq_active_satellite_download_product",
            "forest_area_id",
            "product_id",
            unique=True,
            postgresql_where=text(
                "status IN ('PREPARING', 'DOWNLOADING', 'VALIDATING')"
            ),
            sqlite_where=text(
                "status IN ('PREPARING', 'DOWNLOADING', 'VALIDATING')"
            ),
        ),
        Index("ix_satellite_download_jobs_forest_created", "forest_area_id", "created_at"),
    )

    job_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
    )
    forest_area_id: Mapped[int] = mapped_column(
        ForeignKey("forest_areas.id"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )
    product_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    started_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="PREPARING",
        index=True,
    )
    downloaded_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
    )
    total_bytes: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    progress_percentage: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    satellite_image_id: Mapped[int | None] = mapped_column(
        ForeignKey("satellite_images.id"),
        nullable=True,
        index=True,
    )
    error_message: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
