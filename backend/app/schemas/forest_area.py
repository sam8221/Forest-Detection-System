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

    # -----------------------------------------------------
    # These two limits are the widths of the columns the
    # values are stored in: forest_areas.forest_code is
    # VARCHAR(20) and forest_areas.name is VARCHAR(150).
    #
    # They were previously 30 and 200 here, which let a
    # longer code or a long official name pass validation
    # and then fail in the database, so the officer was
    # shown "The forest area could not be saved." with
    # nothing to act on. A limit stated in the schema is
    # returned as a 422 naming the field and the maximum.
    # Changing these numbers means changing the columns and
    # migrating, not changing them here alone.
    # -----------------------------------------------------

    forest_code: str = Field(
        ...,
        min_length=3,
        max_length=20,
        description=(
            "Unique Forest Area identification code, up to "
            "20 characters."
        ),
    )

    name: str = Field(
        ...,
        min_length=3,
        max_length=150,
        description=(
            "Official name of the forest area, up to 150 "
            "characters."
        ),
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
        max_length=150,
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