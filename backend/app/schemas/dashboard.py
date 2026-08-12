"""
ForestWatch Zambia

Module: Dashboard Schemas

Purpose:
Defines dashboard response schemas.

Author:
Samuel Bikiloni
"""

from pydantic import BaseModel


# =========================================================
# FOREST STATISTICS
# =========================================================

class ForestStatistics(BaseModel):

    total_forests: int
    monitored_forests: int
    protected_forests: int


# =========================================================
# DETECTION STATISTICS
# =========================================================

class DetectionStatistics(BaseModel):

    total_detections: int
    pending_detections: int
    verified_detections: int
    rejected_detections: int


# =========================================================
# ALERT STATISTICS
# =========================================================

class AlertStatistics(BaseModel):

    total_alerts: int
    pending_alerts: int
    sent_alerts: int
    failed_alerts: int
    read_alerts: int
    resolved_alerts: int = 0


# =========================================================
# SATELLITE STATISTICS
# =========================================================

class SatelliteStatistics(BaseModel):

    total_images: int
    processed_images: int
    unprocessed_images: int


# =========================================================
# DASHBOARD STATISTICS
# =========================================================

class DashboardStatistics(BaseModel):

    forests: ForestStatistics
    detections: DetectionStatistics
    alerts: AlertStatistics
    satellite_images: SatelliteStatistics


# =========================================================
# RECENT DETECTION
# =========================================================

class RecentDetection(BaseModel):

    id: int
    forest_name: str
    detected_area_hectares: float
    confidence_score: float
    status: str


# =========================================================
# RECENT ALERT
# =========================================================

class RecentAlert(BaseModel):

    id: int
    title: str
    priority: str
    status: str


# =========================================================
# COMPLETE DASHBOARD RESPONSE
# =========================================================

class DashboardResponse(BaseModel):

    statistics: DashboardStatistics

    recent_detections: list[RecentDetection]

    recent_alerts: list[RecentAlert]