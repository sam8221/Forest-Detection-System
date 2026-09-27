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
    ) -> dict:
        """
        Perform a GET request and return the decoded body.

        Args:
            url:
                Absolute URL to request.
            params:
                Query parameters, or None.
            description:
                What is being fetched, used in the log line
                so a failure can be traced to a step.

        Returns:
            dict: The decoded JSON body.

        Raises:
            PlanetaryUnavailableError:
                The request failed, timed out, returned an
                error status, or returned a body that is
                not JSON.
        """

        try:
            response = requests.get(
                url,
                params=params,
                timeout=self.timeout,
            )

            response.raise_for_status()

            return response.json()

        except requests.Timeout as exc:
            # Logged with the exception so the cause is
            # recoverable from the server log, while the
            # caller receives only the sentence below.
            logger.warning(
                "Planetary Computer %s request timed out "
                "after %.1fs: %s",
                description,
                self.timeout,
                exc,
            )

            raise PlanetaryUnavailableError(
                "The satellite imagery catalogue did not "
                "respond in time. This does not affect "
                "detections or alerts."
            ) from exc

        except requests.RequestException as exc:
            logger.warning(
                "Planetary Computer %s request failed: %s",
                description,
                exc,
            )

            raise PlanetaryUnavailableError(
                "The satellite imagery catalogue could not "
                "be reached. This does not affect "
                "detections or alerts."
            ) from exc

        except ValueError as exc:
            # raise_for_status passed but the body was not
            # JSON, which means the catalogue answered with
            # something unexpected.
            logger.warning(
                "Planetary Computer %s returned a body "
                "that is not JSON: %s",
                description,
                exc,
            )

            raise PlanetaryUnavailableError(
                "The satellite imagery catalogue returned "
                "an unexpected response."
            ) from exc

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
