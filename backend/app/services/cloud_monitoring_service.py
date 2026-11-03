"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Cloud Monitoring Service

Purpose:
    Assembles what the dashboard's cloud monitoring card
    shows for one district.

Responsibilities:
    - Restrict district selection to an officer's
      jurisdiction.
    - Report current cloud cover from the weather provider.
    - Report Sentinel-2 cloud cover from imagery already
      held.
    - Say which observations are clear enough to analyse.
    - Report an unavailable half as unavailable.

The two halves are kept apart on purpose. See the note at
the top of weather_service: a Sentinel-2 product's cloud
cover was measured when the satellite passed, and offering
it as the sky now would be a false statement that happens
to look like a reading.

Jurisdiction:
    A district outside the officer's jurisdiction is refused
    here, in the service, not hidden in the interface. An
    officer who asks for another district by editing the
    request is refused by the same rule that governs every
    other record, app.services.jurisdiction.

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

import logging

from datetime import datetime

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.repositories.cloud_monitoring_repository import (
    CloudMonitoringRepository,
)
from app.services.cloud_conditions import (
    classify_cloud_cover,
    condition_label,
    is_suitable_for_analysis,
)
from app.services.jurisdiction import is_within_jurisdiction
from app.services.weather_service import (
    WeatherError,
    fetch_current_cloud_cover,
)


logger = logging.getLogger(__name__)


#: How many recent observations the card compares.
#:
#: Enough to see a trend across a fortnight of Sentinel-2
#: passes, which at a five-day revisit is three or four
#: scenes per monitored area.
OBSERVATION_LIMIT = 8


class CloudMonitoringError(Exception):
    """The card cannot be built for this request."""


class DistrictNotFound(CloudMonitoringError):
    """No such district."""


class DistrictOutsideJurisdiction(CloudMonitoringError):
    """The officer may not monitor this district."""


def available_districts(
    db: Session,
    user,
) -> list[dict]:
    """
    The districts this officer may select.

    Args:
        db:
            Database session.
        user:
            The signed-in officer.

    Returns:
        One entry per permitted district, in name order.

    A district officer is given their own district only. The
    selector therefore cannot offer a choice the server
    would refuse, while the server still refuses it if asked
    directly.
    """

    repository = CloudMonitoringRepository(db)

    permitted = []

    for district in repository.active_districts():
        if not is_within_jurisdiction(
            role=user.role,
            user_district_id=user.district_id,
            user_province_id=user.province_id,
            target_district_id=district.id,
            target_province_id=district.province_id,
        ):
            continue

        permitted.append(
            {
                "id": district.id,
                "name": district.name,
                "code": district.code,
            }
        )

    return permitted


def default_district_id(
    db: Session,
    user,
) -> int | None:
    """
    The district to show before the officer chooses one.

    Args:
        db:
            Database session.
        user:
            The signed-in officer.

    Returns:
        The officer's own district when they have one, else
        the first they are permitted to see, else None.
    """

    if user.district_id is not None:
        return user.district_id

    permitted = available_districts(db, user)

    return permitted[0]["id"] if permitted else None


def cloud_monitoring_report(
    db: Session,
    user,
    district_id: int,
    force_refresh: bool = False,
) -> dict:
    """
    Everything the cloud monitoring card displays.

    Args:
        db:
            Database session.
        user:
            The signed-in officer.
        district_id:
            District being monitored.
        force_refresh:
            Ask the weather provider again rather than
            reusing a cached reading. What the manual
            refresh button sets.

    Returns:
        Fields for CloudMonitoringResponse.

    Raises:
        DistrictNotFound:
            No district with that id.
        DistrictOutsideJurisdiction:
            The officer may not monitor it.

    A failure to reach the weather provider is not raised.
    The satellite half comes from imagery already held and
    remains useful on its own, so the report is returned
    with the current reading marked unavailable and the
    reason stated. Failing the whole request would take away
    working information because an optional extra was down.
    """

    repository = CloudMonitoringRepository(db)

    district = repository.get_district(district_id)

    if district is None or not district.is_active:
        raise DistrictNotFound(
            "That district is not available for monitoring."
        )

    if not is_within_jurisdiction(
        role=user.role,
        user_district_id=user.district_id,
        user_province_id=user.province_id,
        target_district_id=district.id,
        target_province_id=district.province_id,
    ):
        raise DistrictOutsideJurisdiction(
            "You may only monitor conditions in your own "
            "jurisdiction."
        )

    point = repository.observation_point(district)

    current = _current_reading(point, force_refresh)

    observations = _observations(
        repository,
        district.id,
    )

    return {
        "district_id": district.id,
        "district_name": district.name,
        "observation_point": (
            {
                "latitude": round(point.latitude, 4),
                "longitude": round(point.longitude, 4),
                "source": point.source,
                "monitored_area_count": point.monitored_area_count,
            }
            if point is not None
            else None
        ),
        "current": current,
        "satellite": observations,
        # When this report was assembled. The screen needs
        # it to say "last updated", and it is deliberately
        # not the same field as either the weather
        # observation time or an acquisition date.
        "generated_at": datetime.now().astimezone().isoformat(),
    }


def _current_reading(
    point,
    force_refresh: bool,
) -> dict:
    """
    The current-weather half of the report.

    Args:
        point:
            Where to ask about, or None when the district
            has no point at all.
        force_refresh:
            Bypass the cache.

    Returns:
        A block that always states whether it has a reading.
        When it does not, it says why in words an
        administrator can act on, and carries no percentage
        at all rather than a zero.
    """

    if point is None:
        return {
            "available": False,
            "unavailable_reason": (
                "This district has no monitored forest area "
                "and no reference location, so there is no "
                "point to report conditions for."
            ),
            "percentage": None,
            "condition": "UNKNOWN",
            "condition_label": condition_label(
                classify_cloud_cover(None)
            ),
            "observed_at": None,
            "retrieved_at": None,
            "provider": None,
            "latitude": None,
            "longitude": None,
        }

    try:
        reading = fetch_current_cloud_cover(
            latitude=point.latitude,
            longitude=point.longitude,
            force=force_refresh,
        )

    except WeatherError as exc:
        # Logged so an administrator sees a provider that
        # has stopped answering, rather than only officers
        # noticing a blank panel.
        logger.warning(
            "Current cloud cover unavailable: %s",
            exc,
        )

        return {
            "available": False,
            "unavailable_reason": str(exc),
            "percentage": None,
            "condition": "UNKNOWN",
            "condition_label": condition_label(
                classify_cloud_cover(None)
            ),
            "observed_at": None,
            "retrieved_at": None,
            "provider": get_settings().weather_provider_name,
            "latitude": None,
            "longitude": None,
        }

    condition = classify_cloud_cover(reading.percentage)

    return {
        "available": True,
        "unavailable_reason": None,
        "percentage": reading.percentage,
        "condition": condition.value,
        "condition_label": condition_label(condition),
        "observed_at": reading.observed_at,
        "retrieved_at": reading.retrieved_at.isoformat(),
        "provider": reading.provider,
        "latitude": round(reading.latitude, 4),
        "longitude": round(reading.longitude, 4),
    }


def _observations(
    repository: CloudMonitoringRepository,
    district_id: int,
) -> dict:
    """
    The Sentinel-2 half of the report.

    Args:
        repository:
            Data access for this feature.
        district_id:
            District whose imagery to list.

    Returns:
        The most recent observation, the ones before it for
        comparison, and how many of them are clear enough to
        analyse.

    Every entry carries its own acquisition date. The card
    compares observations, and a comparison without dates on
    each row invites the newest figure to be read as current
    conditions.
    """

    observations = repository.recent_observations(
        district_id,
        OBSERVATION_LIMIT,
    )

    entries = []

    for observation in observations:
        condition = classify_cloud_cover(
            observation.cloud_cover_percentage
        )

        entries.append(
            {
                "image_id": observation.image_id,
                "product_id": observation.product_id,
                "acquisition_date": (
                    observation.acquisition_date.isoformat()
                    if observation.acquisition_date is not None
                    else None
                ),
                "percentage": observation.cloud_cover_percentage,
                "condition": condition.value,
                "condition_label": condition_label(condition),
                "forest_area_name": observation.forest_area_name,
                "is_processed": observation.is_processed,
                "suitable_for_analysis": is_suitable_for_analysis(
                    observation.cloud_cover_percentage
                ),
            }
        )

    suitable = [
        entry
        for entry in entries
        if entry["suitable_for_analysis"] is True
    ]

    return {
        "available": bool(entries),
        "unavailable_reason": (
            None
            if entries
            else (
                "No Sentinel-2 imagery has been registered "
                "for this district yet, so there is no "
                "recorded cloud cover to compare."
            )
        ),
        "latest": entries[0] if entries else None,
        "observations": entries,
        "suitable_count": len(suitable),
        "observation_count": len(entries),
        # Stated so the card can explain what "suitable"
        # means without the number being written into the
        # interface a second time.
        "suitability_threshold": (
            get_settings().max_cloud_cover_percentage
        ),
    }
