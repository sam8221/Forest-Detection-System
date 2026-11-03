"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Cloud Monitoring API

Purpose:
    Serves the dashboard's cloud monitoring card.

Responsibilities:
    - List the districts an officer may monitor.
    - Return current and satellite cloud cover for one.

This module holds no logic. Deciding what an officer may
see, what the figures mean and what to do when a provider is
unreachable all belong to
app.services.cloud_monitoring_service, which is testable
without a web server.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Version:
    1.0.0
===========================================================
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.database.session import get_db
from app.models.user import User
from app.schemas.cloud_monitoring import (
    CloudMonitoringDistrictsResponse,
    CloudMonitoringResponse,
)
from app.services.cloud_monitoring_service import (
    DistrictNotFound,
    DistrictOutsideJurisdiction,
    available_districts,
    cloud_monitoring_report,
    default_district_id,
)


router = APIRouter(
    prefix="/cloud-monitoring",
    tags=["Cloud Monitoring"],
)


@router.get(
    "/districts",
    response_model=CloudMonitoringDistrictsResponse,
)
def get_monitoring_districts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Districts this officer may monitor conditions for.

    A district officer receives their own district only, so
    the selector cannot offer a choice the server would
    refuse. The server still refuses it if asked directly.
    """

    return {
        "districts": available_districts(db, current_user),
        "default_district_id": default_district_id(
            db,
            current_user,
        ),
    }


@router.get(
    "",
    response_model=CloudMonitoringResponse,
)
def get_cloud_monitoring(
    district_id: int = Query(
        description="District to report conditions for.",
    ),
    refresh: bool = Query(
        default=False,
        description=(
            "Ask the weather provider again instead of "
            "reusing a cached reading. Set by the manual "
            "refresh button."
        ),
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Cloud conditions over one district.

    Returns the current reading from the weather provider
    and the cloud cover recorded for recent Sentinel-2
    observations, each with its own timestamp and source.

    A weather provider that cannot be reached does not fail
    the request: the satellite half comes from imagery
    already held and stays useful, so the response marks the
    current reading unavailable and says why.
    """

    try:
        return cloud_monitoring_report(
            db=db,
            user=current_user,
            district_id=district_id,
            force_refresh=refresh,
        )

    except DistrictNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except DistrictOutsideJurisdiction as exc:
        # FR-04. Refused by the service before any figure is
        # read, so a district officer who edits the district
        # id in the request gets nothing back.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
