"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Satellite Images API

Purpose:
    Provides endpoints for managing Sentinel-2
    satellite images.

Responsibilities:
    - Register satellite images.
    - Retrieve satellite images.
    - Retrieve images by forest area.
    - Mark images as processed.
    - Delete satellite images.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Version:
    1.0.0
===========================================================
"""

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from sqlalchemy.orm import Session

from app.api.deps import (
    get_admin_user,
    get_current_active_user,
)
from app.database.session import get_db
from app.models.user import User
from app.repositories.forest_area_repository import (
    ForestAreaRepository,
)
from app.repositories.satellite_image_repository import (
    SatelliteImageRepository,
)
from app.schemas.satellite_image import (
    SatelliteImageCreate,
    SatelliteImageResponse,
)
from app.services.sentinel_service import (
    SentinelService,
)

router = APIRouter(
    prefix="/satellite-images",
    tags=["Satellite Images"],
)

# ---------------------------------------------------------
# Get All Images
# ---------------------------------------------------------
@router.get(
    "",
    response_model=list[SatelliteImageResponse],
)
def get_satellite_images(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    """
    Return all registered satellite images.
    """

    repository = SatelliteImageRepository(db)

    return repository.get_all()


# ---------------------------------------------------------
# Get Image By ID
# ---------------------------------------------------------
@router.get(
    "/{image_id}",
    response_model=SatelliteImageResponse,
)
def get_satellite_image(
    image_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    """
    Retrieve one satellite image.
    """

    repository = SatelliteImageRepository(db)

    image = repository.get_by_id(
        image_id,
    )

    if image is None:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Satellite image not found.",
        )

    return image


# ---------------------------------------------------------
# Get Images By Forest Area
# ---------------------------------------------------------
@router.get(
    "/forest/{forest_area_id}",
    response_model=list[SatelliteImageResponse],
)
def get_images_by_forest_area(
    forest_area_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    """
    Return all images belonging to
    a forest area.
    """

    forest_repository = ForestAreaRepository(db)

    forest = forest_repository.get_by_id(
        forest_area_id,
    )

    if forest is None:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Forest area not found.",
        )

    repository = SatelliteImageRepository(db)

    return repository.get_by_forest_area(
        forest_area_id,
    )


# ---------------------------------------------------------
# Get Latest Image
# ---------------------------------------------------------
@router.get(
    "/forest/{forest_area_id}/latest",
    response_model=SatelliteImageResponse,
)
def get_latest_image(
    forest_area_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    """
    Return the newest satellite image
    for a forest area.
    """

    repository = SatelliteImageRepository(db)

    image = repository.get_latest_image(
        forest_area_id,
    )

    if image is None:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No satellite images found.",
        )

    return image
# ---------------------------------------------------------
# Register Satellite Image
# ---------------------------------------------------------
@router.post(
    "",
    response_model=SatelliteImageResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_satellite_image(
    request: SatelliteImageCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    """
    Register a Sentinel-2 satellite image.
    """

    forest_repository = ForestAreaRepository(db)

    forest = forest_repository.get_by_id(
        request.forest_area_id,
    )

    if forest is None:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Forest area not found.",
        )

    repository = SatelliteImageRepository(db)

    existing = repository.get_by_product_id(
        request.product_id,
    )

    if existing is not None:

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Satellite image already exists.",
        )

    service = SentinelService(db)

    image = service.register_satellite_image(
        forest_area_id=request.forest_area_id,
        product_id=request.product_id,
        tile_id=request.tile_id,
        acquisition_date=request.acquisition_date,
        cloud_cover=request.cloud_cover_percentage,
        file_name=request.file_name,
        storage_path=request.storage_path,
        file_size_mb=request.file_size_mb,
    )

    return image


# ---------------------------------------------------------
# Mark Image as Processed
# ---------------------------------------------------------
@router.put(
    "/{image_id}/processed",
    response_model=SatelliteImageResponse,
)
def mark_image_processed(
    image_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    """
    Mark a satellite image as processed.
    """

    repository = SatelliteImageRepository(db)

    image = repository.get_by_id(
        image_id,
    )

    if image is None:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Satellite image not found.",
        )

    service = SentinelService(db)

    image = service.mark_as_processed(
        image,
    )

    return image


# ---------------------------------------------------------
# Delete Satellite Image
# ---------------------------------------------------------
@router.delete(
    "/{image_id}",
    status_code=status.HTTP_200_OK,
)
def delete_satellite_image(
    image_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_admin_user),
):
    """
    Permanently delete a satellite image.

    Only Administrators can perform this action.
    """

    repository = SatelliteImageRepository(db)

    image = repository.get_by_id(
        image_id,
    )

    if image is None:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Satellite image not found.",
        )

    repository.delete(
        image,
    )

    return {
        "message": "Satellite image deleted successfully."
    }


# ---------------------------------------------------------
# Get Image by Product ID
# ---------------------------------------------------------
@router.get(
    "/product/{product_id}",
    response_model=SatelliteImageResponse,
)
def get_image_by_product_id(
    product_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    """
    Retrieve a satellite image by Sentinel product ID.
    """

    repository = SatelliteImageRepository(db)

    image = repository.get_by_product_id(
        product_id,
    )

    if image is None:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Satellite image not found.",
        )

    return image