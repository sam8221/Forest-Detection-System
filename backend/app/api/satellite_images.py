"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Satellite Images API

Purpose:
    Provides endpoints for searching, downloading and
    managing Sentinel-2 satellite images.

Responsibilities:
    - Search real Sentinel-2 imagery from Copernicus.
    - Download selected Sentinel-2 products.
    - Register downloaded satellite images.
    - Retrieve satellite images.
    - Retrieve images by forest area.
    - Retrieve latest image.
    - Mark images as processed.
    - Delete satellite images.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Version:
    1.2.0
===========================================================
"""

from datetime import date, datetime

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)

from pydantic import BaseModel, Field

from geoalchemy2.shape import to_shape

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

from app.services.copernicus_service import (
    CopernicusService,
)

from app.services.sentinel_service import (
    SentinelService,
)


router = APIRouter(
    prefix="/satellite-images",
    tags=["Satellite Images"],
)


# =========================================================
# DOWNLOAD REQUEST SCHEMA
# =========================================================

class SatelliteDownloadRequest(BaseModel):
    """
    Request data for downloading one Sentinel-2 product.
    """

    product_id: str = Field(
        ...,
        min_length=10,
        max_length=150,
    )

    product_name: str = Field(
        ...,
        min_length=3,
        max_length=255,
    )

    tile_id: str = Field(
        ...,
        min_length=3,
        max_length=20,
    )

    acquisition_date: str

    cloud_cover: float = Field(
        ...,
        ge=0,
        le=100,
    )


# =========================================================
# SEARCH REAL SENTINEL-2 IMAGERY
# =========================================================

@router.get(
    "/forest/{forest_area_id}/search",
)
def search_sentinel_images_for_forest(
    forest_area_id: int,
    start_date: str,
    end_date: str,
    cloud_cover: float = 30.0,
    limit: int = 20,
    db: Session = Depends(get_db),
    _: User = Depends(
        get_current_active_user
    ),
):
    """
    Search the real Copernicus Data Space
    catalogue for Sentinel-2 imagery covering
    a specific ForestWatch forest area.
    """

    # -----------------------------------------------------
    # Validate dates
    # -----------------------------------------------------

    try:

        start = datetime.strptime(
            start_date,
            "%Y-%m-%d",
        ).date()

        end = datetime.strptime(
            end_date,
            "%Y-%m-%d",
        ).date()

    except ValueError:

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Dates must use YYYY-MM-DD format."
            ),
        )

    if start > end:

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "start_date cannot be later "
                "than end_date."
            ),
        )

    # -----------------------------------------------------
    # Validate cloud coverage
    # -----------------------------------------------------

    if cloud_cover < 0 or cloud_cover > 100:

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "cloud_cover must be between "
                "0 and 100."
            ),
        )

    # -----------------------------------------------------
    # Validate limit
    # -----------------------------------------------------

    if limit < 1 or limit > 100:

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "limit must be between "
                "1 and 100."
            ),
        )

    # -----------------------------------------------------
    # Find forest area
    # -----------------------------------------------------

    forest_repository = (
        ForestAreaRepository(db)
    )

    forest = (
        forest_repository.get_by_id(
            forest_area_id
        )
    )

    if forest is None:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Forest area not found.",
        )

    # -----------------------------------------------------
    # Check geometry
    # -----------------------------------------------------

    if forest.geometry is None:

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "The selected forest area "
                "does not have a valid geometry."
            ),
        )

    # -----------------------------------------------------
    # Convert PostGIS geometry to WKT
    # -----------------------------------------------------

    try:

        geometry_wkt = to_shape(
            forest.geometry
        ).wkt

    except Exception as exc:

        raise HTTPException(
            status_code=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail=(
                "Unable to convert forest "
                f"geometry to WKT: {exc}"
            ),
        ) from exc

    # -----------------------------------------------------
    # Search Copernicus
    # -----------------------------------------------------

    copernicus = CopernicusService()

    try:

        products = (
            copernicus.search_products(
                start_date=start_date,
                end_date=end_date,
                cloud_cover=cloud_cover,
                geometry_wkt=geometry_wkt,
                limit=limit,
            )
        )

    except Exception as exc:

        print(
            "Copernicus search error:",
            exc,
        )

        raise HTTPException(
            status_code=(
                status.HTTP_502_BAD_GATEWAY
            ),
            detail=(
                "Unable to retrieve Sentinel-2 "
                "imagery from Copernicus."
            ),
        ) from exc

    # -----------------------------------------------------
    # Format results
    # -----------------------------------------------------

    results = []

    for product in products:

        metadata = (
            copernicus.get_product_metadata(
                product
            )
        )

        results.append(
            {
                "product_id": metadata[
                    "product_id"
                ],

                "product_name": metadata[
                    "product_name"
                ],

                "satellite": "Sentinel-2",

                "tile_id": metadata[
                    "tile_id"
                ],

                "acquisition_date": metadata[
                    "acquisition_date"
                ],

                "cloud_cover_percentage": (
                    metadata[
                        "cloud_cover"
                    ]
                ),

                "processing_level": (
                    metadata[
                        "processing_level"
                    ]
                ),

                "online": metadata[
                    "online"
                ],

                "content_length": metadata[
                    "content_length"
                ],

                "footprint": metadata[
                    "geo_footprint"
                ],
            }
        )

    return {
        "forest_area": {
            "id": forest.id,
            "forest_code": (
                forest.forest_code
            ),
            "name": forest.name,
            "area_hectares": (
                forest.area_hectares
            ),
        },

        "search": {
            "start_date": start_date,
            "end_date": end_date,
            "cloud_cover": cloud_cover,
            "limit": limit,
        },

        "count": len(results),

        "products": results,
    }


# =========================================================
# DOWNLOAD REAL SENTINEL-2 PRODUCT
# =========================================================

@router.post(
    "/forest/{forest_area_id}/download",
    response_model=SatelliteImageResponse,
    status_code=status.HTTP_201_CREATED,
)
def download_sentinel_product(
    forest_area_id: int,
    request: SatelliteDownloadRequest,
    db: Session = Depends(get_db),
    _: User = Depends(
        get_current_active_user
    ),
):
    """
    Download one real Sentinel-2 product from
    Copernicus and register it in the database.
    """

    # -----------------------------------------------------
    # Find forest area
    # -----------------------------------------------------

    forest_repository = (
        ForestAreaRepository(db)
    )

    forest = (
        forest_repository.get_by_id(
            forest_area_id
        )
    )

    if forest is None:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Forest area not found.",
        )

    # -----------------------------------------------------
    # Check duplicate
    # -----------------------------------------------------

    repository = (
        SatelliteImageRepository(db)
    )

    existing = (
        repository.get_by_product_id(
            request.product_id
        )
    )

    if existing is not None:

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This Sentinel-2 product "
                "has already been downloaded."
            ),
        )

    # -----------------------------------------------------
    # Validate acquisition date
    # -----------------------------------------------------

    try:

        acquisition_date = datetime.strptime(
            request.acquisition_date[:10],
            "%Y-%m-%d",
        ).date()

    except ValueError:

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "acquisition_date must contain "
                "a valid YYYY-MM-DD date."
            ),
        )

    # -----------------------------------------------------
    # Download product
    # -----------------------------------------------------

    service = SentinelService(db)

    try:

        image = service.download_product(
            forest_area=forest,
            product_id=request.product_id,
            product_name=request.product_name,
            tile_id=request.tile_id,
            acquisition_date=acquisition_date,
            cloud_cover=request.cloud_cover,
        )

    except Exception as exc:

        print(
            "Sentinel download error:",
            exc,
        )

        raise HTTPException(
            status_code=(
                status.HTTP_502_BAD_GATEWAY
            ),
            detail=(
                "Unable to download the selected "
                f"Sentinel-2 product: {exc}"
            ),
        ) from exc

    return image


# =========================================================
# GET ALL IMAGES
# =========================================================

@router.get(
    "",
    response_model=list[
        SatelliteImageResponse
    ],
)
def get_satellite_images(
    db: Session = Depends(get_db),
    _: User = Depends(
        get_current_active_user
    ),
):
    """
    Return all registered satellite images.
    """

    repository = (
        SatelliteImageRepository(db)
    )

    return repository.get_all()


# =========================================================
# GET IMAGES BY FOREST AREA
# =========================================================

@router.get(
    "/forest/{forest_area_id}",
    response_model=list[
        SatelliteImageResponse
    ],
)
def get_images_by_forest_area(
    forest_area_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(
        get_current_active_user
    ),
):
    """
    Return all downloaded images belonging
    to a forest area.
    """

    forest_repository = (
        ForestAreaRepository(db)
    )

    forest = (
        forest_repository.get_by_id(
            forest_area_id
        )
    )

    if forest is None:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Forest area not found.",
        )

    repository = (
        SatelliteImageRepository(db)
    )

    return repository.get_by_forest_area(
        forest_area_id
    )


# =========================================================
# GET LATEST IMAGE
# =========================================================

@router.get(
    "/forest/{forest_area_id}/latest",
    response_model=SatelliteImageResponse,
)
def get_latest_image(
    forest_area_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(
        get_current_active_user
    ),
):
    """
    Return the newest downloaded satellite
    image for a forest area.
    """

    forest_repository = (
        ForestAreaRepository(db)
    )

    forest = (
        forest_repository.get_by_id(
            forest_area_id
        )
    )

    if forest is None:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Forest area not found.",
        )

    repository = (
        SatelliteImageRepository(db)
    )

    image = (
        repository.get_latest_image(
            forest_area_id
        )
    )

    if image is None:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No satellite images found.",
        )

    return image


# =========================================================
# GET IMAGE BY ID
# =========================================================

@router.get(
    "/{image_id}",
    response_model=SatelliteImageResponse,
)
def get_satellite_image(
    image_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(
        get_current_active_user
    ),
):
    """
    Retrieve one registered satellite image.
    """

    repository = (
        SatelliteImageRepository(db)
    )

    image = (
        repository.get_by_id(
            image_id
        )
    )

    if image is None:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Satellite image not found.",
        )

    return image


# =========================================================
# REGISTER SATELLITE IMAGE
# =========================================================

@router.post(
    "",
    response_model=SatelliteImageResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_satellite_image(
    request: SatelliteImageCreate,
    db: Session = Depends(get_db),
    _: User = Depends(
        get_current_active_user
    ),
):
    """
    Register an already downloaded Sentinel-2 image.
    """

    forest_repository = (
        ForestAreaRepository(db)
    )

    forest = (
        forest_repository.get_by_id(
            request.forest_area_id
        )
    )

    if forest is None:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Forest area not found.",
        )

    repository = (
        SatelliteImageRepository(db)
    )

    existing = (
        repository.get_by_product_id(
            request.product_id
        )
    )

    if existing is not None:

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Satellite image already exists."
            ),
        )

    service = SentinelService(db)

    image = (
        service.register_satellite_image(
            forest_area=forest,
            product_id=request.product_id,
            tile_id=request.tile_id,
            acquisition_date=(
                request.acquisition_date
            ),
            cloud_cover=(
                request.cloud_cover_percentage
            ),
            file_name=request.file_name,
            storage_path=request.storage_path,
            file_size_mb=request.file_size_mb,
        )
    )

    return image


# =========================================================
# MARK IMAGE AS PROCESSED
# =========================================================

@router.put(
    "/{image_id}/processed",
    response_model=SatelliteImageResponse,
)
def mark_image_processed(
    image_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(
        get_current_active_user
    ),
):
    """
    Mark a satellite image as processed.
    """

    repository = (
        SatelliteImageRepository(db)
    )

    image = (
        repository.get_by_id(
            image_id
        )
    )

    if image is None:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Satellite image not found.",
        )

    service = SentinelService(db)

    image = (
        service.mark_as_processed(
            image
        )
    )

    return image


# =========================================================
# DELETE SATELLITE IMAGE
# =========================================================

@router.delete(
    "/{image_id}",
    status_code=status.HTTP_200_OK,
)
def delete_satellite_image(
    image_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(
        get_admin_user
    ),
):
    """
    Permanently delete a satellite image.

    Only administrators can perform this action.
    """

    repository = (
        SatelliteImageRepository(db)
    )

    image = (
        repository.get_by_id(
            image_id
        )
    )

    if image is None:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Satellite image not found.",
        )

    repository.delete(image)

    return {
        "message": (
            "Satellite image deleted successfully."
        )
    }


# =========================================================
# GET IMAGE BY PRODUCT ID
# =========================================================

@router.get(
    "/product/{product_id}",
    response_model=SatelliteImageResponse,
)
def get_image_by_product_id(
    product_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(
        get_current_active_user
    ),
):
    """
    Retrieve a satellite image by
    Sentinel product ID.
    """

    repository = (
        SatelliteImageRepository(db)
    )

    image = (
        repository.get_by_product_id(
            product_id
        )
    )

    if image is None:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Satellite image not found.",
        )

    return image