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

    The field limits mirror the columns in app/models/district.py,
    so a value the schema accepts is always one the database can
    store.

    `province_id` is required rather than optional because
    the corresponding column is a non-null foreign key: a
    district cannot be stored without the province it
    belongs to.

    NOTE: Nothing currently imports this module. The
    districts router at app/api/districts.py returns ORM
    objects directly and declares no response_model, so
    these schemas are not yet on any request or response
    path. Either wire them into that router or remove the
    module; leaving it unreferenced means errors in it are
    never surfaced at import time.
    """

    province_id: int

    name: str = Field(
        ...,
        min_length=2,
        max_length=100,
    )

    # String(20) on the model. This was limited to 10 here,
    # which would have rejected district codes the database
    # accepts.
    code: str = Field(
        ...,
        min_length=2,
        max_length=20,
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