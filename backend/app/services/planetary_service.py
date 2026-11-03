"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Planetary Computer Service

Purpose:
    Retrieves a summary of the most recent Sentinel-2 scene
    covering the monitoring extent, from the Microsoft
    Planetary Computer STAC catalogue.

Responsibilities:
    - Search the catalogue for recent Sentinel-2 scenes.
    - Select the most suitable scene by cloud cover.
    - Resolve the scene's tile endpoint.
    - Report failure in terms the caller can act on.

Note on scope:
    This is a secondary catalogue. Copernicus remains the
    system's imagery source: it is what the detection
    pipeline downloads from and what the map renders
    through. This module supplies only the dashboard's
    scene summary panel, and every failure it raises is
    expected to leave the rest of the dashboard working.

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
import time

import requests

from app.core.config import get_settings


logger = logging.getLogger(__name__)


# =========================================================
# ERRORS
# =========================================================


class PlanetaryUnavailableError(RuntimeError):
    """
    The catalogue could not be reached or did not answer.

    Raised for a network failure, a timeout or an error
    status from the catalogue. The message carried by this
    exception is written for an officer to read, because it
    is what the interface displays.

    The underlying technical detail is logged rather than
    attached: a message such as
    "HTTPSConnectionPool(host=..., port=443)" tells an
    officer nothing they can act on, and publishes the
    system's internal hosts and library versions to anyone
    holding a session.
    """


class PlanetaryNoImageryError(RuntimeError):
    """
    The catalogue answered, but held no usable scene.

    Distinguished from unavailability because the officer's
    response differs: a missing scene is waited out, an
    unreachable catalogue is reported.
    """


# =========================================================
# SERVICE
# =========================================================


class PlanetaryService:
    """
    Reads recent Sentinel-2 scene metadata from the
    Planetary Computer STAC catalogue.

    The class holds no state between calls and opens no
    connection of its own, so it can be constructed per
    request without cost.
    """

    # The catalogue's Sentinel-2 Level-2A collection, which
    # is surface reflectance and already atmospherically
    # corrected. Level-1C is deliberately not used: the
    # detection pipeline compares NDVI across dates, and
    # uncorrected top-of-atmosphere values are not
    # comparable between acquisitions.
    COLLECTION = "sentinel-2-l2a"

    # Scenes examined per search. The catalogue returns them
    # newest first, so this is a window over recent
    # acquisitions rather than an arbitrary cap.
    SEARCH_LIMIT = 20

    # -----------------------------------------------------
    # Retry policy
    #
    # The catalogue is a public service under variable load.
    # Measured against it from this system, the same search
    # returned in 1.8 seconds at one point and 504 Gateway
    # Timeout after 16 seconds a quarter of an hour later,
    # with the request unchanged. Narrowing the search made
    # no reliable difference: with the service busy, a
    # single-scene request was no faster than a twenty-scene
    # one. The cost is the service's, not the query's, so
    # the answer is to tolerate a slow or failed attempt
    # rather than to ask for less.
    #
    # Three attempts, because the failure being absorbed is
    # a moment of load rather than an outage; an outage
    # should still be reported promptly instead of being
    # retried at length.
    # -----------------------------------------------------

    REQUEST_ATTEMPTS = 3

    # Waited before the second and third attempts. Short:
    # an officer is watching the dashboard, and the delay
    # is there to let a burst pass, not to wait out a fault.
    RETRY_BACKOFF_SECONDS = (1.0, 2.0)

    # Statuses worth attempting again. A gateway timeout or
    # a rate limit is a statement about the moment; a 404
    # is a statement about the request, and repeating it
    # only makes the officer wait longer for the same answer.
    RETRY_STATUS_CODES = frozenset({429, 500, 502, 503, 504})

    # The ceiling on everything a scene lookup does, across
    # both of its requests and every retry.
    #
    # The dashboard gives this endpoint 60 seconds before it
    # gives up on its own, so a lookup that ran longer would
    # be abandoned by the browser and its result wasted. The
    # budget stays below that with room to spare, and the
    # officer is told the catalogue is unavailable while
    # they are still waiting to be told something.
    TOTAL_BUDGET_SECONDS = 45.0

    def __init__(self) -> None:
        """
        Load configuration for the catalogue endpoint.
        """

        self.settings = get_settings()

        self.stac_url = self.settings.planetary_stac_url.rstrip("/")

        self.timeout = self.settings.planetary_timeout_seconds

    # -----------------------------------------------------
    # HTTP
    # -----------------------------------------------------

    def request_json(
        self,
        url: str,
        params: dict | None = None,
        description: str = "catalogue",
        deadline: float | None = None,
    ) -> dict:
        """
        Perform a GET request and return the decoded body.

        A timeout, a connection failure or a transient error
        status is attempted again, up to REQUEST_ATTEMPTS
        times and only while the deadline allows. Anything
        that will not change on a second attempt — a 404, a
        body that is not JSON — is reported immediately.

        Args:
            url:
                Absolute URL to request.
            params:
                Query parameters, or None.
            description:
                What is being fetched, used in the log line
                so a failure can be traced to a step.
            deadline:
                time.monotonic() value past which no further
                attempt is started and no attempt is allowed
                to run. None allows the full per-request
                timeout with no overall ceiling.

        Returns:
            dict: The decoded JSON body.

        Raises:
            PlanetaryUnavailableError:
                The request failed, timed out, returned an
                error status, or returned a body that is
                not JSON.
        """

        last_error: Exception | None = None

        for attempt in range(1, self.REQUEST_ATTEMPTS + 1):

            timeout = self.remaining_timeout(deadline)

            if timeout is None:
                # The budget is spent. Report the failure
                # that spent it rather than a new one.
                logger.warning(
                    "Planetary Computer %s gave up: the "
                    "time allowed for the lookup was used "
                    "up after %d attempt(s)",
                    description,
                    attempt - 1,
                )

                raise PlanetaryUnavailableError(
                    "The satellite imagery catalogue did "
                    "not respond in time. This does not "
                    "affect detections or alerts."
                ) from last_error

            try:
                response = requests.get(
                    url,
                    params=params,
                    timeout=timeout,
                )

                response.raise_for_status()

                return response.json()

            except requests.Timeout as exc:
                # Logged with the exception so the cause is
                # recoverable from the server log, while the
                # caller receives only the sentence below.
                logger.warning(
                    "Planetary Computer %s request timed "
                    "out after %.1fs (attempt %d of %d): "
                    "%s",
                    description,
                    timeout,
                    attempt,
                    self.REQUEST_ATTEMPTS,
                    exc,
                )

                last_error = exc

            except requests.HTTPError as exc:
                status = (
                    exc.response.status_code
                    if exc.response is not None
                    else None
                )

                if status not in self.RETRY_STATUS_CODES:
                    logger.warning(
                        "Planetary Computer %s request "
                        "failed: %s",
                        description,
                        exc,
                    )

                    raise PlanetaryUnavailableError(
                        "The satellite imagery catalogue "
                        "could not be reached. This does "
                        "not affect detections or alerts."
                    ) from exc

                logger.warning(
                    "Planetary Computer %s returned %s "
                    "(attempt %d of %d)",
                    description,
                    status,
                    attempt,
                    self.REQUEST_ATTEMPTS,
                )

                last_error = exc

            except requests.RequestException as exc:
                logger.warning(
                    "Planetary Computer %s request failed "
                    "(attempt %d of %d): %s",
                    description,
                    attempt,
                    self.REQUEST_ATTEMPTS,
                    exc,
                )

                last_error = exc

            except ValueError as exc:
                # raise_for_status passed but the body was
                # not JSON, which means the catalogue
                # answered with something unexpected.
                # Repeating the request will not make it
                # parse.
                logger.warning(
                    "Planetary Computer %s returned a body "
                    "that is not JSON: %s",
                    description,
                    exc,
                )

                raise PlanetaryUnavailableError(
                    "The satellite imagery catalogue "
                    "returned an unexpected response."
                ) from exc

            self.wait_before_retry(attempt, deadline)

        # Every attempt was spent on a fault worth retrying.
        logger.warning(
            "Planetary Computer %s failed after %d "
            "attempts: %s",
            description,
            self.REQUEST_ATTEMPTS,
            last_error,
        )

        if isinstance(last_error, requests.Timeout):
            raise PlanetaryUnavailableError(
                "The satellite imagery catalogue did not "
                "respond in time. This does not affect "
                "detections or alerts."
            ) from last_error

        raise PlanetaryUnavailableError(
            "The satellite imagery catalogue could not be "
            "reached. This does not affect detections or "
            "alerts."
        ) from last_error

    # -----------------------------------------------------
    # RETRY SUPPORT
    # -----------------------------------------------------

    def remaining_timeout(
        self,
        deadline: float | None,
    ) -> float | None:
        """
        Return the timeout the next attempt may use.

        Args:
            deadline:
                time.monotonic() value the lookup must
                finish by, or None for no ceiling.

        Returns:
            float | None:
                The per-attempt timeout, or None when there
                is no longer enough time to be worth
                starting another attempt.
        """

        if deadline is None:
            return self.timeout

        remaining = deadline - time.monotonic()

        # Below a second there is no realistic prospect of
        # the catalogue answering, and starting an attempt
        # only delays the message the officer is waiting for.
        if remaining < 1.0:
            return None

        return min(self.timeout, remaining)

    def wait_before_retry(
        self,
        attempt: int,
        deadline: float | None,
    ) -> None:
        """
        Pause between attempts, without overrunning.

        Args:
            attempt:
                The attempt just completed, counting from 1.
            deadline:
                time.monotonic() value the lookup must
                finish by, or None for no ceiling.
        """

        if attempt > len(self.RETRY_BACKOFF_SECONDS):
            return

        delay = self.RETRY_BACKOFF_SECONDS[attempt - 1]

        if deadline is not None:
            # Never sleep past the deadline: the time is
            # better spent on the attempt itself.
            delay = min(
                delay,
                max(0.0, deadline - time.monotonic()),
            )

        if delay > 0:
            time.sleep(delay)

    # -----------------------------------------------------
    # SCENE SELECTION
    # -----------------------------------------------------

    def select_scene(
        self,
        features: list[dict],
        max_cloud_cover: float,
    ) -> dict:
        """
        Choose the scene to summarise.

        Scenes arrive newest first. The most recent one
        within the cloud limit is preferred, because the
        dashboard is reporting what the system can currently
        see.

        If none is within the limit the newest scene is used
        regardless, and the caller still receives its real
        cloud cover figure. Showing a cloudy scene and
        saying so is more useful than showing nothing: it
        tells the officer the province is under cloud, which
        is itself the answer to why no detections have
        appeared.

        Args:
            features:
                STAC items from the catalogue.
            max_cloud_cover:
                Cloud cover ceiling, as a percentage.

        Returns:
            dict: The selected STAC item.

        Raises:
            PlanetaryNoImageryError:
                No scenes were returned at all.
        """

        if not features:
            raise PlanetaryNoImageryError(
                "No recent Sentinel-2 imagery was found "
                "for the monitored area."
            )

        for item in features:
            cloud_cover = item.get("properties", {}).get(
                "eo:cloud_cover"
            )

            # A scene with no cloud figure is accepted: the
            # catalogue not reporting the value is not
            # evidence that the scene is cloudy.
            if cloud_cover is None:
                return item

            try:
                if float(cloud_cover) <= max_cloud_cover:
                    return item

            except (TypeError, ValueError):
                # An unparseable figure is treated the same
                # way as a missing one.
                return item

        return features[0]

    # -----------------------------------------------------
    # PUBLIC ENTRY POINT
    # -----------------------------------------------------

    def get_latest_scene(
        self,
        max_cloud_cover: float | None = None,
    ) -> dict:
        """
        Return a summary of the most recent Sentinel-2 scene.

        Args:
            max_cloud_cover:
                Cloud cover ceiling as a percentage. Falls
                back to the configured system default.

        Returns:
            dict:
                Scene identifier, acquisition timestamp,
                cloud cover, map bounds, centre, zoom range
                and tile endpoints.

        Raises:
            PlanetaryUnavailableError:
                The catalogue could not be reached.
            PlanetaryNoImageryError:
                The catalogue holds no usable scene.
        """

        if max_cloud_cover is None:
            max_cloud_cover = (
                self.settings.max_cloud_cover_percentage
            )

        # The extent comes from configuration rather than a
        # literal, so the system can be pointed at another
        # province without a code change.
        bbox = self.settings.monitoring_bbox

        # One budget covers the search, the tile endpoint
        # lookup and every retry of either, so a slow search
        # cannot leave the second request with the whole
        # allowance still to spend.
        deadline = (
            time.monotonic()
            + self.TOTAL_BUDGET_SECONDS
        )

        search = self.request_json(
            url=f"{self.stac_url}/search",
            params={
                "collections": self.COLLECTION,
                "bbox": ",".join(
                    str(value) for value in bbox
                ),
                "limit": self.SEARCH_LIMIT,
                "sortby": "-datetime",
            },
            description="scene search",
            deadline=deadline,
        )

        item = self.select_scene(
            features=search.get("features", []),
            max_cloud_cover=max_cloud_cover,
        )

        properties = item.get("properties", {})

        tilejson_url = (
            item.get("assets", {})
            .get("tilejson", {})
            .get("href")
        )

        if not tilejson_url:
            raise PlanetaryNoImageryError(
                "The most recent Sentinel-2 scene cannot "
                "be displayed on a map."
            )

        tilejson = self.request_json(
            url=tilejson_url,
            description="tile endpoint",
            deadline=deadline,
        )

        tiles = tilejson.get("tiles", [])

        if not tiles:
            raise PlanetaryNoImageryError(
                "The most recent Sentinel-2 scene "
                "returned no map tiles."
            )

        return {
            "source": "Microsoft Planetary Computer",
            "collection": self.COLLECTION,
            "item_id": item.get("id"),
            "datetime": properties.get("datetime"),
            "cloud_cover": properties.get("eo:cloud_cover"),
            "bounds": tilejson.get("bounds"),
            "center": tilejson.get("center"),
            "minzoom": tilejson.get("minzoom"),
            "maxzoom": tilejson.get("maxzoom"),
            "tiles": tiles,
        }
