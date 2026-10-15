"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Analytics Tests

Purpose:
    Verify the NDVI change statistics, the jurisdiction
    scoping behind every analytics query, and the
    recommendation rules.

Responsibilities:
    - Confirm mean NDVI and decline share on known inputs.
    - Confirm cloud and no-data pixels are excluded.
    - Confirm mismatched rasters are refused.
    - Confirm declined area uses the projected pixel size.
    - Confirm analytics queries carry a jurisdiction filter.
    - Confirm the recommendation thresholds are documented.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Note:
    The rasters built here are SYNTHETIC FIXTURES with
    hand-chosen values, written so the expected statistics
    can be worked out on paper. They are not satellite
    observations and nothing derived from them describes
    real forest loss anywhere.

    Nothing in this module opens a database connection or
    reaches the network. The scoping tests inspect the SQL
    a query compiles to rather than executing it.
===========================================================
"""

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_origin
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app.core.constants import NDVI_NODATA
from app.models.enums import UserRole
from app.models.user import User
from app.services.analytics_service import AnalyticsService
from app.services.recommendation_service import RecommendationRules


# =========================================================
# FIXTURE SUPPORT
# =========================================================

PIXEL_SIZE_METRES = 10.0

TEST_CRS = CRS.from_proj4(
    "+proj=utm +zone=35 +south +datum=WGS84 "
    "+units=m +no_defs"
)


def write_ndvi(
    directory: Path,
    stage: str,
    values: np.ndarray,
) -> Path:
    """
    Write a synthetic cloud-masked NDVI raster.

    The pipeline stores these under the forest area, which
    is the layout AnalyticsService.ndvi_change reads, so the
    fixture reproduces that layout exactly rather than
    taking a path as an argument.
    """

    target = directory / stage / "masked_ndvi"

    target.mkdir(parents=True, exist_ok=True)

    path = target / "ndvi_masked.tif"

    profile = {
        "driver": "GTiff",
        "height": values.shape[0],
        "width": values.shape[1],
        "count": 1,
        "dtype": "float32",
        "crs": TEST_CRS,
        "transform": from_origin(
            500000.0,
            8600000.0,
            PIXEL_SIZE_METRES,
            PIXEL_SIZE_METRES,
        ),
        "nodata": NDVI_NODATA,
    }

    with rasterio.open(path, "w", **profile) as destination:
        destination.write(values.astype("float32"), 1)

    return path


@dataclass
class StubJob:
    """Stands in for an AnalysisJob, carrying only what is read.

    id matters now that outputs are stored per job: the
    service looks for this job's own directory first and
    falls back to the shared pre-job location. These
    fixtures write to the shared location, so they exercise
    the fallback path.
    """

    id: int = 1
    forest_area_id: int = 1
    ndvi_threshold: float = 0.30
    cloud_cover_percentage: float = 4.0
    baseline_start: date | None = date(2025, 5, 1)
    baseline_end: date | None = date(2025, 7, 31)
    comparison_start: date | None = date(2026, 5, 1)
    comparison_end: date | None = date(2026, 7, 31)
    completed_at: datetime | None = None


@dataclass
class StubSettings:
    """Points the service at the fixture directory."""

    satellite_image_storage_path: Path
    ndvi_threshold: float = 0.30


def service_for(storage_root: Path) -> AnalyticsService:
    """
    Build the service without touching a database.

    ndvi_change reads rasters and never queries, so an
    unconnected Session is enough.
    """

    service = AnalyticsService.__new__(AnalyticsService)
    service.db = Session()
    service.settings = StubSettings(
        satellite_image_storage_path=storage_root
    )

    return service


def build_scene(
    tmp_path: Path,
    previous: np.ndarray,
    latest: np.ndarray,
    forest_area_id: int = 1,
) -> AnalyticsService:
    """Write both rasters where the service expects them."""

    area_directory = tmp_path / str(forest_area_id)

    write_ndvi(area_directory, "processing_previous", previous)
    write_ndvi(area_directory, "processing", latest)

    return service_for(tmp_path)


# =========================================================
# NDVI CHANGE STATISTICS
# =========================================================

def test_mean_ndvi_matches_hand_calculation(tmp_path) -> None:
    """
    Means and their difference come out as calculated.

    Four pixels at 0.80 earlier and 0.40 later give means of
    0.80 and 0.40, and a difference of later minus earlier,
    which is -0.40.
    """

    previous = np.full((2, 2), 0.80, dtype="float32")
    latest = np.full((2, 2), 0.40, dtype="float32")

    service = build_scene(tmp_path, previous, latest)

    result = service.ndvi_change(StubJob())

    assert result["rasters_available"] is True
    assert np.isclose(result["mean_ndvi_before"], 0.80, atol=1e-4)
    assert np.isclose(result["mean_ndvi_after"], 0.40, atol=1e-4)
    assert np.isclose(
        result["mean_ndvi_difference"], -0.40, atol=1e-4
    )
    assert result["measurable_pixels"] == 4


def test_no_data_pixels_are_excluded(tmp_path) -> None:
    """
    A pixel unmeasured on either date takes no part.

    Half the grid is left as the no-data sentinel on the
    later date. Were those pixels counted the mean would be
    dragged toward the sentinel and report a collapse that
    did not happen.
    """

    previous = np.full((2, 2), 0.80, dtype="float32")

    latest = np.array(
        [[0.40, 0.40], [NDVI_NODATA, NDVI_NODATA]],
        dtype="float32",
    )

    service = build_scene(tmp_path, previous, latest)

    result = service.ndvi_change(StubJob())

    assert result["measurable_pixels"] == 2
    assert np.isclose(result["mean_ndvi_after"], 0.40, atol=1e-4)
    assert np.isclose(result["mean_ndvi_before"], 0.80, atol=1e-4)


def test_declined_share_counts_only_measurable_pixels(
    tmp_path,
) -> None:
    """
    The declined share is of pixels measurable on BOTH dates.

    Two of four pixels decline, one holds steady, and one is
    unmeasurable later. Three pixels are comparable, so the
    share is two of three rather than two of four.
    """

    previous = np.array(
        [[0.80, 0.80], [0.50, 0.80]], dtype="float32"
    )

    latest = np.array(
        [[0.40, 0.30], [0.50, NDVI_NODATA]], dtype="float32"
    )

    service = build_scene(tmp_path, previous, latest)

    result = service.ndvi_change(StubJob())

    assert result["measurable_pixels"] == 3
    assert np.isclose(
        result["declined_pixel_percentage"],
        100.0 * 2 / 3,
        atol=0.01,
    )


def test_declined_area_uses_the_projected_pixel_size(
    tmp_path,
) -> None:
    """
    Declined area converts pixels to hectares at 10 m.

    Two pixels fall by 0.40, clearing the 0.30 threshold,
    and one falls by 0.05 which does not. Two pixels of
    100 m2 is 0.02 hectares.
    """

    previous = np.array(
        [[0.80, 0.80], [0.50, 0.80]], dtype="float32"
    )

    latest = np.array(
        [[0.40, 0.40], [0.45, 0.80]], dtype="float32"
    )

    service = build_scene(tmp_path, previous, latest)

    result = service.ndvi_change(StubJob())

    assert np.isclose(
        result["declined_hectares"], 0.02, atol=1e-6
    )


def test_mismatched_rasters_are_refused(tmp_path) -> None:
    """
    Grids of different shapes are not compared.

    Comparing them would line up unrelated ground and report
    a change that describes nowhere.
    """

    previous = np.full((2, 2), 0.80, dtype="float32")
    latest = np.full((3, 3), 0.40, dtype="float32")

    service = build_scene(tmp_path, previous, latest)

    with pytest.raises(ValueError, match="pixel grids"):
        service.ndvi_change(StubJob())


def test_missing_rasters_report_absence_not_zero(
    tmp_path,
) -> None:
    """
    With no rasters the statistics are null, never zero.

    An officer reads zero as "no vegetation change" and null
    as "not measured". Returning zero here would assert a
    finding the system does not have.
    """

    service = service_for(tmp_path)

    result = service.ndvi_change(StubJob(forest_area_id=404))

    assert result["rasters_available"] is False
    assert result["mean_ndvi_before"] is None
    assert result["declined_pixel_percentage"] is None
    assert result["declined_hectares"] is None


def test_fully_masked_scene_reports_no_measurable_pixels(
    tmp_path,
) -> None:
    """
    A scene entirely under cloud yields no statistics.
    """

    previous = np.full((2, 2), NDVI_NODATA, dtype="float32")
    latest = np.full((2, 2), NDVI_NODATA, dtype="float32")

    service = build_scene(tmp_path, previous, latest)

    result = service.ndvi_change(StubJob())

    assert result["measurable_pixels"] == 0
    assert result["mean_ndvi_before"] is None


def test_observation_windows_are_reported(tmp_path) -> None:
    """
    The job's windows travel with the statistics.

    The comparison is only defensible if the two windows are
    equivalent seasons in different years, so the dates have
    to be visible alongside the numbers.
    """

    previous = np.full((2, 2), 0.80, dtype="float32")
    latest = np.full((2, 2), 0.40, dtype="float32")

    service = build_scene(tmp_path, previous, latest)

    result = service.ndvi_change(StubJob())

    assert result["baseline_start"] == date(2025, 5, 1)
    assert result["comparison_start"] == date(2026, 5, 1)
    assert result["ndvi_threshold"] == 0.30


# =========================================================
# JURISDICTION SCOPING
# =========================================================

def officer(
    role: UserRole,
    district_id: int | None = None,
    province_id: int | None = None,
) -> User:
    """Build an unsaved User carrying only a jurisdiction."""

    user = User()
    user.role = role
    user.district_id = district_id
    user.province_id = province_id

    return user


def scoped_sql(user: User) -> str:
    """
    Compile the forest-area scope an analytics query uses.

    The Session is never connected: building and compiling a
    query touches no database.
    """

    from app.models.forest_area import ForestArea

    session = Session()

    service = AnalyticsService.__new__(AnalyticsService)
    service.db = session

    query = service._scope_forest_areas(
        session.query(ForestArea.id),
        user,
    )

    return str(
        query.statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def test_district_officer_analytics_are_filtered() -> None:
    """Analytics for a district officer carry its filter."""

    sql = scoped_sql(
        officer(
            UserRole.DISTRICT_FORESTRY_OFFICER,
            district_id=8,
        )
    )

    assert "forest_areas.district_id = 8" in sql


def test_provincial_officer_analytics_are_filtered() -> None:
    """Analytics for a provincial officer cover a province."""

    sql = scoped_sql(
        officer(
            UserRole.PROVINCIAL_FORESTRY_OFFICER,
            province_id=2,
        )
    )

    assert "districts.province_id = 2" in sql


def test_administrator_analytics_are_unfiltered() -> None:
    """An administrator holds no jurisdiction to scope to."""

    sql = scoped_sql(officer(UserRole.ADMIN))

    assert "WHERE" not in sql


def test_officer_without_jurisdiction_sees_nothing() -> None:
    """
    An unassigned account matches no forest area.

    Rejected explicitly rather than left to a NULL
    comparison, which SQLAlchemy would render as IS NULL and
    which would match areas whose district is unset instead
    of matching none.
    """

    sql = scoped_sql(
        officer(
            UserRole.DISTRICT_FORESTRY_OFFICER,
            district_id=None,
        )
    )

    assert "false" in sql.lower()
    assert "IS NULL" not in sql


# =========================================================
# RECOMMENDATION RULES
# =========================================================

def test_recommendation_thresholds_are_reproducible() -> None:
    """
    The rules are plain values, returned with the advice.

    An officer has to be able to see why a recommendation
    appeared, and a reader of the dissertation has to be
    able to reproduce it. Defaults are asserted here so a
    change to any of them is a deliberate, visible edit.
    """

    rules = RecommendationRules()

    assert rules.field_verification_hectares == 5.0
    assert rules.substantial_ndvi_decline == 0.40
    assert rules.cloud_cover_percentage == 30.0
    assert rules.stale_analysis_days == 90
    assert rules.repeat_detection_count == 2

    published = rules.as_dict()

    assert published["field_verification_hectares"] == 5.0
    assert published["substantial_ndvi_decline"] == 0.40


def test_recommendation_rules_are_overridable() -> None:
    """
    Thresholds are configurable rather than fixed in code.
    """

    rules = RecommendationRules(
        field_verification_hectares=2.0,
    )

    assert rules.field_verification_hectares == 2.0
    assert rules.as_dict()["field_verification_hectares"] == 2.0
