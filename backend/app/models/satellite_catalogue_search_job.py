"""Persistent status for asynchronous Copernicus catalogue searches."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base
from app.models.base_model import AuditMixin


ACTIVE_CATALOGUE_SEARCH_STATUSES = ("QUEUED", "RUNNING")


class SatelliteCatalogueSearchJob(AuditMixin, Base):
    """Tracks a historical discovery through provider pagination."""

    __tablename__ = "satellite_catalogue_search_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('QUEUED', 'RUNNING', 'COMPLETED', 'PARTIAL', 'FAILED')",
            name="ck_satellite_catalogue_search_status",
        ),
        Index(
            "uq_active_catalogue_search_per_area",
            "forest_area_id",
            unique=True,
            postgresql_where=text("status IN ('QUEUED', 'RUNNING')"),
            sqlite_where=text("status IN ('QUEUED', 'RUNNING')"),
        ),
        Index(
            "ix_catalogue_search_area_created",
            "forest_area_id",
            "created_at",
        ),
    )

    job_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    forest_area_id: Mapped[int] = mapped_column(
        ForeignKey("forest_areas.id"), nullable=False, index=True
    )
    started_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    cloud_cover: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="QUEUED", index=True
    )
    pages_completed: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    products_found: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
