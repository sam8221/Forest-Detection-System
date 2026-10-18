"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Analytics Report Service

Purpose:
    Turns the analytics an officer sees on screen into a
    document they can file, print or open in a spreadsheet.

Responsibilities:
    - Gather the requested sections from real records.
    - Render them as PDF, CSV or Excel.
    - State plainly where data is unavailable.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Note:
    Every figure is collected through AnalyticsService and
    RecommendationService, which read stored records and
    rasters. Nothing is computed twice and nothing is
    invented: a report is the same numbers the dashboard
    shows, in a form that can be handed to someone.

    Sections are built only from what the officer may see.
    The collecting services scope every query to their
    jurisdiction, so a report cannot contain a district the
    requester has no access to, whatever filters they ask
    for.

    Where a figure is unavailable the report says so.
    Writing a zero would assert a measurement nobody made,
    and a printed document outlives the screen it was
    copied from.

    PDF styling is reused from ReportService so the three
    report types in the system look like one family.

Version:
    1.0.0
===========================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analysis_job import AnalysisJob
from app.models.detection import Detection
from app.models.district import District
from app.models.enums import AnalysisJobStatus
from app.models.forest_area import ForestArea
from app.models.user import User
from app.services.analytics_service import AnalyticsService
from app.services.recommendation_service import (
    RecommendationService,
)
from app.services.report_service import ReportService


#: Sections a report may contain. The request names the ones
#: wanted; anything not asked for is not collected, so an
#: unwanted section costs no queries.
SECTIONS = (
    "summary",
    "forest_loss",
    "ndvi",
    "detections",
    "districts",
    "alerts",
    "recommendations",
    "history",
)

#: Shown wherever a figure could not be measured, so a
#: reader never meets a blank cell and wonders whether it
#: means zero.
UNAVAILABLE = "Not available"


@dataclass
class ReportRequest:
    """What the officer asked for."""

    sections: list[str]
    start_date: date | None = None
    end_date: date | None = None
    district_id: int | None = None
    forest_area_id: int | None = None
    title: str = "Forest Analytics Report"


@dataclass
class ReportData:
    """Everything collected for a report, before rendering."""

    reference: str
    generated_at: datetime
    request: ReportRequest
    scope_description: str
    summary: dict | None = None
    trend: list[dict] = field(default_factory=list)
    districts: list[dict] = field(default_factory=list)
    detections: list[dict] = field(default_factory=list)
    ndvi: dict | None = None
    ndvi_job: dict | None = None
    alerts: dict | None = None
    recommendations: list[dict] = field(default_factory=list)
    history: list[dict] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)

    def has(self, section: str) -> bool:
        """Whether a section was requested."""

        return section in self.request.sections


class AnalyticsReportService:
    """
    Collects analytics and renders them as a document.
    """

    def __init__(self, db: Session):
        self.db = db
        self.analytics = AnalyticsService(db)
        self.recommendations = RecommendationService(db)
        self.pdf = ReportService()

    # =====================================================
    # COLLECTION
    # =====================================================

    def collect(
        self,
        user: User,
        request: ReportRequest,
    ) -> ReportData:
        """
        Gather the requested sections for one officer.

        Every query is scoped to the officer's jurisdiction
        by the services underneath, so the result can only
        contain ground they are permitted to see.

        Limitations are accumulated as the data is gathered
        rather than written afterwards, so the report states
        the specific reasons its own figures are incomplete.
        """

        generated_at = datetime.now(UTC)

        data = ReportData(
            reference=self._reference(generated_at, user),
            generated_at=generated_at,
            request=request,
            scope_description=self._describe_scope(request, user),
        )

        common = {
            "start_date": request.start_date,
            "end_date": request.end_date,
            "district_id": request.district_id,
            "forest_area_id": request.forest_area_id,
        }

        if data.has("summary") or data.has("forest_loss"):
            data.summary = self.analytics.summary(user, **common)

            if data.summary["unique_loss_hectares"] is None:
                data.limitations.append(
                    "No detection in scope carries a mapped "
                    "outline, so the unique affected area "
                    "could not be measured. Only the "
                    "cumulative total is reported, and it "
                    "counts ground detected twice twice."
                )

            if not data.summary["has_results"]:
                data.limitations.append(
                    "No detections fall within the selected "
                    "filters. This is an absence of results, "
                    "not a finding that no clearing occurred."
                )

        if data.has("forest_loss"):
            data.trend = self.analytics.loss_trend(user, **common)

            if not data.trend:
                data.limitations.append(
                    "No analysis completed within the "
                    "selected period, so no trend could be "
                    "plotted."
                )

        if data.has("districts"):
            data.districts = self.analytics.district_comparison(
                user,
                start_date=request.start_date,
                end_date=request.end_date,
            )

            unobserved = [
                row["district"]
                for row in data.districts
                if not row["observed"]
            ]

            if unobserved:
                data.limitations.append(
                    "No analysis has completed in "
                    + ", ".join(unobserved)
                    + ". Their zero figures mean the ground "
                    "has not been examined, not that no "
                    "clearing occurred there."
                )

        if data.has("detections"):
            data.detections = self._collect_detections(user, request)

        if data.has("ndvi"):
            job = self._latest_job(user, request)

            if job is None:
                data.limitations.append(
                    "No completed analysis was found for the "
                    "selected filters, so no NDVI comparison "
                    "could be included."
                )
            else:
                data.ndvi = self.analytics.ndvi_change(job)
                data.ndvi_job = {
                    "id": job.id,
                    "forest_area_id": job.forest_area_id,
                    "completed_at": job.completed_at,
                }

                if not data.ndvi["rasters_available"]:
                    data.limitations.append(
                        f"The rasters for analysis {job.id} "
                        "are no longer on disk, so its NDVI "
                        "statistics could not be recomputed."
                    )

                elif data.ndvi.get("is_legacy_storage"):
                    data.limitations.append(
                        "The NDVI figures come from storage "
                        "shared by several analyses of the "
                        "same area, which overwrote one "
                        "another. They describe the most "
                        "recent analysis of that area, while "
                        "the dates shown belong to the job "
                        "named."
                    )

        if data.has("alerts") or data.has("recommendations"):
            data.alerts = self._collect_alerts(user, request)

        if data.has("recommendations"):
            data.recommendations = [
                item.as_dict()
                for item in self.recommendations.generate(
                    user,
                    district_id=request.district_id,
                    forest_area_id=request.forest_area_id,
                )
            ]

        if data.has("history"):
            data.history = self._collect_history(user, request)

        return data

    # -----------------------------------------------------
    # COLLECTION HELPERS
    # -----------------------------------------------------

    @staticmethod
    def _reference(moment: datetime, user: User) -> str:
        """
        Build a reference an officer can quote.

        Carries the moment and the requesting account, so two
        reports produced from the same filters at different
        times are distinguishable on paper.
        """

        return (
            "FW-ANL-"
            f"{moment.strftime('%Y%m%d-%H%M%S')}-"
            f"{user.id:04d}"
        )

    def _describe_scope(
        self,
        request: ReportRequest,
        user: User,
    ) -> str:
        """Describe the filters in words, for the cover."""

        parts: list[str] = []

        if request.forest_area_id is not None:
            forest = self.db.get(ForestArea, request.forest_area_id)
            parts.append(
                f"Forest area: {forest.name}"
                if forest
                else f"Forest area {request.forest_area_id}"
            )

        if request.district_id is not None:
            district = self.db.get(District, request.district_id)
            parts.append(
                f"District: {district.name}"
                if district
                else f"District {request.district_id}"
            )

        if not parts:
            parts.append(
                "All forest areas within your jurisdiction: "
                + self.pdf.describe_jurisdiction(user)
            )

        if request.start_date or request.end_date:
            parts.append(
                "Period: "
                f"{request.start_date or 'earliest record'}"
                " to "
                f"{request.end_date or 'latest record'}"
            )
        else:
            parts.append("Period: all records")

        return " · ".join(parts)

    def _permitted(self, user: User, request: ReportRequest):
        """Forest area ids this report may cover."""

        return select(
            self.analytics._permitted_forest_area_ids(
                user,
                district_id=request.district_id,
                forest_area_id=request.forest_area_id,
            ).c.id
        )

    def _collect_detections(
        self,
        user: User,
        request: ReportRequest,
    ) -> list[dict]:
        """Detection rows for the detail table."""

        statement = (
            select(
                Detection.id,
                ForestArea.name,
                District.name,
                Detection.detected_area_hectares,
                Detection.ndvi_before,
                Detection.ndvi_after,
                Detection.status,
                Detection.created_at,
                Detection.analysis_job_id,
                Detection.geometry.isnot(None),
            )
            .select_from(Detection)
            .join(ForestArea, ForestArea.id == Detection.forest_area_id)
            .join(District, District.id == ForestArea.district_id)
            .where(
                Detection.forest_area_id.in_(
                    self._permitted(user, request)
                )
            )
            .order_by(Detection.detected_area_hectares.desc())
        )

        if request.start_date is not None:
            statement = statement.where(
                Detection.created_at >= request.start_date
            )

        if request.end_date is not None:
            statement = statement.where(
                Detection.created_at <= request.end_date
            )

        rows = self.db.execute(statement).all()

        return [
            {
                "id": row[0],
                "forest_area": row[1],
                "district": row[2],
                "area_hectares": (
                    float(row[3]) if row[3] is not None else None
                ),
                "ndvi_before": (
                    float(row[4]) if row[4] is not None else None
                ),
                "ndvi_after": (
                    float(row[5]) if row[5] is not None else None
                ),
                "ndvi_decline": (
                    round(float(row[4]) - float(row[5]), 4)
                    if row[4] is not None and row[5] is not None
                    else None
                ),
                "status": row[6].value if row[6] else None,
                "detected_on": row[7],
                "analysis_job_id": row[8],
                "has_outline": bool(row[9]),
            }
            for row in rows
        ]

    def _collect_alerts(
        self,
        user: User,
        request: ReportRequest,
    ) -> dict:
        """Alert counts, scoped to the officer."""

        from app.repositories.alert_repository import (
            AlertRepository,
        )

        alerts = AlertRepository(self.db).get_all_for_user(user)

        resolved = [one for one in alerts if one.is_resolved]

        durations = [
            (one.resolved_at - one.created_at).total_seconds()
            / 3600.0
            for one in resolved
            if one.resolved_at is not None
            and one.created_at is not None
        ]

        return {
            "total": len(alerts),
            "pending": sum(
                1
                for one in alerts
                if one.status.value == "PENDING"
            ),
            "sent": sum(
                1 for one in alerts if one.status.value == "SENT"
            ),
            "read": sum(
                1 for one in alerts if one.status.value == "READ"
            ),
            "resolved": len(resolved),
            "average_resolution_hours": (
                round(sum(durations) / len(durations), 1)
                if durations
                else None
            ),
        }

    def _latest_job(
        self,
        user: User,
        request: ReportRequest,
    ) -> AnalysisJob | None:
        """Most recent completed analysis within the filters."""

        return self.db.execute(
            select(AnalysisJob)
            .where(
                AnalysisJob.forest_area_id.in_(
                    self._permitted(user, request)
                ),
                AnalysisJob.status == AnalysisJobStatus.COMPLETED,
            )
            .order_by(AnalysisJob.completed_at.desc().nullslast())
            .limit(1)
        ).scalars().first()

    def _collect_history(
        self,
        user: User,
        request: ReportRequest,
    ) -> list[dict]:
        """Analysis jobs, whatever their outcome."""

        rows = self.db.execute(
            select(
                AnalysisJob.id,
                ForestArea.name,
                AnalysisJob.status,
                AnalysisJob.baseline_start,
                AnalysisJob.baseline_end,
                AnalysisJob.comparison_start,
                AnalysisJob.comparison_end,
                AnalysisJob.completed_at,
                AnalysisJob.cloud_cover_percentage,
                AnalysisJob.error_message,
            )
            .select_from(AnalysisJob)
            .join(
                ForestArea,
                ForestArea.id == AnalysisJob.forest_area_id,
            )
            .where(
                AnalysisJob.forest_area_id.in_(
                    self._permitted(user, request)
                )
            )
            .order_by(AnalysisJob.created_at.desc())
        ).all()

        return [
            {
                "id": row[0],
                "forest_area": row[1],
                "status": row[2].value if row[2] else None,
                "baseline_start": row[3],
                "baseline_end": row[4],
                "comparison_start": row[5],
                "comparison_end": row[6],
                "completed_at": row[7],
                "cloud_cover_percentage": (
                    float(row[8]) if row[8] is not None else None
                ),
                "error_message": row[9],
            }
            for row in rows
        ]
