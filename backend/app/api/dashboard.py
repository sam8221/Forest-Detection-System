"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Dashboard API

Purpose:
    Provides dashboard statistics and summary information
    for the ForestWatch Zambia system.

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
===========================================================
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.database.session import get_db

from app.models.user import User
from app.models.forest_area import ForestArea
from app.models.detection import Detection
from app.models.alert import Alert
from app.models.satellite_image import SatelliteImage

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


# =========================================================
# ROUTER
# =========================================================

router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"],
)


# =========================================================
# GET DASHBOARD
# =========================================================

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

    # =====================================================
    # FOREST STATISTICS
    # =====================================================

    total_forests = (
        db.query(ForestArea)
        .count()
    )

    monitored_forests = (
        db.query(ForestArea)
        .filter(
            ForestArea.is_active.is_(True)
        )
        .count()
    )

    protected_forests = (
        db.query(ForestArea)
        .filter(
            ForestArea.protected_status.isnot(None)
        )
        .count()
    )

    # =====================================================
    # DETECTION STATISTICS
    # =====================================================

    total_detections = (
        db.query(Detection)
        .count()
    )

    pending_detections = (
        db.query(Detection)
        .filter(
            Detection.status == "PENDING"
        )
        .count()
    )

    verified_detections = (
        db.query(Detection)
        .filter(
            Detection.status == "VERIFIED"
        )
        .count()
    )

    rejected_detections = (
        db.query(Detection)
        .filter(
            Detection.status == "REJECTED"
        )
        .count()
    )

    # =====================================================
    # ALERT STATISTICS
    # =====================================================

    total_alerts = (
        db.query(Alert)
        .count()
    )

    pending_alerts = (
        db.query(Alert)
        .filter(
            Alert.status == "PENDING"
        )
        .count()
    )

    sent_alerts = (
        db.query(Alert)
        .filter(
            Alert.status == "SENT"
        )
        .count()
    )

    failed_alerts = (
        db.query(Alert)
        .filter(
            Alert.status == "FAILED"
        )
        .count()
    )

    read_alerts = (
        db.query(Alert)
        .filter(
            Alert.status == "READ"
        )
        .count()
    )

    resolved_alerts = (
        db.query(Alert)
        .filter(
            Alert.is_resolved.is_(True)
        )
        .count()
    )

    # =====================================================
    # SATELLITE IMAGE STATISTICS
    # =====================================================

    total_images = (
        db.query(SatelliteImage)
        .count()
    )

    processed_images = (
        db.query(SatelliteImage)
        .filter(
            SatelliteImage.is_processed.is_(True)
        )
        .count()
    )

    unprocessed_images = (
        db.query(SatelliteImage)
        .filter(
            SatelliteImage.is_processed.is_(False)
        )
        .count()
    )

    # =====================================================
    # BUILD STATISTICS
    # =====================================================

    statistics = DashboardStatistics(
        forests=ForestStatistics(
            total_forests=total_forests,
            monitored_forests=monitored_forests,
            protected_forests=protected_forests,
        ),

        detections=DetectionStatistics(
            total_detections=total_detections,
            pending_detections=pending_detections,
            verified_detections=verified_detections,
            rejected_detections=rejected_detections,
        ),

        alerts=AlertStatistics(
            total_alerts=total_alerts,
            pending_alerts=pending_alerts,
            sent_alerts=sent_alerts,
            failed_alerts=failed_alerts,
            read_alerts=read_alerts,
            resolved_alerts=resolved_alerts,
        ),

        satellite_images=SatelliteStatistics(
            total_images=total_images,
            processed_images=processed_images,
            unprocessed_images=unprocessed_images,
        ),
    )

    # =====================================================
    # RECENT DETECTIONS
    # =====================================================

    recent_detection_records = (
        db.query(Detection)
        .order_by(
            Detection.created_at.desc()
        )
        .limit(5)
        .all()
    )

    recent_detections = []

    for item in recent_detection_records:

        recent_detections.append(
            RecentDetection(
                id=item.id,

                forest_name=(
                    item.forest_area.name
                    if item.forest_area
                    else "Unknown Forest"
                ),

                detected_area_hectares=(
                    item.detected_area_hectares
                ),

                confidence_score=(
                    item.confidence_score
                ),

                status=item.status.value,
            )
        )

    # =====================================================
    # RECENT ALERTS
    # =====================================================

    recent_alert_records = (
        db.query(Alert)
        .order_by(
            Alert.created_at.desc()
        )
        .limit(5)
        .all()
    )

    recent_alerts = []

    for item in recent_alert_records:

        recent_alerts.append(
            RecentAlert(
                id=item.id,
                title=item.title,
                priority=item.priority.value,
                status=item.status.value,
            )
        )

    # =====================================================
    # RETURN DASHBOARD
    # =====================================================

    return DashboardResponse(
        statistics=statistics,
        recent_detections=recent_detections,
        recent_alerts=recent_alerts,
    )