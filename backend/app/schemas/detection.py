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
from typing import ClassVar

from geoalchemy2.elements import WKBElement
from geoalchemy2.shape import to_shape
from pydantic import (
    BaseModel,
    ConfigDict,
    field_validator,
)
from pyproj import Transformer
from shapely.ops import transform

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

    geometry: str | None = None

    verified_by: int | None

    verified_at: datetime | None

    verification_notes: str | None

    created_at: datetime

    updated_at: datetime

    # -----------------------------------------------------
    # PostGIS geometry conversion
    #
    # The outline of the clearing, so it can be drawn on the
    # map and an officer can see WHERE to go rather than
    # only how large it is.
    #
    # STORED in UTM Zone 35S (EPSG:32735), whose units are
    # metres, so the affected area is measured directly
    # without reprojecting first.
    #
    # RETURNED in WGS84 (EPSG:4326), the same coordinates
    # used by forest boundaries. Converting here means the
    # map receives one projection for every shape it draws.
    # Sending raw UTM instead would place detections far off
    # the map for any client that read the numbers as
    # degrees.
    #
    # Null for detections recorded before outlines were
    # captured.
    # -----------------------------------------------------

    # ClassVar, not a field: Pydantic treats a bare class
    # attribute as part of the response body.
    DISPLAY_SRID: ClassVar[int] = 4326

    @field_validator(
        "geometry",
        mode="before",
    )
    @classmethod
    def convert_geometry_to_wkt(cls, value):
        """
        Convert a PostGIS WKBElement into WGS84 WKT before
        Pydantic response validation.
        """

        if value is None:
            return None

        if isinstance(value, str):
            return value

        if not isinstance(value, WKBElement):
            return str(value)

        shape = to_shape(value)

        source_srid = value.srid

        # -------------------------------------------------
        # Already in display coordinates, or the SRID is
        # unknown and cannot be converted safely.
        # -------------------------------------------------

        if source_srid in (None, -1, cls.DISPLAY_SRID):
            return shape.wkt

        transformer = Transformer.from_crs(
            f"EPSG:{source_srid}",
            f"EPSG:{cls.DISPLAY_SRID}",
            always_xy=True,
        )

        return transform(
            transformer.transform,
            shape,
        ).wkt


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
    