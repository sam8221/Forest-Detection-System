"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Forest Areas API

Purpose:
    Provides endpoints for managing forest areas.

Responsibilities:
    - Create forest areas.
    - Retrieve forest areas.
    - Update forest areas.
    - Deactivate forest areas.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Version:
    1.0.0
===========================================================
"""
from app.schemas.analysis import AnalysisJobResponse
from app.models.analysis_job import AnalysisJob
from app.services.detection_service import DetectionService
from app.models.satellite_image import SatelliteImage
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from sqlalchemy.orm import Session

from app.api.deps import (
    get_current_active_user,
    get_forestry_officer,
)
from app.database.session import get_db
from app.models.forest_area import ForestArea
from app.models.user import User
from app.schemas.forest_area import (
    ForestAreaCreate,
    ForestAreaResponse,
    ForestAreaUpdate,
)

router = APIRouter(
    prefix="/forest-areas",
    tags=["Forest Areas"],
)
# ---------------------------------------------------------
# Get All Forest Areas
# ---------------------------------------------------------
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
            ForestArea.is_active.is_(True),
        )
        .order_by(
            ForestArea.name,
        )
        .all()
    )
# ---------------------------------------------------------
# Get Forest Area
# ---------------------------------------------------------
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
            ForestArea.id == forest_area_id,
        )
        .first()
    )

    if forest is None:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Forest area not found.",
        )

    return forest
# ---------------------------------------------------------
# Create Forest Area
# ---------------------------------------------------------
@router.post(
    "",
    response_model=ForestAreaResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_forest_area(
    forest_data: ForestAreaCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        get_forestry_officer,
    ),
):
    """
    Create a new forest area.
    """

    forest = ForestArea(
        **forest_data.model_dump(),
        created_by=current_user.id,
    )

    db.add(forest)

    db.commit()

    db.refresh(forest)

    return forest
# ---------------------------------------------------------
# Update Forest Area
# ---------------------------------------------------------
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
            ForestArea.id == forest_area_id,
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

    for field, value in update_data.items():
        setattr(
            forest,
            field,
            value,
        )

    db.commit()

    db.refresh(forest)

    return forest
# ---------------------------------------------------------
# Deactivate Forest Area
# ---------------------------------------------------------
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

    The record remains in the database for
    auditing purposes.
    """

    forest = (
        db.query(ForestArea)
        .filter(
            ForestArea.id == forest_area_id,
        )
        .first()
    )

    if forest is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Forest area not found.",
        )

    forest.is_active = False

    db.commit()

    return {
        "message": "Forest area deactivated successfully."
    }
# ---------------------------------------------------------
# Get Forest Area Satellite Images
# ---------------------------------------------------------
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
    """

    return (
        db.query(SatelliteImage)
        .filter(
            SatelliteImage.forest_area_id == forest_area_id,
        )
        .order_by(
            SatelliteImage.acquisition_date.desc(),
        )
        .all()
    )
    # ---------------------------------------------------------
# Run Forest Analysis
# ---------------------------------------------------------
@router.post(
    "/{forest_area_id}/run-analysis",
    response_model=AnalysisJobResponse,
    status_code=status.HTTP_201_CREATED,
)
def run_analysis(
    forest_area_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_forestry_officer),
):
    """
    Start deforestation analysis for a forest area.
    """

    forest = (
        db.query(ForestArea)
        .filter(
            ForestArea.id == forest_area_id,
        )
        .first()
    )

    if forest is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Forest area not found.",
        )

    service = DetectionService(db)

    job = service.run_analysis(
        forest_area_id=forest_area_id,
    )

    return job