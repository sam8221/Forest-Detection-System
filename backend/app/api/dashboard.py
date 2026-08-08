"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Dashboard API

Purpose:
    Provides dashboard statistics and summary
    information for the ForestWatch Zambia system.

Responsibilities:
    - Forest statistics
    - Detection statistics
    - Alert statistics
    - Satellite image statistics
    - Recent detections
    - Recent alerts

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
)
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.database.session import get_db
from app.models.user import User
from app.repositories.alert_repository import AlertRepository
from app.repositories.detection_repository import DetectionRepository
from app.repositories.forest_area_repository import (
    ForestAreaRepository,
)
from app.repositories.satellite_image_repository import (
    SatelliteImageRepository,
)
from app.schemas.dashboard import (
    AlertStatistics,
    DashboardResponse,
    DashboardStatistics,
    DetectionStatistics,
    ForestStatistics,
    RecentAlert,
    RecentDetection,
    SatelliteStatistics,
)

router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"],
)


# ---------------------------------------------------------
# Dashboard Summary
# ---------------------------------------------------------
@router.get(
    "",
    response_model=DashboardResponse,
)
def get_dashboard(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    """
    Return dashboard summary statistics.
    """

    forest_repo = ForestAreaRepository(db)

    detection_repo = DetectionRepository(db)

    alert_repo = AlertRepository(db)

    satellite_repo = SatelliteImageRepository(db)

    statistics = DashboardStatistics(

        forests=ForestStatistics(

            total_forests=forest_repo.count(),

            monitored_forests=forest_repo.count_monitored(),

            protected_forests=forest_repo.count_protected(),
        ),

        detections=DetectionStatistics(

            total_detections=detection_repo.count(),

            pending_detections=detection_repo.count_pending(),

            verified_detections=detection_repo.count_verified(),

            rejected_detections=detection_repo.count_rejected(),
        ),

        alerts=AlertStatistics(

            total_alerts=alert_repo.count(),

            pending_alerts=alert_repo.count_pending(),

            sent_alerts=alert_repo.count_sent(),

            failed_alerts=alert_repo.count_failed(),

            read_alerts=alert_repo.count_read(),
        ),

        satellite_images=SatelliteStatistics(

            total_images=satellite_repo.count(),

            processed_images=satellite_repo.count_processed(),

            unprocessed_images=satellite_repo.count_unprocessed(),
        ),
    )

    recent_detections = [

        RecentDetection(

            id=item.id,

            forest_name=item.forest_area.name,

            detected_area_hectares=item.detected_area_hectares,

            confidence_score=item.confidence_score,

            status=item.status.value,

        )

        for item in detection_repo.get_recent()

    ]

    recent_alerts = [

        RecentAlert(

            id=item.id,

            title=item.title,

            priority=item.priority.value,

            status=item.status.value,

        )

        for item in alert_repo.get_recent()

    ]

    return DashboardResponse(

        statistics=statistics,

        recent_detections=recent_detections,

        recent_alerts=recent_alerts,
    )