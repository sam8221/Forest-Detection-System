"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Analytics API

Purpose:
    Serves forest-loss analytics, NDVI change statistics
    and advisory recommendations to the officer dashboard.

Responsibilities:
    - Summarise monitored area, detections and loss.
    - Return a potential-loss trend over observed days.
    - Compare potential loss across districts.
    - Report NDVI change for one analysis job.
    - Return advisory recommendations.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Note:
    Every endpoint here is scoped to the signed-in officer's
    jurisdiction, in the service and through the
    repositories, so two officers requesting the same figure
    receive different answers. Analytics are as disclosing
    as the records they summarise: a district total names
    where clearing has been found. This is requirement
    FR-04.

    Nothing here writes. Analytics read stored results and
    recommendations advise on them; neither alters a
    detection, an alert or an analysis job.

Version:
    1.0.0
===========================================================
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.database.session import get_db
from app.models.user import User
from app.repositories.analysis_repository import AnalysisRepository

from app.schemas.analytics import (
    AnalyticsSummary,
    DistrictComparison,
    LossTrendPoint,
    NDVIChangeStatistics,
    RecommendationEnvelope,
)

from app.services.analytics_service import AnalyticsService
from app.services.recommendation_service import RecommendationService


router = APIRouter(
    prefix="/analytics",
    tags=["Analytics"],
)


# =========================================================
# SHARED FILTERS
# =========================================================

def date_range(
    start_date: date | None = Query(
        default=None,
        description="Earliest detection date to include.",
    ),
    end_date: date | None = Query(
        default=None,
        description="Latest detection date to include.",
    ),
) -> tuple[date | None, date | None]:
    """
    Validate an optional date range.

    Raises:
        HTTPException:
            422 when the range is inverted, which is almost
            always a mistake in the caller and would
            otherwise return an empty chart that looks like
            an absence of clearing.
    """

    if (
        start_date is not None
        and end_date is not None
        and start_date > end_date
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "start_date must not be later than end_date."
            ),
        )

    return start_date, end_date


# =========================================================
# SUMMARY
# =========================================================

@router.get(
    "/summary",
    response_model=AnalyticsSummary,
)
def get_summary(
    dates: tuple = Depends(date_range),
    district_id: int | None = Query(default=None),
    forest_area_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Return the headline analytics figures.

    Two loss figures are returned because they answer
    different questions. cumulative_loss_hectares adds every
    detection, so ground cleared and detected twice counts
    twice. unique_loss_hectares dissolves the outlines so
    distinct ground counts once, and is null when no
    detection in scope carries an outline.
    """

    start_date, end_date = dates

    return AnalyticsService(db).summary(
        user=current_user,
        start_date=start_date,
        end_date=end_date,
        district_id=district_id,
        forest_area_id=forest_area_id,
    )


# =========================================================
# TREND
# =========================================================

@router.get(
    "/trend",
    response_model=list[LossTrendPoint],
)
def get_loss_trend(
    dates: tuple = Depends(date_range),
    district_id: int | None = Query(default=None),
    forest_area_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Return potential loss per observed day.

    The series carries one point per day an analysis
    completed, not one per calendar day. A point with zero
    hectares means an analysis ran and found no clearing
    large enough to report. A day missing from the series
    was not observed, and the chart should show a gap rather
    than joining through it as though it were zero.
    """

    start_date, end_date = dates

    return AnalyticsService(db).loss_trend(
        user=current_user,
        start_date=start_date,
        end_date=end_date,
        district_id=district_id,
        forest_area_id=forest_area_id,
    )


# =========================================================
# DISTRICT COMPARISON
# =========================================================

@router.get(
    "/districts",
    response_model=list[DistrictComparison],
)
def get_district_comparison(
    dates: tuple = Depends(date_range),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Compare potential loss across districts.

    Every district inside the officer's jurisdiction is
    returned, including those with no analysis at all, so
    the chart can distinguish a district examined and found
    clear from one never examined. observed carries that
    distinction.
    """

    start_date, end_date = dates

    return AnalyticsService(db).district_comparison(
        user=current_user,
        start_date=start_date,
        end_date=end_date,
    )


# =========================================================
# NDVI CHANGE
# =========================================================

@router.get(
    "/ndvi/{job_id}",
    response_model=NDVIChangeStatistics,
)
def get_ndvi_change(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Report the vegetation change one analysis found.

    Raises:
        HTTPException:
            404 when the job does not exist or lies outside
            the officer's jurisdiction, which are not
            distinguished; 409 when the two NDVI rasters
            cover different pixel grids and cannot be
            compared.

    A fall in NDVI is a fall in vegetation index, not a
    finding of deforestation. declined_hectares reports the
    ground whose decline reached the job's threshold; a
    detection additionally has to survive the persistence
    check and the half-hectare minimum, which is why the two
    numbers differ.
    """

    job = AnalysisRepository(db).get_by_id_for_user(
        job_id=job_id,
        user=current_user,
    )

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Analysis job not found.",
        )

    try:
        return AnalyticsService(db).ndvi_change(job)

    except ValueError as error:
        # Mismatched grids are a data condition, not a bug,
        # and the officer needs to be told rather than shown
        # a comparison of unrelated ground.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        )


# =========================================================
# RECOMMENDATIONS
# =========================================================

@router.get(
    "/recommendations",
    response_model=RecommendationEnvelope,
)
def get_recommendations(
    district_id: int | None = Query(default=None),
    forest_area_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Return advisory recommendations, most urgent first.

    Advice, not findings. No rule concludes that
    deforestation has occurred or that clearing was illegal;
    each names what in the data prompted it and what the
    officer might do next. The thresholds in force are
    returned alongside so the reasoning is visible.
    """

    service = RecommendationService(db)

    recommendations = service.generate(
        user=current_user,
        district_id=district_id,
        forest_area_id=forest_area_id,
    )

    return {
        "rules": service.rules.as_dict(),
        "recommendations": [
            item.as_dict() for item in recommendations
        ],
    }
