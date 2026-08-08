"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
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

Version:
    1.0.0
===========================================================
"""

from enum import Enum


# =========================================================
# User Roles
# =========================================================
class UserRole(str, Enum):
    """System user roles."""

    ADMIN = "ADMIN"
    FORESTRY_OFFICER = "FORESTRY_OFFICER"
    RESEARCHER = "RESEARCHER"


# =========================================================
# Protected Status
# =========================================================
class ProtectedStatus(str, Enum):
    """Forest protection categories."""

    PROTECTED_FOREST = "PROTECTED_FOREST"
    NATIONAL_PARK = "NATIONAL_PARK"
    GAME_MANAGEMENT_AREA = "GAME_MANAGEMENT_AREA"
    COMMUNITY_FOREST = "COMMUNITY_FOREST"
    PRIVATE_FOREST = "PRIVATE_FOREST"


# =========================================================
# Monitoring Frequency
# =========================================================
class MonitoringFrequency(str, Enum):
    """Automatic monitoring frequency."""

    DAILY = "DAILY"
    EVERY_2_DAYS = "EVERY_2_DAYS"
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
    """Alert processing status."""

    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    READ = "READ"


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