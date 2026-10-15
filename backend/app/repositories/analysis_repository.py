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
    - Restrict results to an officer's jurisdiction.
    - Delete analysis jobs.

Note:
    Methods whose name ends in _for_user apply jurisdiction
    scoping (requirement FR-04) and are what the API layer
    calls. The unscoped methods remain for system-level
    work, such as the scheduled runner picking up queued
    jobs, which must consider every job regardless of who
    submitted it.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Version:
    1.0.0
===========================================================
"""

from sqlalchemy import false
from sqlalchemy.orm import Query, Session

from app.models.analysis_job import AnalysisJob
from app.models.district import District
from app.models.enums import UserRole
from app.models.forest_area import ForestArea
from app.models.user import User


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
    # Jurisdiction Scoping
    # ---------------------------------------------------------
    def scope_to_jurisdiction(
        self,
        query: Query,
        user: User,
    ) -> Query:
        """
        Restrict an analysis job query to a jurisdiction.

        Args:
            query:
                Query selecting AnalysisJob rows.

            user:
                Officer whose jurisdiction applies.

        Returns:
            The query with the jurisdiction filter applied.

        An analysis job is run over a forest area, which
        belongs to a district, which belongs to a province,
        so scoping joins through both.

        This is the enforcement point for requirement FR-04.
        An analysis job records which forest area was
        examined, over which seasonal windows, and what it
        found, so the history is as disclosing as the
        detections themselves: it shows where the department
        has been looking even where nothing was found.

        An officer with no jurisdiction assigned matches
        nothing. That case is rejected explicitly rather
        than left to a NULL comparison: SQLAlchemy renders
        `column == None` as `IS NULL`, which would match
        rows whose district is unset instead of matching
        none.
        """

        # -----------------------------------------------------
        # Administrators are unrestricted
        # -----------------------------------------------------

        if user.role == UserRole.ADMIN:
            return query

        query = (
            query
            .join(
                ForestArea,
                ForestArea.id
                == AnalysisJob.forest_area_id,
            )
            .join(
                District,
                District.id
                == ForestArea.district_id,
            )
        )

        # -----------------------------------------------------
        # Provincial officers: every district in the province
        # -----------------------------------------------------

        if user.role == UserRole.PROVINCIAL_FORESTRY_OFFICER:

            if user.province_id is None:
                return query.filter(false())

            return query.filter(
                District.province_id
                == user.province_id,
            )

        # -----------------------------------------------------
        # District officers: their district only
        # -----------------------------------------------------

        if user.role == UserRole.DISTRICT_FORESTRY_OFFICER:

            if user.district_id is None:
                return query.filter(false())

            return query.filter(
                ForestArea.district_id
                == user.district_id,
            )

        # -----------------------------------------------------
        # Unknown role: return nothing
        # -----------------------------------------------------

        return query.filter(false())

    # ---------------------------------------------------------
    # Get All within Jurisdiction
    # ---------------------------------------------------------
    def get_all_for_user(
        self,
        user: User,
    ) -> list[AnalysisJob]:
        """
        Retrieve all analysis jobs the user may see.
        """

        query = self.db.query(AnalysisJob)

        return (
            self.scope_to_jurisdiction(query, user)
            .order_by(
                AnalysisJob.created_at.desc(),
            )
            .all()
        )

    # ---------------------------------------------------------
    # Get by ID within Jurisdiction
    # ---------------------------------------------------------
    def get_by_id_for_user(
        self,
        job_id: int,
        user: User,
    ) -> AnalysisJob | None:
        """
        Retrieve an analysis job only if the user may see it.

        Returns None when the job does not exist OR lies
        outside the user's jurisdiction. The two cases are
        deliberately indistinguishable to the caller, so
        that probing for identifiers reveals nothing about
        analyses in other districts.
        """

        query = self.db.query(AnalysisJob).filter(
            AnalysisJob.id == job_id,
        )

        return (
            self.scope_to_jurisdiction(query, user)
            .first()
        )

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