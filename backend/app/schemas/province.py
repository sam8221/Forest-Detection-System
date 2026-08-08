"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Province Schemas

Purpose:
    Defines Pydantic schemas for Provinces.

Responsibilities:
    - Validate province data.
    - Serialize province responses.
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

from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)


# ---------------------------------------------------------
# Base Schema
# ---------------------------------------------------------
class ProvinceBase(BaseModel):
    """
    Common Province fields.
    """

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
class ProvinceCreate(ProvinceBase):
    """
    Used when creating a Province.
    """

    pass


# ---------------------------------------------------------
# Update Schema
# ---------------------------------------------------------
class ProvinceUpdate(BaseModel):
    """
    Used when updating a Province.
    """

    name: str | None = None

    code: str | None = None


# ---------------------------------------------------------
# Response Schema
# ---------------------------------------------------------
class ProvinceResponse(ProvinceBase):
    """
    Province returned by the API.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int

    created_at: datetime

    updated_at: datetime


# ---------------------------------------------------------
# Summary Schema
# ---------------------------------------------------------
class ProvinceSummary(BaseModel):
    """
    Lightweight Province representation.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int

    name: str

    code: str