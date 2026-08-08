"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Analysis Repository

Purpose:
    Provides database operations for analysis jobs.

Responsibilities:
    - Create analysis jobs.
    - Retrieve analysis jobs.
    - Update analysis status.
    - Retrieve latest analysis.
    - Delete analysis jobs.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Version:
    1.0.0
===========================================================
"""

from sqlalchemy.orm import Session

from app.models.analysis_job import AnalysisJob


class AnalysisRepository:
    """
    Handles database operations for analysis jobs.
    """

    def __init__(
        self,
        db: Session,
    ):
        self.db = db

    # ---------------------------------------------------------
    # Create
    # ---------------------------------------------------------
    def create(
        self,
        job: AnalysisJob,
    ) -> AnalysisJob:
        """
        Save a new analysis job.
        """

        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)

        return job

    # ---------------------------------------------------------
    # Get by ID
    # ---------------------------------------------------------
    def get_by_id(
        self,
        job_id: int,
    ) -> AnalysisJob | None:
        """
        Retrieve an analysis job by ID.
        """

        return (
            self.db.query(AnalysisJob)
            .filter(
                AnalysisJob.id == job_id,
            )
            .first()
        )

    # ---------------------------------------------------------
    # Get All
    # ---------------------------------------------------------
    def get_all(
        self,
    ) -> list[AnalysisJob]:
        """
        Retrieve all analysis jobs.
        """

        return (
            self.db.query(AnalysisJob)
            .order_by(
                AnalysisJob.created_at.desc(),
            )
            .all()
        )

    # ---------------------------------------------------------
    # Get by Forest Area
    # ---------------------------------------------------------
    def get_by_forest_area(
        self,
        forest_area_id: int,
    ) -> list[AnalysisJob]:
        """
        Retrieve analysis jobs for a forest area.
        """

        return (
            self.db.query(AnalysisJob)
            .filter(
                AnalysisJob.forest_area_id == forest_area_id,
            )
            .order_by(
                AnalysisJob.created_at.desc(),
            )
            .all()
        )

    # ---------------------------------------------------------
    # Get Latest Analysis
    # ---------------------------------------------------------
    def get_latest(
        self,
        forest_area_id: int,
    ) -> AnalysisJob | None:
        """
        Retrieve the latest analysis job.
        """

        return (
            self.db.query(AnalysisJob)
            .filter(
                AnalysisJob.forest_area_id == forest_area_id,
            )
            .order_by(
                AnalysisJob.created_at.desc(),
            )
            .first()
        )

    # ---------------------------------------------------------
    # Update
    # ---------------------------------------------------------
    def update(
        self,
        job: AnalysisJob,
    ) -> AnalysisJob:
        """
        Update an analysis job.
        """

        self.db.commit()
        self.db.refresh(job)

        return job

    # ---------------------------------------------------------
    # Delete
    # ---------------------------------------------------------
    def delete(
        self,
        job: AnalysisJob,
    ) -> None:
        """
        Permanently delete an analysis job.
        """

        self.db.delete(job)
        self.db.commit()