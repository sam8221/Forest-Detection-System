"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: District Schemas

Purpose:
    Defines Pydantic schemas for Districts.

Responsibilities:
    - Validate district data.
    - Serialize district responses.
    - Support CRUD operations.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Version:
    1.0.0
===========================================================
"""
from app.schemas.province import ProvinceSummary
from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)


# ---------------------------------------------------------
# Base Schema
# ---------------------------------------------------------
class DistrictBase(BaseModel):
    """
    Common District fields.
    """

    district: DistrictSummary

    name: str = Field(
        ...,
        min_length=2,
        max_length=100,
    )

    code: str = Field(
        ...,
        min_length=2,
        max_length=10,
    )


# ---------------------------------------------------------
# Create Schema
# ---------------------------------------------------------
class DistrictCreate(DistrictBase):
    """
    Used when creating a District.
    """

    pass


# ---------------------------------------------------------
# Update Schema
# ---------------------------------------------------------
class DistrictUpdate(BaseModel):
    """
    Used when updating a District.
    """

    province_id: int | None = None

    name: str | None = None

    code: str | None = None


# ---------------------------------------------------------
# Response Schema
# ---------------------------------------------------------
# ---------------------------------------------------------
# Response Schema
# ---------------------------------------------------------
class DistrictResponse(DistrictBase):
    """
    District returned by the API.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int

    province: ProvinceSummary

    created_at: datetime

    updated_at: datetime
# ---------------------------------------------------------
# Summary Schema
# ---------------------------------------------------------
class DistrictSummary(BaseModel):
    """
    Lightweight District representation.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int

    name: str

    code: str