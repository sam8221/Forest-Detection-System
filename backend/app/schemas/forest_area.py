"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Forest Area Schemas

Purpose:
    Defines Pydantic schemas for Forest Areas.

Responsibilities:
    - Validate forest area requests.
    - Serialize forest area responses.
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

from app.models.enums import (
    MonitoringFrequency,
    PriorityLevel,
    ProtectedStatus,
)


# ---------------------------------------------------------
# Base Schema
# ---------------------------------------------------------
class ForestAreaBase(BaseModel):
    """
    Common Forest Area fields.
    """

    forest_code: str = Field(
        ...,
        min_length=3,
        max_length=30,
    )

    name: str = Field(
        ...,
        min_length=3,
        max_length=200,
    )

    district_id: int

    protected_status: ProtectedStatus

    monitoring_frequency: MonitoringFrequency

    priority_level: PriorityLevel

    area_hectares: float

    description: str | None = None


# ---------------------------------------------------------
# Create Schema
# ---------------------------------------------------------
class ForestAreaCreate(ForestAreaBase):
    """
    Used when creating a Forest Area.
    """

    pass


# ---------------------------------------------------------
# Update Schema
# ---------------------------------------------------------
class ForestAreaUpdate(BaseModel):
    """
    Used when updating a Forest Area.
    """

    name: str | None = None

    protected_status: ProtectedStatus | None = None

    monitoring_frequency: MonitoringFrequency | None = None

    priority_level: PriorityLevel | None = None

    area_hectares: float | None = None

    description: str | None = None

    is_active: bool | None = None


# ---------------------------------------------------------
# Response Schema
# ---------------------------------------------------------
class ForestAreaResponse(ForestAreaBase):
    """
    Returned by the API.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int

    created_by: int

    is_active: bool

    created_at: datetime

    updated_at: datetime