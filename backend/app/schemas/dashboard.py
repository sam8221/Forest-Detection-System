"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Dashboard Schemas

Purpose:
    Defines dashboard response schemas.

Responsibilities:
    - Dashboard statistics
    - Recent detections
    - Recent alerts
    - Summary information

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Version:
    1.0.0
===========================================================
"""

from pydantic import BaseModel


# ---------------------------------------------------------
# Forest Statistics
# ---------------------------------------------------------
class ForestStatistics(BaseModel):
    """
    Forest summary statistics.
    """

    total_forests: int

    monitored_forests: int

    protected_forests: int


# ---------------------------------------------------------
# Detection Statistics
# ---------------------------------------------------------
class DetectionStatistics(BaseModel):
    """
    Detection summary statistics.
    """

    total_detections: int

    pending_detections: int

    verified_detections: int

    rejected_detections: int


# ---------------------------------------------------------
# Alert Statistics
# ---------------------------------------------------------
class AlertStatistics(BaseModel):
    """
    Alert summary statistics.
    """

    total_alerts: int

    pending_alerts: int

    sent_alerts: int

    failed_alerts: int

    read_alerts: int


# ---------------------------------------------------------
# Satellite Statistics
# ---------------------------------------------------------
class SatelliteStatistics(BaseModel):
    """
    Satellite imagery statistics.
    """

    total_images: int

    processed_images: int

    unprocessed_images: int


# ---------------------------------------------------------
# Dashboard Statistics
# ---------------------------------------------------------
class DashboardStatistics(BaseModel):
    """
    Overall dashboard statistics.
    """

    forests: ForestStatistics

    detections: DetectionStatistics

    alerts: AlertStatistics

    satellite_images: SatelliteStatistics


# ---------------------------------------------------------
# Recent Detection
# ---------------------------------------------------------
class RecentDetection(BaseModel):
    """
    Recent detection displayed on the dashboard.
    """

    id: int

    forest_name: str

    detected_area_hectares: float

    confidence_score: float

    status: str


# ---------------------------------------------------------
# Recent Alert
# ---------------------------------------------------------
class RecentAlert(BaseModel):
    """
    Recent alert displayed on the dashboard.
    """

    id: int

    title: str

    priority: str

    status: str


# ---------------------------------------------------------
# Dashboard Response
# ---------------------------------------------------------
class DashboardResponse(BaseModel):
    """
    Complete dashboard response.
    """

    statistics: DashboardStatistics

    recent_detections: list[RecentDetection]

    recent_alerts: list[RecentAlert]