"""
ForestWatch Zambia

Module: Alerts API

Purpose:
Provides endpoints for managing alerts.

Responsibilities:
- View alerts.
- View pending alerts.
- View sent alerts.
- View failed alerts.
- View resolved alerts.
- Mark alerts as read.
- Resolve alerts.
- Delete alerts.

Author:
Samuel Bikiloni

Project:
Web-Based Deforestation Detection and Alert System
Using Sentinel-2 Imagery in the Copperbelt, Zambia
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
)
from app.database.session import get_db
from app.models.enums import AlertStatus
from app.models.user import User
from app.repositories.alert_repository import AlertRepository
from app.schemas.alert import AlertResponse


router = APIRouter(
    prefix="/alerts",
    tags=["Alerts"],
)


# ---------------------------------------------------------
# Get All Alerts
# ---------------------------------------------------------

@router.get(
    "",
    response_model=list[AlertResponse],
)
def get_alerts(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    """
    Return all alerts.
    """

    repository = AlertRepository(db)

    return repository.get_all()


# ---------------------------------------------------------
# Get Pending Alerts
# ---------------------------------------------------------

@router.get(
    "/pending",
    response_model=list[AlertResponse],
)
def get_pending_alerts(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    """
    Return pending alerts.
    """

    repository = AlertRepository(db)

    return repository.get_pending()


# ---------------------------------------------------------
# Get Sent Alerts
# ---------------------------------------------------------

@router.get(
    "/sent",
    response_model=list[AlertResponse],
)
def get_sent_alerts(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    """
    Return sent alerts.
    """

    repository = AlertRepository(db)

    return repository.get_sent()


# ---------------------------------------------------------
# Get Failed Alerts
# ---------------------------------------------------------

@router.get(
    "/failed",
    response_model=list[AlertResponse],
)
def get_failed_alerts(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    """
    Return failed alerts.
    """

    repository = AlertRepository(db)

    return repository.get_failed()


# ---------------------------------------------------------
# Get Resolved Alerts
# ---------------------------------------------------------

@router.get(
    "/resolved",
    response_model=list[AlertResponse],
)
def get_resolved_alerts(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    """
    Return all resolved alerts.
    """

    repository = AlertRepository(db)

    return repository.get_resolved()


# ---------------------------------------------------------
# Get Alert
# ---------------------------------------------------------

@router.get(
    "/{alert_id}",
    response_model=AlertResponse,
)
def get_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    """
    Retrieve one alert.
    """

    repository = AlertRepository(db)

    alert = repository.get_by_id(alert_id)

    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found.",
        )

    return alert


# ---------------------------------------------------------
# Mark Alert as Read
# ---------------------------------------------------------

@router.put(
    "/{alert_id}/read",
    response_model=AlertResponse,
)
def mark_as_read(
    alert_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    """
    Mark an alert as read.
    """

    repository = AlertRepository(db)

    alert = repository.get_by_id(alert_id)

    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found.",
        )

    # Do not change an already resolved alert back to READ
    if alert.is_resolved:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Resolved alerts cannot be marked as read.",
        )

    alert.status = AlertStatus.READ
    alert.read_at = datetime.now(UTC)

    repository.update(alert)

    return alert

# ---------------------------------------------------------
# Resolve Alert
# ---------------------------------------------------------

@router.put(
    "/{alert_id}/resolve",
    response_model=AlertResponse,
)
def resolve_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_admin_user),
):
    """
    Resolve an alert.
    """

    repository = AlertRepository(db)

    alert = repository.get_by_id(alert_id)

    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found.",
        )

    # Mark alert as resolved
    alert.status = AlertStatus.RESOLVED
    alert.is_resolved = True
    alert.resolved_at = datetime.now(UTC)

    repository.update(alert)

    return alert

# ---------------------------------------------------------
# Delete Alert
# ---------------------------------------------------------

@router.delete(
    "/{alert_id}",
    status_code=status.HTTP_200_OK,
)
def delete_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_admin_user),
):
    """
    Permanently delete an alert.

    Only Administrators can perform this action.
    """

    repository = AlertRepository(db)

    alert = repository.get_by_id(alert_id)

    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found.",
        )

    repository.delete(alert)

    return {
        "message": "Alert deleted successfully."
    }