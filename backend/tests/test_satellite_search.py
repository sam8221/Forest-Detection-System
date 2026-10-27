from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import satellite_images as satellite_images_api


def _forest():
    return SimpleNamespace(
        id=12,
        geometry=object(),
        forest_code="KTK-TEST",
        name="ktk testing",
        area_hectares=42.0,
    )


def _call_search():
    return satellite_images_api.search_sentinel_images_for_forest(
        forest_area_id=12,
        start_date="2026-10-04",
        end_date="2026-10-19",
        cloud_cover=30,
        limit=20,
        db=object(),
        current_user=SimpleNamespace(id=7),
    )


def _metadata(index):
    return {
        "product_id": f"sentinel-product-{index}",
        "product_name": f"Sentinel product {index}",
        "tile_id": "T35KPV",
        "acquisition_date": "2026-10-10T08:00:00Z",
        "cloud_cover": 12.5,
        "processing_level": "Level-2A",
        "online": True,
        "content_length": 1000,
        "geo_footprint": "POLYGON EMPTY",
    }


def test_valid_forest_search_returns_catalogue_products(monkeypatch):
    class ForestRepository:
        def __init__(self, _db):
            pass

        def get_by_id_for_user(self, *, forest_area_id, user):
            assert forest_area_id == 12
            assert user.id == 7
            return _forest()

    class FakeCopernicus:
        def search_products(self, **kwargs):
            assert kwargs == {
                "start_date": "2026-10-04",
                "end_date": "2026-10-19",
                "cloud_cover": 30,
                "geometry_wkt": "POLYGON ((0 0, 1 0, 1 1, 0 0))",
                "limit": 20,
            }
            return list(range(7))

        def get_product_metadata(self, product):
            return _metadata(product)

    monkeypatch.setattr(
        satellite_images_api,
        "ForestAreaRepository",
        ForestRepository,
    )
    monkeypatch.setattr(
        satellite_images_api,
        "to_shape",
        lambda _geometry: SimpleNamespace(
            wkt="POLYGON ((0 0, 1 0, 1 1, 0 0))"
        ),
    )
    monkeypatch.setattr(
        satellite_images_api,
        "CopernicusService",
        FakeCopernicus,
    )

    result = _call_search()

    assert result["forest_area"]["id"] == 12
    assert result["count"] == 7
    assert len(result["products"]) == 7
    assert result["products"][0]["product_id"] == "sentinel-product-0"


def test_invalid_date_range_is_rejected_before_catalogue_search():
    with pytest.raises(HTTPException) as error:
        satellite_images_api.search_sentinel_images_for_forest(
            forest_area_id=12,
            start_date="2026-10-20",
            end_date="2026-10-19",
            cloud_cover=30,
            limit=20,
            db=object(),
            current_user=SimpleNamespace(id=7),
        )

    assert error.value.status_code == 400
    assert error.value.detail == "start_date cannot be later than end_date."


def test_invalid_date_format_returns_clear_validation_error():
    with pytest.raises(HTTPException) as error:
        satellite_images_api.search_sentinel_images_for_forest(
            forest_area_id=12,
            start_date="04/10/2026",
            end_date="2026-10-19",
            cloud_cover=30,
            limit=20,
            db=object(),
            current_user=SimpleNamespace(id=7),
        )

    assert error.value.status_code == 400
    assert error.value.detail == "Dates must use YYYY-MM-DD format."


def test_copernicus_failure_is_returned_as_sanitized_gateway_error(monkeypatch):
    class ForestRepository:
        def __init__(self, _db):
            pass

        def get_by_id_for_user(self, **_kwargs):
            return _forest()

    class FailedCopernicus:
        def search_products(self, **_kwargs):
            raise RuntimeError("provider internal error and credential details")

    monkeypatch.setattr(
        satellite_images_api,
        "ForestAreaRepository",
        ForestRepository,
    )
    monkeypatch.setattr(
        satellite_images_api,
        "to_shape",
        lambda _geometry: SimpleNamespace(wkt="POLYGON EMPTY"),
    )
    monkeypatch.setattr(
        satellite_images_api,
        "CopernicusService",
        FailedCopernicus,
    )

    with pytest.raises(HTTPException) as error:
        _call_search()

    assert error.value.status_code == 502
    assert error.value.detail == "Unable to retrieve Sentinel-2 imagery from Copernicus."
    assert "credential" not in error.value.detail


def test_copernicus_metadata_failure_is_also_sanitized(monkeypatch):
    class ForestRepository:
        def __init__(self, _db):
            pass

        def get_by_id_for_user(self, **_kwargs):
            return _forest()

    class FailedMetadataCopernicus:
        def search_products(self, **_kwargs):
            return [object()]

        def get_product_metadata(self, _product):
            raise RuntimeError("provider exception with credential details")

    monkeypatch.setattr(
        satellite_images_api,
        "ForestAreaRepository",
        ForestRepository,
    )
    monkeypatch.setattr(
        satellite_images_api,
        "to_shape",
        lambda _geometry: SimpleNamespace(wkt="POLYGON EMPTY"),
    )
    monkeypatch.setattr(
        satellite_images_api,
        "CopernicusService",
        FailedMetadataCopernicus,
    )

    with pytest.raises(HTTPException) as error:
        _call_search()

    assert error.value.status_code == 502
    assert error.value.detail == "Unable to retrieve Sentinel-2 imagery from Copernicus."
    assert "credential" not in error.value.detail
