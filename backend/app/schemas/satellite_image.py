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

    forest_area_id: int = Field(
        ...,
        gt=0,
        description="Forest area identifier.",
    )

    product_id: str = Field(
        ...,
        min_length=5,
        max_length=120,
        description="Unique Sentinel-2 product ID.",
    )

    tile_id: str = Field(
        ...,
        min_length=3,
        max_length=50,
        description="Sentinel-2 tile identifier.",
    )

    acquisition_date: date = Field(
        ...,
        description="Date the satellite image was acquired.",
    )

    cloud_cover_percentage: float = Field(
        ...,
        ge=0,
        le=100,
        description="Cloud cover percentage.",
    )

    file_name: str = Field(
        ...,
        min_length=3,
        max_length=255,
        description="Stored image filename.",
    )

    storage_path: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="Storage location of the image.",
    )

    file_size_mb: float = Field(
        ...,
        gt=0,
        description="Image file size in megabytes.",
    )


# ---------------------------------------------------------
# Create Schema
# ---------------------------------------------------------
class SatelliteImageCreate(SatelliteImageBase):
    """
    Request schema used when registering
    a downloaded Sentinel-2 image.
    """

    pass


# ---------------------------------------------------------
# Update Schema
# ---------------------------------------------------------
class SatelliteImageUpdate(BaseModel):
    """
    Request schema used for updating
    image processing status.
    """

    is_downloaded: bool | None = Field(
        default=None,
    )

    is_processed: bool | None = Field(
        default=None,
    )


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
    Lightweight satellite image schema.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int

    acquisition_date: date

    cloud_cover_percentage: float

    is_processed: bool