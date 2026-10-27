"""Explicit user-selected Sentinel-2 observation pair validation."""

from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

import pytest

import app.api.satellite_images as satellite_images_api
from app.schemas.satellite_image import (
    SatelliteImageAnalysisResponse,
    SatelliteImageResponse,
)
from app.services.analysis_service import AnalysisService
from app.services.satellite_image_selection_service import (
    SatelliteImageSelectionService,
)
from app.services.storage_paths import shared_extract_root


def image(**changes):
    values = {
        "id": 1,
        "forest_area_id": 4,
        "is_active": True,
        "is_downloaded": True,
        "tile_id": "35KPV",
        "acquisition_date": date(2024, 4, 10),
        "processing_level": "L2A",
    }
    values.update(changes)
    return SimpleNamespace(**values)


def test_accepts_explicit_active_downloaded_same_tile_level2a_pair():
    previous = image(id=1, acquisition_date=date(2024, 4, 10))
    recent = image(id=2, acquisition_date=date(2025, 4, 10))
    assert SatelliteImageSelectionService.validate_explicit_pair(
        previous, recent, forest_area_id=4
    ) is None


def test_explicit_pair_order_uses_dates_not_database_ids():
    september = image(id=47, acquisition_date=date(2026, 9, 17), tile_id="T35LPF")
    october = image(id=46, acquisition_date=date(2026, 10, 18), tile_id="T35LPF")

    assert SatelliteImageSelectionService.validate_explicit_pair(
        september, october, forest_area_id=4
    ) is None
    with pytest.raises(ValueError, match="previous observation must have an earlier"):
        SatelliteImageSelectionService.validate_explicit_pair(
            october, september, forest_area_id=4
        )


def test_image_response_exposes_pair_eligibility_fields():
    fields = SatelliteImageResponse.model_fields
    assert "processing_level" in fields
    assert "is_active" in fields
    assert "is_downloaded" in fields


@pytest.mark.parametrize(
    "record,files,expected,reason",
    [
        (image(), True, True, None),
        (image(is_active=False), True, False, "inactive"),
        (image(is_downloaded=False), False, False, "not been downloaded"),
        (image(processing_level="L1C"), True, False, "Level-2A"),
        (image(), False, False, "files are missing"),
    ],
)
def test_analysis_readiness_reports_real_product_eligibility(
    record, files, expected, reason
):
    ready, explanation = SatelliteImageSelectionService.analysis_readiness(
        record,
        files,
    )
    assert ready is expected
    if reason is None:
        assert explanation is None
    else:
        assert reason in explanation


def test_image_list_marks_products_ready_only_when_local_files_are_available(
    monkeypatch,
):
    now = datetime.now(timezone.utc)

    def listed_image(image_id):
        return SimpleNamespace(
            id=image_id,
            forest_area_id=4,
            product_id=f"S2_PRODUCT_{image_id}",
            tile_id="35KPV",
            acquisition_date=date(2025, 4, image_id),
            cloud_cover_percentage=8.5,
            file_name=f"product-{image_id}.zip",
            storage_path="private-storage-path",
            file_size_mb=1.0,
            processing_level="L2A",
            is_downloaded=True,
            is_processed=False,
            is_active=True,
            created_at=now,
            updated_at=now,
        )

    first = listed_image(1)
    second = listed_image(2)

    class LocalAvailability:
        def __init__(self, _db):
            pass

        def _usable_local_image(self, image_id):
            return first if image_id == first.id else None

    monkeypatch.setattr(
        satellite_images_api,
        "AnalysisService",
        LocalAvailability,
    )
    rows = satellite_images_api._analysis_candidate_responses(
        [first, second],
        object(),
    )

    assert rows[0]["is_ready_for_analysis"] is True
    assert rows[0]["readiness_reason"] is None
    assert rows[1]["is_ready_for_analysis"] is False
    assert "files are missing" in rows[1]["readiness_reason"]
    assert SatelliteImageAnalysisResponse.model_validate(rows[0])


def test_explicit_pair_reuses_only_its_own_extracted_product(tmp_path):
    image_record = image(id=11)
    image_record.file_name = "S2_EXACT_PRODUCT.zip"

    class FakeDatabase:
        def get(self, model, image_id):
            return image_record if image_id == image_record.id else None

    service = AnalysisService.__new__(AnalysisService)
    service.db = FakeDatabase()
    service.settings = SimpleNamespace(satellite_image_storage_path=Path(tmp_path))
    extracted = shared_extract_root(4, 11, storage_root=Path(tmp_path))
    extracted.mkdir(parents=True)
    (extracted / "S2_OTHER_PRODUCT.SAFE").mkdir()

    assert service._usable_local_image(11) is None

    exact_product = extracted / "S2_EXACT_PRODUCT.SAFE"
    granule = exact_product / "GRANULE" / "tile" / "IMG_DATA" / "R10m"
    granule.mkdir(parents=True)
    (exact_product / "MTD_MSIL2A.xml").write_text("<metadata />")
    for band in ("B02", "B03", "B04", "B08"):
        (granule / f"T35LPF_test_{band}_10m.jp2").write_bytes(b"band")
    scl = exact_product / "GRANULE" / "tile" / "IMG_DATA" / "R20m"
    scl.mkdir(parents=True)
    (scl / "T35LPF_test_SCL_20m.jp2").write_bytes(b"scl")

    assert service._usable_local_image(11) is image_record


def test_downloaded_archive_missing_required_bands_is_not_usable(tmp_path):
    image_record = image(id=12)
    image_record.file_name = "S2_EXACT_PRODUCT.SAFE.zip"

    class FakeDatabase:
        def get(self, model, image_id):
            return image_record if image_id == image_record.id else None

    service = AnalysisService.__new__(AnalysisService)
    service.db = FakeDatabase()
    service.settings = SimpleNamespace(satellite_image_storage_path=Path(tmp_path))
    archive_path = Path(tmp_path) / "4" / image_record.file_name
    archive_path.parent.mkdir(parents=True)
    with ZipFile(archive_path, "w") as archive:
        archive.writestr(
            "S2_EXACT_PRODUCT.SAFE/MTD_MSIL2A.xml",
            "<metadata />",
        )
        archive.writestr(
            "S2_EXACT_PRODUCT.SAFE/GRANULE/tile/IMG_DATA/R10m/T35LPF_test_B04_10m.jp2",
            b"red band only",
        )

    assert service._usable_local_image(image_record.id) is None


def test_archive_uses_its_valid_recorded_path_when_output_root_changes(tmp_path):
    image_record = image(id=13)
    image_record.file_name = "S2_RECORDED_PRODUCT.SAFE.zip"
    archive_path = tmp_path / "original-imagery" / image_record.file_name
    archive_path.parent.mkdir(parents=True)
    archive_path.write_bytes(b"real archive location")
    image_record.storage_path = str(archive_path)

    service = AnalysisService.__new__(AnalysisService)
    service.settings = SimpleNamespace(
        satellite_image_storage_path=tmp_path / "new-output-root"
    )

    assert service._local_archive_path(image_record) == archive_path.resolve()


@pytest.mark.parametrize(
    "previous,recent,forest_id,message",
    [
        (None, image(id=2), 4, "Both selected"),
        (image(), image(), 4, "different"),
        (image(forest_area_id=8), image(id=2, acquisition_date=date(2025, 4, 10)), 4, "belong"),
        (image(is_active=False), image(id=2, acquisition_date=date(2025, 4, 10)), 4, "active and downloaded"),
        (image(is_downloaded=False), image(id=2, acquisition_date=date(2025, 4, 10)), 4, "active and downloaded"),
        (image(), image(id=2, tile_id="35KQV", acquisition_date=date(2025, 4, 10)), 4, "coverage"),
        (image(), image(id=2, acquisition_date=date(2024, 4, 9)), 4, "earlier"),
        (image(processing_level="L1C"), image(id=2, acquisition_date=date(2025, 4, 10)), 4, "Level-2A"),
    ],
)
def test_rejects_incomplete_or_incompatible_explicit_pair(
    previous, recent, forest_id, message
):
    with pytest.raises(ValueError, match=message):
        SatelliteImageSelectionService.validate_explicit_pair(
            previous, recent, forest_area_id=forest_id
        )


# =========================================================
# PROCESSING LEVEL SPELLINGS
#
# The same Level-2A product arrives under several names
# depending on which code path registered it: the Copernicus
# catalogue reports "Level-2A" on some responses,
# copernicus_service falls back to the product type
# "S2MSI2A", and sentinel_service writes "L2A" itself.
#
# Comparing against the single literal "L2A" made a genuine
# Level-2A pair unusable purely because of how it had been
# recorded. These tests pin the behaviour in both directions:
# every Level-2A spelling is accepted, and no Level-1C
# spelling is.
# =========================================================

LEVEL_2A_SPELLINGS = ["L2A", "S2MSI2A", "Level-2A", "level_2a", "MSIL2A"]

NOT_LEVEL_2A = ["L1C", "S2MSI1C", "Level-1C", "", None, "L3A"]


@pytest.mark.parametrize("spelling", LEVEL_2A_SPELLINGS)
def test_explicit_pair_accepts_every_level_2a_spelling(spelling):
    previous = image(
        id=1,
        acquisition_date=date(2024, 4, 10),
        processing_level=spelling,
    )
    recent = image(
        id=2,
        acquisition_date=date(2025, 4, 10),
        processing_level=spelling,
    )

    assert SatelliteImageSelectionService.validate_explicit_pair(
        previous, recent, forest_area_id=4
    ) is None


@pytest.mark.parametrize("spelling", NOT_LEVEL_2A)
def test_explicit_pair_rejects_anything_that_is_not_level_2a(spelling):
    previous = image(
        id=1,
        acquisition_date=date(2024, 4, 10),
        processing_level=spelling,
    )
    recent = image(id=2, acquisition_date=date(2025, 4, 10))

    with pytest.raises(ValueError, match="Level-2A"):
        SatelliteImageSelectionService.validate_explicit_pair(
            previous, recent, forest_area_id=4
        )


@pytest.mark.parametrize("spelling", LEVEL_2A_SPELLINGS)
def test_readiness_accepts_every_level_2a_spelling(spelling):
    ready, reason = SatelliteImageSelectionService.analysis_readiness(
        image(processing_level=spelling),
        local_files_available=True,
    )

    assert (ready, reason) == (True, None)


@pytest.mark.parametrize("spelling", NOT_LEVEL_2A)
def test_readiness_rejects_anything_that_is_not_level_2a(spelling):
    ready, reason = SatelliteImageSelectionService.analysis_readiness(
        image(processing_level=spelling),
        local_files_available=True,
    )

    assert ready is False
    assert "Level-2A" in reason


# =========================================================
# AUTOMATIC PAIR SELECTION
#
# The automatic path used to apply no processing-level rule
# at all: it ordered downloaded images by date and took the
# newest, so a Level-1C scene could be handed to a pipeline
# that cannot mask it.
#
# The rule is applied in Python rather than in SQL, because
# the level is stored under several spellings and matching
# them in SQL would mean normalising a column in the where
# clause. These tests therefore stand a fake session in for
# the database and supply the rows the query would return.
#
# What is deliberately not re-tested here is the SQL itself -
# the forest area, tile, date, downloaded and active filters.
# Those are unchanged, and asserting them against a fake that
# ignores filters would prove nothing. They are covered by
# the validation tests above, which apply the same rules to
# a pair in Python.
# =========================================================

class FakeQuery:
    """Returns one prepared result set, ignoring the filters."""

    def __init__(self, rows):
        self._rows = rows

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def all(self):
        return list(self._rows)


class FakeSession:
    """
    Answers each query() with the next prepared result set.

    A list of result sets rather than one, because
    get_latest_compatible_pair queries more than once and
    each call stands for a different set of candidates.
    """

    def __init__(self, *result_sets):
        self._result_sets = list(result_sets)
        self.queries = 0

    def query(self, *args, **kwargs):
        rows = (
            self._result_sets[self.queries]
            if self.queries < len(self._result_sets)
            else []
        )
        self.queries += 1
        return FakeQuery(rows)


def test_latest_image_is_the_newest_level_2a_not_the_newest_product():
    """A Level-1C scene carries no SCL band and cannot be masked."""

    level_1c = image(id=3, acquisition_date=date(2026, 10, 18), processing_level="L1C")
    level_2a = image(id=2, acquisition_date=date(2026, 9, 10))

    service = SatelliteImageSelectionService(
        FakeSession([level_1c, level_2a])
    )

    assert service.get_latest_image(forest_area_id=4) is level_2a


def test_latest_image_recognises_a_catalogue_spelling_of_level_2a():
    """The defect this guards: an S2MSI2A product looked unusable."""

    catalogue_spelling = image(id=9, processing_level="S2MSI2A")

    service = SatelliteImageSelectionService(
        FakeSession([catalogue_spelling])
    )

    assert service.get_latest_image(forest_area_id=4) is catalogue_spelling


def test_latest_image_is_none_when_only_level_1c_is_held():
    service = SatelliteImageSelectionService(
        FakeSession(
            [
                image(id=3, processing_level="L1C"),
                image(id=2, processing_level="S2MSI1C"),
            ]
        )
    )

    assert service.get_latest_image(forest_area_id=4) is None


def test_previous_image_skips_a_level_1c_baseline():
    """A baseline that cannot be cloud masked is not a baseline."""

    level_1c = image(id=5, acquisition_date=date(2025, 9, 25), processing_level="L1C")
    level_2a = image(id=4, acquisition_date=date(2025, 4, 10))

    service = SatelliteImageSelectionService(
        FakeSession([level_1c, level_2a])
    )

    previous = service.get_previous_image(
        latest_image=image(id=6, acquisition_date=date(2026, 9, 10)),
    )

    assert previous is level_2a


def test_compatible_pair_search_passes_over_a_level_1c_latest_image():
    """
    The newest product is Level-1C, so it is skipped before a
    baseline is even looked for; the search moves on to the
    Level-2A scene behind it.
    """

    level_1c = image(id=3, acquisition_date=date(2026, 10, 18), processing_level="L1C")
    level_2a = image(id=2, acquisition_date=date(2026, 9, 10))
    baseline = image(id=1, acquisition_date=date(2025, 9, 25))

    session = FakeSession([level_1c, level_2a], [baseline])
    service = SatelliteImageSelectionService(session)

    assert service.get_latest_compatible_pair(forest_area_id=4) == (
        baseline,
        level_2a,
    )

    # Two queries: the candidate list, then one baseline
    # lookup. A third would mean the Level-1C scene had been
    # taken seriously enough to search for a baseline for it.
    assert session.queries == 2


def test_final_pair_validation_rejects_a_non_level_2a_scene():
    """
    _validate_pair is the last gate before the pipeline. It
    repeats the processing-level rule so a pair assembled by
    some other route cannot bypass it.
    """

    service = SatelliteImageSelectionService.__new__(
        SatelliteImageSelectionService
    )

    with pytest.raises(ValueError, match="Level-2A processing"):
        service._validate_pair(
            previous_image=image(
                id=1,
                acquisition_date=date(2024, 4, 10),
                processing_level="L1C",
            ),
            latest_image=image(id=2, acquisition_date=date(2025, 4, 10)),
        )
