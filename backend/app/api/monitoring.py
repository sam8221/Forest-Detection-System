"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Monitoring Map API

Purpose:
    Serves the interactive monitoring map: the forest
    boundary, NDVI overlays, their distribution, point
    readings and an NDVI trend.

Responsibilities:
    - Describe a forest area and its available layers.
    - Serve a coloured NDVI overlay as a PNG with bounds.
    - Report the distribution of valid pixels.
    - Read the layers under a clicked coordinate.
    - Report mean NDVI at detected locations over time.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Note:
    Raster work happens in the backend. A Sentinel-2 tile is
    about 480 MB as float32, and the browser receives a
    coloured PNG of at most 1024 pixels on its longest edge
    together with the bounds to place it.

    Every endpoint resolves the forest area through
    ForestAreaRepository.get_by_id_for_user, so an officer
    cannot open the monitoring map for a district they do
    not cover, nor read a pixel value from it. This is
    requirement FR-04, and it applies to imagery for the
    same reason it applies to detections: the imagery shows
    where the department has been looking.

Version:
    1.0.0
===========================================================
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from geoalchemy2.shape import to_shape
from shapely.geometry import mapping
from sqlalchemy import Float, cast, func, select
from sqlalchemy.orm import Session

from app.api.deps import (
    get_current_active_user,
    get_map_imagery_user,
)
from app.database.session import get_db
from app.models.analysis_job import AnalysisJob
from app.models.detection import Detection
from app.models.enums import AnalysisJobStatus
from app.models.user import User
from app.repositories.forest_area_repository import (
    ForestAreaRepository,
)
from app.services.raster_render_service import (
    LAYERS,
    RasterRenderService,
)


router = APIRouter(
    prefix="/monitoring",
    tags=["Monitoring Map"],
)


# =========================================================
# SHARED RESOLUTION
# =========================================================

def resolve_forest_area(
    forest_area_id: int,
    db: Session,
    user: User,
):
    """
    Load a forest area the officer is permitted to see.

    Raises:
        HTTPException:
            404 when the area does not exist or lies outside
            the officer's jurisdiction. The two are not
            distinguished, so requesting identifiers in
            sequence reveals nothing about other districts.
    """

    forest = ForestAreaRepository(db).get_by_id_for_user(
        forest_area_id=forest_area_id,
        user=user,
    )

    if forest is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Forest area not found.",
        )

    return forest


def resolve_job(
    forest_area_id: int,
    job_id: int | None,
    db: Session,
) -> AnalysisJob | None:
    """
    Choose which analysis job's outputs to read.

    An explicit job_id is honoured, but only when it belongs
    to this forest area: accepting another area's job would
    let an officer read outputs from a district they cannot
    see by naming a job instead of an area.

    With no job_id the most recently completed job is used,
    which is what opening the map means by "the analysis".

    Returns None when the area has no completed job at all,
    and the caller then reports no layers rather than
    drawing something.
    """

    statement = select(AnalysisJob).where(
        AnalysisJob.forest_area_id == forest_area_id,
    )

    if job_id is not None:
        statement = statement.where(AnalysisJob.id == job_id)
    else:
        statement = statement.where(
            AnalysisJob.status == AnalysisJobStatus.COMPLETED,
        )

    return db.execute(
        statement.order_by(
            AnalysisJob.completed_at.desc().nullslast()
        ).limit(1)
    ).scalars().first()


# =========================================================
# LAYERS AND BOUNDARY
# =========================================================

@router.get("/{forest_area_id}/layers")
def get_layers(
    forest_area_id: int,
    job_id: int | None = Query(
        default=None,
        description=(
            "Read the outputs of this analysis job. Omitted, "
            "the most recent completed job is used."
        ),
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Describe the forest area and what can be drawn over it.

    Returns the boundary as GeoJSON so the map can zoom to
    it and outline it, the bounds of the imagery overlays,
    and which layers exist for this area.

    A layer marked unavailable has not been produced by the
    pipeline: either no analysis has completed for this
    area, or it did not reach that stage. The interface
    should say so rather than drawing an empty overlay,
    which would look like measured ground with no
    vegetation.
    """

    forest = resolve_forest_area(forest_area_id, db, current_user)

    service = RasterRenderService()

    # Which job's outputs to read. An explicit job_id wins;
    # otherwise the most recent completed job, which is what
    # an officer opening the map means by "the analysis".
    job = resolve_job(forest_area_id, job_id, db)

    effective_job_id = job.id if job is not None else None

    layers = service.available_layers(
        forest_area_id, effective_job_id
    )

    # Bounds come from whichever layer exists; they describe
    # the same tile, so the first available one is enough.
    bounds = None

    for entry in layers:
        if not entry["available"]:
            continue

        rendered = service.render(
            forest_area_id, entry["key"], effective_job_id
        )

        if rendered is not None:
            bounds = rendered[1]
            break

    boundary = None

    if forest.geometry is not None:
        boundary = mapping(to_shape(forest.geometry))

    latest_job = job

    return {
        "forest_area": {
            "id": forest.id,
            "name": forest.name,
            "forest_code": forest.forest_code,
            "area_hectares": forest.area_hectares,
            "boundary": boundary,
        },
        "imagery_bounds": bounds,
        "layers": layers,
        "latest_analysis": (
            None
            if latest_job is None
            else {
                "id": latest_job.id,
                "completed_at": latest_job.completed_at,
                "ndvi_threshold": latest_job.ndvi_threshold,
                "baseline_start": latest_job.baseline_start,
                "baseline_end": latest_job.baseline_end,
                "comparison_start": latest_job.comparison_start,
                "comparison_end": latest_job.comparison_end,
                "cloud_cover_percentage": (
                    latest_job.cloud_cover_percentage
                ),
                "status": latest_job.status.value,
                # NULL output_directory means this job ran
                # before outputs were separated per job, so
                # its rasters are the shared ones and may
                # belong to a later analysis of the same
                # area. The interface says so rather than
                # presenting them as this job's own.
                "is_legacy_storage": (
                    latest_job.output_directory is None
                ),
            }
        ),
    }


# =========================================================
# OVERLAY IMAGE
# =========================================================

@router.get("/{forest_area_id}/overlay/{layer}.png")
def get_overlay(
    forest_area_id: int,
    layer: str,
    job_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_map_imagery_user),
):
    """
    Serve one layer as a coloured PNG.

    Authenticated through get_map_imagery_user, which also
    accepts the token as a query parameter, because a map
    draws an image layer by pointing at a URL and that
    request carries no headers the page can set.

    Invalid pixels are transparent rather than coloured, so
    a cloud-masked gap shows the basemap through it instead
    of reading as bare ground.
    """

    resolve_forest_area(forest_area_id, db, current_user)

    if layer not in LAYERS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Unknown layer '{layer}'. Available: "
                + ", ".join(sorted(LAYERS))
            ),
        )

    job = resolve_job(forest_area_id, job_id, db)

    rendered = RasterRenderService().render(
        forest_area_id,
        layer,
        job.id if job is not None else None,
    )

    if rendered is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "That layer has not been produced for this "
                "forest area. Run an analysis to generate it."
            ),
        )

    png, bounds, metadata = rendered

    return Response(
        content=png,
        media_type="image/png",
        headers={
            # The bounds travel with the image so a client
            # that fetched the PNG directly can still place
            # it without a second request.
            "X-Imagery-Bounds": ",".join(
                str(value) for value in bounds
            ),
            "X-Imagery-CRS": "EPSG:4326",
            "X-Imagery-Layer": metadata["layer"],
            "Cache-Control": "private, max-age=300",
        },
    )


# =========================================================
# HISTOGRAM
# =========================================================

@router.get("/{forest_area_id}/histogram")
def get_histogram(
    forest_area_id: int,
    layer: str = Query(default="ndvi_current"),
    bins: int = Query(default=40, ge=5, le=120),
    job_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Return the distribution of valid pixels in a layer.

    Only pixels carrying a reading are counted. Including
    cloud-masked gaps would pile a spike onto whichever bin
    the no-data sentinel falls in and misrepresent the
    distribution entirely.
    """

    resolve_forest_area(forest_area_id, db, current_user)

    job = resolve_job(forest_area_id, job_id, db)

    result = RasterRenderService().histogram(
        forest_area_id=forest_area_id,
        layer=layer,
        bins=bins,
        job_id=job.id if job is not None else None,
    )

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "That layer has not been produced for this "
                "forest area."
            ),
        )

    return result


# =========================================================
# POINT SAMPLE
# =========================================================

@router.get("/{forest_area_id}/sample")
def sample_point(
    forest_area_id: int,
    longitude: float = Query(ge=-180.0, le=180.0),
    latitude: float = Query(ge=-90.0, le=90.0),
    job_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Read every available layer under one coordinate.

    A null reading means the point fell outside the imagery
    or on a pixel with no valid measurement. It is reported
    as null rather than zero: an officer clicking a cloud
    gap must not be shown a number that looks like bare
    ground.
    """

    resolve_forest_area(forest_area_id, db, current_user)

    job = resolve_job(forest_area_id, job_id, db)

    return RasterRenderService().sample(
        forest_area_id=forest_area_id,
        longitude=longitude,
        latitude=latitude,
        job_id=job.id if job is not None else None,
    )


# =========================================================
# NDVI TREND
# =========================================================

@router.get("/{forest_area_id}/ndvi-trend")
def get_ndvi_trend(
    forest_area_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Mean NDVI at detected locations, by observation date.

    Each completed analysis contributes two points: the mean
    NDVI its detections recorded for the baseline window,
    placed at that window's end, and the mean for the
    comparison window, placed at its end. Both come from
    ndvi_before and ndvi_after stored on the detections, so
    the series is read from the database rather than
    recomputed from imagery.

    READ THIS BEFORE USING THE NUMBERS:

        These are means over DETECTED PATCHES, not over the
        whole forest area. Detected patches are by selection
        the ground that lost vegetation, so the series
        describes the condition of those places and is not a
        measure of the area's overall greenness. A
        whole-area mean exists only for the most recent
        analysis, through the analytics NDVI endpoint, since
        the pipeline keeps only the latest rasters.

        Jobs with no seasonal windows recorded are left out
        rather than placed at their completion date, which
        would put a 2025 observation on a 2026 axis.
    """

    resolve_forest_area(forest_area_id, db, current_user)

    rows = db.execute(
        select(
            AnalysisJob.id,
            AnalysisJob.baseline_end,
            AnalysisJob.comparison_end,
            func.avg(cast(Detection.ndvi_before, Float)),
            func.avg(cast(Detection.ndvi_after, Float)),
            func.count(Detection.id),
        )
        .select_from(AnalysisJob)
        .join(
            Detection,
            Detection.analysis_job_id == AnalysisJob.id,
        )
        .where(
            AnalysisJob.forest_area_id == forest_area_id,
            AnalysisJob.baseline_end.isnot(None),
            AnalysisJob.comparison_end.isnot(None),
        )
        .group_by(
            AnalysisJob.id,
            AnalysisJob.baseline_end,
            AnalysisJob.comparison_end,
        )
        .order_by(AnalysisJob.comparison_end)
    ).all()

    points = []

    for row in rows:
        job_id, baseline_end, comparison_end, before, after, count = row

        points.append(
            {
                "date": baseline_end,
                "mean_ndvi": round(float(before), 4),
                "observation": "baseline",
                "analysis_job_id": int(job_id),
                "detections": int(count),
            }
        )

        points.append(
            {
                "date": comparison_end,
                "mean_ndvi": round(float(after), 4),
                "observation": "comparison",
                "analysis_job_id": int(job_id),
                "detections": int(count),
            }
        )

    points.sort(key=lambda item: item["date"])

    return {
        "forest_area_id": forest_area_id,
        "basis": (
            "Mean NDVI across detected patches, not across "
            "the whole forest area."
        ),
        "points": points,
    }
