"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Analysis API

Purpose:
    Provides API endpoints for forest analysis.

Workflow:
    1. Create analysis job.
    2. Return job immediately.
    3. Persist the job in PENDING for the analysis queue worker.
    4. Compare previous and newest imagery.
    5. Generate detections and alerts.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia
===========================================================
"""

from __future__ import annotations

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
)

from sqlalchemy.orm import Session

from app.api.deps import (
    get_current_active_user,
    get_forestry_officer,
)
from app.database.session import get_db

from app.models.analysis_job import AnalysisJob
from app.models.enums import AnalysisJobStatus, AnalysisJobType

from app.models.forest_area import ForestArea
from app.models.satellite_image import SatelliteImage
from app.models.user import User
from app.repositories.analysis_repository import (
    AnalysisRepository,
)
from app.repositories.detection_repository import (
    DetectionRepository,
)
from app.repositories.forest_area_repository import (
    ForestAreaRepository,
)

from app.schemas.analysis import (
    SeasonalWindowRequest,
    SelectedImagePairRequest,
)
from app.services.analysis_service import (
    AnalysisOutputStorageError,
    AnalysisService,
    public_analysis_error_message,
)
from app.services.boundary_comparison_service import validate_stored_forest_boundary
from app.services.satellite_image_selection_service import (
    SatelliteImageSelectionService,
)


router = APIRouter(
    prefix="/analysis",
    tags=["Analysis"],
)

def _queue_available(request: Request) -> bool:
    scheduler = getattr(request.app.state, "analysis_scheduler", None)
    return bool(scheduler and scheduler.is_running)


def _active_job_for_area(db: Session, forest_area_id: int) -> AnalysisJob | None:
    return (
        db.query(AnalysisJob)
        .filter(
            AnalysisJob.forest_area_id == forest_area_id,
            AnalysisJob.status.in_(
                [AnalysisJobStatus.PENDING, AnalysisJobStatus.RUNNING]
            ),
        )
        .order_by(AnalysisJob.created_at.desc(), AnalysisJob.id.desc())
        .first()
    )


def _verified_completed_result(job: AnalysisJob, db: Session) -> tuple[bool, str | None]:
    if job.status != AnalysisJobStatus.COMPLETED:
        return False, None
    if job.started_at is None or job.completed_at is None:
        return (
            False,
            "This job is marked completed but has no complete execution timestamps. "
            "Its results are not verified; run a new analysis.",
        )
    try:
        AnalysisService(db).verify_required_outputs(job)
    except (OSError, TypeError, ValueError) as exc:
        return (
            False,
            "The completed job's required outputs could not be verified: "
            + (public_analysis_error_message(str(exc)) or "output validation failed."),
        )
    return True, None


# =========================================================
# RUN ANALYSIS
# =========================================================

@router.post("/run/{forest_id}")
def run_analysis(
    forest_id: int,
    request: Request,
    windows: SeasonalWindowRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_forestry_officer),
):
    """
    Start a forest analysis.

    The request returns immediately after creating
    the analysis job.

    The analysis worker claims the persisted job after the
    request commits, so a process restart cannot discard the
    handoff between the request and its work.

    Requires an authenticated Forestry Officer. Running an
    analysis downloads Sentinel-2 products from Copernicus
    and is recorded against the officer who started it, so
    it must never be reachable anonymously.

    An optional request body may specify the baseline and
    comparison windows. When omitted, equivalent windows one
    year apart are derived automatically.
    """

    # -----------------------------------------------------
    # Find forest area
    # -----------------------------------------------------

    # Scoped to the officer's jurisdiction, so an analysis
    # cannot be started over a forest area the officer does
    # not cover. Reading a detection and commissioning the
    # work that produces one are both restricted by FR-04;
    # an unscoped lookup here would let an officer queue
    # processing for another district and learn the result
    # through the job they submitted.
    forest = ForestAreaRepository(db).get_by_id_for_user(
        forest_area_id=forest_id,
        user=current_user,
    )

    # Absent, inactive and out-of-jurisdiction all answer
    # 404, so the response does not distinguish a forest
    # area that exists elsewhere from one that does not
    # exist at all.
    if forest is None or not forest.is_active:

        raise HTTPException(
            status_code=404,
            detail="Forest area not found.",
        )

    # -----------------------------------------------------
    # Check whether imagery already exists
    # -----------------------------------------------------

    latest_image = None

    if forest.satellite_images:

        latest_image = max(
            forest.satellite_images,
            key=lambda image: (
                image.acquisition_date,
                image.id,
            ),
        )

    # -----------------------------------------------------
    # Create initial analysis job
    # -----------------------------------------------------

    #
    # If an image exists, use it temporarily.
    #
    # The background process will later check Copernicus
    # for a newer image.
    #

    if latest_image is None:

        raise HTTPException(
            status_code=422,
            detail=(
                "No satellite image is registered for "
                "this forest area yet. A Sentinel-2 image "
                "must be acquired before the first analysis."
            ),
        )

    # Serialize submissions for this forest. The duplicate check and job
    # insert happen under one row lock, so two quick clicks cannot enqueue the
    # same work twice.
    db.query(ForestArea.id).filter(ForestArea.id == forest.id).with_for_update().first()

    active_job = _active_job_for_area(db, forest.id)
    if active_job is not None:
        if (
            active_job.previous_satellite_image_id is None
            and active_job.satellite_image_id == latest_image.id
        ):
            return {
                "message": "This analysis is already queued or running.",
                "analysis_job_id": active_job.id,
                "forest_area_id": forest.id,
                "satellite_image_id": active_job.satellite_image_id,
                "status": active_job.status.value,
                "job_type": active_job.job_type.value,
                "duplicate": True,
                "worker_available": _queue_available(request),
            }
        raise HTTPException(
            status_code=409,
            detail=(
                f"Analysis job #{active_job.id} is already active for this forest area. "
                "Wait for it to finish before starting another analysis."
            ),
        )

    service = AnalysisService(db)

    try:

        job = service.create_analysis_job(
            forest_area_id=forest.id,

            satellite_image_id=latest_image.id,

            started_by=current_user.id,

            job_type=AnalysisJobType.MANUAL,

            baseline_start=(
                windows.baseline_start
                if windows is not None
                else None
            ),

            baseline_end=(
                windows.baseline_end
                if windows is not None
                else None
            ),

            comparison_start=(
                windows.comparison_start
                if windows is not None
                else None
            ),

            comparison_end=(
                windows.comparison_end
                if windows is not None
                else None
            ),
        )

    except ValueError as exc:

        # -------------------------------------------------
        # Invalid seasonal windows
        # -------------------------------------------------

        db.rollback()

        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    except Exception as exc:

        db.rollback()

        raise HTTPException(
            status_code=500,
            detail=(
                "Unable to create analysis job: "
                f"{exc}"
            ),
        ) from exc

    # The persistent worker polls analysis_jobs for PENDING rows. The request
    # returns after the database transaction commits; no in-process HTTP task
    # is responsible for keeping the job alive.

    return {
        "message": (
            "Forest analysis has been started."
        ),

        "analysis_job_id": job.id,

        "forest_area_id": forest.id,

        "satellite_image_id": latest_image.id,

        "status": "PENDING",

        "job_type": "MANUAL",

        "worker_available": _queue_available(request),

        "note": (
            "Sentinel-2 acquisition and deforestation analysis are queued for the analysis worker."
        ),
    }


@router.post("/run/{forest_id}/pair")
def run_selected_pair_analysis(
    forest_id: int,
    pair: SelectedImagePairRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_forestry_officer),
):
    """Run an analysis for exactly the two selected local products."""

    forest = ForestAreaRepository(db).get_by_id_for_user(
        forest_area_id=forest_id,
        user=current_user,
    )
    if forest is None or not forest.is_active:
        raise HTTPException(status_code=404, detail="Forest area not found.")

    try:
        boundary = validate_stored_forest_boundary(forest.geometry)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    previous = db.get(SatelliteImage, pair.previous_satellite_image_id)
    recent = db.get(SatelliteImage, pair.recent_satellite_image_id)
    try:
        SatelliteImageSelectionService.validate_explicit_pair(
            previous, recent, forest.id
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    service = AnalysisService(db)
    if (
        service._usable_local_image(previous.id) is None
        or service._usable_local_image(recent.id) is None
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "A selected product is marked downloaded but its archive or extracted "
                "bands are missing from local storage. Reacquire that product before comparing."
            ),
        )

    try:
        service.validate_local_image_inputs(previous)
        service.validate_local_image_inputs(recent)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    db.query(ForestArea.id).filter(ForestArea.id == forest.id).with_for_update().first()

    active_job = _active_job_for_area(db, forest.id)
    if active_job is not None:
        if (
            active_job.previous_satellite_image_id == previous.id
            and active_job.satellite_image_id == recent.id
        ):
            return {
                "message": "This selected pair is already queued or running.",
                "analysis_job_id": active_job.id,
                "forest_area_id": forest.id,
                "previous_satellite_image_id": previous.id,
                "recent_satellite_image_id": recent.id,
                "previous_acquisition_date": previous.acquisition_date,
                "recent_acquisition_date": recent.acquisition_date,
                "status": active_job.status.value,
                "job_type": active_job.job_type.value,
                "duplicate": True,
                "worker_available": _queue_available(request),
            }
        raise HTTPException(
            status_code=409,
            detail=(
                f"Analysis job #{active_job.id} is already active for this forest area. "
                "Wait for it to finish before starting another pair."
            ),
        )

    try:
        job = service.create_analysis_job(
            forest_area_id=forest.id,
            satellite_image_id=recent.id,
            previous_satellite_image_id=previous.id,
            started_by=current_user.id,
            job_type=AnalysisJobType.MANUAL,
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except AnalysisOutputStorageError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {
        "message": "The selected Sentinel-2 pair is queued for analysis.",
        "analysis_job_id": job.id,
        "forest_area_id": forest.id,
        "previous_satellite_image_id": previous.id,
        "recent_satellite_image_id": recent.id,
        "previous_acquisition_date": previous.acquisition_date,
        "recent_acquisition_date": recent.acquisition_date,
        "status": "PENDING",
        "worker_available": _queue_available(request),
    }


# =========================================================
# GET ANALYSIS JOBS
# =========================================================

@router.get("/jobs")
def get_analysis_jobs(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Return the analysis jobs the officer may see.

    Scoped to the officer's jurisdiction in the repository.
    An analysis job records which forest area was examined
    and over which seasonal windows, so the history shows
    where the department has been looking even where nothing
    was found. See FR-04.
    """

    jobs = AnalysisRepository(db).get_all_for_user(
        current_user
    )

    return [
        {
            "id": job.id,

            "forest_area_id": (
                job.forest_area_id
            ),

            "satellite_image_id": (
                job.satellite_image_id
            ),

            "previous_satellite_image_id": (
                job.previous_satellite_image_id
            ),

            "status": (
                job.status.value
            ),

            "job_type": (
                job.job_type.value
            ),

            "started_by": (
                job.started_by
            ),

            "started_at": (
                job.started_at
            ),

            "completed_at": (
                job.completed_at
            ),

            "duration_seconds": (
                job.duration_seconds
            ),

            "cloud_cover_percentage": (
                job.cloud_cover_percentage
            ),

            "vegetation_change_percentage": (
                job.vegetation_change_percentage
            ),

            "ndvi_threshold": (
                job.ndvi_threshold
            ),

            "error_message": (
                public_analysis_error_message(job.error_message)
            ),

            "execution_log": (
                job.execution_log
            ),

            "created_at": (
                job.created_at
            ),

            "updated_at": (
                job.updated_at
            ),

            "worker_available": _queue_available(request),
        }

        for job in jobs
    ]


# =========================================================
# GET SINGLE ANALYSIS JOB
# =========================================================

@router.get("/jobs/{job_id}")
def get_analysis_job(
    job_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Return details of one analysis job the officer may see.

    Raises:
        HTTPException:
            404 when the job does not exist, or was run over
            a forest area outside the officer's
            jurisdiction.

    The two cases return the same 404 on purpose, so that
    requesting identifiers in sequence reveals nothing about
    analyses in other districts. See FR-04.
    """

    job = AnalysisRepository(db).get_by_id_for_user(
        job_id=job_id,
        user=current_user,
    )

    if job is None:

        raise HTTPException(
            status_code=404,
            detail="Analysis job not found.",
        )

    results_verified, results_verification_error = _verified_completed_result(job, db)

    # What this job actually measured, read back from the
    # detections it produced rather than recomputed here.
    #
    # The interface used to read the affected area and the
    # confidence from fields this response never carried, so
    # every completed analysis displayed 0.00 ha at 0.00%
    # confidence however much clearing it had found. Those
    # are measurements, and a measurement that is not
    # reported must not be shown as a value.
    measured = DetectionRepository(db).measured_totals_for_job(job.id)

    return {
        "id": job.id,

        "forest_area_id": (
            job.forest_area_id
        ),

        "satellite_image_id": (
            job.satellite_image_id
        ),

        "previous_satellite_image_id": (
            job.previous_satellite_image_id
        ),

        "status": (
            job.status.value
        ),

        "job_type": (
            job.job_type.value
        ),

        "started_by": (
            job.started_by
        ),

        "started_at": (
            job.started_at
        ),

        "completed_at": (
            job.completed_at
        ),

        "duration_seconds": (
            job.duration_seconds
        ),

        "cloud_cover_percentage": (
            job.cloud_cover_percentage
        ),

        "vegetation_change_percentage": (
            job.vegetation_change_percentage
        ),

        "ndvi_threshold": (
            job.ndvi_threshold
        ),

        "error_message": (
            public_analysis_error_message(job.error_message)
        ),

        # What the run is doing right now. A full analysis
        # downloads two Sentinel-2 products and processes
        # roughly 120 million pixels twice, so it runs for
        # several minutes. Without this the interface can
        # only show RUNNING, which looks identical to a job
        # that has hung.
        "execution_log": (
            job.execution_log
        ),

        "created_at": (
            job.created_at
        ),

        "updated_at": (
            job.updated_at
        ),

        "worker_available": _queue_available(request),

        "results_verified": results_verified,

        "results_verification_error": results_verification_error,

        # detection_count is always a real number, and zero
        # is a valid outcome: a job can complete having found
        # no qualifying clearing.
        #
        # The area and the mean confidence are null in that
        # case rather than 0.0, because "no area was
        # measured" and "an area of zero was measured" are
        # different findings and the interface has to be able
        # to tell them apart.
        "detection_count": measured["detection_count"],

        "detected_area_hectares": measured["detected_area_hectares"],

        "mean_confidence_score": measured["mean_confidence_score"],
    }
