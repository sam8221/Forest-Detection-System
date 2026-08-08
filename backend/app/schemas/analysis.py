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

from pydantic import BaseModel, ConfigDict

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
    """

    started_by: int | None = None


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