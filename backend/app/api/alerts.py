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
from app.models.audit_log import AuditLog
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
    current_user: User = Depends(get_current_active_user),
):
    """
    Return the alerts the officer may see.

    Scoped to the officer's jurisdiction in the repository,
    so an alert about a detection in another district is not
    returned by this endpoint under any request. See FR-04.
    """

    repository = AlertRepository(db)

    return repository.get_all_for_user(current_user)


# ---------------------------------------------------------
# Get Pending Alerts
# ---------------------------------------------------------

@router.get(
    "/pending",
    response_model=list[AlertResponse],
)
def get_pending_alerts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Return pending alerts within the officer's jurisdiction.
    """

    repository = AlertRepository(db)

    return repository.get_by_status_for_user(
        AlertStatus.PENDING,
        current_user,
    )


# ---------------------------------------------------------
# Get Sent Alerts
# ---------------------------------------------------------

@router.get(
    "/sent",
    response_model=list[AlertResponse],
)
def get_sent_alerts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Return sent alerts within the officer's jurisdiction.
    """

    repository = AlertRepository(db)

    return repository.get_by_status_for_user(
        AlertStatus.SENT,
        current_user,
    )


# ---------------------------------------------------------
# Get Failed Alerts
# ---------------------------------------------------------

@router.get(
    "/failed",
    response_model=list[AlertResponse],
)
def get_failed_alerts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Return failed alerts within the officer's jurisdiction.
    """

    repository = AlertRepository(db)

    return repository.get_by_status_for_user(
        AlertStatus.FAILED,
        current_user,
    )


# ---------------------------------------------------------
# Get Resolved Alerts
# ---------------------------------------------------------

@router.get(
    "/resolved",
    response_model=list[AlertResponse],
)
def get_resolved_alerts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Return resolved alerts within the officer's jurisdiction.
    """

    repository = AlertRepository(db)

    return repository.get_resolved_for_user(current_user)


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
    current_user: User = Depends(get_current_active_user),
):
    """
    Retrieve one alert the officer may see.

    Raises:
        HTTPException:
            404 when the alert does not exist, or lies
            outside the officer's jurisdiction.

    The two cases return the same 404 on purpose. Answering
    403 would confirm that an alert exists for a district
    the officer does not cover, which is itself information
    about where clearing has been detected.

    Requesting the identifier directly is the case FR-04
    exists for, so the jurisdiction filter is part of the
    query rather than a check on the row after loading it.
    """

    repository = AlertRepository(db)

    alert = repository.get_by_id_for_user(
        alert_id=alert_id,
        user=current_user,
    )

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
    current_user: User = Depends(get_current_active_user),
):
    """
    Mark an alert as read.

    Scoped to the officer's jurisdiction: an officer cannot
    mark an alert read in a district they do not cover.
    Permitting it would both disclose the alert and disturb
    another district's review workflow, since READ is how an
    officer records that they have seen it.
    """

    repository = AlertRepository(db)

    alert = repository.get_by_id_for_user(
        alert_id=alert_id,
        user=current_user,
    )

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

    previous_status = alert.status

    alert.status = AlertStatus.READ
    alert.read_at = datetime.now(UTC)

    # FR-19: an alert status change is recorded with the
    # officer who made it. The previous status is kept in the
    # detail, because the trail has to show what changed, not
    # only that something did. repository.update commits, so
    # the audit row is written in the same transaction as the
    # change it describes.
    db.add(
        AuditLog(
            user_id=current_user.id,
            action="ALERT_MARKED_READ",
            entity_type="Alert",
            entity_id=alert.id,
            detail=(
                f"Alert {alert.id} status "
                f"{previous_status.value} -> "
                f"{AlertStatus.READ.value} "
                f"by {current_user.email}."
            ),
        )
    )

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
    current_user: User = Depends(get_admin_user),
):
    """
    Resolve an alert.

    Administrator only, so no jurisdiction scoping applies:
    administration holds no district or province.
    """

    repository = AlertRepository(db)

    alert = repository.get_by_id(alert_id)

    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found.",
        )

    previous_status = alert.status

    # Mark alert as resolved
    alert.status = AlertStatus.RESOLVED
    alert.is_resolved = True
    alert.resolved_at = datetime.now(UTC)

    # FR-19: resolution is the final status change in an
    # alert's life, so it is recorded with the account that
    # made it and the status it replaced.
    db.add(
        AuditLog(
            user_id=current_user.id,
            action="ALERT_RESOLVED",
            entity_type="Alert",
            entity_id=alert.id,
            detail=(
                f"Alert {alert.id} status "
                f"{previous_status.value} -> "
                f"{AlertStatus.RESOLVED.value} "
                f"by {current_user.email}."
            ),
        )
    )

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
    current_user: User = Depends(get_admin_user),
):
    """
    Permanently delete an alert.

    Only Administrators can perform this action.

    The deletion is recorded before the row is removed. An
    alert is evidence that clearing was detected and
    notified, so its removal has to leave a trail: the audit
    entry names the detection the alert was raised about,
    which the alert row itself can no longer be read for
    once it is gone.
    """

    repository = AlertRepository(db)

    alert = repository.get_by_id(alert_id)

    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found.",
        )

    db.add(
        AuditLog(
            user_id=current_user.id,
            action="ALERT_DELETED",
            entity_type="Alert",
            entity_id=alert.id,
            detail=(
                f"Alert {alert.id} for detection "
                f"{alert.detection_id} deleted by "
                f"{current_user.email}."
            ),
        )
    )

    repository.delete(alert)

    return {
        "message": "Alert deleted successfully."
    }