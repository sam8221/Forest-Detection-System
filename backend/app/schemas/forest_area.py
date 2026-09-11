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
    - Expose district information in API responses.

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

from geoalchemy2.elements import WKBElement
from geoalchemy2.shape import to_shape

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from app.models.enums import (
    MonitoringFrequency,
    PriorityLevel,
    ProtectedStatus,
)


# =========================================================
# BASE SCHEMA
# =========================================================

class ForestAreaBase(BaseModel):
    """
    Defines the common fields shared by Forest Area
    creation, update, and response schemas.
    """

    forest_code: str = Field(
        ...,
        min_length=3,
        max_length=30,
        description="Unique Forest Area identification code.",
    )

    name: str = Field(
        ...,
        min_length=3,
        max_length=200,
        description="Official name of the forest area.",
    )

    district_id: int = Field(
        ...,
        description="Database identifier of the associated district.",
    )

    geometry: str = Field(
        ...,
        description=(
            "Forest boundary represented as a WKT POLYGON "
            "using WGS84 coordinates with SRID 4326."
        ),
    )

    protected_status: ProtectedStatus = Field(
        ...,
        description="Protection classification of the forest area.",
    )

    monitoring_frequency: MonitoringFrequency = Field(
        ...,
        description="Frequency at which the area is monitored.",
    )

    priority_level: PriorityLevel = Field(
        ...,
        description="Monitoring priority assigned to the forest area.",
    )

    area_hectares: float = Field(
        ...,
        gt=0,
        description="Forest area size in hectares.",
    )

    description: str | None = Field(
        default=None,
        description="Additional information about the forest area.",
    )


# =========================================================
# CREATE SCHEMA
# =========================================================

class ForestAreaCreate(ForestAreaBase):
    """
    Defines the data required when creating a new
    Forest Area.
    """

    pass


# =========================================================
# UPDATE SCHEMA
# =========================================================

class ForestAreaUpdate(BaseModel):
    """
    Defines the fields that can be modified for an
    existing Forest Area.
    """

    name: str | None = Field(
        default=None,
        min_length=3,
        max_length=200,
    )

    geometry: str | None = Field(
        default=None,
        description=(
            "Updated forest boundary represented as a "
            "WKT POLYGON using WGS84 coordinates with "
            "SRID 4326."
        ),
    )

    protected_status: ProtectedStatus | None = None

    monitoring_frequency: MonitoringFrequency | None = None

    priority_level: PriorityLevel | None = None

    area_hectares: float | None = Field(
        default=None,
        gt=0,
    )

    description: str | None = None

    is_active: bool | None = None


# =========================================================
# RESPONSE SCHEMA
# =========================================================

class ForestAreaResponse(ForestAreaBase):
    """
    Defines the Forest Area information returned by
    the API.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int

    created_by: int

    is_active: bool

    created_at: datetime

    updated_at: datetime

    # -----------------------------------------------------
    # District information
    # -----------------------------------------------------

    district_name: str | None = Field(
        default=None,
        description="Name of the associated district.",
    )

    district_code: str | None = Field(
        default=None,
        description="Official code of the associated district.",
    )

    # -----------------------------------------------------
    # PostGIS geometry conversion
    # -----------------------------------------------------

    @field_validator(
        "geometry",
        mode="before",
    )
    @classmethod
    def convert_geometry_to_wkt(cls, value):
        """
        Convert a PostGIS WKBElement into a WKT string
        before Pydantic response validation.
        """

        if isinstance(value, WKBElement):
            return to_shape(value).wkt

        if isinstance(value, str):
            return value

        return str(value)