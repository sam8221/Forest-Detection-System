"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Planetary Computer Router

Purpose:
    Exposes the dashboard's Sentinel-2 scene summary over
    HTTP.

Responsibilities:
    - Authenticate the caller.
    - Delegate to PlanetaryService.
    - Translate service errors into HTTP responses.

Note on layering:
    This module contains no business logic, in keeping with
    the architecture used throughout app/api. The catalogue
    search, scene selection and error handling all live in
    app/services/planetary_service.py, where they can be
    exercised without a web server.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Version:
    2.0.0
===========================================================
"""

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_current_active_user
from app.models.user import User
from app.services.planetary_service import (
    PlanetaryNoImageryError,
    PlanetaryService,
    PlanetaryUnavailableError,
)


router = APIRouter(
    prefix="/planetary",
    tags=["Planetary Computer"],
)


@router.get("/sentinel")
def get_sentinel_image(
    cloud_cover: float | None = Query(
        default=None,
        ge=0,
        le=100,
        description=(
            "Cloud cover ceiling as a percentage. Defaults "
            "to the configured system threshold."
        ),
    ),
    _: User = Depends(get_current_active_user),
) -> dict:
    """
    Return a summary of the most recent Sentinel-2 scene.

    Args:
        cloud_cover:
            Cloud cover ceiling, or None for the configured
            default.

    Returns:
        dict: Scene metadata and map tile endpoints.

    Raises:
        HTTPException:
            502 when the catalogue cannot be reached, or
            404 when it holds no usable scene.

    Note:
        The detail returned is the message raised by the
        service, which is written to be shown to an officer.
        The underlying technical cause is written to the
        server log instead of being returned, so that a
        network fault does not put internal host names and
        library details on screen.
    """

    service = PlanetaryService()

    try:
        return service.get_latest_scene(
            max_cloud_cover=cloud_cover,
        )

    except PlanetaryUnavailableError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc

    except PlanetaryNoImageryError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc
