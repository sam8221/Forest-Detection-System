from fastapi import APIRouter, Query, Response
import math
import requests


router = APIRouter(
    prefix="/sentinel",
    tags=["Sentinel-2"],
)


SENTINEL_WMS_URL = (
    "https://sh.dataspace.copernicus.eu/ogc/wms/"
    "0a0b0bc0-5f64-4a9b-826a-28a79ef8007b"
)

MAX_RESOLUTION_METERS = 180.0
MAX_IMAGE_SIZE = 2048
MIN_IMAGE_SIZE = 512


@router.get("/wms")
def sentinel_wms(
    service: str = Query("WMS"),
    version: str = Query("1.1.1"),
    request: str = Query("GetMap"),
    layers: str = Query("1_TRUE_COLOR"),
    styles: str = Query(""),
    format: str = Query("image/png"),
    transparent: str = Query("false"),
    width: int = Query(1024),
    height: int = Query(768),
    srs: str = Query("EPSG:3857"),
    bbox: str = Query(...),
    time: str | None = Query(None),
):

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
    }

    if time:
        params["TIME"] = time

    try:
        response = requests.get(
            SENTINEL_WMS_URL,
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