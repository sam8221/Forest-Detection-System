"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Copernicus Service

Purpose:
    Communicates with the Copernicus Data Space
    Ecosystem API.

Responsibilities:
    - Authenticate with Copernicus.
    - Search real Sentinel-2 products.
    - Filter products by date.
    - Filter products by cloud coverage.
    - Filter products geographically.
    - Retrieve the latest product.
    - Download Sentinel-2 imagery.
    - Return product metadata.

Author:
    Samuel Bikiloni

Project:
    Intelligent Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Version:
    2.0.0
===========================================================
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import requests

from app.core.config import get_settings


settings = get_settings()


class CopernicusService:
    """
    Handles communication with the
    Copernicus Data Space Ecosystem.
    """

    # =====================================================
    # ENDPOINTS
    # =====================================================

    BASE_URL = (
        "https://catalogue.dataspace.copernicus.eu"
        "/odata/v1"
    )

    DOWNLOAD_URL = (
        "https://download.dataspace.copernicus.eu"
        "/odata/v1"
    )

    TOKEN_URL = (
        "https://identity.dataspace.copernicus.eu"
        "/auth/realms/CDSE/protocol/openid-connect/token"
    )

    # =====================================================
    # TIMEOUTS
    # =====================================================

    AUTH_TIMEOUT = 30

    SEARCH_TIMEOUT = 30

    DOWNLOAD_TIMEOUT = (
        60,
        600,
    )

    # =====================================================
    # INITIALIZATION
    # =====================================================

    def __init__(self) -> None:

        self.session = requests.Session()

        self.session.headers.update(
            {
                "Accept": "application/json",
                "User-Agent": (
                    "ForestWatch-Zambia/2.0"
                ),
            }
        )

        self._access_token: str | None = None

    # =====================================================
    # AUTHENTICATION
    # =====================================================

    def authenticate(self) -> str:
        """
        Authenticate with Copernicus Data Space.
        """

        username = getattr(
            settings,
            "copernicus_username",
            "",
        )

        password = getattr(
            settings,
            "copernicus_password",
            "",
        )

        if not username or not password:

            raise RuntimeError(
                "Copernicus username/password are not "
                "configured. Check .env."
            )

        try:

            response = requests.post(
                self.TOKEN_URL,

                data={
                    "client_id": "cdse-public",

                    "grant_type": "password",

                    "username": username,

                    "password": password,
                },

                headers={
                    "Content-Type":
                        "application/x-www-form-urlencoded",
                },

                timeout=self.AUTH_TIMEOUT,
            )

        except requests.exceptions.Timeout as exc:

            raise RuntimeError(
                "Copernicus authentication timed out "
                f"after {self.AUTH_TIMEOUT} seconds."
            ) from exc

        except requests.exceptions.RequestException as exc:

            raise RuntimeError(
                "Unable to connect to Copernicus "
                f"authentication service: {exc}"
            ) from exc

        if response.status_code != 200:

            raise RuntimeError(
                "Copernicus authentication failed. "
                f"HTTP {response.status_code}. "
                f"Response: {response.text[:1000]}"
            )

        try:

            data = response.json()

        except ValueError as exc:

            raise RuntimeError(
                "Copernicus authentication returned "
                "invalid JSON."
            ) from exc

        token = data.get(
            "access_token"
        )

        if not token:

            raise RuntimeError(
                "Copernicus authentication succeeded "
                "but no access token was returned."
            )

        self._access_token = token

        self.session.headers.update(
            {
                "Authorization":
                    f"Bearer {token}",
            }
        )

        return token

    # =====================================================
    # ENSURE AUTHENTICATED
    # =====================================================

    def _ensure_authenticated(self) -> None:
        """
        Ensure that the HTTP session has a valid
        Copernicus access token.
        """

        if not self._access_token:

            self.authenticate()

    # =====================================================
    # SEARCH SENTINEL-2 PRODUCTS
    # =====================================================

    def search_products(
        self,
        start_date: str,
        end_date: str,
        cloud_cover: float = 30.0,
        geometry_wkt: str | None = None,
        tile_id: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """
        Search the Copernicus catalogue for
        Sentinel-2 Level-2A products.
        """

        # -------------------------------------------------
        # IMPORTANT:
        # Authenticate BEFORE catalogue search.
        # -------------------------------------------------

        self._ensure_authenticated()

        # -------------------------------------------------
        # Validate cloud coverage
        # -------------------------------------------------

        cloud_cover = max(
            0.0,
            min(
                float(cloud_cover),
                100.0,
            ),
        )

        # -------------------------------------------------
        # Validate limit
        # -------------------------------------------------

        limit = max(
            1,
            min(
                int(limit),
                100,
            ),
        )

        # -------------------------------------------------
        # Validate tile
        # -------------------------------------------------

        if tile_id:

            tile_id = (
                tile_id.strip().upper()
            )

            if not re.fullmatch(
                r"T\d{2}[A-Z]{3}",
                tile_id,
            ):

                raise ValueError(
                    "Invalid Sentinel-2 tile ID. "
                    "Expected format such as T35LPF."
                )

        # -------------------------------------------------
        # Dates
        # -------------------------------------------------

        start_datetime = (
            f"{start_date}T00:00:00.000Z"
        )

        end_datetime = (
            f"{end_date}T23:59:59.999Z"
        )

        # -------------------------------------------------
        # Base filters
        # -------------------------------------------------

        filters = [

            "Collection/Name eq 'SENTINEL-2'",

            (
                "Attributes/"
                "OData.CSC.StringAttribute/"
                "any("
                "att:att/Name eq 'productType' "
                "and "
                "att/OData.CSC.StringAttribute/"
                "Value eq 'S2MSI2A'"
                ")"
            ),

            (
                "Attributes/"
                "OData.CSC.DoubleAttribute/"
                "any("
                "att:att/Name eq 'cloudCover' "
                "and "
                "att/OData.CSC.DoubleAttribute/"
                f"Value le {cloud_cover:.2f}"
                ")"
            ),

            (
                "ContentDate/Start ge "
                f"{start_datetime}"
            ),

            (
                "ContentDate/Start le "
                f"{end_datetime}"
            ),
        ]

        # -------------------------------------------------
        # Tile filter
        # -------------------------------------------------

        if tile_id:

            filters.append(
                (
                    "contains(Name,"
                    f"'{tile_id}')"
                )
            )

        # -------------------------------------------------
        # Geometry filter
        # -------------------------------------------------

        if geometry_wkt:

            geometry = (
                geometry_wkt.strip()
            )

            if geometry.upper().startswith(
                "SRID=4326;"
            ):

                geometry = geometry[
                    len("SRID=4326;"):
                ].strip()

            if not geometry.upper().startswith(
                "POLYGON"
            ):

                raise ValueError(
                    "Forest area geometry must "
                    "be a WKT POLYGON."
                )

            geography = (
                "geography'SRID=4326;"
                f"{geometry}'"
            )

            filters.append(
                (
                    "OData.CSC.Intersects("
                    f"area={geography}"
                    ")"
                )
            )

        # -------------------------------------------------
        # Build request
        # -------------------------------------------------

        filter_query = (
            " and ".join(filters)
        )

        params = {

            "$filter":
                filter_query,

            "$orderby":
                "ContentDate/Start desc",

            "$top":
                limit,

            "$expand":
                "Attributes",
        }

        url = (
            f"{self.BASE_URL}/Products"
        )

        print(
            "Copernicus: searching catalogue..."
        )

        try:

            response = self.session.get(
                url,

                params=params,

                timeout=self.SEARCH_TIMEOUT,
            )

            # -------------------------------------------------
            # Token expired
            # -------------------------------------------------

            if response.status_code == 401:

                print(
                    "Copernicus: token expired, "
                    "authenticating again..."
                )

                self._access_token = None

                self.authenticate()

                response = self.session.get(
                    url,

                    params=params,

                    timeout=self.SEARCH_TIMEOUT,
                )

            response.raise_for_status()

        except requests.exceptions.Timeout as exc:

            raise RuntimeError(
                "Copernicus catalogue search timed out "
                f"after {self.SEARCH_TIMEOUT} seconds."
            ) from exc

        except requests.exceptions.HTTPError as exc:

            status_code = (
                exc.response.status_code
                if exc.response is not None
                else None
            )

            response_text = (
                exc.response.text[:2000]
                if exc.response is not None
                else ""
            )

            raise RuntimeError(
                "Copernicus catalogue request failed. "
                f"HTTP {status_code}. "
                f"Response: {response_text}"
            ) from exc

        except requests.exceptions.RequestException as exc:

            raise RuntimeError(
                "Unable to connect to Copernicus "
                f"catalogue: {exc}"
            ) from exc

        # -------------------------------------------------
        # JSON
        # -------------------------------------------------

        try:

            data = response.json()

        except ValueError as exc:

            raise RuntimeError(
                "Copernicus returned invalid JSON."
            ) from exc

        products = data.get(
            "value",
            [],
        )

        print(
            "Copernicus: products found:",
            len(products),
        )

        return products

    # =====================================================
    # GET LATEST PRODUCT
    # =====================================================

    def get_latest_product(
        self,
        products: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """
        Return newest product.
        """

        if not products:

            return None

        return products[0]

    # =====================================================
    # PRODUCT METADATA
    # =====================================================

    def get_product_metadata(
        self,
        product: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Convert Copernicus metadata into
        ForestWatch representation.
        """

        content_date = (
            product.get("ContentDate")
            or {}
        )

        attributes = (
            product.get("Attributes")
            or []
        )

        cloud_cover = None

        product_type = None

        tile_id = None

        processing_level = None

        for attribute in attributes:

            name = attribute.get(
                "Name"
            )

            value = attribute.get(
                "Value"
            )

            if name == "cloudCover":

                cloud_cover = value

            elif name == "productType":

                product_type = value

            elif name == "tileId":

                tile_id = value

            elif name == "processingLevel":

                processing_level = value

        # -------------------------------------------------
        # Some catalogue responses may not expose tileId
        # as an attribute. Try extracting it from Name.
        # -------------------------------------------------

        product_name = product.get(
            "Name"
        ) or ""

        if not tile_id:

            match = re.search(
                r"_T(\d{2}[A-Z]{3})_",
                product_name,
            )

            if match:

                tile_id = (
                    f"T{match.group(1)}"
                )

        return {

            "id":
                product.get("Id"),

            "name":
                product_name,

            "product_id":
                product.get("Id"),

            "product_name":
                product_name,

            "product_type":
                product_type,

            "tile_id":
                tile_id,

            "processing_level":
                (
                    processing_level
                    or "S2MSI2A"
                ),

            "cloud_cover":
                cloud_cover,

            "acquisition_date":
                content_date.get(
                    "Start"
                ),

            "content_date":
                content_date,

            "footprint":
                product.get(
                    "GeoFootprint"
                ),

            "geo_footprint":
                product.get(
                    "GeoFootprint"
                ),

            "s3_path":
                product.get(
                    "S3Path"
                ),

            "content_length":
                product.get(
                    "ContentLength"
                ),

            "online":
                product.get(
                    "Online"
                ),
        }

    # =====================================================
    # DOWNLOAD FILE
    # =====================================================

    def download_file(
        self,
        download_url: str,
        destination: Path,
    ) -> Path:
        """
        Download Sentinel-2 product.
        """

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self._ensure_authenticated()

        print(
            "Copernicus: downloading product..."
        )

        try:

            with self.session.get(
                download_url,

                stream=True,

                timeout=self.DOWNLOAD_TIMEOUT,
            ) as response:

                if response.status_code == 401:

                    self._access_token = None

                    self.authenticate()

                    with self.session.get(
                        download_url,

                        stream=True,

                        timeout=self.DOWNLOAD_TIMEOUT,
                    ) as retry_response:

                        retry_response.raise_for_status()

                        with open(
                            destination,
                            "wb",
                        ) as file:

                            for chunk in (
                                retry_response
                                .iter_content(
                                    chunk_size=
                                    1024 * 1024
                                )
                            ):

                                if chunk:

                                    file.write(
                                        chunk
                                    )

                else:

                    response.raise_for_status()

                    with open(
                        destination,
                        "wb",
                    ) as file:

                        for chunk in (
                            response.iter_content(
                                chunk_size=
                                1024 * 1024
                            )
                        ):

                            if chunk:

                                file.write(
                                    chunk
                                )

        except requests.exceptions.Timeout as exc:

            raise RuntimeError(
                "Sentinel-2 download timed out."
            ) from exc

        except requests.exceptions.RequestException as exc:

            raise RuntimeError(
                "Failed to download Sentinel-2 "
                f"product: {exc}"
            ) from exc

        print(
            "Copernicus: download completed."
        )

        return destination

    # =====================================================
    # DOWNLOAD PRODUCT
    # =====================================================

    def download_product(
        self,
        product_id: str,
        destination: Path,
    ) -> Path:
        """
        Download Sentinel-2 product by ID.
        """

        self._ensure_authenticated()

        download_url = (
            f"{self.DOWNLOAD_URL}"
            f"/Products({product_id})/$value"
        )

        return self.download_file(
            download_url=download_url,

            destination=destination,
        )

    # =====================================================
    # DOWNLOAD LATEST PRODUCT
    # =====================================================

    def download_latest_product(
        self,
        products: list[dict[str, Any]],
        destination_folder: Path,
    ) -> Path | None:
        """
        Download newest Sentinel-2 product.
        """

        latest = (
            self.get_latest_product(
                products
            )
        )

        if latest is None:

            return None

        product_id = latest.get(
            "Id"
        )

        product_name = latest.get(
            "Name"
        )

        if not product_id:

            raise RuntimeError(
                "Sentinel-2 product does not "
                "contain a valid product ID."
            )

        if not product_name:

            product_name = (
                f"sentinel_product_"
                f"{product_id}"
            )

        destination = (
            destination_folder
            / f"{product_name}.zip"
        )

        return self.download_product(
            product_id=product_id,

            destination=destination,
        )
        