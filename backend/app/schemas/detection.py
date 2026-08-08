"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Detection Schemas

Purpose:
    Defines Pydantic schemas for deforestation
    detections.

Responsibilities:
    - Validate detection data.
    - Serialize detection responses.
    - Support detection verification.

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

from pydantic import (
    BaseModel,
    ConfigDict,
)

from app.models.enums import DetectionStatus


# ---------------------------------------------------------
# Base Schema
# ---------------------------------------------------------
class DetectionBase(BaseModel):
    """
    Common detection fields.
    """

    forest_area_id: int

    satellite_image_id: int

    analysis_job_id: int

    detected_area_hectares: float

    confidence_score: float

    ndvi_before: float

    ndvi_after: float

    vegetation_loss_percentage: float


# ---------------------------------------------------------
# Create Schema
# ---------------------------------------------------------
class DetectionCreate(DetectionBase):
    """
    Used internally when creating detections.
    """

    pass


# ---------------------------------------------------------
# Update Schema
# ---------------------------------------------------------
class DetectionUpdate(BaseModel):
    """
    Used when verifying or closing detections.
    """

    status: DetectionStatus | None = None

    verification_notes: str | None = None

    verified_by: int | None = None


# ---------------------------------------------------------
# Response Schema
# ---------------------------------------------------------
class DetectionResponse(DetectionBase):
    """
    Returned by the API.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int

    status: DetectionStatus

    verified_by: int | None

    verified_at: datetime | None

    verification_notes: str | None

    created_at: datetime

    updated_at: datetime


# ---------------------------------------------------------
# Summary Schema
# ---------------------------------------------------------
class DetectionSummary(BaseModel):
    """
    Lightweight detection model.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int

    status: DetectionStatus

    detected_area_hectares: float

    confidence_score: float
# ---------------------------------------------------------
# Verification Schema
# ---------------------------------------------------------
class DetectionVerification(BaseModel):
    """
    Used by Forestry Officers to verify or reject
    a detection.
    """

    status: DetectionStatus

    verification_notes: str | None = None
    