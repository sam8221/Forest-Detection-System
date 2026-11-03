from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
import requests
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.satellite_catalogue_product import SatelliteCatalogueProduct
from app.services import copernicus_service as copernicus_module
from app.services.copernicus_service import CopernicusService
from app.services.satellite_catalogue_service import (
    catalogue_filters,
    parse_provider_datetime,
    persist_catalogue_page,
)


class FakeCatalogueResponse:
    def __init__(self, payload, status_code=200, headers=None):
        self.payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(
                f"HTTP {self.status_code}", response=self
            )


class FakeCatalogueSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


def _service(responses):
    service = object.__new__(CopernicusService)
    service.session = FakeCatalogueSession(responses)
    service._ensure_authenticated = lambda: None
    service._refresh_or_authenticate = lambda: None
    return service


def _provider_product(product_id, tile):
    return {
        "Id": product_id,
        "Name": f"S2A_MSIL2A_20261018T081611_N0500_R121_{tile}_20261018T110000.SAFE",
        "ContentDate": {"Start": "2026-10-18T08:16:11.000Z"},
        "Attributes": [
            {"Name": "tileId", "Value": tile.removeprefix("T")},
            {"Name": "cloudCover", "Value": 12.5},
            {"Name": "productType", "Value": "S2MSI2A"},
        ],
    }


def test_search_products_follows_every_page_and_deduplicates_stable_provider_ids():
    base = f"{CopernicusService.BASE_URL}/Products"
    page_one_products = [
        _provider_product("product-1", "T35LPF"),
        _provider_product("product-2", "T35LQF"),
    ]
    page_two_products = [
        _provider_product("product-2", "T35LQF"),
        _provider_product("product-3", "T35LPG"),
    ]
    service = _service(
        [
            FakeCatalogueResponse(
                {"value": page_one_products, "@odata.nextLink": f"{base}?$skip=2"}
            ),
            FakeCatalogueResponse({"value": page_two_products}),
        ]
    )
    persisted_pages = []

    products = service.search_products(
        start_date="2026-06-01",
        end_date="2026-10-27",
        cloud_cover=30,
        geometry_wkt="POLYGON ((27  -13, 29 -13, 29 -12, 27 -13))",
        limit=2,
        on_page=lambda page, page_number: persisted_pages.append(
            (page_number, [item["Id"] for item in page])
        ),
    )

    assert [item["Id"] for item in products] == [
        "product-1",
        "product-2",
        "product-3",
    ]
    assert persisted_pages == [
        (1, ["product-1", "product-2"]),
        (2, ["product-3"]),
    ]
    assert len(service.session.calls) == 2
    initial_params = service.session.calls[0][1]["params"]
    assert initial_params["$top"] == 2
    assert "2026-06-01T00:00:00.000Z" in initial_params["$filter"]
    assert "2026-10-27T23:59:59.999Z" in initial_params["$filter"]
    assert "Value le 30.00" in initial_params["$filter"]
    assert "OData.CSC.Intersects" in initial_params["$filter"]
    assert service.session.calls[1][1]["params"] is None


def test_search_can_remove_cloud_filter_and_retries_a_rate_limited_page(monkeypatch):
    delays = []
    monkeypatch.setattr(copernicus_module.time, "sleep", delays.append)
    service = _service(
        [
            FakeCatalogueResponse({}, status_code=429, headers={"Retry-After": "1"}),
            FakeCatalogueResponse({"value": [_provider_product("product-1", "T35LPF")]}),
        ]
    )

    products = service.search_products(
        start_date="2026-06-01",
        end_date="2026-10-27",
        cloud_cover=None,
    )

    filter_query = service.session.calls[0][1]["params"]["$filter"]
    assert "cloudCover" not in filter_query
    assert [item["Id"] for item in products] == ["product-1"]
    assert len(service.session.calls) == 2
    assert delays == [1.0]


def test_later_pagination_failure_raises_an_incomplete_search(monkeypatch):
    monkeypatch.setattr(copernicus_module.time, "sleep", lambda _delay: None)
    base = f"{CopernicusService.BASE_URL}/Products"
    service = _service(
        [
            FakeCatalogueResponse(
                {"value": [_provider_product("product-1", "T35LPF")], "@odata.nextLink": f"{base}?$skip=1"}
            ),
            *[FakeCatalogueResponse({}, status_code=503) for _ in range(5)],
        ]
    )
    persisted_pages = []

    with pytest.raises(RuntimeError, match="incomplete"):
        service.search_products(
            start_date="2026-06-01",
            end_date="2026-10-27",
            on_page=lambda page, number: persisted_pages.append(
                (number, [item["Id"] for item in page])
            ),
        )

    assert persisted_pages == [(1, ["product-1"])]
    assert len(service.session.calls) == 6


def test_catalogue_page_upserts_metadata_without_deleting_discovered_products():
    engine = create_engine("sqlite://")
    SatelliteCatalogueProduct.__table__.create(engine)

    class MetadataProvider:
        def get_product_metadata(self, product):
            return product

    with Session(engine) as db:
        first_page = [
            {
                "product_id": "provider-1",
                "product_name": "Product one",
                "tile_id": "T35LPF",
                "acquisition_date": "2026-06-03T08:11:00Z",
                "cloud_cover": 11.5,
                "processing_level": "S2MSI2A",
                "online": True,
                "content_length": 123,
                "geo_footprint": {"type": "Polygon", "coordinates": []},
            },
            {
                "product_id": "provider-2",
                "product_name": "Product two",
                "tile_id": "T35LQF",
                "acquisition_date": "2026-06-08T08:11:00Z",
                "cloud_cover": None,
            },
        ]
        persist_catalogue_page(
            db,
            forest_area_id=10,
            products=first_page,
            copernicus=MetadataProvider(),
        )
        first_seen = (
            db.query(SatelliteCatalogueProduct)
            .filter_by(product_id="provider-1")
            .one()
            .first_seen_at
        )

        persist_catalogue_page(
            db,
            forest_area_id=10,
            products=[
                {
                    **first_page[0],
                    "cloud_cover": 8.0,
                    "online": False,
                }
            ],
            copernicus=MetadataProvider(),
        )

        rows = db.query(SatelliteCatalogueProduct).order_by(
            SatelliteCatalogueProduct.product_id
        ).all()
        assert [row.product_id for row in rows] == ["provider-1", "provider-2"]
        assert rows[0].first_seen_at == first_seen
        assert rows[0].cloud_cover_percentage == 8.0
        assert rows[0].online is False
        assert rows[1].cloud_cover_percentage is None
        assert rows[0].acquisition_datetime.replace(tzinfo=UTC) == datetime(
            2026, 6, 3, 8, 11, tzinfo=UTC
        )
        filters = catalogue_filters(
            forest_area_id=10,
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 30),
            tile_id="T35LPF",
            max_cloud_cover=10,
            product_id="provider-1",
        )
        filtered = db.query(SatelliteCatalogueProduct).filter(*filters).all()
        assert [row.product_id for row in filtered] == ["provider-1"]

    engine.dispose()


def test_provider_timestamp_preserves_unknown_values_as_unknown():
    assert parse_provider_datetime(None) is None
    assert parse_provider_datetime("not-a-date") is None
    assert parse_provider_datetime("2026-06-03T08:11:00Z") == datetime(
        2026, 6, 3, 8, 11, tzinfo=UTC
    )
