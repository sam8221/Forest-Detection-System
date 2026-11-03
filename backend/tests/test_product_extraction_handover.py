"""What acquisition leaves behind, and what extraction then has to do.

Three things have to agree about which members of a Level-2A product
this system reads: what CopernicusService downloads, what
SentinelProcessorService unpacks, and what the completeness checks
require. They disagreed once. Acquisition fetched B04, B08 and SCL
while the pipeline also needed B02, B03 and MTD_MSIL2A.xml, so every
freshly downloaded product was unpacked and then rejected:

    The selected Sentinel-2 archive is missing required Level-2A
    metadata or bands.

The analysis before it had already searched Copernicus again for
imagery it was holding on disk. These tests pin the agreement, and
the two savings that follow from it: nothing outside the required set
is unpacked, and a product just downloaded is not unpacked at all.

No credentials and no network are involved.
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.copernicus_service import CopernicusService
from app.services.sentinel_processor_service import (
    REQUIRED_PRODUCT_MEMBERS,
    SentinelProcessorService,
)
from app.services.sentinel_service import SentinelService
from app.services.storage_paths import shared_extract_root


# Shortened stand-ins for a real product and granule name, which
# are about 65 and 38 characters. Windows limits a path to 260 by
# default, and pytest's temporary directories are already long, so
# the real names leave no room beneath one. The structure is what
# these tests are about, not the length of the names.
PRODUCT = "S2A_TEST.SAFE"
GRANULE = "L2A_G1"


def member_paths() -> dict[str, str]:
    """Where each required member sits inside a SAFE product."""

    tile = "T35LMD"
    granule = f"{PRODUCT}/GRANULE/{GRANULE}/IMG_DATA"

    return {
        "MTD_MSIL2A.xml": f"{PRODUCT}/MTD_MSIL2A.xml",
        "_B02_10m.jp2": f"{granule}/R10m/{tile}_B02_10m.jp2",
        "_B03_10m.jp2": f"{granule}/R10m/{tile}_B03_10m.jp2",
        "_B04_10m.jp2": f"{granule}/R10m/{tile}_B04_10m.jp2",
        "_B08_10m.jp2": f"{granule}/R10m/{tile}_B08_10m.jp2",
        "_SCL_20m.jp2": f"{granule}/R20m/{tile}_SCL_20m.jp2",
    }


# A whole Level-2A product also carries these. The pipeline never
# opens any of them, and together they are most of its ~1 GB.
UNUSED_MEMBERS = (
    f"{PRODUCT}/GRANULE/{GRANULE}/IMG_DATA/R10m/T35LMD_TCI_10m.jp2",
    f"{PRODUCT}/GRANULE/{GRANULE}/IMG_DATA/R20m/T35LMD_B05_20m.jp2",
    f"{PRODUCT}/GRANULE/{GRANULE}/IMG_DATA/R60m/T35LMD_B01_60m.jp2",
    f"{PRODUCT}/GRANULE/{GRANULE}/QI_DATA/MSK_CLDPRB_20m.jp2",
    f"{PRODUCT}/INSPIRE.xml",
    f"{PRODUCT}/HTML/UserProduct_index.html",
)


def whole_product_archive(path: Path) -> Path:
    """An archive holding the required members and the rest besides."""

    with zipfile.ZipFile(path, "w") as archive:
        for member in member_paths().values():
            archive.writestr(member, b"required")
        for member in UNUSED_MEMBERS:
            archive.writestr(member, b"never opened by this pipeline")
    return path


# =========================================================
# ONE DEFINITION OF A USABLE PRODUCT
# =========================================================


def test_acquisition_fetches_exactly_what_the_pipeline_requires():
    """The download set and the required set are the same set."""

    downloaded = {
        suffix.casefold()
        for _resolution, suffix in CopernicusService.REQUIRED_BAND_NODES
    } | {name.casefold() for name in CopernicusService.REQUIRED_PRODUCT_NODES}

    required = {member.casefold() for member in REQUIRED_PRODUCT_MEMBERS}

    assert downloaded == required


# =========================================================
# SELECTIVE EXTRACTION
# =========================================================


def test_only_the_required_members_are_unpacked(tmp_path):
    archive = whole_product_archive(tmp_path / f"{PRODUCT}.zip")
    extract_directory = tmp_path / "extracted"

    SentinelProcessorService().extract_product(archive, extract_directory)

    unpacked = sorted(
        path.relative_to(extract_directory).as_posix()
        for path in extract_directory.rglob("*")
        if path.is_file()
    )

    assert unpacked == sorted(member_paths().values())
    for unused in UNUSED_MEMBERS:
        assert not (extract_directory / unused).exists()


def test_an_incomplete_archive_is_reported_rather_than_unpacked_whole(tmp_path):
    archive = tmp_path / "incomplete.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        # The NDVI bands only: what acquisition used to fetch.
        for suffix in ("_B04_10m.jp2", "_B08_10m.jp2", "_SCL_20m.jp2"):
            handle.writestr(member_paths()[suffix], b"required")
        for member in UNUSED_MEMBERS:
            handle.writestr(member, b"never opened by this pipeline")

    extract_directory = tmp_path / "extracted"

    with pytest.raises(ValueError, match="missing required Level-2A"):
        SentinelProcessorService().extract_product(archive, extract_directory)

    # The verdict did not cost a gigabyte of writes.
    for unused in UNUSED_MEMBERS:
        assert not (extract_directory / unused).exists()


def test_an_already_complete_extraction_is_not_repeated(tmp_path):
    extract_directory = tmp_path / "extracted"
    for member in member_paths().values():
        target = extract_directory / member
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"already here")

    # No archive at all: a complete tree must be enough.
    returned = SentinelProcessorService().extract_product(
        tmp_path / "absent.zip",
        extract_directory,
    )

    assert returned == extract_directory


# =========================================================
# HANDOVER FROM ACQUISITION TO EXTRACTION
# =========================================================


def test_downloaded_members_are_moved_into_the_extraction_directory(tmp_path, monkeypatch):
    """A product just downloaded does not need unpacking.

    The staged files are the same bytes the archive holds, and
    staging and extraction share a volume, so each one is a rename.
    Extracting instead would read and write all of them again.
    """

    service = SentinelService.__new__(SentinelService)
    service.settings = SimpleNamespace(satellite_image_storage_path=tmp_path)

    staging = tmp_path / f"{PRODUCT}.zip.bands"
    staging.mkdir()

    staged = {}
    for suffix, archive_path in member_paths().items():
        part = staging / f"{Path(archive_path).name}.part"
        part.write_bytes(suffix.encode())
        staged[archive_path] = part

    image = SimpleNamespace(id=55, forest_area_id=70, product_id="test-product")

    service._claim_staged_product(image, staged)

    extract_root = shared_extract_root(
        forest_area_id=70,
        satellite_image_id=55,
        storage_root=tmp_path,
    )

    # Placed exactly where extraction would have put them, so the
    # analysis finds a complete product and skips unpacking.
    assert SentinelProcessorService.has_complete_extracted_product(extract_root)
    assert (extract_root / member_paths()["_B04_10m.jp2"]).read_bytes() == b"_B04_10m.jp2"

    # Moved, not copied: nothing is left behind to go stale.
    assert not any(part.exists() for part in staged.values())
    assert not staging.exists()


def test_an_incomplete_registered_product_is_not_reused(tmp_path):
    """A row marked downloaded is not on its own evidence of a product.

    Four such rows existed: registered, marked downloaded, and
    pointing at archives holding only the NDVI bands. Reusing them
    meant the analysis accepted them here and rejected them later,
    and nothing ever replaced them, because this is the check that
    decides whether to acquire again.
    """

    service = SentinelService.__new__(SentinelService)
    service.settings = SimpleNamespace(satellite_image_storage_path=tmp_path)

    archive_directory = tmp_path / "70"
    archive_directory.mkdir()
    incomplete = archive_directory / f"{PRODUCT}.zip"
    with zipfile.ZipFile(incomplete, "w") as handle:
        for suffix in ("_B04_10m.jp2", "_B08_10m.jp2", "_SCL_20m.jp2"):
            handle.writestr(member_paths()[suffix], b"required")

    image = SimpleNamespace(
        id=57,
        forest_area_id=70,
        product_id="test-product",
        file_name=incomplete.name,
        storage_path=str(incomplete),
    )

    assert service.local_product_is_complete(image) is False

    # The same archive, now carrying every input, is reused.
    with zipfile.ZipFile(incomplete, "w") as handle:
        for member in member_paths().values():
            handle.writestr(member, b"required")

    assert service.local_product_is_complete(image) is True


def test_a_complete_extraction_is_enough_without_the_archive(tmp_path):
    """The pipeline reads the extracted tree, so that is checked first.

    An archive deleted to reclaim space does not make a product
    unusable while its extracted bands are still there.
    """

    service = SentinelService.__new__(SentinelService)
    service.settings = SimpleNamespace(satellite_image_storage_path=tmp_path)

    extract_root = shared_extract_root(
        forest_area_id=70,
        satellite_image_id=58,
        storage_root=tmp_path,
    )
    for member in member_paths().values():
        target = extract_root / member
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"required")

    image = SimpleNamespace(
        id=58,
        forest_area_id=70,
        product_id="test-product",
        file_name=f"{PRODUCT}.zip",
        storage_path=str(tmp_path / "70" / f"{PRODUCT}.zip"),
    )

    assert service.local_product_is_complete(image) is True


def test_an_unusable_registered_product_can_be_acquired_again(tmp_path, monkeypatch):
    """Registered must not mean unreachable.

    The acquire endpoint answered 409 "already been downloaded"
    for any registered product. Combined with the gap above, that
    left an officer with five products the catalogue showed as
    acquired, the analysis refused, and no control could replace.
    The refusal now depends on the files, not on the row.
    """

    from fastapi import BackgroundTasks, HTTPException, Response

    from app.api import satellite_images as api

    # The request schema requires a Copernicus-length identifier.
    complete_id = "complete-product-id"
    incomplete_id = "incomplete-product-id"

    complete = SimpleNamespace(id=1, product_id=complete_id)
    incomplete = SimpleNamespace(id=2, product_id=incomplete_id)
    registered = {complete_id: complete, incomplete_id: incomplete}

    class Forests:
        def __init__(self, _db):
            pass

        def get_by_id_for_user(self, forest_area_id, user):
            return SimpleNamespace(id=forest_area_id)

    class Images:
        def __init__(self, _db):
            pass

        def get_by_product_id(self, product_id):
            return registered.get(product_id)

    class Completeness:
        def __init__(self, _db):
            pass

        def local_product_is_complete(self, image):
            return image is complete

    class Jobs:
        def __init__(self, _db):
            pass

        def create_or_get_active(self, **_kwargs):
            return SimpleNamespace(job_id="job-1"), True

    monkeypatch.setattr(api, "ForestAreaRepository", Forests)
    monkeypatch.setattr(api, "SatelliteImageRepository", Images)
    monkeypatch.setattr(api, "SentinelService", Completeness)
    monkeypatch.setattr(api, "SatelliteDownloadJobService", Jobs)

    def acquire(product_id):
        return api.download_sentinel_product(
            forest_area_id=70,
            request=api.SatelliteDownloadRequest(
                product_id=product_id,
                product_name=PRODUCT,
                tile_id="T35LPG",
                acquisition_date="2026-10-27",
                cloud_cover=4.0,
            ),
            background_tasks=BackgroundTasks(),
            response=Response(),
            db=object(),
            current_user=SimpleNamespace(id=3),
        )

    with pytest.raises(HTTPException) as refused:
        acquire(complete_id)
    assert refused.value.status_code == 409

    # Neither an unusable registered product nor an unregistered
    # one is refused: both have to be fetched.
    assert acquire(incomplete_id).job_id == "job-1"
    assert acquire("unregistered-product-id").job_id == "job-1"


def test_a_failed_handover_leaves_the_archive_usable(tmp_path, caplog):
    """Placing the files is a saving, not a step the download needs.

    The archive is already saved and validated by this point, so the
    analysis can still unpack it. Raising here would fail an
    acquisition that in fact succeeded.
    """

    service = SentinelService.__new__(SentinelService)
    service.settings = SimpleNamespace(satellite_image_storage_path=tmp_path)

    image = SimpleNamespace(id=56, forest_area_id=70, product_id="test-product")
    missing = tmp_path / "staging" / "nothing-was-staged-here.part"

    service._claim_staged_product(image, {member_paths()["_B04_10m.jp2"]: missing})

    extract_root = shared_extract_root(
        forest_area_id=70,
        satellite_image_id=56,
        storage_root=tmp_path,
    )
    assert not SentinelProcessorService.has_complete_extracted_product(extract_root)
