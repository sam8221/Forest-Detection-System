"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Models Package

Purpose:
    Imports all SQLAlchemy models so that relationships
    between models are registered correctly.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia
===========================================================
"""

from app.models.alert import Alert
from app.models.alert_recipient import AlertRecipient
from app.models.analysis_job import AnalysisJob
from app.models.detection import Detection
from app.models.district import District
from app.models.email_queue import EmailQueue
from app.models.forest_area import ForestArea
from app.models.province import Province
from app.models.satellite_image import SatelliteImage
from app.models.user import User

__all__ = [
    "Alert",
    "AlertRecipient",
    "AnalysisJob",
    "Detection",
    "District",
    "EmailQueue",
    "ForestArea",
    "Province",
    "SatelliteImage",
    "User",
]