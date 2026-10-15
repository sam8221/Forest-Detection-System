"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Analytics Service

Purpose:
    Derives forest-loss analytics from stored analysis
    results, for the officer dashboard.

Responsibilities:
    - Summarise monitored area, detections and loss.
    - Produce a potential-loss trend over time.
    - Compare potential loss across districts.
    - Report NDVI change statistics for one analysis.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Note:
    Every figure here is derived from rows the detection
    pipeline wrote. Nothing is estimated, interpolated or
    filled in. Where there is no observation the response
    says so rather than returning zero, because an officer
    reads a zero as "nothing was cleared" and an absence as
    "we have not looked".

    All queries are scoped to the signed-in officer's
    jurisdiction through the repositories, so two officers
    looking at the same screen see different totals. This is
    requirement FR-04 and it is applied in the query, not in
    the interface.

    Aggregation happens in the database. Analytics over
    thousands of detections must not pull them into memory
    to add up in Python.

Version:
    1.0.0
===========================================================
"""

from __future__ import annotations

from datetime import date

import numpy as np
import rasterio
from sqlalchemy import Date, Float, cast, false, func, select
from sqlalchemy.orm import Query, Session

from app.core.config import get_settings
from app.core.constants import NDVI_NODATA
from app.models.analysis_job import AnalysisJob
from app.models.detection import Detection
from app.models.district import District
from app.models.enums import AnalysisJobStatus, UserRole
from app.models.forest_area import ForestArea
from app.models.user import User


class AnalyticsService:
    """
    Produces forest-loss analytics from stored results.
    """

    def __init__(
        self,
        db: Session,
    ):
        self.db = db
        self.settings = get_settings()

    # =====================================================
    # JURISDICTION
    # =====================================================

    def _scope_forest_areas(
        self,
        query: Query,
        user: User,
    ) -> Query:
        """
        Restrict a ForestArea query to a jurisdiction.

        Analytics join everything back to a forest area, so
        scoping once here covers detections, jobs and
        districts alike. The rule matches the repositories:
        an administrator is unrestricted, a provincial
        officer sees their province, a district officer sees
        their district, and an officer with no jurisdiction
        assigned matches nothing rather than matching rows
        whose district happens to be unset.
        """

        if user.role == UserRole.ADMIN:
            return query

        query = query.join(
            District,
            District.id == ForestArea.district_id,
        )

        if user.role == UserRole.PROVINCIAL_FORESTRY_OFFICER:

            if user.province_id is None:
                return query.filter(false())

            return query.filter(
                District.province_id == user.province_id,
            )

        if user.role == UserRole.DISTRICT_FORESTRY_OFFICER:

            if user.district_id is None:
                return query.filter(false())

            return query.filter(
                ForestArea.district_id == user.district_id,
            )

        return query.filter(false())

    def _permitted_forest_area_ids(
        self,
        user: User,
        district_id: int | None = None,
        forest_area_id: int | None = None,
    ):
        """
        Return a subquery of forest area ids the user may see.

        Kept as a subquery rather than a list of identifiers
        so the restriction is applied by the database inside
        each aggregate, rather than by first fetching every
        area the officer may see.

        The optional filters narrow that set further. They
        can only ever remove areas, never add one outside
        the jurisdiction, because they are applied on top of
        the scope rather than instead of it.
        """

        query = self._scope_forest_areas(
            self.db.query(ForestArea.id),
            user,
        )

        if district_id is not None:
            query = query.filter(
                ForestArea.district_id == district_id,
            )

        if forest_area_id is not None:
            query = query.filter(
                ForestArea.id == forest_area_id,
            )

        return query.subquery()

    # =====================================================
    # SUMMARY
    # =====================================================

    def summary(
        self,
        user: User,
        start_date: date | None = None,
        end_date: date | None = None,
        district_id: int | None = None,
        forest_area_id: int | None = None,
    ) -> dict:
        """
        Return the headline figures for the dashboard.

        Args:
            user:
                Officer whose jurisdiction applies.
            start_date / end_date:
                Inclusive bounds on the detection date.
            district_id / forest_area_id:
                Optional narrowing within the jurisdiction.

        Returns:
            dict with monitored area, potential loss,
            detection and area counts, and the latest
            analysis date.

        Two different loss figures are reported, and they
        answer different questions.

        cumulative_loss_hectares adds up every detection. A
        place cleared and detected again in a later analysis
        is counted twice, which is what an officer wants when
        asking how much clearing has been reported.

        unique_loss_hectares dissolves the detection outlines
        with ST_Union first, so ground counted twice is
        counted once. That is the honest answer to how much
        distinct land is affected.

        unique_loss_hectares covers only detections that
        carry an outline. Detections recorded before the
        geometry column existed have none and cannot be
        dissolved, so the response reports how many were
        included. Presenting the dissolved figure without
        that count would understate the affected area while
        looking more precise.
        """

        permitted = self._permitted_forest_area_ids(
            user,
            district_id=district_id,
            forest_area_id=forest_area_id,
        )
        permitted_ids = select(permitted.c.id)

        # -------------------------------------------------
        # Monitored area
        #
        # Not date filtered: a forest area is monitored now
        # or it is not, regardless of the window being
        # examined.
        # -------------------------------------------------

        monitored = self.db.query(
            func.count(ForestArea.id),
            func.coalesce(
                func.sum(ForestArea.area_hectares),
                0.0,
            ),
        ).filter(
            ForestArea.id.in_(permitted_ids),
            ForestArea.is_active.is_(True),
        ).one()

        # -------------------------------------------------
        # Detections
        # -------------------------------------------------

        detection_query = self.db.query(Detection).filter(
            Detection.forest_area_id.in_(permitted_ids),
        )

        detection_query = self._apply_detection_dates(
            detection_query,
            start_date,
            end_date,
        )

        totals = detection_query.with_entities(
            func.count(Detection.id),
            func.coalesce(
                func.sum(Detection.detected_area_hectares),
                0.0,
            ),
            func.count(func.distinct(Detection.forest_area_id)),
        ).one()

        # -------------------------------------------------
        # Unique affected ground
        #
        # ST_Union dissolves overlapping outlines so the same
        # ground is not counted twice. Detections are stored
        # in a projected system measured in metres, so the
        # area divides straight to hectares.
        # -------------------------------------------------

        unique_hectares, with_geometry = self._dissolved_area(
            detection_query
        )

        # -------------------------------------------------
        # Latest analysis
        #
        # The date an analysis finished, not the date a
        # detection row was written, because an officer
        # asking "how current is this" means the imagery
        # work rather than the bookkeeping.
        # -------------------------------------------------

        latest_analysis = self.db.query(
            func.max(AnalysisJob.completed_at),
        ).filter(
            AnalysisJob.forest_area_id.in_(permitted_ids),
            AnalysisJob.status == AnalysisJobStatus.COMPLETED,
        ).scalar()

        analysed_areas = self.db.query(
            func.count(func.distinct(AnalysisJob.forest_area_id)),
        ).filter(
            AnalysisJob.forest_area_id.in_(permitted_ids),
            AnalysisJob.status == AnalysisJobStatus.COMPLETED,
        ).scalar()

        return {
            "monitored_forest_areas": int(monitored[0] or 0),
            "monitored_hectares": round(float(monitored[1] or 0.0), 2),
            "total_detections": int(totals[0] or 0),
            "cumulative_loss_hectares": round(float(totals[1] or 0.0), 2),
            "unique_loss_hectares": (
                None if with_geometry == 0
                else round(unique_hectares, 2)
            ),
            "detections_with_outline": int(with_geometry),
            "forest_areas_with_detections": int(totals[2] or 0),
            "forest_areas_analysed": int(analysed_areas or 0),
            "latest_analysis_at": latest_analysis,
            "has_results": int(totals[0] or 0) > 0,
        }

    def _dissolved_area(
        self,
        detection_query: Query,
    ) -> tuple[float, int]:
        """
        Return dissolved affected hectares and the row count.

        Only detections carrying an outline take part. The
        count is returned so the caller can say how much of
        the evidence the dissolved figure rests on.
        """

        row = detection_query.with_entities(
            func.coalesce(
                func.ST_Area(
                    func.ST_Union(Detection.geometry)
                ),
                0.0,
            ),
            func.count(Detection.geometry),
        ).filter(
            Detection.geometry.isnot(None),
        ).one()

        return (float(row[0] or 0.0) / 10_000.0, int(row[1] or 0))

    @staticmethod
    def _apply_detection_dates(
        query: Query,
        start_date: date | None,
        end_date: date | None,
    ) -> Query:
        """Bound a detection query by date, inclusive."""

        if start_date is not None:
            query = query.filter(
                cast(Detection.created_at, Date) >= start_date,
            )

        if end_date is not None:
            query = query.filter(
                cast(Detection.created_at, Date) <= end_date,
            )

        return query

    # =====================================================
    # TREND
    # =====================================================

    def loss_trend(
        self,
        user: User,
        start_date: date | None = None,
        end_date: date | None = None,
        district_id: int | None = None,
        forest_area_id: int | None = None,
    ) -> list[dict]:
        """
        Return potential loss per day, with observed days.

        Returns:
            One entry per day on which an analysis completed
            inside the jurisdiction, carrying the hectares
            detected and the number of detections.

        Why the series is built from analysis days rather
        than from detection days:

            A day with no detections can mean two different
            things. Either an analysis ran and confirmed no
            clearing large enough to report, which is a real
            zero, or no analysis ran at all, which is not a
            measurement. Charting only the days that produced
            detections hides the first case; charting every
            calendar day invents the second.

            So the series carries one point per day an
            analysis completed. observed is true on those
            days, and a day with observed true and zero
            hectares is a genuine "nothing found". Days
            between points are gaps in observation and the
            chart should not join them as though measured.
        """

        permitted = self._permitted_forest_area_ids(
            user,
            district_id=district_id,
            forest_area_id=forest_area_id,
        )
        permitted_ids = select(permitted.c.id)

        job_day = cast(AnalysisJob.completed_at, Date)

        jobs = self.db.query(
            job_day.label("day"),
            func.count(AnalysisJob.id).label("analyses"),
        ).filter(
            AnalysisJob.forest_area_id.in_(permitted_ids),
            AnalysisJob.status == AnalysisJobStatus.COMPLETED,
            AnalysisJob.completed_at.isnot(None),
        )

        if start_date is not None:
            jobs = jobs.filter(job_day >= start_date)

        if end_date is not None:
            jobs = jobs.filter(job_day <= end_date)

        jobs = jobs.group_by(job_day).subquery()

        detection_day = cast(Detection.created_at, Date)

        detections = self.db.query(
            detection_day.label("day"),
            func.count(Detection.id).label("detections"),
            func.coalesce(
                func.sum(
                    cast(Detection.detected_area_hectares, Float)
                ),
                0.0,
            ).label("hectares"),
        ).filter(
            Detection.forest_area_id.in_(permitted_ids),
        )

        if start_date is not None:
            detections = detections.filter(
                detection_day >= start_date
            )

        if end_date is not None:
            detections = detections.filter(
                detection_day <= end_date
            )

        detections = detections.group_by(detection_day).subquery()

        rows = self.db.execute(
            select(
                jobs.c.day,
                jobs.c.analyses,
                func.coalesce(detections.c.detections, 0),
                func.coalesce(detections.c.hectares, 0.0),
            )
            .select_from(
                jobs.outerjoin(
                    detections,
                    detections.c.day == jobs.c.day,
                )
            )
            .order_by(jobs.c.day)
        ).all()

        return [
            {
                "date": row[0],
                "analyses": int(row[1] or 0),
                "detections": int(row[2] or 0),
                "loss_hectares": round(float(row[3] or 0.0), 2),
                "observed": True,
            }
            for row in rows
        ]

    # =====================================================
    # DISTRICT COMPARISON
    # =====================================================

    def district_comparison(
        self,
        user: User,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[dict]:
        """
        Compare potential loss across districts.

        Every district inside the officer's jurisdiction is
        returned, including those with nothing detected, so
        the chart distinguishes a district that was looked at
        and found clear from one that is simply absent.

        observed records whether any analysis has completed
        there. A district with observed false and zero
        hectares has not been examined; reading its bar as
        "no deforestation" would be wrong.
        """

        permitted = self._permitted_forest_area_ids(user)
        permitted_ids = select(permitted.c.id)

        detection_query = self.db.query(Detection).filter(
            Detection.forest_area_id.in_(permitted_ids),
        )

        detection_query = self._apply_detection_dates(
            detection_query,
            start_date,
            end_date,
        )

        totals = detection_query.with_entities(
            ForestArea.district_id.label("district_id"),
            func.count(Detection.id).label("detections"),
            func.coalesce(
                func.sum(
                    cast(Detection.detected_area_hectares, Float)
                ),
                0.0,
            ).label("hectares"),
        ).join(
            ForestArea,
            ForestArea.id == Detection.forest_area_id,
        ).group_by(
            ForestArea.district_id
        ).subquery()

        analysed = self.db.query(
            ForestArea.district_id.label("district_id"),
            func.count(AnalysisJob.id).label("analyses"),
        ).join(
            AnalysisJob,
            AnalysisJob.forest_area_id == ForestArea.id,
        ).filter(
            ForestArea.id.in_(permitted_ids),
            AnalysisJob.status == AnalysisJobStatus.COMPLETED,
        ).group_by(
            ForestArea.district_id
        ).subquery()

        districts = self._scope_districts(user)

        rows = self.db.execute(
            select(
                District.id,
                District.name,
                func.coalesce(totals.c.detections, 0),
                func.coalesce(totals.c.hectares, 0.0),
                func.coalesce(analysed.c.analyses, 0),
            )
            .select_from(District)
            .outerjoin(
                totals,
                totals.c.district_id == District.id,
            )
            .outerjoin(
                analysed,
                analysed.c.district_id == District.id,
            )
            .where(District.id.in_(districts))
            .order_by(District.name)
        ).all()

        return [
            {
                "district_id": int(row[0]),
                "district": row[1],
                "detections": int(row[2] or 0),
                "loss_hectares": round(float(row[3] or 0.0), 2),
                "analyses": int(row[4] or 0),
                "observed": int(row[4] or 0) > 0,
            }
            for row in rows
        ]

    # =====================================================
    # NDVI CHANGE STATISTICS
    # =====================================================

    def ndvi_change(
        self,
        job: AnalysisJob,
    ) -> dict:
        """
        Summarise the vegetation change one analysis found.

        Args:
            job:
                A completed analysis job the caller has
                already confirmed the officer may see.

        Returns:
            dict carrying the two mean NDVI values, their
            difference, the share of measurable pixels that
            declined, the area that declined past the job's
            threshold, and the observation dates. Values are
            None where the rasters for the job are no longer
            on disk.

        The figures come from the cloud-masked NDVI rasters
        the pipeline wrote, so cloud, shadow and no-data
        pixels have already been excluded by
        CloudMaskService. Only pixels measurable on BOTH
        dates are compared, because a pixel clouded on one
        date has no change to report and counting it would
        pull the mean toward whichever date saw ground.

        What this is not:

            A decline in NDVI is a decline in vegetation
            index, not a finding of deforestation. Harvest,
            fire, drought, seasonal leaf fall and cultivation
            all reduce it. The share reported here is the
            share of ground that lost vegetation index
            between two observations, and the officer decides
            what explains it. This is why the response
            reports declined area separately from the
            detections, which additionally had to survive the
            persistence check and the half-hectare minimum.

        LIMITATION, and it matters when reading an old job:

            The pipeline writes its rasters under the forest
            area, not under the job, at
            storage/satellite_images/<forest_area_id>/...
            Each run overwrites the previous one. So these
            figures describe the MOST RECENT analysis of that
            forest area, and asking for an older job returns
            the newer rasters rather than the ones that job
            produced.

            The window dates returned alongside come from the
            job itself and are correct for it, so an old job
            can present recent rasters under its own dates.
            Treat the statistics as current for the area
            rather than historical for the job until the
            pipeline writes per-job directories.
        """

        directory = (
            self.settings.satellite_image_storage_path
            / str(job.forest_area_id)
        )

        previous_path = (
            directory
            / "processing_previous"
            / "masked_ndvi"
            / "ndvi_masked.tif"
        )

        latest_path = (
            directory
            / "processing"
            / "masked_ndvi"
            / "ndvi_masked.tif"
        )

        windows = {
            "baseline_start": job.baseline_start,
            "baseline_end": job.baseline_end,
            "comparison_start": job.comparison_start,
            "comparison_end": job.comparison_end,
            "completed_at": job.completed_at,
            "ndvi_threshold": job.ndvi_threshold,
            "cloud_cover_percentage": job.cloud_cover_percentage,
        }

        if not previous_path.exists() or not latest_path.exists():
            return {
                **windows,
                "rasters_available": False,
                "mean_ndvi_before": None,
                "mean_ndvi_after": None,
                "mean_ndvi_difference": None,
                "declined_pixel_percentage": None,
                "declined_hectares": None,
                "measurable_pixels": None,
            }

        with rasterio.open(previous_path) as previous_src:
            previous = previous_src.read(1)
            transform = previous_src.transform

        with rasterio.open(latest_path) as latest_src:
            latest = latest_src.read(1)

            if latest.shape != previous.shape:
                raise ValueError(
                    "The two NDVI rasters cover different "
                    f"pixel grids: {previous.shape} against "
                    f"{latest.shape}. They cannot be compared."
                )

        measurable = (
            np.isfinite(previous)
            & np.isfinite(latest)
            & (previous != NDVI_NODATA)
            & (latest != NDVI_NODATA)
        )

        measurable_pixels = int(np.count_nonzero(measurable))

        if measurable_pixels == 0:
            return {
                **windows,
                "rasters_available": True,
                "mean_ndvi_before": None,
                "mean_ndvi_after": None,
                "mean_ndvi_difference": None,
                "declined_pixel_percentage": None,
                "declined_hectares": None,
                "measurable_pixels": 0,
            }

        before = float(previous[measurable].mean())
        after = float(latest[measurable].mean())

        # Decline is previous minus latest, so a positive
        # value means vegetation was lost. This is the sign
        # convention flag_change expects and the one the
        # pipeline uses.
        decline = previous[measurable] - latest[measurable]

        declined = decline > 0

        threshold = float(
            job.ndvi_threshold
            or self.settings.ndvi_threshold
        )

        past_threshold = int(
            np.count_nonzero(decline >= threshold)
        )

        pixel_area_m2 = abs(transform.a) * abs(transform.e)

        return {
            **windows,
            "rasters_available": True,
            "mean_ndvi_before": round(before, 4),
            "mean_ndvi_after": round(after, 4),
            "mean_ndvi_difference": round(after - before, 4),
            "declined_pixel_percentage": round(
                100.0
                * int(np.count_nonzero(declined))
                / measurable_pixels,
                2,
            ),
            "declined_hectares": round(
                past_threshold * pixel_area_m2 / 10_000.0,
                4,
            ),
            "measurable_pixels": measurable_pixels,
        }

    def _scope_districts(self, user: User):
        """Return a select of district ids the user may see."""

        query = self.db.query(District.id)

        if user.role == UserRole.ADMIN:
            return query.subquery().select()

        if user.role == UserRole.PROVINCIAL_FORESTRY_OFFICER:

            if user.province_id is None:
                return query.filter(false()).subquery().select()

            return query.filter(
                District.province_id == user.province_id,
            ).subquery().select()

        if user.role == UserRole.DISTRICT_FORESTRY_OFFICER:

            if user.district_id is None:
                return query.filter(false()).subquery().select()

            return query.filter(
                District.id == user.district_id,
            ).subquery().select()

        return query.filter(false()).subquery().select()
