"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Analysis API

Purpose:
    Provides API endpoints for forest analysis.

Responsibilities:
    - Start analysis.
    - View analysis jobs.
    - View analysis details.

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
@router.post("/run/{forest_id}")
def run_analysis(
    forest_id: int,
    db: Session = Depends(get_db),
):
    """
    Start analysis for a forest area.
    """

    forest = (
        db.query(ForestArea)
        .filter(
            ForestArea.id == forest_id,
        )
        .first()
    )

    if forest is None:
        raise HTTPException(
            status_code=404,
            detail="Forest area not found.",
        )

    latest_image = (
        forest.satellite_images[-1]
        if forest.satellite_images
        else None
    )

    if latest_image is None:
        raise HTTPException(
            status_code=404,
            detail="No satellite image available.",
        )

    service = AnalysisService(db)

    job = service.create_analysis_job(
        forest_area_id=forest.id,
        satellite_image_id=latest_image.id,
        started_by=None,
        job_type=AnalysisJobType.MANUAL,
    )

    service.execute(job)

    return {
        "message": "Analysis completed successfully.",
        "analysis_job_id": job.id,
    }
@router.get("/jobs")
def get_analysis_jobs(
    db: Session = Depends(get_db),
):
    """
    Return all analysis jobs ordered by newest first.
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
            "forest_area_id": job.forest_area_id,
            "satellite_image_id": job.satellite_image_id,
            "status": job.status.value,
            "job_type": job.job_type.value,
            "started_at": job.started_at,
            "completed_at": job.completed_at,
            "duration_seconds": job.duration_seconds,
            "created_at": job.created_at,
        }
        for job in jobs
    ]
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
        "forest_area_id": job.forest_area_id,
        "satellite_image_id": job.satellite_image_id,
        "status": job.status.value,
        "job_type": job.job_type.value,
        "started_by": job.started_by,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
        "duration_seconds": job.duration_seconds,
        "cloud_cover_percentage": job.cloud_cover_percentage,
        "vegetation_change_percentage": job.vegetation_change_percentage,
        "ndvi_threshold": job.ndvi_threshold,
        "error_message": job.error_message,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }