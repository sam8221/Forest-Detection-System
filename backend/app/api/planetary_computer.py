from fastapi import APIRouter, HTTPException, Query
import requests

router = APIRouter(
    prefix="/planetary",
    tags=["Planetary Computer"],
)

STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"

COPPERBELT_BBOX = (
    27.20,
    -13.70,
    29.50,
    -11.70,
)


@router.get("/sentinel")
def get_sentinel_image(
    cloud_cover: int = Query(30, ge=0, le=100),
):
    search_url = f"{STAC_URL}/search"

    params = {
        "collections": "sentinel-2-l2a",
        "bbox": ",".join(str(value) for value in COPPERBELT_BBOX),
        "limit": 20,
        "sortby": "-datetime",
    }

    try:
        response = requests.get(
            search_url,
            params=params,
            timeout=60,
        )

        response.raise_for_status()

        data = response.json()

    except requests.RequestException as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Planetary Computer STAC request failed: {exc}",
        )

    features = data.get("features", [])

    if not features:
        raise HTTPException(
            status_code=404,
            detail="No Sentinel-2 imagery was found for the Copperbelt.",
        )

    suitable_items = []

    for item in features:
        item_cloud_cover = item.get(
            "properties",
            {},
        ).get(
            "eo:cloud_cover"
        )

        if item_cloud_cover is None:
            suitable_items.append(item)
            continue

        if float(item_cloud_cover) <= cloud_cover:
            suitable_items.append(item)

    if not suitable_items:
        suitable_items = features

    item = suitable_items[0]

    item_id = item["id"]

    properties = item.get(
        "properties",
        {},
    )

    assets = item.get(
        "assets",
        {},
    )

    tilejson_asset = assets.get("tilejson")

    if not tilejson_asset:
        raise HTTPException(
            status_code=404,
            detail="TileJSON asset was not found for the Sentinel-2 image.",
        )

    tilejson_url = tilejson_asset.get("href")

    if not tilejson_url:
        raise HTTPException(
            status_code=404,
            detail="Sentinel-2 TileJSON URL is missing.",
        )

    try:
        tilejson_response = requests.get(
            tilejson_url,
            timeout=60,
        )

        tilejson_response.raise_for_status()

        tilejson = tilejson_response.json()

    except requests.RequestException as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Planetary Computer TileJSON request failed: {exc}",
        )

    tiles = tilejson.get("tiles", [])

    if not tiles:
        raise HTTPException(
            status_code=404,
            detail="Planetary Computer returned no map tiles.",
        )

    return {
        "source": "Microsoft Planetary Computer",
        "collection": "sentinel-2-l2a",
        "item_id": item_id,
        "datetime": properties.get("datetime"),
        "cloud_cover": properties.get("eo:cloud_cover"),
        "bounds": tilejson.get("bounds"),
        "center": tilejson.get("center"),
        "minzoom": tilejson.get("minzoom"),
        "maxzoom": tilejson.get("maxzoom"),
        "tiles": tiles,
    }