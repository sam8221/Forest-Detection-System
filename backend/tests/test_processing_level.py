"""
Recognition of Sentinel-2 processing levels.

The pipeline requires Level-2A, and the same level reaches
the database under several names depending on which code path
registered the product. These tests pin which spellings count
as Level-2A, which do not, and what is stored for a newly
registered product.
"""

from types import SimpleNamespace

import pytest

from app.core.constants import (
    SENTINEL2_LEVEL_2A,
    is_level_2a,
    normalize_processing_level,
    processing_level_key,
)


# =========================================================
# RECOGNITION
# =========================================================

@pytest.mark.parametrize(
    "spelling",
    [
        # Written by sentinel_service when it registers a
        # product itself.
        "L2A",
        # The Copernicus processingLevel attribute.
        "Level-2A",
        # The Copernicus productType, which copernicus_service
        # falls back to when processingLevel is absent.
        "S2MSI2A",
        # Seen in product names.
        "MSIL2A",
        # Case and separators must not matter.
        "l2a",
        "level_2a",
        "LEVEL-2A",
        "  L2A  ",
    ],
)
def test_level_2a_spellings_are_recognised(spelling):
    assert is_level_2a(spelling) is True


@pytest.mark.parametrize(
    "spelling",
    [
        # Level-1C is top-of-atmosphere and carries no SCL
        # band, so it can be neither masked nor compared with
        # a surface reflectance scene. None of its spellings
        # may slip through.
        "L1C",
        "Level-1C",
        "S2MSI1C",
        "MSIL1C",
        "l1c",
        # Not a Sentinel-2 level at all.
        "L3A",
        "Landsat",
        # A level that was never recorded is unusable, not
        # assumed to be Level-2A.
        "",
        "   ",
        None,
    ],
)
def test_anything_that_is_not_level_2a_is_rejected(spelling):
    assert is_level_2a(spelling) is False


def test_recognition_is_by_explicit_spelling_not_by_resemblance():
    """
    The accepted spellings are an explicit set. A value that
    merely contains "2A", or that looks like one of them with
    something appended, is not Level-2A.
    """

    assert is_level_2a("L2A_PARTIAL") is False
    assert is_level_2a("NOT-L2A-REALLY") is False
    assert is_level_2a("2A") is False


def test_key_folds_case_and_discards_separators():
    assert processing_level_key("Level-2A") == "LEVEL2A"
    assert processing_level_key("level_2a") == "LEVEL2A"
    assert processing_level_key(" l2a ") == "L2A"


# =========================================================
# WHAT GETS STORED
# =========================================================

@pytest.mark.parametrize(
    "spelling",
    ["L2A", "Level-2A", "S2MSI2A", "MSIL2A", "level_2a"],
)
def test_every_level_2a_spelling_is_stored_canonically(spelling):
    assert normalize_processing_level(spelling) == SENTINEL2_LEVEL_2A
    assert SENTINEL2_LEVEL_2A == "L2A"


@pytest.mark.parametrize("spelling", ["L1C", "Level-1C", "S2MSI1C", "L3A"])
def test_an_unrecognised_level_is_stored_as_the_catalogue_reported_it(spelling):
    """
    Rewriting it would hide what was actually acquired. The
    row keeps the catalogue's own value and simply fails the
    Level-2A check.
    """

    assert normalize_processing_level(spelling) == spelling
    assert is_level_2a(normalize_processing_level(spelling)) is False


def test_registering_a_product_stores_the_canonical_spelling():
    """
    sentinel_service.register_satellite_image is the only place
    a satellite_images row is created, so normalising there is
    what keeps newly registered products consistent.
    """

    from datetime import date

    from app.services.sentinel_service import SentinelService

    created = {}

    class RecordingRepository:
        def get_by_product_id(self, product_id):
            return None

        def create(self, image):
            created["image"] = image
            return image

    service = SentinelService.__new__(SentinelService)
    service.repository = RecordingRepository()
    service.db = SimpleNamespace(
        add=lambda image: created.setdefault("image", image),
        commit=lambda: None,
        refresh=lambda image: None,
    )

    image = service.register_satellite_image(
        forest_area=SimpleNamespace(id=4),
        product_id="S2C_MSIL2A_20260910T075621",
        tile_id="T35LPF",
        acquisition_date=date(2026, 9, 10),
        cloud_cover=4.5,
        file_name="product.SAFE.zip",
        storage_path="/storage/product.SAFE.zip",
        file_size_mb=640.0,
        # The spelling the Copernicus catalogue hands over.
        processing_level="S2MSI2A",
    )

    assert image.processing_level == "L2A"
    assert is_level_2a(image.processing_level) is True
