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
    3. Run Sentinel-2 acquisition and analysis in background.
    4. Compare previous and newest imagery.
    5. Generate detections and alerts.

Author:
    Samuel Bikiloni

Project:
    Intelligent Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia
===========================================================
"""

from __future__ import annotations

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
)

from sqlalchemy.orm import Session

from app.database.session import get_db

from app.models.analysis_job import AnalysisJob
from app.models.enums import AnalysisJobType

from app.models.forest_area import ForestArea

from app.services.analysis_service import AnalysisService


router = APIRouter(
    prefix="/analysis",
    tags=["Analysis"],
)


# =========================================================
# BACKGROUND ANALYSIS
# =========================================================

def run_analysis_background(
    job_id: int,
) -> None:
    """
    Execute the long-running analysis in the background.

    A new database session is created because the original
    request session must not be reused inside a background
    task.
    """

    from app.database.session import SessionLocal

    db = SessionLocal()

    try:

        # -------------------------------------------------
        # Find job
        # -------------------------------------------------

        job = (
            db.query(AnalysisJob)
            .filter(
                AnalysisJob.id == job_id,
            )
            .first()
        )

        if job is None:
            return

        # -------------------------------------------------
        # Execute analysis
        # -------------------------------------------------

        service = AnalysisService(db)

        service.execute(job)

    except Exception as exc:

        # -------------------------------------------------
        # Mark background job as failed
        # -------------------------------------------------

        db.rollback()

        try:

            job = (
                db.query(AnalysisJob)
                .filter(
                    AnalysisJob.id == job_id,
                )
                .first()
            )

            if job is not None:

                service = AnalysisService(db)

                service.fail_analysis(
                    job=job,
                    error_message=str(exc),
                )

        except Exception:

            db.rollback()

    finally:

        db.close()


# =========================================================
# RUN ANALYSIS
# =========================================================

@router.post("/run/{forest_id}")
def run_analysis(
    forest_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Start a forest analysis.

    The request returns immediately after creating
    the analysis job.

    The actual Sentinel-2 acquisition and deforestation
    analysis runs in the background.
    """

    # -----------------------------------------------------
    # Find forest area
    # -----------------------------------------------------

    forest = (
        db.query(ForestArea)
        .filter(
            ForestArea.id == forest_id,
            ForestArea.is_active.is_(True),
        )
        .first()
    )

    if forest is None:

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

    service = AnalysisService(db)

    try:

        job = service.create_analysis_job(
            forest_area_id=forest.id,

            satellite_image_id=latest_image.id,

            started_by=None,

            job_type=AnalysisJobType.AUTOMATIC,

        )

    except Exception as exc:

        db.rollback()

        raise HTTPException(
            status_code=500,
            detail=(
                "Unable to create analysis job: "
                f"{exc}"
            ),
        ) from exc

    # -----------------------------------------------------
    # Queue background processing
    # -----------------------------------------------------

    background_tasks.add_task(
        run_analysis_background,
        job.id,
    )

    # -----------------------------------------------------
    # Return immediately
    # -----------------------------------------------------

    return {
        "message": (
            "Forest analysis has been started."
        ),

        "analysis_job_id": job.id,

        "forest_area_id": forest.id,

        "satellite_image_id": latest_image.id,

        "status": "PENDING",

        "job_type": "AUTOMATIC",

        "note": (
            "Sentinel-2 acquisition and deforestation "
            "analysis are running in the background."
        ),
    }


# =========================================================
# GET ANALYSIS JOBS
# =========================================================

@router.get("/jobs")
def get_analysis_jobs(
    db: Session = Depends(get_db),
):
    """
    Return all analysis jobs.
    """

    jobs = (
        db.query(AnalysisJob)
        .order_by(
            AnalysisJob.created_at.desc(),
        )
        .all()
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
                job.error_message
            ),

            "created_at": (
                job.created_at
            ),

            "updated_at": (
                job.updated_at
            ),
        }

        for job in jobs
    ]


# =========================================================
# GET SINGLE ANALYSIS JOB
# =========================================================

@router.get("/jobs/{job_id}")
def get_analysis_job(
    job_id: int,
    db: Session = Depends(get_db),
):
    """
    Return details of one analysis job.
    """

    job = (
        db.query(AnalysisJob)
        .filter(
            AnalysisJob.id == job_id,
        )
        .first()
    )

    if job is None:

        raise HTTPException(
            status_code=404,
            detail="Analysis job not found.",
        )

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
            job.error_message
        ),

        "created_at": (
            job.created_at
        ),

        "updated_at": (
            job.updated_at
        ),
    }