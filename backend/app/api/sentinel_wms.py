"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Sentinel-2 Imagery Proxy

Purpose:
    Serves Copernicus Sentinel-2 imagery to the map.

Responsibilities:
    - Forward map requests to the Copernicus WMS.
    - Keep the Sentinel Hub instance identifier on the
      server, out of the browser.
    - Constrain the requested image size.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Note:
    The browser never sees the instance identifier. If the
    map called Copernicus directly, that identifier would
    be readable in the page source and anyone could draw
    against the department's quota.
===========================================================
"""

from fastapi import APIRouter, Depends, Request, Response
import math
import requests

from app.api.deps import get_map_imagery_user
from app.core.config import get_settings
from app.models.user import User


router = APIRouter(
    prefix="/sentinel",
    tags=["Sentinel-2"],
)


MAX_RESOLUTION_METERS = 180.0
MAX_IMAGE_SIZE = 2048
MIN_IMAGE_SIZE = 512


@router.get("/wms")
def sentinel_wms(
    http_request: Request,
    _: User = Depends(get_map_imagery_user),
):
    """
    Return a Sentinel-2 map image for the requested extent.

    Args:
        http_request:
            The incoming request. Its query string carries
            the OGC WMS parameters (BBOX, WIDTH, HEIGHT,
            LAYERS, SRS, FORMAT, TIME and so on), which are
            read from the raw query rather than bound as
            typed parameters. See the note on case below.

        _:
            The authenticated officer, resolved by
            get_map_imagery_user. Not referenced in the
            body; the dependency is present to reject
            unauthenticated callers before any Copernicus
            quota is spent.

    Returns:
        Response:
            The image bytes from Copernicus, with the
            upstream content type and a short cache
            lifetime. On failure, a plain-text or XML
            response carrying the reason.

    Error cases:
        400: BBOX is absent, is not four comma-separated
            numbers, or describes a zero or inverted extent;
            WIDTH or HEIGHT is not numeric.
        503: No Sentinel Hub instance identifier is
            configured, so imagery cannot be requested.
        502: Copernicus could not be reached.
        Any other upstream status is passed through with the
        upstream body, so an OGC ServiceException reaches
        the caller intact rather than being reported as a
        generic failure.

    Parameter names are read WITHOUT regard to case. The OGC
    WMS specification defines request parameter names as
    case-insensitive and clients rely on that: Leaflet sends
    LAYERS, FORMAT and VERSION in upper case while sending
    width, height, srs and bbox in lower case, in the same
    request. Binding them as typed parameters would match
    only one spelling of each, so a request would silently
    fall back to the default layer instead of returning the
    layer the officer selected.

    The system is restricted to authorised Forestry
    Department officers, and each request consumes
    Copernicus quota from the department's account. The
    authentication may arrive in the Authorization header
    or, for map layers that cannot set headers, as an
    access_token query parameter.
    """

    # -----------------------------------------------------
    # Normalise the query string
    #
    # The last value wins if a name appears more than once,
    # which matches how the parameters are built up.
    # -----------------------------------------------------

    params_lower = {
        key.lower(): value
        for key, value in http_request.query_params.items()
    }

    def param(name: str, default=None):
        """Read one parameter, ignoring its case."""

        value = params_lower.get(name.lower())

        return default if value in (None, "") else value

    settings = get_settings()

    layers = param("layers", "1_TRUE_COLOR")
    styles = param("styles", "") or ""
    service = param("service", "WMS")
    version = param("version", "1.1.1")
    request = param("request", "GetMap")
    format = param("format", "image/png")
    transparent = param("transparent", "false")
    srs = param("srs") or param("crs") or "EPSG:3857"
    time = param("time")

    bbox = param("bbox")

    if not bbox:
        return Response(
            content="Missing BBOX parameter.",
            status_code=400,
            media_type="text/plain",
        )

    try:
        width = int(float(param("width", 1024)))
        height = int(float(param("height", 768)))

    except (TypeError, ValueError):
        return Response(
            content="WIDTH and HEIGHT must be numbers.",
            status_code=400,
            media_type="text/plain",
        )

    try:
        wms_url = settings.sentinel_wms_url

    except RuntimeError as exc:
        return Response(
            content=str(exc),
            status_code=503,
            media_type="text/plain",
        )

    try:
        coordinates = [
            float(value.strip())
            for value in bbox.split(",")
        ]

        if len(coordinates) != 4:
            raise ValueError()

        min_x, min_y, max_x, max_y = coordinates

        if min_x >= max_x or min_y >= max_y:
            raise ValueError()

    except (ValueError, TypeError):
        return Response(
            content="Invalid BBOX. Expected minX,minY,maxX,maxY.",
            status_code=400,
            media_type="text/plain",
        )

    requested_width = max(
        int(width),
        MIN_IMAGE_SIZE,
    )

    requested_height = max(
        int(height),
        MIN_IMAGE_SIZE,
    )

    bbox_width = abs(max_x - min_x)
    bbox_height = abs(max_y - min_y)

    required_width = math.ceil(
        bbox_width / MAX_RESOLUTION_METERS
    )

    required_height = math.ceil(
        bbox_height / MAX_RESOLUTION_METERS
    )

    final_width = max(
        requested_width,
        required_width,
        MIN_IMAGE_SIZE,
    )

    final_height = max(
        requested_height,
        required_height,
        MIN_IMAGE_SIZE,
    )

    scale = max(
        final_width / MAX_IMAGE_SIZE,
        final_height / MAX_IMAGE_SIZE,
        1.0,
    )

    final_width = min(
        math.ceil(final_width / scale),
        MAX_IMAGE_SIZE,
    )

    final_height = min(
        math.ceil(final_height / scale),
        MAX_IMAGE_SIZE,
    )

    final_width = max(
        final_width,
        MIN_IMAGE_SIZE,
    )

    final_height = max(
        final_height,
        MIN_IMAGE_SIZE,
    )

    params = {
        "SERVICE": service,
        "VERSION": version,
        "REQUEST": request,
        "LAYERS": layers,
        "STYLES": styles,
        "FORMAT": format,
        "TRANSPARENT": transparent,
        "WIDTH": final_width,
        "HEIGHT": final_height,
        "SRS": srs,
        "BBOX": (
            f"{min_x},{min_y},"
            f"{max_x},{max_y}"
        ),

        # -------------------------------------------------
        # Suppress the burnt-in Copernicus logo
        #
        # Sentinel Hub draws a Copernicus logo into the
        # bottom-left of every image unless asked not to.
        # It is drawn over the imagery itself, which on
        # this map is the evidence an officer is judging:
        # it obscures whatever ground falls in that corner,
        # and it is resampled with the image rather than
        # being part of the page.
        #
        # This is a rendering option, not the licence
        # condition. Attribution is still required and is
        # still given, as a credit line on the map
        # ("Sentinel-2 (c) Copernicus Data Space
        # Ecosystem"), which is where the Copernicus terms
        # ask for it. Removing that credit line would
        # breach the data licence; removing this logo does
        # not.
        # -------------------------------------------------

        "SHOWLOGO": "false",
    }

    if time:
        params["TIME"] = time

    try:
        response = requests.get(
            wms_url,
            params=params,
            timeout=90,
        )

    except requests.RequestException as exc:
        return Response(
            content=(
                "Copernicus connection failed: "
                f"{exc}"
            ),
            status_code=502,
            media_type="text/plain",
        )

    content_type = response.headers.get(
        "content-type",
        "",
    )

    if response.status_code != 200:
        return Response(
            content=response.content,
            status_code=response.status_code,
            media_type=(
                content_type
                or "application/xml"
            ),
        )

    return Response(
        content=response.content,
        status_code=200,
        media_type=(
            content_type
            or "image/png"
        ),
        headers={
            "Cache-Control": "public, max-age=60",
        },
    )