"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Dashboard Schemas

Purpose:
    Defines the response contracts for the dashboard, the
    screen an officer opens first.

Responsibilities:
    - Describe the headline counts returned to the browser.
    - Describe the recent detection and alert summaries.
    - Describe the per-district breakdown.

How it works:
    These are Pydantic models, so they do two jobs at once.
    They validate what the API sends, and they generate the
    OpenAPI schema that documents it, which means the
    contract cannot drift from the code without the
    documentation changing with it.

    The figures are aggregates computed by the repository
    layer, already filtered to the requesting officer's
    jurisdiction. A district officer's totals cover their
    district alone. The schema is identical for every role;
    what differs is the scope of the query that filled it,
    and that decision is made on the server.

Note:
    Nothing here carries a geometry or a precise location.
    The dashboard reports counts and summaries; the
    coordinates of a suspected clearing are served only by
    the detection endpoints, which are individually
    jurisdiction-checked.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia
===========================================================
"""

from datetime import date

from pydantic import BaseModel


# =========================================================
# FOREST STATISTICS
# =========================================================

class ForestStatistics(BaseModel):
    """
    Counts of forest areas within the officer's jurisdiction.

    Attributes:
        total_forests:
            Forest areas registered, whether monitored or
            not.
        monitored_forests:
            Those with monitoring enabled, so an analysis
            job will pick them up.
        protected_forests:
            Those whose protected status is other than
            none, drawn from the ProtectedStatus enum.
    """

    total_forests: int
    monitored_forests: int
    protected_forests: int


# =========================================================
# DETECTION STATISTICS
# =========================================================

class DetectionStatistics(BaseModel):
    """
    Counts of detections by review state.

    The three review states are reported separately rather
    than as a single total, because they call for different
    action: pending detections await an officer, verified
    ones are confirmed clearing, and rejected ones are false
    positives. The verified and rejected counts together are
    the basis of the accuracy evaluation.

    Attributes:
        total_detections:
            All detections, in any state.
        pending_detections:
            Awaiting an officer's judgement.
        verified_detections:
            Confirmed as clearing by an officer.
        rejected_detections:
            Judged not to be clearing by an officer.
    """

    total_detections: int
    pending_detections: int
    verified_detections: int
    rejected_detections: int


# =========================================================
# ALERT STATISTICS
# =========================================================

class AlertStatistics(BaseModel):
    """
    Counts of alerts by delivery and handling state.

    Attributes:
        total_alerts:
            All alerts raised, in any state.
        pending_alerts:
            Queued but not yet despatched.
        sent_alerts:
            Despatched to their recipients.
        failed_alerts:
            Despatch was attempted and did not succeed.
            Distinguished from pending because the officer
            responsible is not going to be told without
            intervention.
        read_alerts:
            Opened by a recipient.
        resolved_alerts:
            Closed by an officer after acting on them.
            Defaults to zero so that a dashboard built
            before any alert was resolved still validates.
    """

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
    """
    Counts of satellite products held and their state.

    Attributes:
        total_images:
            Products registered against forest areas.
        processed_images:
            Those converted to NDVI rasters and available
            to an analysis job.
        unprocessed_images:
            Those downloaded or registered but not yet
            converted, and so not yet usable for detection.
    """

    total_images: int
    processed_images: int
    unprocessed_images: int


# =========================================================
# DASHBOARD STATISTICS
# =========================================================

class DashboardStatistics(BaseModel):
    """
    The four count groups shown across the dashboard tiles.

    Attributes:
        forests:
            Forest area counts.
        detections:
            Detection counts by review state.
        alerts:
            Alert counts by delivery and handling state.
        satellite_images:
            Product counts by processing state.
    """

    forests: ForestStatistics
    detections: DetectionStatistics
    alerts: AlertStatistics
    satellite_images: SatelliteStatistics


# =========================================================
# RECENT DETECTION
# =========================================================

class RecentDetection(BaseModel):
    """
    One detection, summarised for the dashboard list.

    Carries only what the list shows. The full record,
    including the NDVI readings before and after and the
    detection geometry, is fetched when an officer opens it.

    Attributes:
        id:
            Detection primary key, used to open the full
            record.
        forest_name:
            Name of the forest area the detection falls in,
            resolved here so the list need not look it up.
        detected_area_hectares:
            Area of vegetation loss, in hectares. Never
            below the configured minimum detection area,
            since smaller patches are suppressed.
        confidence_score:
            Confidence in the detection, 0.0 to 1.0.
        status:
            Review state as a string, from DetectionStatus.
    """

    id: int
    forest_name: str
    detected_area_hectares: float
    confidence_score: float
    status: str


# =========================================================
# RECENT ALERT
# =========================================================

class RecentAlert(BaseModel):
    """
    One alert, summarised for the dashboard list.

    Attributes:
        id:
            Alert primary key, used to open the full record.
        title:
            Short description shown in the list.
        priority:
            Urgency as a string, from PriorityLevel.
        status:
            Delivery and handling state as a string, from
            AlertStatus.
    """

    id: int
    title: str
    priority: str
    status: str


# =========================================================
# COMPLETE DASHBOARD RESPONSE
# =========================================================

class DashboardResponse(BaseModel):
    """
    The complete dashboard payload.

    NOTE: These figures are system-wide totals, not the
    signed-in officer's jurisdiction. The endpoint that
    builds them, get_dashboard in app/api/dashboard.py,
    requires an authenticated user but does not filter on
    that user's district or province, so a District
    Forestry Officer is shown national counts. This does
    not satisfy FR-04. The district breakdown endpoint in
    the same module does apply the jurisdiction rule and
    can be followed as the pattern.

    Attributes:
        statistics:
            The four count groups behind the tiles.
        recent_detections:
            Most recent detections, newest first.
        recent_alerts:
            Most recent alerts, newest first.
    """

    statistics: DashboardStatistics

    recent_detections: list[RecentDetection]

    recent_alerts: list[RecentAlert]


# =========================================================
# DISTRICT BREAKDOWN
# =========================================================

class DistrictSummary(BaseModel):
    """
    Deforestation activity within one district.

    Produced for officers who are responsible for more than
    one district. A District Forestry Officer sees a single
    district and has no use for a comparison; a Provincial
    Forestry Officer supervises several and needs to know
    which of them is worst affected and which has work
    waiting.
    """

    district_id: int

    district_name: str

    monitored_forests: int

    total_detections: int

    pending_detections: int

    verified_detections: int

    affected_area_hectares: float

    latest_detection: date | None = None

    oldest_pending_detection: date | None = None


class DistrictBreakdownResponse(BaseModel):
    """
    District comparison for a supervising officer.
    """

    scope: str

    districts: list[DistrictSummary]