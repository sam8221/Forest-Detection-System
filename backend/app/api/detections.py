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
    - Trigger alerts when detections are verified.

Author:
    Samuel Bikiloni

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
from sqlalchemy.orm import Session

from app.api.deps import (
    get_admin_user,
    get_current_active_user,
    get_forestry_officer,
)

from app.database.session import get_db

from app.models.enums import DetectionStatus
from app.models.user import User

from app.repositories.detection_repository import (
    DetectionRepository,
)

from app.schemas.detection import (
    DetectionResponse,
    DetectionVerification,
)

from app.services.detection_service import (
    DetectionService,
)


# =========================================================
# ROUTER
# =========================================================

router = APIRouter(
    prefix="/detections",
    tags=["Detections"],
)


# =========================================================
# GET ALL DETECTIONS
# =========================================================

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


# =========================================================
# GET PENDING DETECTIONS
# =========================================================

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


# =========================================================
# GET VERIFIED DETECTIONS
# =========================================================

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


# =========================================================
# GET FOREST DETECTIONS
# =========================================================

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


# =========================================================
# GET ONE DETECTION
# =========================================================

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


# =========================================================
# VERIFY DETECTION
# =========================================================

@router.put(
    "/{detection_id}/verify",
    response_model=DetectionResponse,
    status_code=status.HTTP_200_OK,
)
def verify_detection(
    detection_id: int,
    request: DetectionVerification,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_forestry_officer),
):
    """
    Verify a pending detection.

    The status is ALWAYS changed to VERIFIED.
    The status supplied by the client is ignored.

    After verification, the DetectionService also
    processes the detection and triggers the alert
    workflow.
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

    # -----------------------------------------------------
    # Only pending detections can be verified
    # -----------------------------------------------------

    if detection.status != DetectionStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Only pending detections can be verified. "
                f"Current status: {detection.status.value}"
            ),
        )

    # -----------------------------------------------------
    # Use DetectionService
    # -----------------------------------------------------

    service = DetectionService(db)

    detection = service.verify_detection(
        detection=detection,
        verified_by=current_user.id,
    )

    # -----------------------------------------------------
    # Save verification notes
    # -----------------------------------------------------

    if request.verification_notes:
        detection.verification_notes = (
            request.verification_notes
        )

        detection = repository.update(
            detection,
        )

    return detection


# =========================================================
# REJECT DETECTION
# =========================================================

@router.put(
    "/{detection_id}/reject",
    response_model=DetectionResponse,
    status_code=status.HTTP_200_OK,
)
def reject_detection(
    detection_id: int,
    request: DetectionVerification,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_forestry_officer),
):
    """
    Reject a pending detection.
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

    # -----------------------------------------------------
    # Only pending detections can be rejected
    # -----------------------------------------------------

    if detection.status != DetectionStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Only pending detections can be rejected. "
                f"Current status: {detection.status.value}"
            ),
        )

    # -----------------------------------------------------
    # Use DetectionService
    # -----------------------------------------------------

    service = DetectionService(db)

    detection = service.reject_detection(
        detection=detection,
        verified_by=current_user.id,
        notes=request.verification_notes or "Detection rejected.",
    )

    return detection


# =========================================================
# CLOSE DETECTION
# =========================================================

@router.put(
    "/{detection_id}/close",
    response_model=DetectionResponse,
    status_code=status.HTTP_200_OK,
)
def close_detection(
    detection_id: int,
    request: DetectionVerification,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_forestry_officer),
):
    """
    Close a verified detection.
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

    # -----------------------------------------------------
    # Only verified detections can be closed
    # -----------------------------------------------------

    if detection.status != DetectionStatus.VERIFIED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Only verified detections can be closed. "
                f"Current status: {detection.status.value}"
            ),
        )

    # -----------------------------------------------------
    # Use DetectionService
    # -----------------------------------------------------

    service = DetectionService(db)

    detection = service.close_detection(
        detection=detection,
        notes=request.verification_notes,
    )

    return detection


# =========================================================
# DELETE DETECTION
# =========================================================

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

    repository.delete(
        detection,
    )

    return {
        "message": "Detection deleted successfully.",
    }