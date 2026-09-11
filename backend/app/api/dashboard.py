"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Dashboard API

Purpose:
    Provides fast dashboard statistics and summary
    information for the ForestWatch Zambia system.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia
===========================================================
"""

from fastapi import APIRouter, Depends
from sqlalchemy import func, case
from sqlalchemy.orm import Session, selectinload

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


router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"],
)


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

    Optimized to minimize database round trips.
    """

    # =====================================================
    # FOREST STATISTICS
    # =====================================================

    forest_stats = db.query(
        func.count(ForestArea.id).label("total_forests"),

        func.count(
            case(
                (
                    ForestArea.is_active.is_(True),
                    1,
                )
            )
        ).label("monitored_forests"),

        func.count(
            case(
                (
                    ForestArea.protected_status.isnot(None),
                    1,
                )
            )
        ).label("protected_forests"),
    ).one()

    # =====================================================
    # DETECTION STATISTICS
    # =====================================================

    detection_stats = db.query(
        func.count(Detection.id).label(
            "total_detections"
        ),

        func.count(
            case(
                (
                    Detection.status == "PENDING",
                    1,
                )
            )
        ).label("pending_detections"),

        func.count(
            case(
                (
                    Detection.status == "VERIFIED",
                    1,
                )
            )
        ).label("verified_detections"),

        func.count(
            case(
                (
                    Detection.status == "REJECTED",
                    1,
                )
            )
        ).label("rejected_detections"),
    ).one()

    # =====================================================
    # ALERT STATISTICS
    # =====================================================

    alert_stats = db.query(
        func.count(Alert.id).label(
            "total_alerts"
        ),

        func.count(
            case(
                (
                    Alert.status == "PENDING",
                    1,
                )
            )
        ).label("pending_alerts"),

        func.count(
            case(
                (
                    Alert.status == "SENT",
                    1,
                )
            )
        ).label("sent_alerts"),

        func.count(
            case(
                (
                    Alert.status == "FAILED",
                    1,
                )
            )
        ).label("failed_alerts"),

        func.count(
            case(
                (
                    Alert.status == "READ",
                    1,
                )
            )
        ).label("read_alerts"),

        func.count(
            case(
                (
                    Alert.is_resolved.is_(True),
                    1,
                )
            )
        ).label("resolved_alerts"),
    ).one()

    # =====================================================
    # SATELLITE STATISTICS
    # =====================================================

    satellite_stats = db.query(
        func.count(
            SatelliteImage.id
        ).label("total_images"),

        func.count(
            case(
                (
                    SatelliteImage.is_processed.is_(True),
                    1,
                )
            )
        ).label("processed_images"),

        func.count(
            case(
                (
                    SatelliteImage.is_processed.is_(False),
                    1,
                )
            )
        ).label("unprocessed_images"),
    ).one()

    # =====================================================
    # RECENT DETECTIONS
    # =====================================================

    recent_detection_records = (
        db.query(Detection)
        .options(
            selectinload(
                Detection.forest_area
            )
        )
        .order_by(
            Detection.created_at.desc()
        )
        .limit(5)
        .all()
    )

    recent_detections = [
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
        for item in recent_detection_records
    ]

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

    recent_alerts = [
        RecentAlert(
            id=item.id,
            title=item.title,
            priority=item.priority.value,
            status=item.status.value,
        )
        for item in recent_alert_records
    ]

    # =====================================================
    # BUILD RESPONSE
    # =====================================================

    statistics = DashboardStatistics(

        forests=ForestStatistics(
            total_forests=forest_stats.total_forests,
            monitored_forests=forest_stats.monitored_forests,
            protected_forests=forest_stats.protected_forests,
        ),

        detections=DetectionStatistics(
            total_detections=detection_stats.total_detections,
            pending_detections=detection_stats.pending_detections,
            verified_detections=detection_stats.verified_detections,
            rejected_detections=detection_stats.rejected_detections,
        ),

        alerts=AlertStatistics(
            total_alerts=alert_stats.total_alerts,
            pending_alerts=alert_stats.pending_alerts,
            sent_alerts=alert_stats.sent_alerts,
            failed_alerts=alert_stats.failed_alerts,
            read_alerts=alert_stats.read_alerts,
            resolved_alerts=alert_stats.resolved_alerts,
        ),

        satellite_images=SatelliteStatistics(
            total_images=satellite_stats.total_images,
            processed_images=satellite_stats.processed_images,
            unprocessed_images=satellite_stats.unprocessed_images,
        ),
    )

    return DashboardResponse(
        statistics=statistics,
        recent_detections=recent_detections,
        recent_alerts=recent_alerts,
    )