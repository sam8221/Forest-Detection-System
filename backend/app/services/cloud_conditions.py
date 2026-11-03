"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Cloud Conditions

Purpose:
    Turns a cloud-cover percentage into the words and the
    judgement the interface shows an officer.

Responsibilities:
    - Classify a percentage on the okta scale.
    - Say whether a scene is cloud-free enough to analyse.
    - Say nothing at all when there is no measurement.

What this module will not do:
    It will not invent a percentage. Every function here
    accepts None and returns an absence, because "we do not
    know how cloudy it is" is a real answer and the one
    thing that must never be replaced by a plausible
    number. An officer deciding whether to wait for clearer
    imagery is entitled to know that the system has no
    reading rather than to be shown a guess.

    It also holds no database session and makes no request,
    so the classification and the suitability rule can both
    be tested against hand-worked values with no network
    and no database, which is what the accuracy chapter
    needs.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Version:
    1.0.0
===========================================================
"""

from __future__ import annotations

from enum import Enum

from app.core.config import get_settings


class CloudCondition(str, Enum):
    """
    How much of the sky is covered, in words.

    Boundaries come from the okta scale and live in
    configuration. See the note beside
    cloud_clear_max_percentage in app.core.config.
    """

    CLEAR = "CLEAR"

    PARTLY_CLOUDY = "PARTLY_CLOUDY"

    CLOUDY = "CLOUDY"

    VERY_CLOUDY = "VERY_CLOUDY"

    #: No measurement. Not a condition, but the interface
    #: needs something to show, and showing a condition
    #: would be stating a fact nobody established.
    UNKNOWN = "UNKNOWN"


#: What each condition is called on screen.
CONDITION_LABELS: dict[CloudCondition, str] = {
    CloudCondition.CLEAR: "Clear",
    CloudCondition.PARTLY_CLOUDY: "Partly cloudy",
    CloudCondition.CLOUDY: "Cloudy",
    CloudCondition.VERY_CLOUDY: "Very cloudy",
    CloudCondition.UNKNOWN: "Not available",
}


def classify_cloud_cover(
    percentage: float | None,
) -> CloudCondition:
    """
    Describe a cloud-cover percentage in words.

    Args:
        percentage:
            Sky covered, 0 to 100. None when there is no
            measurement.

    Returns:
        The matching condition, or UNKNOWN when there is
        nothing to classify.

    A value outside 0 to 100 is treated as no measurement
    rather than clamped. A provider reporting 150 percent
    cloud cover has malfunctioned, and clamping it to 100
    would turn an obvious fault into a confident reading of
    total overcast.
    """

    if percentage is None:
        return CloudCondition.UNKNOWN

    try:
        value = float(percentage)

    except (TypeError, ValueError):
        return CloudCondition.UNKNOWN

    if value != value:  # NaN
        return CloudCondition.UNKNOWN

    if value < 0 or value > 100:
        return CloudCondition.UNKNOWN

    settings = get_settings()

    if value <= settings.cloud_clear_max_percentage:
        return CloudCondition.CLEAR

    if value <= settings.cloud_partly_cloudy_max_percentage:
        return CloudCondition.PARTLY_CLOUDY

    if value <= settings.cloud_cloudy_max_percentage:
        return CloudCondition.CLOUDY

    return CloudCondition.VERY_CLOUDY


def condition_label(condition: CloudCondition) -> str:
    """
    The on-screen wording for a condition.

    Args:
        condition:
            Condition to name.

    Returns:
        Its label, or the unknown label for anything this
        module does not recognise.
    """

    return CONDITION_LABELS.get(
        condition,
        CONDITION_LABELS[CloudCondition.UNKNOWN],
    )


def is_suitable_for_analysis(
    percentage: float | None,
) -> bool | None:
    """
    Whether a scene is clear enough to measure NDVI from.

    Args:
        percentage:
            Cloud cover recorded for the scene.

    Returns:
        True or False, or None when there is no measurement.

    Judged against MAX_CLOUD_COVER_PERCENTAGE, the threshold
    the rest of the system already uses when searching the
    catalogue. One threshold, one meaning: a scene called
    suitable here is one the search would have returned.

    None rather than False for a missing measurement. False
    would say the scene is unsuitable, which is a finding;
    the truth is that no finding can be made. The interface
    shows the difference, because an officer who reads
    "unsuitable" waits for another pass while one who reads
    "unknown" goes and looks.

    This answers requirement 6 in the narrow way it should
    be answered: the figure helps an officer choose an
    observation. It never decides, on its own, that an area
    has been cleared. Cloud lowers NDVI; so does felling. A
    cloud-cover number separates those two readings for a
    person, and nothing in the detection path consults it to
    classify anything.
    """

    if percentage is None:
        return None

    condition = classify_cloud_cover(percentage)

    if condition is CloudCondition.UNKNOWN:
        return None

    return float(percentage) <= (
        get_settings().max_cloud_cover_percentage
    )
