"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Analysis Schemas

Purpose:
    Defines Pydantic schemas for Analysis Jobs.

Responsibilities:
    - Validate API requests.
    - Serialize API responses.
    - Support FastAPI documentation.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Version:
    1.0.0
===========================================================
"""

from datetime import datetime

from datetime import date

from pydantic import BaseModel, ConfigDict, model_validator

from app.models.enums import (
    AnalysisJobStatus,
    AnalysisJobType,
)


# ---------------------------------------------------------
# Base Schema
# ---------------------------------------------------------
class AnalysisJobBase(BaseModel):
    """
    Common fields shared by Analysis Job schemas.
    """

    forest_area_id: int
    satellite_image_id: int
    job_type: AnalysisJobType


# ---------------------------------------------------------
# Create Schema
# ---------------------------------------------------------
class AnalysisJobCreate(AnalysisJobBase):
    """
    Schema used when creating a new analysis job.

    The four window fields select which seasonal periods are
    compared. They are optional: when omitted, equivalent
    windows one year apart are derived automatically, so a
    caller that supplies nothing still gets a seasonally
    valid comparison.

    Supply all four to target a specific period, such as the
    May to July dry season in two consecutive years.
    """

    started_by: int | None = None

    baseline_start: date | None = None
    baseline_end: date | None = None
    comparison_start: date | None = None
    comparison_end: date | None = None


# ---------------------------------------------------------
# Seasonal Window Request Schema
# ---------------------------------------------------------
class SeasonalWindowRequest(BaseModel):
    """
    Optional seasonal windows supplied when starting an
    analysis from the API.

    All four dates must be given together, or none at all.
    A half-specified comparison is rejected rather than
    silently completed, because the officer's intent would
    be ambiguous.
    """

    baseline_start: date | None = None
    baseline_end: date | None = None
    comparison_start: date | None = None
    comparison_end: date | None = None

    @model_validator(mode="after")
    def validate_window_pair(self) -> "SeasonalWindowRequest":
        """
        Ensure the windows are complete, ordered and
        non-overlapping.
        """

        supplied = [
            self.baseline_start,
            self.baseline_end,
            self.comparison_start,
            self.comparison_end,
        ]

        # -------------------------------------------------
        # Nothing supplied: defaults will be derived later
        # -------------------------------------------------

        if all(value is None for value in supplied):
            return self

        # -------------------------------------------------
        # Partially supplied: reject
        # -------------------------------------------------

        if any(value is None for value in supplied):
            raise ValueError(
                "Provide all four window dates together, "
                "or none of them."
            )

        # -------------------------------------------------
        # Ordering
        # -------------------------------------------------

        if self.baseline_start > self.baseline_end:
            raise ValueError(
                "Baseline window start date cannot be "
                "after its end date."
            )

        if self.comparison_start > self.comparison_end:
            raise ValueError(
                "Comparison window start date cannot be "
                "after its end date."
            )

        # -------------------------------------------------
        # The two windows must not overlap
        # -------------------------------------------------

        if self.baseline_end >= self.comparison_start:
            raise ValueError(
                "The baseline window must end before the "
                "comparison window begins."
            )

        return self


# ---------------------------------------------------------
# Update Schema
# ---------------------------------------------------------
class AnalysisJobUpdate(BaseModel):
    """
    Schema used when updating an analysis job.
    """

    status: AnalysisJobStatus | None = None
    completed_at: datetime | None = None
    duration_seconds: float | None = None
    cloud_cover_percentage: float | None = None
    vegetation_change_percentage: float | None = None
    ndvi_threshold: float | None = None
    error_message: str | None = None


# ---------------------------------------------------------
# Response Schema
# ---------------------------------------------------------
class AnalysisJobResponse(AnalysisJobBase):
    """
    Schema returned by the API.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int

    status: AnalysisJobStatus

    started_by: int | None

    started_at: datetime | None

    completed_at: datetime | None

    duration_seconds: float | None

    cloud_cover_percentage: float | None

    vegetation_change_percentage: float | None

    ndvi_threshold: float | None

    error_message: str | None

    created_at: datetime

    updated_at: datetime