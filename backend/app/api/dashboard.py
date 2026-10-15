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

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_active_user
from app.database.session import get_db

from app.models.user import User
from app.models.district import District
from app.models.enums import DetectionStatus, UserRole
from app.models.forest_area import ForestArea
from app.models.detection import Detection
from app.models.alert import Alert
from app.models.satellite_image import SatelliteImage
from app.repositories.forest_area_repository import (
    ForestAreaRepository,
)

from app.schemas.dashboard import (
    AlertStatistics,
    DashboardResponse,
    DashboardStatistics,
    DetectionStatistics,
    DistrictBreakdownResponse,
    DistrictSummary,
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
    current_user: User = Depends(
        get_current_active_user
    ),
):
    """
    Return dashboard summary statistics.

    Args:
        db:
            Database session.
        _:
            The authenticated officer. Required so that an
            unauthenticated caller is refused, but not read:
            see the note below.

    Returns:
        DashboardResponse:
            Counts of forest areas, detections, alerts and
            satellite products, with the most recent
            detections and alerts.

    Each group of counts is gathered in a single aggregate
    query rather than by counting rows in Python, so the
    whole dashboard costs a small fixed number of round
    trips regardless of how many records exist.

    Every figure is scoped to the officer's jurisdiction, so
    two officers signing in at the same moment are shown
    different totals: a district officer sees their district,
    a provincial officer sees every district in their
    province, and an administrator sees national figures
    because administration holds no jurisdiction.

    The permitted set of forest areas is derived once from
    ForestAreaRepository.scope_to_jurisdiction and applied as
    a subquery inside each aggregate. Reusing that method
    rather than restating the rule here means the dashboard
    cannot disagree with the forest area and detection
    endpoints about what an officer may see. This is
    requirement FR-04, enforced in the query: a record
    outside the officer's area is not counted, not listed,
    and cannot be returned.
    """

    # =====================================================
    # JURISDICTION SCOPE
    #
    # Every figure below is restricted to the forest areas
    # this officer is responsible for. The permitted set is
    # derived once, from ForestAreaRepository, so the
    # dashboard cannot drift from the rule the forest area
    # and detection endpoints enforce: there is one
    # definition of a jurisdiction, not four.
    #
    # It is kept as a subquery rather than a list of
    # identifiers so the restriction is applied by the
    # database inside each aggregate, rather than by first
    # fetching every area the officer may see.
    #
    # An administrator is unrestricted, so no filter is
    # built and the counts stay national. That is correct
    # for the role: administration has no jurisdiction.
    # =====================================================

    permitted_forest_areas = None

    if current_user.role != UserRole.ADMIN:

        permitted_forest_areas = (
            ForestAreaRepository(db)
            .scope_to_jurisdiction(
                db.query(ForestArea.id),
                current_user,
            )
            .subquery()
        )

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
    )

    if permitted_forest_areas is not None:
        forest_stats = forest_stats.filter(
            ForestArea.id.in_(
                select(permitted_forest_areas.c.id)
            )
        )

    forest_stats = forest_stats.one()

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
    )

    if permitted_forest_areas is not None:
        detection_stats = detection_stats.filter(
            Detection.forest_area_id.in_(
                select(permitted_forest_areas.c.id)
            )
        )

    detection_stats = detection_stats.one()

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
    )

    # An alert is raised about a detection, so its
    # jurisdiction is the jurisdiction of that detection.
    if permitted_forest_areas is not None:
        alert_stats = alert_stats.join(
            Detection,
            Detection.id == Alert.detection_id,
        ).filter(
            Detection.forest_area_id.in_(
                select(permitted_forest_areas.c.id)
            )
        )

    alert_stats = alert_stats.one()

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
    )

    if permitted_forest_areas is not None:
        satellite_stats = satellite_stats.filter(
            SatelliteImage.forest_area_id.in_(
                select(permitted_forest_areas.c.id)
            )
        )

    satellite_stats = satellite_stats.one()

    # =====================================================
    # RECENT DETECTIONS
    # =====================================================

    recent_detection_query = (
        db.query(Detection)
        .options(
            selectinload(
                Detection.forest_area
            )
        )
    )

    if permitted_forest_areas is not None:
        recent_detection_query = (
            recent_detection_query.filter(
                Detection.forest_area_id.in_(
                    select(permitted_forest_areas.c.id)
                )
            )
        )

    recent_detection_records = (
        recent_detection_query
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

    recent_alert_query = db.query(Alert)

    if permitted_forest_areas is not None:
        recent_alert_query = recent_alert_query.join(
            Detection,
            Detection.id == Alert.detection_id,
        ).filter(
            Detection.forest_area_id.in_(
                select(permitted_forest_areas.c.id)
            )
        )

    recent_alert_records = (
        recent_alert_query
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


# =========================================================
# DISTRICT BREAKDOWN
# =========================================================

@router.get(
    "/districts",
    response_model=DistrictBreakdownResponse,
)
def get_district_breakdown(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Compare deforestation activity across districts.

    Returns:
        One row per district the officer is responsible for.

    Raises:
        HTTPException 403:
            The officer is responsible for a single
            district, so there is nothing to compare.

    Why this endpoint is restricted:

        A Provincial Forestry Officer supervises several
        districts. Without a breakdown they see one merged
        list and cannot tell which district is worst
        affected, or where reviews are piling up.

        A District Forestry Officer is responsible for one
        district. A comparison would either show them a
        single row, which tells them nothing they cannot
        already see, or show them other districts, which is
        precisely what requirement FR-04 forbids.

    The rows returned are limited to the officer's own
    province. This repeats the jurisdiction rule rather than
    trusting the interface not to ask for more.
    """

    if current_user.role == UserRole.DISTRICT_FORESTRY_OFFICER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "A district breakdown is available to "
                "officers responsible for more than one "
                "district."
            ),
        )

    # -----------------------------------------------------
    # Aggregate per district
    #
    # Counted with outer joins so a district with no forest
    # areas, or forest areas with no detections, still
    # appears. A district reporting zero is information: it
    # means nothing has been found there, which is different
    # from it being absent from the list.
    # -----------------------------------------------------

    query = (
        db.query(
            District.id.label("district_id"),

            District.name.label("district_name"),

            func.count(
                func.distinct(ForestArea.id)
            ).label("monitored_forests"),

            func.count(
                func.distinct(Detection.id)
            ).label("total_detections"),

            func.count(
                func.distinct(
                    case(
                        (
                            Detection.status
                            == DetectionStatus.PENDING,
                            Detection.id,
                        ),
                        else_=None,
                    )
                )
            ).label("pending_detections"),

            func.count(
                func.distinct(
                    case(
                        (
                            Detection.status
                            == DetectionStatus.VERIFIED,
                            Detection.id,
                        ),
                        else_=None,
                    )
                )
            ).label("verified_detections"),

            func.coalesce(
                func.sum(
                    Detection.detected_area_hectares
                ),
                0.0,
            ).label("affected_area_hectares"),

            func.max(
                func.date(Detection.created_at)
            ).label("latest_detection"),

            func.min(
                case(
                    (
                        Detection.status
                        == DetectionStatus.PENDING,
                        func.date(Detection.created_at),
                    ),
                    else_=None,
                )
            ).label("oldest_pending_detection"),
        )
        .outerjoin(
            ForestArea,
            (ForestArea.district_id == District.id)
            & (ForestArea.is_active.is_(True)),
        )
        .outerjoin(
            Detection,
            Detection.forest_area_id == ForestArea.id,
        )
        .filter(District.is_active.is_(True))
        .group_by(District.id, District.name)
        .order_by(District.name.asc())
    )

    # -----------------------------------------------------
    # Apply the officer's jurisdiction
    # -----------------------------------------------------

    if current_user.role == UserRole.PROVINCIAL_FORESTRY_OFFICER:

        # An officer with no province assigned is refused
        # every record elsewhere in the system, so the
        # breakdown must be empty here too rather than
        # falling back to showing everything.
        if current_user.province_id is None:
            return DistrictBreakdownResponse(
                scope="No province assigned",
                districts=[],
            )

        query = query.filter(
            District.province_id
            == current_user.province_id,
        )

        scope = (
            current_user.province.name
            if current_user.province is not None
            else "Assigned province"
        )

    else:
        # Administrators supervise nationally.
        scope = "All provinces"

    rows = query.all()

    return DistrictBreakdownResponse(
        scope=scope,
        districts=[
            DistrictSummary(
                district_id=row.district_id,
                district_name=row.district_name,
                monitored_forests=row.monitored_forests,
                total_detections=row.total_detections,
                pending_detections=row.pending_detections,
                verified_detections=row.verified_detections,
                affected_area_hectares=round(
                    float(row.affected_area_hectares or 0.0),
                    2,
                ),
                latest_detection=row.latest_detection,
                oldest_pending_detection=(
                    row.oldest_pending_detection
                ),
            )
            for row in rows
        ],
    )