"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Copernicus Service

Purpose:
    Communicates with the Copernicus Data Space
    Ecosystem API.

Responsibilities:
    - Authenticate with Copernicus
    - Search Sentinel-2 products
    - Download imagery
    - Return metadata

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia
===========================================================
"""

from __future__ import annotations

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

    BASE_URL = "https://catalogue.dataspace.copernicus.eu/odata/v1"

    def __init__(self) -> None:
        self.session = requests.Session()

    def search_products(
        self,
        start_date: str,
        end_date: str,
        cloud_cover: float,
    ) -> list[dict[str, Any]]:
        """
        Search for Sentinel-2 products.

        NOTE:
        Geographic filtering (forest polygon or
        bounding box) will be added later.
        """

        url = (
            f"{self.BASE_URL}/Products"
            "?$filter="
            "Collection/Name eq 'SENTINEL-2'"
        )

        response = self.session.get(
            url,
            timeout=60,
        )

        response.raise_for_status()

        return response.json().get("value", [])

    def download_file(
        self,
        download_url: str,
        destination: Path,
    ) -> Path:
        """
        Download a Sentinel product.
        """

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with self.session.get(
            download_url,
            stream=True,
            timeout=600,
        ) as response:

            response.raise_for_status()

            with open(destination, "wb") as file:

                for chunk in response.iter_content(
                    chunk_size=8192,
                ):

                    if chunk:
                        file.write(chunk)

        return destination
        def authenticate(self) -> str:
          """
             Authenticate with the Copernicus Data Space
        Ecosystem and return an access token.

            Environment variables required:

        COPERNICUS_CLIENT_ID
        COPERNICUS_CLIENT_SECRET
        """

        token_url = (
            "https://identity.dataspace.copernicus.eu"
            "/auth/realms/CDSE/protocol/openid-connect/token"
        )

        response = requests.post(
            token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": settings.copernicus_client_id,
                "client_secret": settings.copernicus_client_secret,
            },
            timeout=60,
        )

        response.raise_for_status()

        token = response.json()["access_token"]

        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}",
            }
        )

        return token

    def product_exists(
        self,
        product_id: str,
        products: list[dict[str, Any]],
    ) -> bool:
        """
        Check whether a product already exists
        in the returned search results.
        """

        return any(
            product.get("Id") == product_id
            for product in products
        )

    def download_product(
        self,
        product_id: str,
        destination: Path,
    ) -> Path:
        """
        Download a Sentinel-2 product by ID.
        """

        self.authenticate()

        download_url = (
            f"{self.BASE_URL}/Products"
            f"({product_id})/$value"
        )

        return self.download_file(
            download_url=download_url,
            destination=destination,
        )

    def download_latest_product(
        self,
        products: list[dict[str, Any]],
        destination_folder: Path,
    ) -> Path | None:
        """
        Download the newest product from a search.
        """

        if not products:
            return None

        latest = products[0]

        product_id = latest["Id"]

        product_name = latest["Name"]

        destination = (
            destination_folder /
            f"{product_name}.zip"
        )

        return self.download_product(
            product_id=product_id,
            destination=destination,
        )