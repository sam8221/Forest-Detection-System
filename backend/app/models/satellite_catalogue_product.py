"""Persist provider catalogue metadata independently of downloaded imagery."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base
from app.models.base_model import AuditMixin


class SatelliteCatalogueProduct(AuditMixin, Base):
    """One real Copernicus product discovered over a forest area."""

    __tablename__ = "satellite_catalogue_products"
    __table_args__ = (
        UniqueConstraint(
            "forest_area_id",
            "product_id",
            name="uq_satellite_catalogue_product",
        ),
        Index(
            "ix_sat_catalogue_area_acquisition",
            "forest_area_id",
            "acquisition_datetime",
        ),
        Index("ix_sat_catalogue_product_tile", "forest_area_id", "tile_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    forest_area_id: Mapped[int] = mapped_column(
        ForeignKey("forest_areas.id"), nullable=False, index=True
    )
    product_id: Mapped[str] = mapped_column(String(150), nullable=False)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    tile_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    acquisition_datetime: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    acquisition_timestamp: Mapped[str | None] = mapped_column(
        String(40), nullable=True
    )
    cloud_cover_percentage: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    processing_level: Mapped[str | None] = mapped_column(String(30), nullable=True)
    product_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    online: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    content_length: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    footprint: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
