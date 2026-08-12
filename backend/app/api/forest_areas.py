"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Forest Areas API

Purpose:
    Provides endpoints for managing forest areas,
    satellite imagery, and forest analysis.

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia
===========================================================
"""

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)

from geoalchemy2 import WKTElement
from sqlalchemy.orm import Session

from app.api.deps import (
    get_current_active_user,
    get_forestry_officer,
)

from app.database.session import get_db

from app.models.forest_area import ForestArea
from app.models.satellite_image import SatelliteImage
from app.models.user import User

from app.schemas.forest_area import (
    ForestAreaCreate,
    ForestAreaResponse,
    ForestAreaUpdate,
)

from app.schemas.analysis import AnalysisJobResponse

from app.services.analysis_service import AnalysisService


# =========================================================
# ROUTER
# =========================================================

router = APIRouter(
    prefix="/forest-areas",
    tags=["Forest Areas"],
)


# =========================================================
# GET ALL FOREST AREAS
# =========================================================

@router.get(
    "",
    response_model=list[ForestAreaResponse],
)
def get_forest_areas(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    """
    Return all active forest areas.
    """

    return (
        db.query(ForestArea)
        .filter(
            ForestArea.is_active.is_(True)
        )
        .order_by(
            ForestArea.name
        )
        .all()
    )


# =========================================================
# GET ONE FOREST AREA
# =========================================================

@router.get(
    "/{forest_area_id}",
    response_model=ForestAreaResponse,
)
def get_forest_area(
    forest_area_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    """
    Retrieve one forest area.
    """

    forest = (
        db.query(ForestArea)
        .filter(
            ForestArea.id == forest_area_id
        )
        .first()
    )

    if forest is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Forest area not found.",
        )

    return forest


# =========================================================
# CREATE FOREST AREA
# =========================================================

@router.post(
    "",
    response_model=ForestAreaResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_forest_area(
    forest_data: ForestAreaCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_forestry_officer),
):
    """
    Create a new forest area.
    """

    data = forest_data.model_dump()

    geometry_wkt = data.pop("geometry")

    try:
        geometry = WKTElement(
            geometry_wkt,
            srid=4326,
        )

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid geometry: {str(exc)}",
        )

    forest = ForestArea(
        **data,
        geometry=geometry,
        created_by=current_user.id,
    )

    db.add(forest)

    try:
        db.commit()
        db.refresh(forest)

    except Exception as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not create forest area: {str(exc)}",
        )

    return forest


# =========================================================
# UPDATE FOREST AREA
# =========================================================

@router.put(
    "/{forest_area_id}",
    response_model=ForestAreaResponse,
    status_code=status.HTTP_200_OK,
)
def update_forest_area(
    forest_area_id: int,
    forest_data: ForestAreaUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_forestry_officer),
):
    """
    Update an existing forest area.
    """

    forest = (
        db.query(ForestArea)
        .filter(
            ForestArea.id == forest_area_id
        )
        .first()
    )

    if forest is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Forest area not found.",
        )

    update_data = forest_data.model_dump(
        exclude_unset=True,
    )

    # -----------------------------------------------------
    # Handle geometry separately
    # -----------------------------------------------------

    if "geometry" in update_data:

        geometry_wkt = update_data.pop("geometry")

        try:
            update_data["geometry"] = WKTElement(
                geometry_wkt,
                srid=4326,
            )

        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid geometry: {str(exc)}",
            )

    # -----------------------------------------------------
    # Update fields
    # -----------------------------------------------------

    for field, value in update_data.items():

        setattr(
            forest,
            field,
            value,
        )

    try:
        db.commit()
        db.refresh(forest)

    except Exception as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not update forest area: {str(exc)}",
        )

    return forest


# =========================================================
# DEACTIVATE FOREST AREA
# =========================================================

@router.delete(
    "/{forest_area_id}",
    status_code=status.HTTP_200_OK,
)
def delete_forest_area(
    forest_area_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_forestry_officer),
):
    """
    Deactivate a forest area.
    """

    forest = (
        db.query(ForestArea)
        .filter(
            ForestArea.id == forest_area_id
        )
        .first()
    )

    if forest is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Forest area not found.",
        )

    forest.is_active = False

    try:
        db.commit()

    except Exception as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not deactivate forest area: {str(exc)}",
        )

    return {
        "message": "Forest area deactivated successfully."
    }


# =========================================================
# GET SATELLITE IMAGES
# =========================================================

@router.get(
    "/{forest_area_id}/images",
)
def get_satellite_images(
    forest_area_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    """
    Return all satellite images for a forest area.

    Only direct SatelliteImage fields are returned.
    Relationships are intentionally excluded to prevent
    PostGIS WKBElement serialization errors.
    """

    # -----------------------------------------------------
    # Verify forest area exists
    # -----------------------------------------------------

    forest = (
        db.query(ForestArea)
        .filter(
            ForestArea.id == forest_area_id
        )
        .first()
    )

    if forest is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Forest area not found.",
        )

    # -----------------------------------------------------
    # Retrieve satellite images
    # -----------------------------------------------------

    images = (
        db.query(SatelliteImage)
        .filter(
            SatelliteImage.forest_area_id
            == forest_area_id
        )
        .order_by(
            SatelliteImage.acquisition_date.desc()
        )
        .all()
    )

    # -----------------------------------------------------
    # Convert ORM objects to JSON-safe dictionaries
    # -----------------------------------------------------

    result = []

    for image in images:

        result.append(
            {
                "id": image.id,
                "forest_area_id": image.forest_area_id,
                "product_id": image.product_id,
                "tile_id": image.tile_id,
                "satellite_name": image.satellite_name,
                "acquisition_date": image.acquisition_date,
                "processing_level": image.processing_level,
            }
        )

    return result


# =========================================================
# RUN FOREST ANALYSIS
# =========================================================

@router.post(
    "/{forest_area_id}/run-analysis",
    response_model=AnalysisJobResponse,
    status_code=status.HTTP_201_CREATED,
)
def run_analysis(
    forest_area_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_forestry_officer),
):
    """
    Start deforestation analysis for a forest area.
    """

    # -----------------------------------------------------
    # Verify forest area exists
    # -----------------------------------------------------

    forest = (
        db.query(ForestArea)
        .filter(
            ForestArea.id == forest_area_id
        )
        .first()
    )

    if forest is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Forest area not found.",
        )

    # -----------------------------------------------------
    # Create analysis service
    # -----------------------------------------------------

    service = AnalysisService(db)

    # -----------------------------------------------------
    # Run analysis
    # -----------------------------------------------------

    try:

        job = service.run_analysis(
            forest_area_id=forest_area_id,
            started_by=current_user.id,
        )

    except ValueError as exc:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )

    except Exception as exc:

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Analysis failed: {str(exc)}",
        )

    return job