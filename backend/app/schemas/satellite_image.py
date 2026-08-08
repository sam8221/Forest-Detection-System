"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Satellite Image Schemas

Purpose:
    Defines Pydantic schemas for Sentinel-2
    satellite imagery.

Responsibilities:
    - Validate image requests.
    - Serialize satellite image responses.
    - Support image management.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Version:
    1.0.0
===========================================================
"""

from datetime import date, datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)


# ---------------------------------------------------------
# Base Schema
# ---------------------------------------------------------
class SatelliteImageBase(BaseModel):
    """
    Common satellite image fields.
    """

    forest_area_id: int

    product_id: str = Field(
        ...,
        max_length=120,
    )

    tile_id: str = Field(
        ...,
        max_length=50,
    )

    acquisition_date: date

    cloud_cover_percentage: float

    file_name: str

    storage_path: str

    file_size_mb: float


# ---------------------------------------------------------
# Create Schema
# ---------------------------------------------------------
class SatelliteImageCreate(SatelliteImageBase):
    """
    Used when registering a downloaded
    Sentinel-2 image.
    """

    pass


# ---------------------------------------------------------
# Update Schema
# ---------------------------------------------------------
class SatelliteImageUpdate(BaseModel):
    """
    Used when updating image status.
    """

    is_downloaded: bool | None = None

    is_processed: bool | None = None


# ---------------------------------------------------------
# Response Schema
# ---------------------------------------------------------
class SatelliteImageResponse(
    SatelliteImageBase
):
    """
    Returned by the API.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int

    is_downloaded: bool

    is_processed: bool

    created_at: datetime

    updated_at: datetime


# ---------------------------------------------------------
# Summary Schema
# ---------------------------------------------------------
class SatelliteImageSummary(BaseModel):
    """
    Lightweight satellite image model.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int

    acquisition_date: date

    cloud_cover_percentage: float

    is_processed: bool