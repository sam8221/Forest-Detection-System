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

B04 = "T35LMD_20250707T081021_B04_10m.jp2"
B08 = "T35LMD_20250707T081021_B08_10m.jp2"
SCL = "T35LMD_20250707T081021_SCL_20m.jp2"


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
    """Node listings for the three required bands."""

    def entry(name, size):
        return {"Name": name, "ContentLength": size} if sizes else {"Name": name}

    return {
        "Nodes(R10m)/Nodes": {
            "result": [
                entry("T35LMD_20250707T081021_TCI_10m.jp2", 90),
                entry(B04, 40),
                entry(B08, 40),
            ]
        },
        "Nodes(R20m)/Nodes": {"result": [entry(SCL, 20)]},
        "Nodes(GRANULE)/Nodes": {"result": [{"Name": GRANULE}]},
    }


class FakeSession:
    def __init__(self, band_script, node_listings=None):
        self.headers = {}
        self.listings = node_listings if node_listings is not None else listings()
        self.band_script = list(band_script)
        self.band_requests = []

    def get(self, url, **kwargs):
        headers = dict(kwargs.get("headers") or {})

        if url.endswith("/Nodes"):
            # R10m/R20m before GRANULE: their URLs contain it too.
            for key in ("Nodes(R10m)/Nodes", "Nodes(R20m)/Nodes", "Nodes(GRANULE)/Nodes"):
                if url.endswith(key):
                    return FakeListingResponse(self.listings[key])
            raise AssertionError(f"unexpected listing request: {url}")

        self.band_requests.append((url, headers))
        if not self.band_script:
            raise AssertionError(f"unscripted band request: {url}")
        nxt = self.band_script.pop(0)
        return nxt(headers) if callable(nxt) else nxt


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


def test_only_the_three_bands_analysis_reads_are_requested():
    service = make_service([])

    bands = service.locate_required_band_nodes(PRODUCT_ID, PRODUCT_NAME)

    assert [band["file_name"] for band in bands] == [B04, B08, SCL]
    # TCI is present in the listing and deliberately not fetched.
    assert all("TCI" not in band["file_name"] for band in bands)
    # Paths mirror the SAFE layout so extraction is unchanged.
    assert bands[0]["archive_path"] == (
        f"{PRODUCT_NAME}/GRANULE/{GRANULE}/IMG_DATA/R10m/{B04}"
    )
    assert bands[2]["archive_path"].endswith(f"/IMG_DATA/R20m/{SCL}")
    assert all(band["url"].endswith("/$value") for band in bands)


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


def test_bands_are_assembled_into_an_archive_the_existing_validator_accepts(tmp_path):
    service = make_service(
        [
            FakeBandResponse(200, [b"R" * 40]),
            FakeBandResponse(200, [b"N" * 40]),
            FakeBandResponse(200, [b"S" * 20]),
        ]
    )
    destination = tmp_path / f"{PRODUCT_NAME}.zip"

    saved = service.download_product_bands(
        product_id=PRODUCT_ID,
        product_name=PRODUCT_NAME,
        destination=destination,
        progress_callback=None,
    )

    assert saved == destination
    assert zipfile.is_zipfile(saved)
    # The unchanged validator and NDVI pipeline must accept this.
    SentinelService._validate_downloaded_product(saved)

    with zipfile.ZipFile(saved) as archive:
        names = archive.namelist()
        assert sorted(Path(n).name for n in names) == sorted([B04, B08, SCL])
        assert archive.read(
            f"{PRODUCT_NAME}/GRANULE/{GRANULE}/IMG_DATA/R20m/{SCL}"
        ) == b"S" * 20

    # Staged bands are cleared only once the archive exists.
    assert not (tmp_path / f"{destination.name}.bands").exists()
    assert not destination.with_suffix(".zip.part").exists()


def test_progress_is_measured_across_all_bands_and_never_claims_completion(tmp_path):
    service = make_service(
        [
            FakeBandResponse(200, [b"R" * 20, b"R" * 20]),
            FakeBandResponse(200, [b"N" * 20, b"N" * 20]),
            FakeBandResponse(200, [b"S" * 20]),
        ]
    )
    reports: list[tuple[str, int, int | None]] = []

    service.download_product_bands(
        product_id=PRODUCT_ID,
        product_name=PRODUCT_NAME,
        destination=tmp_path / f"{PRODUCT_NAME}.zip",
        progress_callback=lambda s, d, t: reports.append((s, d, t)),
    )

    totals = {total for _s, _d, total in reports}
    assert totals == {100}, "total is the sum of the three band sizes"

    downloading = [d for s, d, _t in reports if s == "DOWNLOADING"]
    assert downloading == sorted(downloading), "byte count never goes backwards"
    assert max(downloading) <= 100

    # The second band's progress is offset by the first, not restarted:
    # its halfway point reads 60, not 20.
    assert 60 in downloading
    assert 80 in downloading
    assert reports[-1][0] == "VALIDATING"
    assert reports[-1][1] == 100


def test_an_unknown_band_size_reports_indeterminate_progress(tmp_path):
    # No ContentLength in the listing, and the size probe fails too.
    # Sizes are resolved for every band first, so the three failed
    # probes precede the three transfers.
    service = make_service(
        [
            FakeBandResponse(500),
            FakeBandResponse(500),
            FakeBandResponse(500),
            FakeBandResponse(200, [b"R" * 40]),
            FakeBandResponse(200, [b"N" * 40]),
            FakeBandResponse(200, [b"S" * 20]),
        ],
        listings(sizes=False),
    )
    reports: list[tuple[str, int, int | None]] = []

    service.download_product_bands(
        product_id=PRODUCT_ID,
        product_name=PRODUCT_NAME,
        destination=tmp_path / f"{PRODUCT_NAME}.zip",
        progress_callback=lambda s, d, t: reports.append((s, d, t)),
    )

    # No total means no percentage may be invented downstream.
    assert all(total is None for _s, _d, total in reports)
    assert max(d for _s, d, _t in reports) == 100


def test_a_failed_acquisition_keeps_its_bands_so_a_retry_resumes(tmp_path, monkeypatch):
    monkeypatch.setattr(CopernicusService, "BAND_ATTEMPT_LIMIT", 2)
    monkeypatch.setattr("app.services.copernicus_service.time.sleep", lambda _s: None)
    destination = tmp_path / f"{PRODUCT_NAME}.zip"

    failing = make_service(
        [
            FakeBandResponse(200, [b"R" * 40]),
            # B08 never completes.
            FakeBandResponse(200, [b"N" * 15], error=reset_error()),
            FakeBandResponse(206, [b"N" * 5], error=reset_error()),
        ]
    )

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

    # The retry resumes: B04 is already whole, B08 continues from byte 20.
    resuming = make_service(
        [
            FakeBandResponse(206, [b"N" * 20]),
            FakeBandResponse(200, [b"S" * 20]),
        ]
    )
    resuming.download_product_bands(
        product_id=PRODUCT_ID,
        product_name=PRODUCT_NAME,
        destination=destination,
        progress_callback=None,
    )

    assert destination.is_file()
    SentinelService._validate_downloaded_product(destination)
    requested = resuming.session.band_requests
    assert requested[0][1]["Range"] == "bytes=20-", "B08 resumed, not restarted"
    assert len(requested) == 2, "B04 was not transferred a second time"
