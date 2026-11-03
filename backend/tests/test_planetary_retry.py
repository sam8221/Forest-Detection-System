"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Tests: Planetary Computer retry behaviour

What these establish:
    The dashboard's scene summary comes from a public
    catalogue under variable load. Measured from this
    system, the same search returned in 1.8 seconds at one
    point and 504 Gateway Timeout after 16 seconds a
    quarter of an hour later. A single slow moment must not
    put a failure notice in front of an officer.

    These tests cover what the service does about that:
    which failures are attempted again, which are reported
    at once, and that neither can make the lookup run past
    the time the dashboard is prepared to wait.

How time is handled:
    The service's clock is replaced with one the tests
    advance themselves. Without it a test cannot distinguish
    "the budget stopped the retry" from "no time passed
    because the fake answered instantly", and the budget is
    the thing under test. It also keeps the suite fast: no
    test waits for a real backoff.

No network is used. requests.get is replaced throughout, so
these tests describe the service's own decisions rather than
the catalogue's behaviour on the day they are run.
===========================================================
"""

import pytest
import requests

from app.services import planetary_service as planetary_module
from app.services.planetary_service import (
    PlanetaryService,
    PlanetaryUnavailableError,
)


# =========================================================
# DOUBLES
# =========================================================


class FakeClock:
    """
    Stands in for the time module inside the service.

    Only monotonic() and sleep() are used there. Sleeping
    advances the clock rather than pausing, so a backoff
    costs the budget what it would really cost without
    costing the test anything.
    """

    def __init__(self):
        self.now = 1000.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class FakeResponse:
    """A requests.Response with only what the service uses."""

    def __init__(self, status_code=200, payload=None, invalid_json=False):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self._invalid_json = invalid_json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(
                f"{self.status_code} error",
                response=self,
            )

    def json(self):
        if self._invalid_json:
            raise ValueError("not JSON")
        return self._payload


class Recorder:
    """
    Stands in for requests.get and records every call.

    A call that fails with a timeout advances the clock by
    the timeout it was given, which is what a real read
    timeout costs.
    """

    def __init__(self, outcomes, clock=None):
        self.outcomes = list(outcomes)
        self.calls = []
        self.clock = clock

    def __call__(self, url, params=None, timeout=None):
        self.calls.append(
            {"url": url, "params": params, "timeout": timeout}
        )

        outcome = self.outcomes.pop(0)

        if isinstance(outcome, Exception):
            if self.clock is not None and timeout:
                self.clock.now += timeout
            raise outcome

        return outcome


@pytest.fixture
def clock(monkeypatch):
    """Replace the service's clock with one the test drives."""

    fake = FakeClock()
    monkeypatch.setattr(planetary_module, "time", fake)
    return fake


@pytest.fixture
def service(clock):
    return PlanetaryService()


# =========================================================
# RETRIED FAILURES
# =========================================================


def test_a_timeout_is_attempted_again_and_can_succeed(
    service, monkeypatch
):
    """
    One slow moment must not reach the officer.

    This is the fault that produced the notice on the
    dashboard: a read timeout on a catalogue that was busy
    rather than down.
    """

    recorder = Recorder(
        [
            requests.Timeout("read timed out"),
            FakeResponse(payload={"features": ["scene"]}),
        ]
    )
    monkeypatch.setattr(requests, "get", recorder)

    result = service.request_json(url="https://example.test/search")

    assert result == {"features": ["scene"]}
    assert len(recorder.calls) == 2


def test_a_gateway_timeout_is_attempted_again(service, monkeypatch):
    """
    504 is the status the catalogue actually returned when
    it was overloaded, and it says nothing about the request
    being wrong.
    """

    recorder = Recorder(
        [
            FakeResponse(status_code=504),
            FakeResponse(payload={"features": []}),
        ]
    )
    monkeypatch.setattr(requests, "get", recorder)

    assert service.request_json(url="https://example.test/search") == {
        "features": []
    }
    assert len(recorder.calls) == 2


def test_a_connection_failure_is_attempted_again(service, monkeypatch):
    recorder = Recorder(
        [
            requests.ConnectionError("connection reset"),
            FakeResponse(payload={"ok": True}),
        ]
    )
    monkeypatch.setattr(requests, "get", recorder)

    assert service.request_json(url="https://example.test/search") == {
        "ok": True
    }
    assert len(recorder.calls) == 2


def test_attempts_stop_at_the_configured_limit(service, monkeypatch):
    """
    An outage is reported rather than retried at length: an
    officer waiting on a dead service should be told so.
    """

    recorder = Recorder(
        [requests.Timeout("read timed out")]
        * service.REQUEST_ATTEMPTS
    )
    monkeypatch.setattr(requests, "get", recorder)

    with pytest.raises(PlanetaryUnavailableError) as failure:
        service.request_json(url="https://example.test/search")

    assert len(recorder.calls) == service.REQUEST_ATTEMPTS
    assert "did not respond in time" in str(failure.value)


# =========================================================
# FAILURES REPORTED AT ONCE
# =========================================================


def test_a_404_is_not_attempted_again(service, monkeypatch):
    """
    A 404 is a statement about the request. Repeating it
    only makes the officer wait longer for the same answer.
    """

    recorder = Recorder([FakeResponse(status_code=404)])
    monkeypatch.setattr(requests, "get", recorder)

    with pytest.raises(PlanetaryUnavailableError) as failure:
        service.request_json(url="https://example.test/search")

    assert len(recorder.calls) == 1
    assert "could not be reached" in str(failure.value)


def test_a_body_that_is_not_json_is_not_attempted_again(
    service, monkeypatch
):
    recorder = Recorder([FakeResponse(invalid_json=True)])
    monkeypatch.setattr(requests, "get", recorder)

    with pytest.raises(PlanetaryUnavailableError) as failure:
        service.request_json(url="https://example.test/search")

    assert len(recorder.calls) == 1
    assert "unexpected response" in str(failure.value)


# =========================================================
# THE TIME BUDGET
# =========================================================


def test_a_request_is_not_started_without_time_to_finish_it(
    service, monkeypatch, clock
):
    """
    The dashboard abandons this endpoint after 60 seconds,
    so a lookup that ran longer would produce a result
    nobody is still waiting for.

    This is the second request of a lookup whose search
    already spent the allowance. Starting it would delay the
    message the officer is waiting for without any realistic
    prospect of an answer, so it is not started at all.
    """

    recorder = Recorder([FakeResponse(payload={"tiles": []})], clock)
    monkeypatch.setattr(requests, "get", recorder)

    with pytest.raises(PlanetaryUnavailableError) as failure:
        service.request_json(
            url="https://example.test/tilejson",
            deadline=clock.monotonic() + 0.2,
        )

    assert recorder.calls == []
    assert "did not respond in time" in str(failure.value)


def test_a_retry_is_not_started_without_time_to_finish_it(
    service, monkeypatch, clock
):
    """
    The first attempt is always made when the lookup begins,
    because the whole allowance is available to it. What the
    budget stops is the attempt after a slow failure.
    """

    recorder = Recorder(
        [requests.Timeout("read timed out")]
        * service.REQUEST_ATTEMPTS,
        clock,
    )
    monkeypatch.setattr(requests, "get", recorder)

    # Enough for one attempt, not for a second.
    with pytest.raises(PlanetaryUnavailableError):
        service.request_json(
            url="https://example.test/search",
            deadline=clock.monotonic() + 1.5,
        )

    assert len(recorder.calls) == 1
    assert recorder.calls[0]["timeout"] == pytest.approx(1.5)


def test_an_attempt_may_not_outlast_the_budget(service, clock):
    """
    The per-attempt timeout is cut to whatever time is left,
    so one attempt cannot overrun the whole allowance.
    """

    service.timeout = 20.0

    assert service.remaining_timeout(None) == 20.0
    assert service.remaining_timeout(
        clock.monotonic() + 5.0
    ) == pytest.approx(5.0)
    assert service.remaining_timeout(clock.monotonic() + 0.1) is None


def test_a_whole_lookup_stays_within_its_budget(
    service, monkeypatch, clock
):
    """
    Every attempt of both requests, and the backoff between
    them, has to fit inside one allowance.
    """

    started = clock.monotonic()

    recorder = Recorder(
        [requests.Timeout("read timed out")] * 10,
        clock,
    )
    monkeypatch.setattr(requests, "get", recorder)

    with pytest.raises(PlanetaryUnavailableError):
        service.get_latest_scene()

    elapsed = clock.monotonic() - started

    assert elapsed <= service.TOTAL_BUDGET_SECONDS
    assert len(recorder.calls) <= service.REQUEST_ATTEMPTS


def test_the_budget_covers_both_requests_of_a_lookup(
    service, monkeypatch
):
    """
    A lookup makes two requests in sequence. A slow search
    must not leave the tile endpoint request free to spend
    the whole allowance again.
    """

    seen = []

    def fake_request_json(url, params=None, description="catalogue",
                          deadline=None):
        seen.append(deadline)

        if "search" in url:
            return {
                "features": [
                    {
                        "id": "scene",
                        "properties": {
                            "datetime": "2026-10-27T08:14:51Z",
                            "eo:cloud_cover": 12.7,
                        },
                        "assets": {
                            "tilejson": {
                                "href": "https://example.test/tilejson"
                            }
                        },
                    }
                ]
            }

        return {
            "tiles": ["https://example.test/{z}/{x}/{y}.png"],
            "bounds": [27.2, -13.7, 29.5, -11.7],
            "center": [28.35, -12.7, 10],
            "minzoom": 8,
            "maxzoom": 14,
        }

    monkeypatch.setattr(service, "request_json", fake_request_json)

    scene = service.get_latest_scene()

    assert scene["item_id"] == "scene"
    assert len(seen) == 2
    assert seen[0] is not None
    # The same deadline, not a fresh allowance for the second.
    assert seen[0] == seen[1]
