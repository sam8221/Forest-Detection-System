"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Analytics Schemas

Purpose:
    Response shapes for the forest-loss analytics, NDVI
    change statistics and advisory recommendations.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Note:
    Several fields are deliberately optional rather than
    defaulting to zero. A missing value means "not
    measured"; zero means "measured as none". Collapsing the
    two would let the interface show an officer a confident
    zero where the system has no observation at all.

Version:
    1.0.0
===========================================================
"""

from datetime import date, datetime

from pydantic import BaseModel, Field


# =========================================================
# SUMMARY
# =========================================================

class AnalyticsSummary(BaseModel):
    """Headline figures for the analytics dashboard."""

    monitored_forest_areas: int = Field(
        description="Active forest areas in the jurisdiction.",
    )

    monitored_hectares: float = Field(
        description="Total hectares under monitoring.",
    )

    total_detections: int = Field(
        description="Potential deforestation detections.",
    )

    cumulative_loss_hectares: float = Field(
        description=(
            "Sum of every detection's area. Ground detected "
            "in two analyses is counted twice."
        ),
    )

    unique_loss_hectares: float | None = Field(
        default=None,
        description=(
            "Distinct affected ground, with overlapping "
            "outlines dissolved. None when no detection in "
            "scope carries an outline."
        ),
    )

    detections_with_outline: int = Field(
        description=(
            "How many detections the unique figure rests on."
        ),
    )

    forest_areas_with_detections: int

    forest_areas_analysed: int

    latest_analysis_at: datetime | None = Field(
        default=None,
        description="When the most recent analysis completed.",
    )

    has_results: bool = Field(
        description=(
            "False when nothing has been detected in scope, "
            "so the interface shows an empty state rather "
            "than zeros."
        ),
    )


# =========================================================
# TREND
# =========================================================

class LossTrendPoint(BaseModel):
    """Potential loss recorded on one observed day."""

    date: date

    analyses: int = Field(
        description="Analyses that completed on this day.",
    )

    detections: int

    loss_hectares: float

    observed: bool = Field(
        description=(
            "True for every point returned. The series "
            "carries only days an analysis completed, so a "
            "zero here is a real 'nothing found'. Days "
            "absent from the series were not observed and "
            "should not be drawn as zero."
        ),
    )


# =========================================================
# DISTRICT COMPARISON
# =========================================================

class DistrictComparison(BaseModel):
    """Potential loss in one district."""

    district_id: int

    district: str

    detections: int

    loss_hectares: float

    analyses: int

    observed: bool = Field(
        description=(
            "False when no analysis has completed in this "
            "district, so its zero means 'not examined' "
            "rather than 'nothing found'."
        ),
    )


# =========================================================
# NDVI CHANGE
# =========================================================

class NDVIChangeStatistics(BaseModel):
    """Vegetation change between two observations."""

    rasters_available: bool

    mean_ndvi_before: float | None = None

    mean_ndvi_after: float | None = None

    mean_ndvi_difference: float | None = Field(
        default=None,
        description="Later mean minus earlier mean.",
    )

    declined_pixel_percentage: float | None = Field(
        default=None,
        description=(
            "Share of pixels measurable on both dates whose "
            "vegetation index fell. A fall is not by itself "
            "deforestation."
        ),
    )

    declined_hectares: float | None = Field(
        default=None,
        description=(
            "Area whose decline reached the job's NDVI "
            "threshold, before the persistence check and the "
            "half-hectare minimum that a detection must also "
            "survive."
        ),
    )

    measurable_pixels: int | None = None

    baseline_start: date | None = None
    baseline_end: date | None = None
    comparison_start: date | None = None
    comparison_end: date | None = None

    completed_at: datetime | None = None

    ndvi_threshold: float | None = None

    cloud_cover_percentage: float | None = None


# =========================================================
# RECOMMENDATIONS
# =========================================================

class RecommendationResponse(BaseModel):
    """One piece of advice about one place."""

    rule: str = Field(
        description="Identifier of the rule that fired.",
    )

    priority: str

    finding: str = Field(
        description="What in the data prompted this.",
    )

    action: str = Field(
        description="What the officer might do next.",
    )

    forest_area_id: int | None = None
    forest_area: str | None = None
    district: str | None = None
    detection_id: int | None = None
    analysis_job_id: int | None = None

    created_at: datetime


class RecommendationEnvelope(BaseModel):
    """Recommendations together with the rules behind them."""

    rules: dict = Field(
        description=(
            "The thresholds in force, returned so an officer "
            "can see why advice appeared and a reader can "
            "reproduce it."
        ),
    )

    recommendations: list[RecommendationResponse]
