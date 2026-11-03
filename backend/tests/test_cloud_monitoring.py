"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Tests: Cloud monitoring

What these protect:

    Two separate measurements that look alike and mean
    different things. A Sentinel-2 product carries the
    cloud cover measured when the satellite passed, which
    may be days old. A weather provider reports the sky now.
    Showing one as the other would be a false statement
    wearing the shape of a reading, so the tests keep them
    in separate fields with separate timestamps and separate
    sources.

    And the rule that matters most: no fabricated
    percentage. Every failure path is checked to carry no
    figure at all rather than a zero, because a zero reads
    as a clear sky and an officer would act on it.

Nothing here contacts a weather provider. The HTTP call is
stubbed in every test.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia
===========================================================
"""

from datetime import date, datetime
from types import SimpleNamespace

import pytest

from app.models.enums import UserRole
from app.repositories.cloud_monitoring_repository import (
    POINT_FROM_DISTRICT_REFERENCE,
    POINT_FROM_MONITORED_AREAS,
    DISTRICT_REFERENCE_POINTS,
    ObservationPoint,
    SatelliteObservation,
)
from app.services import cloud_monitoring_service
from app.services import weather_service
from app.services.cloud_conditions import (
    CloudCondition,
    classify_cloud_cover,
    condition_label,
    is_suitable_for_analysis,
)
from app.services.cloud_monitoring_service import (
    DistrictNotFound,
    DistrictOutsideJurisdiction,
    available_districts,
    cloud_monitoring_report,
    default_district_id,
)
from app.services.weather_service import (
    WeatherDisabled,
    WeatherUnavailable,
    fetch_current_cloud_cover,
    reset_weather_cache,
)


# =========================================================
# FIXTURES AND STUBS
# =========================================================


@pytest.fixture(autouse=True)
def clean_weather_cache():
    reset_weather_cache()
    yield
    reset_weather_cache()


def officer(
    role=UserRole.DISTRICT_FORESTRY_OFFICER,
    district_id=8,
    province_id=1,
):
    return SimpleNamespace(
        id=3,
        full_name="Kitwe Officer",
        role=role,
        district_id=district_id,
        province_id=province_id,
    )


def district(id=8, name="Kitwe", code="KIT", province_id=1, active=True):
    return SimpleNamespace(
        id=id,
        name=name,
        code=code,
        province_id=province_id,
        is_active=active,
    )


def observation(
    image_id=1,
    cloud=12.0,
    day=date(2026, 10, 28),
    area="Chichele Forest",
    processed=True,
):
    return SatelliteObservation(
        image_id=image_id,
        product_id=f"S2A_MSIL2A_{image_id}",
        acquisition_date=day,
        cloud_cover_percentage=cloud,
        forest_area_name=area,
        is_processed=processed,
    )


class StubRepository:
    """Stands in for CloudMonitoringRepository."""

    def __init__(
        self,
        districts=None,
        point=None,
        observations=None,
    ):
        self._districts = districts if districts is not None else [district()]
        self._point = point
        self._observations = observations if observations is not None else []

    def active_districts(self):
        return [d for d in self._districts if d.is_active]

    def get_district(self, district_id):
        for d in self._districts:
            if d.id == district_id:
                return d
        return None

    def observation_point(self, district):
        return self._point

    def recent_observations(self, district_id, limit):
        return self._observations[:limit]


@pytest.fixture
def stub_repository(monkeypatch):
    """Install a stub repository for the service to use."""

    def install(**kwargs):
        repository = StubRepository(**kwargs)

        monkeypatch.setattr(
            cloud_monitoring_service,
            "CloudMonitoringRepository",
            lambda db: repository,
        )

        return repository

    return install


@pytest.fixture
def stub_weather(monkeypatch):
    """Make the weather reading return or raise, without a network."""

    def install(reading=None, error=None):
        calls = []

        def fake(latitude, longitude, force=False):
            calls.append(
                {
                    "latitude": latitude,
                    "longitude": longitude,
                    "force": force,
                }
            )

            if error is not None:
                raise error

            return reading

        monkeypatch.setattr(
            cloud_monitoring_service,
            "fetch_current_cloud_cover",
            fake,
        )

        return calls

    return install


def weather_reading(percentage=18.0):
    return weather_service.CurrentCloudCover(
        percentage=percentage,
        observed_at="2026-11-02T13:45",
        provider="Open-Meteo",
        latitude=-12.7592,
        longitude=28.3137,
        requested_latitude=-12.7897,
        requested_longitude=28.3205,
        retrieved_at=datetime(2026, 11, 2, 13, 47).astimezone(),
    )


# =========================================================
# CLASSIFICATION
#
# Boundaries are the okta scale, from configuration. These
# check the edges, where an off-by-one would silently
# relabel a quarter of the range.
# =========================================================


@pytest.mark.parametrize(
    "percentage, expected",
    [
        (0.0, CloudCondition.CLEAR),
        (12.5, CloudCondition.CLEAR),
        (12.6, CloudCondition.PARTLY_CLOUDY),
        (50.0, CloudCondition.PARTLY_CLOUDY),
        (50.1, CloudCondition.CLOUDY),
        (87.5, CloudCondition.CLOUDY),
        (87.6, CloudCondition.VERY_CLOUDY),
        (100.0, CloudCondition.VERY_CLOUDY),
    ],
)
def test_a_percentage_is_classified_on_the_okta_boundaries(
    percentage,
    expected,
):
    assert classify_cloud_cover(percentage) is expected


def test_no_measurement_is_unknown_not_clear():
    """
    The failure this prevents: a missing reading rendering
    as a clear sky, which is the most useful-looking and
    most misleading thing it could become.
    """

    assert classify_cloud_cover(None) is CloudCondition.UNKNOWN

    assert condition_label(CloudCondition.UNKNOWN) == "Not available"


@pytest.mark.parametrize("value", [-1, 101, 150, float("nan"), "cloudy", None])
def test_an_impossible_figure_is_not_classified(value):
    """
    A provider reporting 150 percent has malfunctioned.
    Clamping to 100 would turn an obvious fault into a
    confident reading of total overcast.
    """

    assert classify_cloud_cover(value) is CloudCondition.UNKNOWN


# =========================================================
# SUITABILITY
# =========================================================


def test_a_clear_scene_is_suitable_and_a_cloudy_one_is_not():
    # The threshold is MAX_CLOUD_COVER_PERCENTAGE, the same
    # one the catalogue search already uses.
    assert is_suitable_for_analysis(10.0) is True

    assert is_suitable_for_analysis(95.0) is False


def test_an_unmeasured_scene_is_neither_suitable_nor_unsuitable():
    """
    None, not False.

    False says the scene is unsuitable, which is a finding.
    The truth is that no finding can be made, and an officer
    waits for another pass on the first but goes and looks
    on the second.
    """

    assert is_suitable_for_analysis(None) is None


# =========================================================
# THE WEATHER READING
# =========================================================


class StubResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = "stub body"

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def install_requests(monkeypatch, response=None, error=None):
    """Replace requests.get for the weather service only."""

    import requests

    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append({"url": url, "params": params, "timeout": timeout})

        if error is not None:
            raise error

        return response

    monkeypatch.setattr(requests, "get", fake_get)

    return calls


def good_payload(cloud=42.0):
    return {
        "latitude": -12.759226,
        "longitude": 28.313692,
        "timezone": "Africa/Lusaka",
        "current": {
            "time": "2026-11-02T13:45",
            "interval": 900,
            "cloud_cover": cloud,
        },
    }


def test_a_reading_carries_the_provider_time_and_grid_point(monkeypatch):
    install_requests(monkeypatch, response=StubResponse(good_payload()))

    reading = fetch_current_cloud_cover(-12.7897, 28.3205)

    assert reading.percentage == 42.0

    # The provider's own timestamp, not the time we asked.
    assert reading.observed_at == "2026-11-02T13:45"

    # The grid point answered for, which differs from the
    # point requested and is shown so an officer can judge
    # how near the reading is.
    assert reading.latitude == pytest.approx(-12.759226)
    assert reading.requested_latitude == -12.7897


def test_the_request_asks_only_for_cloud_cover_in_zambian_time(monkeypatch):
    calls = install_requests(
        monkeypatch, response=StubResponse(good_payload())
    )

    fetch_current_cloud_cover(-12.7897, 28.3205)

    assert calls[0]["params"]["current"] == "cloud_cover"
    assert calls[0]["params"]["timezone"] == "Africa/Lusaka"

    # An officer is waiting on a card while this runs.
    assert calls[0]["timeout"] == (3.05, 6.0)


def test_no_credential_is_sent_when_none_is_configured(monkeypatch):
    """
    The default provider needs no key, and some providers
    reject a request carrying an empty one.
    """

    calls = install_requests(
        monkeypatch, response=StubResponse(good_payload())
    )

    fetch_current_cloud_cover(-12.7897, 28.3205)

    assert "apikey" not in calls[0]["params"]


def test_a_reading_is_reused_until_it_stops_being_current(monkeypatch):
    calls = install_requests(
        monkeypatch, response=StubResponse(good_payload())
    )

    fetch_current_cloud_cover(-12.7897, 28.3205)
    fetch_current_cloud_cover(-12.7897, 28.3205)
    fetch_current_cloud_cover(-12.7898, 28.3205)

    # Three asks, one request: the third rounds to the same
    # grid key, so officers watching one district share a
    # reading instead of each costing a call.
    assert len(calls) == 1


def test_a_manual_refresh_asks_again(monkeypatch):
    calls = install_requests(
        monkeypatch, response=StubResponse(good_payload())
    )

    fetch_current_cloud_cover(-12.7897, 28.3205)
    fetch_current_cloud_cover(-12.7897, 28.3205, force=True)

    assert len(calls) == 2


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"current": None},
        {"current": {}},
        {"current": {"cloud_cover": None, "time": "2026-11-02T13:45"}},
        {"current": {"cloud_cover": "not a number", "time": "x"}},
        {"current": {"cloud_cover": 150, "time": "x"}},
        {"current": {"cloud_cover": -5, "time": "x"}},
        # A figure with no observation time cannot be shown
        # as current, which is the card's whole claim.
        {"current": {"cloud_cover": 20}},
    ],
)
def test_an_unusable_answer_raises_rather_than_returning_zero(
    monkeypatch,
    payload,
):
    install_requests(monkeypatch, response=StubResponse(payload))

    with pytest.raises(WeatherUnavailable):
        fetch_current_cloud_cover(-12.7897, 28.3205)


def test_a_provider_that_cannot_be_reached_raises(monkeypatch):
    install_requests(monkeypatch, error=OSError("no route to host"))

    with pytest.raises(WeatherUnavailable):
        fetch_current_cloud_cover(-12.7897, 28.3205)


def test_a_provider_fault_does_not_repeat_the_providers_body(monkeypatch):
    """
    A failing provider can answer with an HTML page, and the
    request carried a credential for providers that use one.
    Only the status code is reported.
    """

    install_requests(
        monkeypatch,
        response=StubResponse({}, status_code=503),
    )

    with pytest.raises(WeatherUnavailable) as raised:
        fetch_current_cloud_cover(-12.7897, 28.3205)

    assert "503" in str(raised.value)
    assert "stub body" not in str(raised.value)


# =========================================================
# DISTRICT SELECTION AND JURISDICTION
# =========================================================


def test_a_district_officer_is_offered_only_their_own_district(
    stub_repository,
):
    stub_repository(
        districts=[
            district(id=8, name="Kitwe"),
            district(id=9, name="Ndola"),
        ]
    )

    offered = available_districts(db=None, user=officer(district_id=8))

    assert [d["name"] for d in offered] == ["Kitwe"]


def test_a_provincial_officer_is_offered_the_whole_province(
    stub_repository,
):
    stub_repository(
        districts=[
            district(id=8, name="Kitwe", province_id=1),
            district(id=9, name="Ndola", province_id=1),
            district(id=99, name="Elsewhere", province_id=2),
        ]
    )

    offered = available_districts(
        db=None,
        user=officer(
            role=UserRole.PROVINCIAL_FORESTRY_OFFICER,
            district_id=None,
            province_id=1,
        ),
    )

    assert [d["name"] for d in offered] == ["Kitwe", "Ndola"]


def test_requesting_another_district_is_refused_on_the_server(
    stub_repository,
    stub_weather,
):
    """
    FR-04. The selector only offers the officer's own
    district, but a hidden option is not access control. An
    officer who edits the district id in the request is
    refused here, before any figure is read.
    """

    stub_repository(
        districts=[district(id=8, name="Kitwe"), district(id=9, name="Ndola")],
        point=ObservationPoint(-12.9, 28.6, POINT_FROM_MONITORED_AREAS, 2),
        observations=[observation()],
    )

    calls = stub_weather(reading=weather_reading())

    with pytest.raises(DistrictOutsideJurisdiction):
        cloud_monitoring_report(
            db=None,
            user=officer(district_id=8),
            district_id=9,
        )

    # Refused before the provider was asked anything.
    assert calls == []


def test_an_unknown_district_is_not_found(stub_repository):
    stub_repository(districts=[district(id=8)])

    with pytest.raises(DistrictNotFound):
        cloud_monitoring_report(
            db=None,
            user=officer(role=UserRole.ADMIN),
            district_id=404,
        )


def test_an_inactive_district_is_not_monitored(stub_repository):
    stub_repository(districts=[district(id=8, active=False)])

    with pytest.raises(DistrictNotFound):
        cloud_monitoring_report(
            db=None,
            user=officer(role=UserRole.ADMIN),
            district_id=8,
        )


def test_the_officers_own_district_is_shown_first(stub_repository):
    stub_repository(
        districts=[district(id=8, name="Kitwe"), district(id=9, name="Ndola")]
    )

    assert default_district_id(db=None, user=officer(district_id=9)) == 9


# =========================================================
# THE REPORT
# =========================================================


def test_the_report_keeps_current_and_satellite_cloud_apart(
    stub_repository,
    stub_weather,
):
    """
    The distinction the whole feature rests on.

    The satellite figure was measured when the satellite
    passed; the weather figure is the sky now. They are
    different numbers, in different fields, each with its
    own time and source.
    """

    stub_repository(
        districts=[district()],
        point=ObservationPoint(-12.78, 28.32, POINT_FROM_MONITORED_AREAS, 3),
        observations=[observation(cloud=7.0, day=date(2026, 10, 28))],
    )

    stub_weather(reading=weather_reading(percentage=64.0))

    report = cloud_monitoring_report(
        db=None,
        user=officer(),
        district_id=8,
    )

    assert report["current"]["percentage"] == 64.0
    assert report["current"]["observed_at"] == "2026-11-02T13:45"
    assert report["current"]["provider"] == "Open-Meteo"

    assert report["satellite"]["latest"]["percentage"] == 7.0
    assert report["satellite"]["latest"]["acquisition_date"] == "2026-10-28"

    # Three separate times, none standing in for another.
    assert report["generated_at"]
    assert (
        report["current"]["observed_at"]
        != report["satellite"]["latest"]["acquisition_date"]
    )


def test_an_unreachable_provider_does_not_lose_the_satellite_half(
    stub_repository,
    stub_weather,
):
    """
    The satellite figures come from imagery already held, so
    they stay useful when the weather provider is down.
    Failing the whole request would remove working
    information because an optional extra stopped answering.
    """

    stub_repository(
        districts=[district()],
        point=ObservationPoint(-12.78, 28.32, POINT_FROM_MONITORED_AREAS, 3),
        observations=[observation(cloud=9.0)],
    )

    stub_weather(error=WeatherUnavailable("provider unreachable"))

    report = cloud_monitoring_report(db=None, user=officer(), district_id=8)

    assert report["current"]["available"] is False
    assert "unreachable" in report["current"]["unavailable_reason"]

    # No fabricated figure in its place.
    assert report["current"]["percentage"] is None
    assert report["current"]["condition"] == "UNKNOWN"

    assert report["satellite"]["available"] is True
    assert report["satellite"]["latest"]["percentage"] == 9.0


def test_weather_switched_off_is_reported_as_such(
    stub_repository,
    stub_weather,
):
    stub_repository(
        districts=[district()],
        point=ObservationPoint(-12.78, 28.32, POINT_FROM_MONITORED_AREAS, 1),
    )

    stub_weather(
        error=WeatherDisabled("Current weather readings are switched off")
    )

    report = cloud_monitoring_report(db=None, user=officer(), district_id=8)

    assert report["current"]["available"] is False
    assert "switched off" in report["current"]["unavailable_reason"]
    assert report["current"]["percentage"] is None


def test_a_district_with_no_imagery_says_so(
    stub_repository,
    stub_weather,
):
    """
    Not an error, and not an empty gauge reading zero. The
    district simply has no registered imagery yet.
    """

    stub_repository(
        districts=[district()],
        point=ObservationPoint(-12.78, 28.32, POINT_FROM_MONITORED_AREAS, 1),
        observations=[],
    )

    stub_weather(reading=weather_reading())

    report = cloud_monitoring_report(db=None, user=officer(), district_id=8)

    assert report["satellite"]["available"] is False
    assert report["satellite"]["latest"] is None
    assert report["satellite"]["observation_count"] == 0
    assert "No Sentinel-2 imagery" in report["satellite"]["unavailable_reason"]


def test_observations_can_be_compared_and_counted_for_suitability(
    stub_repository,
    stub_weather,
):
    stub_repository(
        districts=[district()],
        point=ObservationPoint(-12.78, 28.32, POINT_FROM_MONITORED_AREAS, 2),
        observations=[
            observation(image_id=1, cloud=5.0, day=date(2026, 10, 30)),
            observation(image_id=2, cloud=22.0, day=date(2026, 10, 25)),
            observation(image_id=3, cloud=88.0, day=date(2026, 10, 20)),
        ],
    )

    stub_weather(reading=weather_reading())

    report = cloud_monitoring_report(db=None, user=officer(), district_id=8)

    satellite = report["satellite"]

    assert satellite["observation_count"] == 3

    # Two are within MAX_CLOUD_COVER_PERCENTAGE (30).
    assert satellite["suitable_count"] == 2

    # Every row carries its own date, so the newest figure
    # cannot be read as the sky now.
    assert [o["acquisition_date"] for o in satellite["observations"]] == [
        "2026-10-30",
        "2026-10-25",
        "2026-10-20",
    ]

    assert satellite["observations"][2]["condition"] == "VERY_CLOUDY"
    assert satellite["observations"][2]["suitable_for_analysis"] is False


def test_the_point_says_whether_it_came_from_monitored_areas(
    stub_repository,
    stub_weather,
):
    """
    A district with monitored forest areas gets a point
    derived from their geometry. One without falls back to
    its district town, and the card says which, because in
    the Copperbelt the town is usually a mining settlement
    some way from the reserve.
    """

    stub_repository(
        districts=[district()],
        point=ObservationPoint(
            -12.8400, 28.0942, POINT_FROM_DISTRICT_REFERENCE, 0
        ),
    )

    stub_weather(reading=weather_reading())

    report = cloud_monitoring_report(db=None, user=officer(), district_id=8)

    assert report["observation_point"]["source"] == POINT_FROM_DISTRICT_REFERENCE
    assert report["observation_point"]["monitored_area_count"] == 0


def test_a_district_with_no_location_at_all_is_handled(
    stub_repository,
    stub_weather,
):
    stub_repository(districts=[district()], point=None)

    calls = stub_weather(reading=weather_reading())

    report = cloud_monitoring_report(db=None, user=officer(), district_id=8)

    assert report["observation_point"] is None
    assert report["current"]["available"] is False
    assert report["current"]["percentage"] is None

    # Nothing was asked of the provider: there was nowhere
    # to ask about.
    assert calls == []


def test_a_manual_refresh_is_passed_through(
    stub_repository,
    stub_weather,
):
    stub_repository(
        districts=[district()],
        point=ObservationPoint(-12.78, 28.32, POINT_FROM_MONITORED_AREAS, 1),
    )

    calls = stub_weather(reading=weather_reading())

    cloud_monitoring_report(
        db=None,
        user=officer(),
        district_id=8,
        force_refresh=True,
    )

    assert calls[0]["force"] is True


def test_every_copperbelt_district_has_a_reference_point():
    """
    Four of the ten districts had no monitored forest area
    when this was written, so the fallback has to cover all
    of them or those officers get a card with no location.
    """

    expected = {
        "Kitwe",
        "Ndola",
        "Chingola",
        "Mufulira",
        "Luanshya",
        "Kalulushi",
        "Chililabombwe",
        "Lufwanyama",
        "Masaiti",
        "Mpongwe",
    }

    assert expected <= set(DISTRICT_REFERENCE_POINTS)

    # All inside the Copperbelt's bounding box, so a
    # transposed pair would be caught.
    for name, (latitude, longitude) in DISTRICT_REFERENCE_POINTS.items():
        assert -14.5 < latitude < -11.5, name
        assert 26.5 < longitude < 29.5, name
