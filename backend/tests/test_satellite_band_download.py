"""Per-band, resumable Copernicus acquisition.

Copernicus refuses Range on a whole .SAFE.zip (HTTP 416, DAT-ZIP-116
"Range requests are not supported for multi-object downloads"), so a
connection reset part-way through a ~1 GB product discards every byte.
The individual band nodes do support Range, and analysis only reads
three of them, so acquisition fetches those and assembles an archive.

These tests use mocked HTTP responses only; no credentials and no
network are involved.
"""

from __future__ import annotations

import threading
import time
import zipfile
from pathlib import Path

import pytest
import requests

from app.services.copernicus_service import (
    CopernicusAuthorizationError,
    CopernicusService,
)
from app.services.sentinel_service import SentinelService


PRODUCT_ID = "11111111-2222-3333-4444-555555555555"
PRODUCT_NAME = "S2A_MSIL2A_20250707T081021_N0511_R078_T35LMD_20250707T114515.SAFE"
GRANULE = "L2A_T35LMD_A043862_20250707T082708"

B02 = "T35LMD_20250707T081021_B02_10m.jp2"
B03 = "T35LMD_20250707T081021_B03_10m.jp2"
B04 = "T35LMD_20250707T081021_B04_10m.jp2"
B08 = "T35LMD_20250707T081021_B08_10m.jp2"
SCL = "T35LMD_20250707T081021_SCL_20m.jp2"
METADATA = "MTD_MSIL2A.xml"

# Members are transferred concurrently, so a test that scripts
# more than one of them keys its replies by member rather than
# by arrival order. These are the sizes the listings declare.
MEMBER_SIZES = {
    METADATA: 10,
    B02: 40,
    B03: 40,
    B04: 40,
    B08: 40,
    SCL: 20,
}


class FakeListingResponse:
    def __init__(self, payload, status_code=200):
        self.status_code = status_code
        self._payload = payload
        self.headers = {}

    def json(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class FakeBandResponse:
    """One band transfer attempt."""

    def __init__(self, status_code=200, chunks=(), content_length=None, error=None):
        self.status_code = status_code
        self.chunks = list(chunks)
        self.headers = (
            {} if content_length is None else {"Content-Length": str(content_length)}
        )
        self.error = error

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def iter_content(self, chunk_size):
        for chunk in self.chunks:
            yield chunk
        if self.error is not None:
            raise self.error


def listings(sizes=True):
    """Node listings for every required product member."""

    def entry(name, size):
        return {"Name": name, "ContentLength": size} if sizes else {"Name": name}

    return {
        f"Nodes({PRODUCT_NAME})/Nodes": {
            "result": [
                entry(METADATA, MEMBER_SIZES[METADATA]),
                {"Name": "GRANULE"},
                {"Name": "INSPIRE.xml"},
            ]
        },
        "Nodes(R10m)/Nodes": {
            "result": [
                entry("T35LMD_20250707T081021_TCI_10m.jp2", 90),
                entry(B02, MEMBER_SIZES[B02]),
                entry(B03, MEMBER_SIZES[B03]),
                entry(B04, MEMBER_SIZES[B04]),
                entry(B08, MEMBER_SIZES[B08]),
            ]
        },
        "Nodes(R20m)/Nodes": {"result": [entry(SCL, MEMBER_SIZES[SCL])]},
        "Nodes(GRANULE)/Nodes": {"result": [{"Name": GRANULE}]},
    }


class FakeSession:
    """Scripted Copernicus replies.

    band_script is either a list, answered in order, which suits a
    test driving one member's transfer directly, or a dict keyed by
    member file name, which a whole acquisition needs because its
    members are transferred concurrently and so arrive in no fixed
    order.
    """

    def __init__(self, band_script, node_listings=None):
        self.headers = {}
        self.listings = node_listings if node_listings is not None else listings()
        self.band_script = (
            {name: list(script) for name, script in band_script.items()}
            if isinstance(band_script, dict)
            else list(band_script)
        )
        self.band_requests = []
        self._lock = threading.Lock()

    def _next_reply(self, url):
        if isinstance(self.band_script, dict):
            for name, script in self.band_script.items():
                if name in url:
                    if not script:
                        raise AssertionError(f"unscripted request for {name}")
                    return script.pop(0)
            raise AssertionError(f"no script for {url}")

        if not self.band_script:
            raise AssertionError(f"unscripted band request: {url}")
        return self.band_script.pop(0)

    def get(self, url, **kwargs):
        headers = dict(kwargs.get("headers") or {})

        if url.endswith("/Nodes"):
            # R10m/R20m and the product root before GRANULE:
            # their URLs contain it too.
            for key in (
                "Nodes(R10m)/Nodes",
                "Nodes(R20m)/Nodes",
                "Nodes(GRANULE)/Nodes",
                f"Nodes({PRODUCT_NAME})/Nodes",
            ):
                if url.endswith(key):
                    return FakeListingResponse(self.listings[key])
            raise AssertionError(f"unexpected listing request: {url}")

        with self._lock:
            self.band_requests.append((url, headers))
            reply = self._next_reply(url)

        return reply(headers) if callable(reply) else reply

    def requests_for(self, member):
        """Every band request made for one member, in order."""

        return [
            (url, headers)
            for url, headers in self.band_requests
            if member in url
        ]


def make_service(band_script, node_listings=None):
    service = CopernicusService()
    service.session = FakeSession(band_script, node_listings)
    # Pre-authenticated so no token request is attempted.
    service._access_token = "test-token"
    service._token_expires_at = None
    return service


def reset_error():
    return requests.exceptions.ChunkedEncodingError("connection reset")


# =========================================================
# LOCATING BANDS
# =========================================================


def test_only_the_members_analysis_reads_are_requested():
    service = make_service([])

    bands = service.locate_required_band_nodes(PRODUCT_ID, PRODUCT_NAME)

    # Level-2A metadata, the four 10 m bands NDVI and the
    # true-colour preview read, and the 20 m SCL. No more.
    assert [band["file_name"] for band in bands] == [
        METADATA,
        B02,
        B03,
        B04,
        B08,
        SCL,
    ]
    # TCI is present in the listing and deliberately not fetched.
    assert all("TCI" not in band["file_name"] for band in bands)
    # Paths mirror the SAFE layout so extraction is unchanged.
    assert bands[0]["archive_path"] == f"{PRODUCT_NAME}/{METADATA}"
    assert bands[3]["archive_path"] == (
        f"{PRODUCT_NAME}/GRANULE/{GRANULE}/IMG_DATA/R10m/{B04}"
    )
    assert bands[-1]["archive_path"].endswith(f"/IMG_DATA/R20m/{SCL}")
    assert all(band["url"].endswith("/$value") for band in bands)


def test_the_true_colour_bands_the_preview_needs_are_requested():
    """B02 and B03 are inputs, not extras.

    render_rgb_preview opens B04/B03/B02 as red/green/blue, and
    every completeness check in the system requires them. A
    product acquired without them is rejected as incomplete after
    its bands have already been downloaded and unpacked.
    """

    service = make_service([])

    names = [
        band["file_name"]
        for band in service.locate_required_band_nodes(PRODUCT_ID, PRODUCT_NAME)
    ]

    assert B02 in names
    assert B03 in names
    assert METADATA in names


def test_a_product_without_level_2a_metadata_is_rejected():
    without_metadata = listings()
    without_metadata[f"Nodes({PRODUCT_NAME})/Nodes"] = {
        "result": [{"Name": "MTD_MSIL1C.xml"}, {"Name": "GRANULE"}]
    }
    service = make_service([], without_metadata)

    with pytest.raises(RuntimeError, match="Level-2A"):
        service.locate_required_band_nodes(PRODUCT_ID, PRODUCT_NAME)


def test_a_level_1c_product_without_an_scl_band_is_rejected():
    without_scl = listings()
    without_scl["Nodes(R20m)/Nodes"] = {"result": [{"Name": "something_else.jp2"}]}
    service = make_service([], without_scl)

    with pytest.raises(RuntimeError, match="missing a band required"):
        service.locate_required_band_nodes(PRODUCT_ID, PRODUCT_NAME)


# =========================================================
# RESUMING
# =========================================================


def test_a_dropped_transfer_resumes_from_the_bytes_already_written(tmp_path):
    part = tmp_path / f"{B04}.part"
    script = [
        # First attempt dies after 10 of 40 bytes.
        FakeBandResponse(200, [b"a" * 10], error=reset_error()),
        # Resume delivers the remaining 30.
        FakeBandResponse(206, [b"b" * 30]),
    ]
    service = make_service(script)
    seen: list[int] = []

    total = service._download_node_resumable(
        url="https://example.invalid/band/$value",
        part_path=part,
        expected_size=40,
        on_progress=seen.append,
    )

    assert total == 40
    assert part.read_bytes() == b"a" * 10 + b"b" * 30
    # The second attempt asked to continue, it did not start again.
    assert service.session.band_requests[1][1]["Range"] == "bytes=10-"
    assert max(seen) == 40


def test_a_server_ignoring_range_restarts_the_band_instead_of_appending(tmp_path):
    part = tmp_path / f"{B04}.part"
    part.write_bytes(b"x" * 10)
    # 200, not 206: the whole object is coming, so the 10 stale bytes
    # must be discarded rather than kept as a prefix.
    service = make_service([FakeBandResponse(200, [b"y" * 40])])

    total = service._download_node_resumable(
        url="https://example.invalid/band/$value",
        part_path=part,
        expected_size=40,
        on_progress=lambda _n: None,
    )

    assert total == 40
    assert part.read_bytes() == b"y" * 40


def test_a_partial_file_past_the_object_end_is_discarded_and_refetched(tmp_path):
    part = tmp_path / f"{B04}.part"
    part.write_bytes(b"z" * 99)
    script = [
        FakeBandResponse(416),
        FakeBandResponse(200, [b"w" * 40]),
    ]
    service = make_service(script)

    total = service._download_node_resumable(
        url="https://example.invalid/band/$value",
        part_path=part,
        expected_size=40,
        on_progress=lambda _n: None,
    )

    assert total == 40
    assert part.read_bytes() == b"w" * 40


def test_an_already_complete_part_file_is_not_transferred_again(tmp_path):
    part = tmp_path / f"{B04}.part"
    part.write_bytes(b"q" * 40)
    service = make_service([])

    total = service._download_node_resumable(
        url="https://example.invalid/band/$value",
        part_path=part,
        expected_size=40,
        on_progress=lambda _n: None,
    )

    assert total == 40
    assert service.session.band_requests == []


def test_a_permanently_denied_band_is_not_retried(tmp_path):
    service = make_service([FakeBandResponse(403)])

    with pytest.raises(CopernicusAuthorizationError):
        service._download_node_resumable(
            url="https://example.invalid/band/$value",
            part_path=tmp_path / "band.part",
            expected_size=40,
            on_progress=lambda _n: None,
        )

    assert len(service.session.band_requests) == 1


def test_a_link_that_never_settles_fails_with_a_resumable_explanation(tmp_path, monkeypatch):
    monkeypatch.setattr(CopernicusService, "BAND_ATTEMPT_LIMIT", 3)
    monkeypatch.setattr("app.services.copernicus_service.time.sleep", lambda _s: None)
    part = tmp_path / f"{B04}.part"
    service = make_service(
        [FakeBandResponse(200, [b"a" * 5], error=reset_error()) for _ in range(3)]
    )

    with pytest.raises(RuntimeError, match="resumes instead of starting again"):
        service._download_node_resumable(
            url="https://example.invalid/band/$value",
            part_path=part,
            expected_size=40,
            on_progress=lambda _n: None,
        )

    # The bytes received are kept, which is what lets a retry continue.
    assert part.is_file()
    assert part.stat().st_size > 0


# =========================================================
# WHOLE ACQUISITION
# =========================================================


def whole_product(fill=None):
    """A reply per member that delivers it in one chunk."""

    letters = {
        METADATA: b"M",
        B02: b"B",
        B03: b"G",
        B04: b"R",
        B08: b"N",
        SCL: b"S",
    }
    return {
        name: [
            FakeBandResponse(
                200,
                [(fill or letters[name]) * MEMBER_SIZES[name]],
            )
        ]
        for name in MEMBER_SIZES
    }


def test_members_are_assembled_into_an_archive_the_validator_accepts(tmp_path):
    service = make_service(whole_product())
    destination = tmp_path / f"{PRODUCT_NAME}.zip"

    saved = service.download_product_bands(
        product_id=PRODUCT_ID,
        product_name=PRODUCT_NAME,
        destination=destination,
        progress_callback=None,
    )

    assert saved == destination
    assert zipfile.is_zipfile(saved)
    # The validator and the NDVI pipeline must accept this.
    SentinelService._validate_downloaded_product(saved)

    with zipfile.ZipFile(saved) as archive:
        names = archive.namelist()
        assert sorted(Path(n).name for n in names) == sorted(MEMBER_SIZES)
        assert archive.read(
            f"{PRODUCT_NAME}/GRANULE/{GRANULE}/IMG_DATA/R20m/{SCL}"
        ) == b"S" * 20
        assert archive.read(f"{PRODUCT_NAME}/{METADATA}") == b"M" * 10

    # Staged members are cleared only once the archive exists.
    assert not (tmp_path / f"{destination.name}.bands").exists()
    assert not destination.with_suffix(".zip.part").exists()


def test_members_are_transferred_concurrently(tmp_path):
    """All members must be in flight at once, not one after another.

    This is what pays for carrying B02, B03 and the metadata: the
    officer waits for the largest member rather than for the sum
    of all of them.
    """

    lock = threading.Lock()
    state = {"in_flight": 0, "most": 0}

    class Concurrent(FakeBandResponse):
        def iter_content(self, chunk_size):
            with lock:
                state["in_flight"] += 1
                state["most"] = max(state["most"], state["in_flight"])
            # Long enough that a sequential implementation cannot
            # overlap two transfers by accident, short enough not
            # to slow the suite.
            time.sleep(0.05)
            try:
                yield from super().iter_content(chunk_size)
            finally:
                with lock:
                    state["in_flight"] -= 1

    service = make_service(
        {
            name: [Concurrent(200, [b"X" * MEMBER_SIZES[name]])]
            for name in MEMBER_SIZES
        }
    )

    service.download_product_bands(
        product_id=PRODUCT_ID,
        product_name=PRODUCT_NAME,
        destination=tmp_path / f"{PRODUCT_NAME}.zip",
        progress_callback=None,
    )

    assert state["most"] == min(
        CopernicusService.BAND_TRANSFER_WORKERS,
        len(MEMBER_SIZES),
    ), "every available worker must be transferring at once"
    assert state["in_flight"] == 0


def test_staged_members_are_handed_over_instead_of_deleted(tmp_path):
    """A caller that will place the files itself claims them here.

    They are the same bytes the archive holds, so unpacking them
    back out of it would read and write every one again.
    """

    service = make_service(whole_product())
    destination = tmp_path / f"{PRODUCT_NAME}.zip"
    claimed: dict[str, Path] = {}

    service.download_product_bands(
        product_id=PRODUCT_ID,
        product_name=PRODUCT_NAME,
        destination=destination,
        progress_callback=None,
        staged_band_sink=claimed.update,
    )

    assert destination.is_file()
    assert sorted(Path(path).name for path in claimed) == sorted(MEMBER_SIZES)
    assert all(path.is_file() for path in claimed.values())
    assert claimed[f"{PRODUCT_NAME}/{METADATA}"].read_bytes() == b"M" * 10


def test_progress_is_measured_across_all_members_and_never_claims_completion(tmp_path):
    # Two chunks per member, so progress is reported part-way
    # through each one as well as at its end.
    service = make_service(
        {
            name: [
                FakeBandResponse(
                    200,
                    [
                        b"X" * (MEMBER_SIZES[name] // 2),
                        b"X" * (MEMBER_SIZES[name] - MEMBER_SIZES[name] // 2),
                    ],
                )
            ]
            for name in MEMBER_SIZES
        }
    )
    reports: list[tuple[str, int, int | None]] = []
    lock = threading.Lock()

    def record(stage, downloaded, total):
        # Reports arrive from several transfer threads.
        with lock:
            reports.append((stage, downloaded, total))

    service.download_product_bands(
        product_id=PRODUCT_ID,
        product_name=PRODUCT_NAME,
        destination=tmp_path / f"{PRODUCT_NAME}.zip",
        progress_callback=record,
    )

    expected_total = sum(MEMBER_SIZES.values())
    totals = {total for _s, _d, total in reports}
    assert totals == {expected_total}, "total is the sum of every member's size"

    downloading = [d for s, d, _t in reports if s == "DOWNLOADING"]
    # The figure is the sum across concurrent transfers, so no
    # member's count can be reported as if it were the whole.
    assert max(downloading) <= expected_total
    assert reports[-1][0] == "VALIDATING"
    assert reports[-1][1] == expected_total


def test_progress_is_never_reported_from_two_threads_at_once(tmp_path):
    """Concurrent transfers must not mean concurrent callbacks.

    The caller records progress against a database session. A
    SQLAlchemy Session operated on by two threads at once raises
    IllegalStateChangeError, which killed every acquisition the
    moment the transfers were made parallel. The callback is
    invoked under the lock that guards the byte count, so a
    caller does not have to defend itself.
    """

    inside = {"now": 0, "most": 0}
    plain_lock = threading.Lock()

    def record(_stage, _downloaded, _total):
        with plain_lock:
            inside["now"] += 1
            inside["most"] = max(inside["most"], inside["now"])
        # Long enough for an unguarded implementation to overlap.
        time.sleep(0.01)
        with plain_lock:
            inside["now"] -= 1

    service = make_service(
        {
            name: [
                FakeBandResponse(
                    200,
                    [b"X" * (MEMBER_SIZES[name] // 2)] * 2,
                )
            ]
            for name in MEMBER_SIZES
        }
    )

    service.download_product_bands(
        product_id=PRODUCT_ID,
        product_name=PRODUCT_NAME,
        destination=tmp_path / f"{PRODUCT_NAME}.zip",
        progress_callback=record,
    )

    assert inside["most"] == 1


def test_an_unknown_member_size_reports_indeterminate_progress(tmp_path):
    # No ContentLength in the listing, and the size probe fails
    # too. Sizes are resolved for every member before any
    # transfer starts, so each member answers a failed probe
    # first and its transfer second.
    letters = {
        METADATA: b"M",
        B02: b"B",
        B03: b"G",
        B04: b"R",
        B08: b"N",
        SCL: b"S",
    }
    service = make_service(
        {
            name: [
                FakeBandResponse(500),
                FakeBandResponse(200, [letters[name] * MEMBER_SIZES[name]]),
            ]
            for name in MEMBER_SIZES
        },
        listings(sizes=False),
    )
    reports: list[tuple[str, int, int | None]] = []
    lock = threading.Lock()

    def record(stage, downloaded, total):
        with lock:
            reports.append((stage, downloaded, total))

    service.download_product_bands(
        product_id=PRODUCT_ID,
        product_name=PRODUCT_NAME,
        destination=tmp_path / f"{PRODUCT_NAME}.zip",
        progress_callback=record,
    )

    # No total means no percentage may be invented downstream.
    assert all(total is None for _s, _d, total in reports)
    assert max(d for _s, d, _t in reports) == sum(MEMBER_SIZES.values())


def test_a_failed_acquisition_keeps_its_bands_so_a_retry_resumes(tmp_path, monkeypatch):
    monkeypatch.setattr(CopernicusService, "BAND_ATTEMPT_LIMIT", 2)
    monkeypatch.setattr("app.services.copernicus_service.time.sleep", lambda _s: None)
    destination = tmp_path / f"{PRODUCT_NAME}.zip"

    script = whole_product()
    # B08 never completes: two attempts, both cut short, which is
    # the limit set above.
    script[B08] = [
        FakeBandResponse(200, [b"N" * 15], error=reset_error()),
        FakeBandResponse(206, [b"N" * 5], error=reset_error()),
    ]
    failing = make_service(script)

    with pytest.raises(RuntimeError):
        failing.download_product_bands(
            product_id=PRODUCT_ID,
            product_name=PRODUCT_NAME,
            destination=destination,
            progress_callback=None,
        )

    staging = tmp_path / f"{destination.name}.bands"
    assert (staging / f"{B04}.part").read_bytes() == b"R" * 40
    assert (staging / f"{B08}.part").stat().st_size == 20
    assert not destination.exists(), "nothing may look acquired"

    # The retry resumes: every other member is already whole, and
    # B08 continues from byte 20 rather than starting again.
    resuming = make_service({B08: [FakeBandResponse(206, [b"N" * 20])]})
    resuming.download_product_bands(
        product_id=PRODUCT_ID,
        product_name=PRODUCT_NAME,
        destination=destination,
        progress_callback=None,
    )

    assert destination.is_file()
    SentinelService._validate_downloaded_product(destination)
    requested = resuming.session.band_requests
    assert len(requested) == 1, "only the unfinished member was transferred"
    assert requested[0][1]["Range"] == "bytes=20-", "B08 resumed, not restarted"
