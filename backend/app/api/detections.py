"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Detections API

Purpose:
    Provides endpoints for managing deforestation
    detections.

Responsibilities:
    - View detections.
    - Verify detections.
    - Reject detections.
    - Close detections.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Version:
    1.0.0
===========================================================
"""

from datetime import UTC, datetime

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
    get_forestry_officer,
)
from app.database.session import get_db
from app.models.user import User
from app.repositories.detection_repository import DetectionRepository
from app.schemas.detection import (
    DetectionResponse,
    DetectionVerification,
)

router = APIRouter(
    prefix="/detections",
    tags=["Detections"],
)


# ---------------------------------------------------------
# Get All Detections
# ---------------------------------------------------------
@router.get(
    "",
    response_model=list[DetectionResponse],
)
def get_detections(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    """
    Return all detections.
    """

    repository = DetectionRepository(db)

    return repository.get_all()


# ---------------------------------------------------------
# Get Pending Detections
# ---------------------------------------------------------
@router.get(
    "/pending",
    response_model=list[DetectionResponse],
)
def get_pending_detections(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    """
    Return all pending detections.
    """

    repository = DetectionRepository(db)

    return repository.get_pending()


# ---------------------------------------------------------
# Get Verified Detections
# ---------------------------------------------------------
@router.get(
    "/verified",
    response_model=list[DetectionResponse],
)
def get_verified_detections(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    """
    Return all verified detections.
    """

    repository = DetectionRepository(db)

    return repository.get_verified()


# ---------------------------------------------------------
# Get Forest Detections
# ---------------------------------------------------------
@router.get(
    "/forest/{forest_area_id}",
    response_model=list[DetectionResponse],
)
def get_forest_detections(
    forest_area_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    """
    Return detections belonging to one forest area.
    """

    repository = DetectionRepository(db)

    return repository.get_by_forest_area(
        forest_area_id,
    )


# ---------------------------------------------------------
# Get Detection
# ---------------------------------------------------------
@router.get(
    "/{detection_id}",
    response_model=DetectionResponse,
)
def get_detection(
    detection_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    """
    Retrieve one detection.
    """

    repository = DetectionRepository(db)

    detection = repository.get_by_id(
        detection_id,
    )

    if detection is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Detection not found.",
        )

    return detection


# ---------------------------------------------------------
# Verify Detection
# ---------------------------------------------------------
@router.put(
    "/{detection_id}/verify",
    response_model=DetectionResponse,
)
def verify_detection(
    detection_id: int,
    request: DetectionVerification,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_forestry_officer),
):
    """
    Verify or reject a detection.
    """

    repository = DetectionRepository(db)

    detection = repository.get_by_id(
        detection_id,
    )

    if detection is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Detection not found.",
        )

    detection.status = request.status
    detection.verification_notes = request.verification_notes
    detection.verified_by = current_user.id
    detection.verified_at = datetime.now(UTC)

    repository.update(detection)

    return detection


# ---------------------------------------------------------
# Delete Detection
# ---------------------------------------------------------
@router.delete(
    "/{detection_id}",
    status_code=status.HTTP_200_OK,
)
def delete_detection(
    detection_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_admin_user),
):
    """
    Permanently delete a detection.

    Only Administrators can perform this action.
    """

    repository = DetectionRepository(db)

    detection = repository.get_by_id(
        detection_id,
    )

    if detection is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Detection not found.",
        )

    repository.delete(detection)

    return {
        "message": "Detection deleted successfully."
    }