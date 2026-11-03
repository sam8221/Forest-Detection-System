"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Weather Service

Purpose:
    Reads the cloud cover over a point in the Copperbelt as
    it is now, from a weather provider.

Responsibilities:
    - Ask the configured provider for current cloud cover.
    - Report the observation time and the provider's name.
    - Cache a reading for as long as it stays current.
    - Fail honestly when the provider cannot be reached.

Why this is separate from the Sentinel-2 cloud cover:

    A Sentinel-2 product carries the cloud cover measured
    when the satellite passed overhead, which may be several
    days ago. That figure answers "could this image have been
    used", and it is the one the analysis cares about.

    It does not answer "what is the sky doing now", which is
    what an officer planning a field visit or waiting for a
    usable pass wants. Presenting one as the other would
    mean telling somebody the sky is clear on the strength
    of a measurement taken last Tuesday.

    So the two are fetched from different places, carried in
    different fields, and labelled with their own times and
    sources all the way to the screen.

Security:
    A provider that needs a credential receives it from
    configuration, in the query string only if the provider
    requires it there. It is never logged and never returned
    to a caller. The default provider needs none.

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

import logging
import threading
import time

from dataclasses import dataclass
from datetime import datetime

from app.core.config import get_settings


logger = logging.getLogger(__name__)


# =========================================================
# ERRORS
# =========================================================


class WeatherError(Exception):
    """The current cloud cover could not be obtained."""


class WeatherDisabled(WeatherError):
    """The current-weather reading is switched off."""


class WeatherUnavailable(WeatherError):
    """The provider could not be reached, or answered badly."""


# =========================================================
# READING
# =========================================================


@dataclass(frozen=True)
class CurrentCloudCover:
    """
    One current cloud-cover reading.

    Attributes:
        percentage:
            Sky covered, 0 to 100.
        observed_at:
            When the provider says the reading applies. Its
            own timestamp, not the time this system asked.
        provider:
            Who supplied it, for the screen.
        latitude, longitude:
            The point the provider actually answered for,
            which is the nearest point on its grid and not
            necessarily the point requested.
        requested_latitude, requested_longitude:
            The point this system asked about.
        retrieved_at:
            When this system received it. Distinct from
            observed_at: a cached reading is retrieved once
            and shown many times, and an officer judging
            whether it is stale needs both.
    """

    percentage: float

    observed_at: str

    provider: str

    latitude: float

    longitude: float

    requested_latitude: float

    requested_longitude: float

    retrieved_at: datetime


# =========================================================
# CACHE
#
# Readings are cached per grid point for as long as the
# provider's own update interval. Several officers watching
# the same district therefore cost one request, and a card
# that refreshes on a timer does not multiply into a
# request per officer per minute.
# =========================================================

_cache: dict[tuple[float, float], tuple[float, CurrentCloudCover]] = {}

_cache_lock = threading.Lock()


def reset_weather_cache() -> None:
    """Forget every cached reading. Used by tests."""

    with _cache_lock:
        _cache.clear()


def _cache_key(
    latitude: float,
    longitude: float,
) -> tuple[float, float]:
    """
    The key a reading is cached under.

    Rounded to three decimal places, about a hundred metres.
    Two forest areas in the same district resolve to the
    same key and share one request, which is the point;
    rounding further would start answering for the wrong
    place.
    """

    return (round(latitude, 3), round(longitude, 3))


# =========================================================
# FETCH
# =========================================================


def fetch_current_cloud_cover(
    latitude: float,
    longitude: float,
    force: bool = False,
) -> CurrentCloudCover:
    """
    Current cloud cover over a point.

    Args:
        latitude, longitude:
            Where to ask about, in WGS84.
        force:
            Ask the provider even if a cached reading is
            still current. Used by the manual refresh
            button.

    Returns:
        The reading.

    Raises:
        WeatherDisabled:
            WEATHER_ENABLED is off.
        WeatherUnavailable:
            The provider could not be reached, answered with
            a fault, or answered without a cloud-cover
            figure.

    Raising rather than returning a default is deliberate.
    There is no sensible default for "how cloudy is it", and
    a function that returned zero on failure would put a
    clear sky on the screen every time the network dropped.
    """

    settings = get_settings()

    if not settings.weather_enabled:
        raise WeatherDisabled(
            "Current weather readings are switched off "
            "(WEATHER_ENABLED), so only satellite cloud "
            "cover is available."
        )

    key = _cache_key(latitude, longitude)

    now = time.monotonic()

    if not force:
        with _cache_lock:
            cached = _cache.get(key)

            if cached is not None:
                stored_at, reading = cached

                if now - stored_at < settings.weather_cache_seconds:
                    return reading

    reading = _request_cloud_cover(
        latitude,
        longitude,
        settings,
    )

    with _cache_lock:
        _cache[key] = (time.monotonic(), reading)

    return reading


def _request_cloud_cover(
    latitude: float,
    longitude: float,
    settings,
) -> CurrentCloudCover:
    """
    Make one request to the provider.

    Args:
        latitude, longitude:
            Point to ask about.
        settings:
            Application settings, passed in so the caller's
            single read of them is the one used.

    Returns:
        The reading.

    Raises:
        WeatherUnavailable:
            Anything that stops a reading being produced.
    """

    # Imported here so the application, its migrations and
    # its tests all start without the package, exactly as
    # the SMS service does with its SDK.
    import requests

    parameters = {
        "latitude": f"{latitude:.4f}",
        "longitude": f"{longitude:.4f}",
        "current": "cloud_cover",
        "timezone": "Africa/Lusaka",
    }

    # Only sent when a provider needs one. The default
    # provider does not, and sending an empty key would
    # make some providers reject the request.
    if settings.weather_api_key:
        parameters["apikey"] = settings.weather_api_key

    try:
        response = requests.get(
            settings.weather_api_url,
            params=parameters,
            timeout=(3.05, 6.0),
        )

    except Exception as exc:
        raise WeatherUnavailable(
            "The weather provider could not be reached, so "
            "current cloud cover is unavailable."
        ) from exc

    if response.status_code != 200:
        # The provider's own words are not repeated here.
        # A failing provider can return an HTML page, and
        # the request carried a credential for providers
        # that use one, so only the code is reported.
        raise WeatherUnavailable(
            f"The weather provider answered with status "
            f"{response.status_code}, so current cloud "
            f"cover is unavailable."
        )

    try:
        payload = response.json()

    except Exception as exc:
        raise WeatherUnavailable(
            "The weather provider's answer could not be "
            "read, so current cloud cover is unavailable."
        ) from exc

    return _read_payload(
        payload,
        latitude,
        longitude,
        settings,
    )


def _read_payload(
    payload: object,
    requested_latitude: float,
    requested_longitude: float,
    settings,
) -> CurrentCloudCover:
    """
    Pull the reading out of the provider's response.

    Args:
        payload:
            Whatever the provider returned.
        requested_latitude, requested_longitude:
            What was asked for, kept so the screen can show
            how far the answer's grid point is from it.
        settings:
            Application settings.

    Returns:
        The reading.

    Raises:
        WeatherUnavailable:
            The response carries no usable cloud-cover
            figure.

    A response that cannot be read is a failure, not a zero.
    This is the one place a fabricated percentage could
    enter the system, so every path out of it either
    carries a number the provider sent or raises.
    """

    if not isinstance(payload, dict):
        raise WeatherUnavailable(
            "The weather provider returned an unexpected "
            "response, so current cloud cover is "
            "unavailable."
        )

    current = payload.get("current")

    if not isinstance(current, dict):
        raise WeatherUnavailable(
            "The weather provider returned no current "
            "observation, so current cloud cover is "
            "unavailable."
        )

    raw = current.get("cloud_cover")

    if raw is None:
        raise WeatherUnavailable(
            "The weather provider returned no cloud-cover "
            "figure, so current cloud cover is unavailable."
        )

    try:
        percentage = float(raw)

    except (TypeError, ValueError) as exc:
        raise WeatherUnavailable(
            "The weather provider's cloud-cover figure "
            "could not be read, so current cloud cover is "
            "unavailable."
        ) from exc

    if percentage < 0 or percentage > 100:
        raise WeatherUnavailable(
            "The weather provider reported a cloud-cover "
            "figure outside 0 to 100 percent, so it cannot "
            "be trusted and is not shown."
        )

    observed_at = str(current.get("time") or "").strip()

    if not observed_at:
        # Without the provider's own timestamp there is no
        # way to tell a fresh reading from yesterday's, and
        # the card's whole claim is that it says when.
        raise WeatherUnavailable(
            "The weather provider gave no observation time, "
            "so the reading cannot be shown as current."
        )

    return CurrentCloudCover(
        percentage=percentage,
        observed_at=observed_at,
        provider=settings.weather_provider_name,
        # The grid point the provider answered for, when it
        # says; otherwise what was asked for.
        latitude=float(
            payload.get("latitude", requested_latitude)
        ),
        longitude=float(
            payload.get("longitude", requested_longitude)
        ),
        requested_latitude=requested_latitude,
        requested_longitude=requested_longitude,
        retrieved_at=datetime.now().astimezone(),
    )
