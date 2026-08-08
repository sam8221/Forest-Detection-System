"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Alert Schemas

Purpose:
    Defines Pydantic schemas for system alerts.

Responsibilities:
    - Validate alert data.
    - Serialize alert responses.
    - Support alert management.

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

from app.models.enums import (
    AlertStatus,
    AlertType,
    PriorityLevel,
)


# ---------------------------------------------------------
# Base Schema
# ---------------------------------------------------------
class AlertBase(BaseModel):
    """
    Common alert fields.
    """

    detection_id: int

    title: str

    message: str

    alert_type: AlertType

    priority: PriorityLevel


# ---------------------------------------------------------
# Create Schema
# ---------------------------------------------------------
class AlertCreate(AlertBase):
    """
    Used internally when creating alerts.
    """

    pass


# ---------------------------------------------------------
# Update Schema
# ---------------------------------------------------------
class AlertUpdate(BaseModel):
    """
    Used when updating an alert.
    """

    status: AlertStatus | None = None

    is_resolved: bool | None = None

    resolution_notes: str | None = None


# ---------------------------------------------------------
# Response Schema
# ---------------------------------------------------------
class AlertResponse(AlertBase):
    """
    Alert returned by the API.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int

    status: AlertStatus

    is_resolved: bool

    resolved_at: datetime | None

    resolution_notes: str | None

    created_at: datetime

    updated_at: datetime


# ---------------------------------------------------------
# Summary Schema
# ---------------------------------------------------------
class AlertSummary(BaseModel):
    """
    Lightweight alert representation.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int

    title: str

    priority: PriorityLevel

    status: AlertStatus

    is_resolved: bool


# ---------------------------------------------------------
# Mark As Read Schema
# ---------------------------------------------------------
class AlertReadRequest(BaseModel):
    """
    Used when a user marks an alert as read.
    """

    is_read: bool = True