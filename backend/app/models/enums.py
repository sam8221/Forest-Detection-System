"""
ForestWatch Zambia

Module: System Enumerations

Purpose:
Defines all enumerations used throughout the
ForestWatch Zambia application.

Responsibilities:
- User roles
- Forest protection status
- Monitoring frequency
- Priority levels
- Analysis job status
- Detection status
- Alert types
- Alert status
- Generated file types

Author:
Samuel Bikiloni

Project:
Web-Based Deforestation Detection and Alert System
Using Sentinel-2 Imagery in the Copperbelt, Zambia
"""

from enum import Enum


# =========================================================
# User Roles
# =========================================================

class UserRole(str, Enum):
    """
    System user roles.

    The system is restricted to authorised officers of the
    Zambian Forestry Department.

    ADMIN provisions accounts and configures thresholds but
    has no operational alert duties. Keeping administration
    separate from operational review means the audit trail
    stays independent of the people being audited.

    The two officer roles differ only in the extent of their
    jurisdiction: a district officer sees one district, a
    provincial officer sees every district in their province.
    """

    ADMIN = "ADMIN"
    PROVINCIAL_FORESTRY_OFFICER = "PROVINCIAL_FORESTRY_OFFICER"
    DISTRICT_FORESTRY_OFFICER = "DISTRICT_FORESTRY_OFFICER"


# =========================================================
# Protected Status
# =========================================================

class ProtectedStatus(str, Enum):
    """Forest protection categories."""

    PROTECTED_FOREST = "PROTECTED_FOREST"
    COMMUNITY_FOREST = "COMMUNITY_FOREST"
    PRIVATE_FOREST = "PRIVATE_FOREST"


# =========================================================
# Monitoring Frequency
# =========================================================

class MonitoringFrequency(str, Enum):
    """Automatic monitoring frequency."""

    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"


# =========================================================
# Priority Level
# =========================================================

class PriorityLevel(str, Enum):
    """Monitoring priority."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# =========================================================
# Analysis Job Type
# =========================================================

class AnalysisJobType(str, Enum):
    """Analysis execution type."""

    MANUAL = "MANUAL"
    AUTOMATIC = "AUTOMATIC"


# =========================================================
# Analysis Job Status
# =========================================================

class AnalysisJobStatus(str, Enum):
    """Analysis job status."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


# =========================================================
# Detection Status
# =========================================================

class DetectionStatus(str, Enum):
    """Detection verification status."""

    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    CLOSED = "CLOSED"


# =========================================================
# Alert Type
# =========================================================

class AlertType(str, Enum):
    """Alert delivery channel."""

    EMAIL = "EMAIL"
    DASHBOARD = "DASHBOARD"


# =========================================================
# Alert Status
# =========================================================

class AlertStatus(str, Enum):
    """Alert processing and resolution status."""

    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    READ = "READ"
    RESOLVED = "RESOLVED"


# =========================================================
# Email Queue Status
# =========================================================

class EmailQueueStatus(str, Enum):
    """Email queue processing status."""

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SENT = "SENT"
    FAILED = "FAILED"


# =========================================================
# Generated File Type
# =========================================================

class GeneratedFileType(str, Enum):
    """Supported generated file types."""

    PDF = "PDF"
    CSV = "CSV"
    PNG = "PNG"
    GEOJSON = "GEOJSON"


# =========================================================
# Monitoring Trigger
# =========================================================

class MonitoringTrigger(str, Enum):
    """How monitoring was initiated."""

    MANUAL = "MANUAL"
    SCHEDULED = "SCHEDULED"