"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Recommendation Service

Purpose:
    Turns stored analysis results into advisory messages
    for Forestry Officers.

Responsibilities:
    - Apply documented rules to real records.
    - Name the location, finding and suggested action.
    - Assign a priority.
    - Leave the finding itself unchanged.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

What a recommendation is, and is not:

    A recommendation is advice about what an officer might
    do next. It is not a finding, and it is not evidence.
    Nothing here writes to a detection, an alert or an
    analysis job: the service reads, and returns advice the
    officer is free to ignore.

    No rule concludes that deforestation has occurred, and
    none concludes that clearing was illegal. NDVI falls for
    harvest, fire, drought, seasonal leaf loss and
    cultivation as well as for felling, and this system
    measures none of the things that would tell them apart.
    Every message is phrased as something to check.

    The rules are plain thresholds held in one place and
    stated in the response, so an officer can see why a
    recommendation appeared and a reader of the dissertation
    can reproduce it. There is no model and no external
    service: the same records always produce the same
    advice.

Version:
    1.0.0
===========================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import Float, cast, func, select
from sqlalchemy.orm import Session

from app.models.analysis_job import AnalysisJob
from app.models.detection import Detection
from app.models.district import District
from app.models.enums import (
    AnalysisJobStatus,
    DetectionStatus,
    PriorityLevel,
)
from app.models.forest_area import ForestArea
from app.models.user import User
from app.services.analytics_service import AnalyticsService


# =========================================================
# RULE THRESHOLDS
#
# Every number the rules use, in one place. They are stated
# in each recommendation so the reason is visible to the
# officer reading it rather than buried in code.
# =========================================================

@dataclass(frozen=True)
class RecommendationRules:
    """Thresholds governing when advice is offered."""

    # A single clearing at or above this size is worth a
    # visit before the picture changes. Five hectares is ten
    # times the half-hectare minimum the Forests Act sets
    # for a forest, so a clearing this size is substantial
    # rather than marginal.
    field_verification_hectares: float = 5.0

    # Separate detections within this distance of each other
    # are treated as the same locality for the purpose of
    # noticing repetition.
    repeat_locality_metres: float = 500.0

    # How many detections in one locality before repetition
    # is worth remarking on.
    repeat_detection_count: int = 2

    # NDVI decline at or above this is a substantial drop
    # and worth explaining before it is called anything.
    substantial_ndvi_decline: float = 0.40

    # Cloud cover above this leaves too little clear ground
    # for a confident comparison.
    cloud_cover_percentage: float = 30.0

    # An analysis older than this is no longer a current
    # assessment.
    stale_analysis_days: int = 90

    # A monitored area with no completed analysis in this
    # long has no current observation at all.
    no_imagery_days: int = 120

    def as_dict(self) -> dict:
        """Return the thresholds for display in responses."""

        return {
            "field_verification_hectares": (
                self.field_verification_hectares
            ),
            "repeat_locality_metres": self.repeat_locality_metres,
            "repeat_detection_count": self.repeat_detection_count,
            "substantial_ndvi_decline": (
                self.substantial_ndvi_decline
            ),
            "cloud_cover_percentage": self.cloud_cover_percentage,
            "stale_analysis_days": self.stale_analysis_days,
            "no_imagery_days": self.no_imagery_days,
        }


@dataclass
class Recommendation:
    """One piece of advice about one place."""

    rule: str
    priority: PriorityLevel
    finding: str
    action: str
    forest_area_id: int | None = None
    forest_area: str | None = None
    district: str | None = None
    detection_id: int | None = None
    analysis_job_id: int | None = None
    created_at: datetime = field(
        default_factory=lambda: datetime.now(UTC)
    )

    def as_dict(self) -> dict:
        """Return the recommendation as a response body."""

        return {
            "rule": self.rule,
            "priority": self.priority.value,
            "finding": self.finding,
            "action": self.action,
            "forest_area_id": self.forest_area_id,
            "forest_area": self.forest_area,
            "district": self.district,
            "detection_id": self.detection_id,
            "analysis_job_id": self.analysis_job_id,
            "created_at": self.created_at,
        }


class RecommendationService:
    """
    Generates advisory messages from stored results.
    """

    def __init__(
        self,
        db: Session,
        rules: RecommendationRules | None = None,
    ):
        self.db = db
        self.rules = rules or RecommendationRules()
        self.analytics = AnalyticsService(db)

    # =====================================================
    # ENTRY POINT
    # =====================================================

    def generate(
        self,
        user: User,
        district_id: int | None = None,
        forest_area_id: int | None = None,
    ) -> list[Recommendation]:
        """
        Return advice for everything the officer may see.

        Ordered most urgent first, so the top of the list is
        the place to start.
        """

        permitted = self.analytics._permitted_forest_area_ids(
            user,
            district_id=district_id,
            forest_area_id=forest_area_id,
        )
        permitted_ids = select(permitted.c.id)

        recommendations: list[Recommendation] = []

        recommendations += self._large_clearings(permitted_ids)
        recommendations += self._repeated_localities(permitted_ids)
        recommendations += self._substantial_decline(permitted_ids)
        recommendations += self._cloudy_analyses(permitted_ids)
        recommendations += self._stale_analyses(permitted_ids)
        recommendations += self._areas_without_imagery(permitted_ids)

        order = {
            PriorityLevel.CRITICAL: 0,
            PriorityLevel.HIGH: 1,
            PriorityLevel.MEDIUM: 2,
            PriorityLevel.LOW: 3,
        }

        recommendations.sort(
            key=lambda item: order[item.priority]
        )

        return recommendations

    # =====================================================
    # RULE 1: SIGNIFICANT POTENTIAL VEGETATION LOSS
    # =====================================================

    def _large_clearings(self, permitted_ids) -> list[Recommendation]:
        """
        A substantial clearing is worth visiting.

        Only detections still awaiting review are offered.
        One already verified or rejected has had its officer
        decision, and repeating the advice would be noise.
        """

        rows = self.db.execute(
            select(
                Detection.id,
                Detection.detected_area_hectares,
                ForestArea.id,
                ForestArea.name,
                District.name,
            )
            .select_from(Detection)
            .join(ForestArea, ForestArea.id == Detection.forest_area_id)
            .join(District, District.id == ForestArea.district_id)
            .where(
                Detection.forest_area_id.in_(permitted_ids),
                Detection.status == DetectionStatus.PENDING,
                cast(Detection.detected_area_hectares, Float)
                >= self.rules.field_verification_hectares,
            )
            .order_by(
                cast(
                    Detection.detected_area_hectares, Float
                ).desc()
            )
        ).all()

        return [
            Recommendation(
                rule="SIGNIFICANT_POTENTIAL_LOSS",
                priority=PriorityLevel.HIGH,
                finding=(
                    f"A clearing of {float(row[1]):.2f} hectares "
                    f"is awaiting review in {row[3]}. That is at "
                    f"or above the "
                    f"{self.rules.field_verification_hectares} "
                    "hectare threshold for prioritising a visit."
                ),
                action=(
                    "Prioritise this location for field "
                    "verification. The imagery shows vegetation "
                    "loss; only a visit can establish what caused "
                    "it."
                ),
                forest_area_id=int(row[2]),
                forest_area=row[3],
                district=row[4],
                detection_id=int(row[0]),
            )
            for row in rows
        ]

    # =====================================================
    # RULE 2: REPEATED DETECTIONS IN ONE LOCALITY
    # =====================================================

    def _repeated_localities(
        self, permitted_ids
    ) -> list[Recommendation]:
        """
        Several detections close together over time.

        Clusters are formed with ST_ClusterDBSCAN over the
        detection outlines, so "the same locality" means
        within a stated distance on the ground rather than
        merely inside the same forest area, which can be
        thousands of hectares.

        Detections without an outline cannot be clustered and
        are skipped rather than guessed at.
        """

        clustered = (
            select(
                Detection.id.label("detection_id"),
                Detection.forest_area_id.label("forest_area_id"),
                func.ST_ClusterDBSCAN(
                    Detection.geometry,
                    self.rules.repeat_locality_metres,
                    self.rules.repeat_detection_count,
                )
                .over()
                .label("cluster"),
            )
            .where(
                Detection.forest_area_id.in_(permitted_ids),
                Detection.geometry.isnot(None),
            )
            .subquery()
        )

        rows = self.db.execute(
            select(
                clustered.c.forest_area_id,
                ForestArea.name,
                District.name,
                func.count(clustered.c.detection_id),
            )
            .select_from(clustered)
            .join(
                ForestArea,
                ForestArea.id == clustered.c.forest_area_id,
            )
            .join(District, District.id == ForestArea.district_id)
            .where(clustered.c.cluster.isnot(None))
            .group_by(
                clustered.c.forest_area_id,
                clustered.c.cluster,
                ForestArea.name,
                District.name,
            )
            .having(
                func.count(clustered.c.detection_id)
                >= self.rules.repeat_detection_count
            )
        ).all()

        return [
            Recommendation(
                rule="REPEATED_DETECTIONS",
                priority=PriorityLevel.MEDIUM,
                finding=(
                    f"{int(row[3])} separate detections lie within "
                    f"{self.rules.repeat_locality_metres:.0f} m of "
                    f"one another in {row[1]}. Clearing in one "
                    "locality across more than one observation may "
                    "indicate activity that is continuing."
                ),
                action=(
                    "Review the earlier observations for this "
                    "locality together, and consider monitoring it "
                    "more frequently than the rest of the area."
                ),
                forest_area_id=int(row[0]),
                forest_area=row[1],
                district=row[2],
            )
            for row in rows
        ]

    # =====================================================
    # RULE 3: SUBSTANTIAL NDVI DECREASE
    # =====================================================

    def _substantial_decline(
        self, permitted_ids
    ) -> list[Recommendation]:
        """
        A large drop in vegetation index needs explaining.

        Deliberately phrased as a question rather than a
        conclusion. A drop of this size is consistent with
        felling and equally consistent with fire, harvest or
        a failed season.
        """

        decline = Detection.ndvi_before - Detection.ndvi_after

        rows = self.db.execute(
            select(
                Detection.id,
                Detection.ndvi_before,
                Detection.ndvi_after,
                ForestArea.id,
                ForestArea.name,
                District.name,
            )
            .select_from(Detection)
            .join(ForestArea, ForestArea.id == Detection.forest_area_id)
            .join(District, District.id == ForestArea.district_id)
            .where(
                Detection.forest_area_id.in_(permitted_ids),
                Detection.ndvi_before.isnot(None),
                Detection.ndvi_after.isnot(None),
                decline >= self.rules.substantial_ndvi_decline,
            )
            .order_by(decline.desc())
        ).all()

        return [
            Recommendation(
                rule="SUBSTANTIAL_NDVI_DECREASE",
                priority=PriorityLevel.MEDIUM,
                finding=(
                    f"NDVI fell from {float(row[1]):.3f} to "
                    f"{float(row[2]):.3f}, a drop of "
                    f"{float(row[1]) - float(row[2]):.3f}, in "
                    f"{row[4]}."
                ),
                action=(
                    "Investigate what caused this change before "
                    "classifying it. Fire, harvest, drought and "
                    "cultivation all lower the vegetation index, "
                    "and the imagery alone does not distinguish "
                    "them from felling."
                ),
                forest_area_id=int(row[3]),
                forest_area=row[4],
                district=row[5],
                detection_id=int(row[0]),
            )
            for row in rows
        ]

    # =====================================================
    # RULE 4: EXCESSIVE CLOUD COVER
    # =====================================================

    def _cloudy_analyses(self, permitted_ids) -> list[Recommendation]:
        """
        Cloud leaves too little ground visible to trust.
        """

        rows = self.db.execute(
            select(
                AnalysisJob.id,
                AnalysisJob.cloud_cover_percentage,
                ForestArea.id,
                ForestArea.name,
                District.name,
            )
            .select_from(AnalysisJob)
            .join(
                ForestArea,
                ForestArea.id == AnalysisJob.forest_area_id,
            )
            .join(District, District.id == ForestArea.district_id)
            .where(
                AnalysisJob.forest_area_id.in_(permitted_ids),
                AnalysisJob.status == AnalysisJobStatus.COMPLETED,
                AnalysisJob.cloud_cover_percentage.isnot(None),
                cast(AnalysisJob.cloud_cover_percentage, Float)
                > self.rules.cloud_cover_percentage,
            )
            .order_by(
                cast(
                    AnalysisJob.cloud_cover_percentage, Float
                ).desc()
            )
        ).all()

        return [
            Recommendation(
                rule="EXCESSIVE_CLOUD_COVER",
                priority=PriorityLevel.LOW,
                finding=(
                    f"The imagery analysed for {row[3]} carried "
                    f"{float(row[1]):.1f}% cloud, above the "
                    f"{self.rules.cloud_cover_percentage:.0f}% "
                    "level at which too little ground remains "
                    "measurable for a confident comparison."
                ),
                action=(
                    "Obtain another observation with clearer "
                    "conditions before drawing conclusions from "
                    "this analysis."
                ),
                forest_area_id=int(row[2]),
                forest_area=row[3],
                district=row[4],
                analysis_job_id=int(row[0]),
            )
            for row in rows
        ]

    # =====================================================
    # RULE 5: OUTDATED ANALYSIS
    # =====================================================

    def _stale_analyses(self, permitted_ids) -> list[Recommendation]:
        """
        The most recent analysis is no longer current.
        """

        cutoff = datetime.now(UTC) - timedelta(
            days=self.rules.stale_analysis_days
        )

        latest = (
            select(
                AnalysisJob.forest_area_id.label("forest_area_id"),
                func.max(AnalysisJob.completed_at).label("completed_at"),
            )
            .where(
                AnalysisJob.forest_area_id.in_(permitted_ids),
                AnalysisJob.status == AnalysisJobStatus.COMPLETED,
                AnalysisJob.completed_at.isnot(None),
            )
            .group_by(AnalysisJob.forest_area_id)
            .subquery()
        )

        rows = self.db.execute(
            select(
                latest.c.forest_area_id,
                latest.c.completed_at,
                ForestArea.name,
                District.name,
            )
            .select_from(latest)
            .join(
                ForestArea,
                ForestArea.id == latest.c.forest_area_id,
            )
            .join(District, District.id == ForestArea.district_id)
            .where(latest.c.completed_at < cutoff)
            .order_by(latest.c.completed_at)
        ).all()

        return [
            Recommendation(
                rule="OUTDATED_ANALYSIS",
                priority=PriorityLevel.LOW,
                finding=(
                    f"The most recent completed analysis for "
                    f"{row[2]} finished on "
                    f"{row[1].date().isoformat()}, more than "
                    f"{self.rules.stale_analysis_days} days ago."
                ),
                action=(
                    "Obtain newer imagery and run a fresh analysis "
                    "before treating these results as a current "
                    "assessment of the area."
                ),
                forest_area_id=int(row[0]),
                forest_area=row[2],
                district=row[3],
            )
            for row in rows
        ]

    # =====================================================
    # RULE 6: NO SUITABLE IMAGERY
    # =====================================================

    def _areas_without_imagery(
        self, permitted_ids
    ) -> list[Recommendation]:
        """
        A monitored area with no completed analysis at all.

        Distinct from rule 5. There the area was examined and
        the result has aged; here it has never produced a
        result, so there is nothing to age. An empty bar on
        the district chart for such an area means "not
        looked at", not "nothing found".
        """

        completed = (
            select(AnalysisJob.forest_area_id)
            .where(
                AnalysisJob.status == AnalysisJobStatus.COMPLETED,
            )
            .distinct()
        )

        rows = self.db.execute(
            select(
                ForestArea.id,
                ForestArea.name,
                District.name,
            )
            .select_from(ForestArea)
            .join(District, District.id == ForestArea.district_id)
            .where(
                ForestArea.id.in_(permitted_ids),
                ForestArea.is_active.is_(True),
                ForestArea.id.notin_(completed),
            )
            .order_by(ForestArea.name)
        ).all()

        return [
            Recommendation(
                rule="NO_SUITABLE_IMAGERY",
                priority=PriorityLevel.MEDIUM,
                finding=(
                    f"{row[1]} is monitored but has no completed "
                    "analysis, so no observation of it exists in "
                    "the system."
                ),
                action=(
                    "Acquire a Sentinel-2 product for this area "
                    "and schedule an analysis. Until then its "
                    "absence from the charts reflects a lack of "
                    "observation rather than an absence of "
                    "clearing."
                ),
                forest_area_id=int(row[0]),
                forest_area=row[1],
                district=row[2],
            )
            for row in rows
        ]
