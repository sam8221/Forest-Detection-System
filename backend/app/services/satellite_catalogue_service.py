"""Database helpers for the persistent Sentinel-2 catalogue."""

from __future__ import annotations

import json
import math
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.satellite_catalogue_product import SatelliteCatalogueProduct
from app.models.satellite_catalogue_search_job import SatelliteCatalogueSearchJob


def parse_provider_datetime(value: Any) -> datetime | None:
    """Parse an OData ISO timestamp without inventing a timezone or value."""

    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _number_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) and 0 <= parsed <= 100 else None


def _integer_or_none(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def persist_catalogue_page(
    db: Session,
    *,
    forest_area_id: int,
    products: list[dict[str, Any]],
    copernicus,
) -> list[str]:
    """Upsert one provider page and return its valid stable provider IDs."""

    now = datetime.now(UTC)
    persisted_ids: list[str] = []
    for provider_product in products:
        metadata = copernicus.get_product_metadata(provider_product)
        product_id = metadata.get("product_id")
        if not isinstance(product_id, str) or not product_id.strip():
            # The provider ID is the stable key. Never fabricate one from a
            # display name or date when the source omitted it.
            continue
        product_id = product_id.strip()
        if len(product_id) > 150:
            continue

        row = (
            db.query(SatelliteCatalogueProduct)
            .filter(
                SatelliteCatalogueProduct.forest_area_id == forest_area_id,
                SatelliteCatalogueProduct.product_id == product_id,
            )
            .first()
        )
        if row is None:
            row = SatelliteCatalogueProduct(
                forest_area_id=forest_area_id,
                product_id=product_id,
                product_name=(metadata.get("product_name") or product_id)[:255],
                first_seen_at=now,
                last_seen_at=now,
            )
            db.add(row)
        persisted_ids.append(product_id)

        product_name = metadata.get("product_name")
        if isinstance(product_name, str) and product_name.strip():
            row.product_name = product_name.strip()[:255]
        row.tile_id = metadata.get("tile_id")
        row.acquisition_timestamp = metadata.get("acquisition_date")
        row.acquisition_datetime = parse_provider_datetime(
            metadata.get("acquisition_date")
        )
        row.cloud_cover_percentage = _number_or_none(metadata.get("cloud_cover"))
        processing_level = metadata.get("processing_level")
        row.processing_level = (
            str(processing_level)[:30] if processing_level is not None else None
        )
        product_type = metadata.get("product_type")
        row.product_type = str(product_type)[:30] if product_type is not None else None
        online = metadata.get("online")
        row.online = online if isinstance(online, bool) else None
        row.content_length = _integer_or_none(metadata.get("content_length"))
        footprint = metadata.get("geo_footprint")
        if footprint is None:
            row.footprint = None
        elif isinstance(footprint, str):
            row.footprint = footprint
        else:
            try:
                row.footprint = json.dumps(footprint, separators=(",", ":"))
            except (TypeError, ValueError):
                row.footprint = None
        row.last_seen_at = now

    db.commit()
    return persisted_ids


def catalogue_filters(
    *,
    forest_area_id: int,
    start_date: date,
    end_date: date,
    tile_id: str | None = None,
    max_cloud_cover: float | None = None,
    product_id: str | None = None,
):
    """Build the common SQL filters for list/count queries."""

    filters = [
        SatelliteCatalogueProduct.forest_area_id == forest_area_id,
        SatelliteCatalogueProduct.acquisition_datetime >= datetime.combine(
            start_date, time.min, tzinfo=UTC
        ),
        SatelliteCatalogueProduct.acquisition_datetime < datetime.combine(
            end_date + timedelta(days=1), time.min, tzinfo=UTC
        ),
    ]
    if tile_id:
        filters.append(SatelliteCatalogueProduct.tile_id == tile_id.upper())
    if max_cloud_cover is not None:
        filters.append(
            SatelliteCatalogueProduct.cloud_cover_percentage <= max_cloud_cover
        )
    if product_id:
        filters.append(
            SatelliteCatalogueProduct.product_id.ilike(f"%{product_id.strip()}%")
        )
    return filters


def latest_successful_search(
    db: Session,
    *,
    forest_area_id: int,
    start_date: date,
    end_date: date,
    cloud_cover: float | None,
) -> SatelliteCatalogueSearchJob | None:
    """Find a recent completed search that fully covers requested criteria."""

    query = db.query(SatelliteCatalogueSearchJob).filter(
        SatelliteCatalogueSearchJob.forest_area_id == forest_area_id,
        SatelliteCatalogueSearchJob.status == "COMPLETED",
        SatelliteCatalogueSearchJob.start_date <= start_date,
        SatelliteCatalogueSearchJob.end_date >= end_date,
    )
    if cloud_cover is None:
        query = query.filter(SatelliteCatalogueSearchJob.cloud_cover.is_(None))
    else:
        # A completed no-cloud-limit query also satisfies a cloud-limited read.
        query = query.filter(
            or_(
                SatelliteCatalogueSearchJob.cloud_cover.is_(None),
                SatelliteCatalogueSearchJob.cloud_cover >= cloud_cover,
            )
        )
    return query.order_by(
        SatelliteCatalogueSearchJob.completed_at.desc()
    ).first()


def latest_search_job(
    db: Session, forest_area_id: int
) -> SatelliteCatalogueSearchJob | None:
    return (
        db.query(SatelliteCatalogueSearchJob)
        .filter(SatelliteCatalogueSearchJob.forest_area_id == forest_area_id)
        .order_by(SatelliteCatalogueSearchJob.created_at.desc())
        .first()
    )


def serialize_search_job(job: SatelliteCatalogueSearchJob | None) -> dict | None:
    if job is None:
        return None
    return {
        "job_id": job.job_id,
        "forest_area_id": job.forest_area_id,
        "start_date": job.start_date.isoformat(),
        "end_date": job.end_date.isoformat(),
        "cloud_cover": job.cloud_cover,
        "status": job.status,
        "pages_completed": job.pages_completed,
        "products_found": job.products_found,
        "error_message": job.error_message,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
    }
