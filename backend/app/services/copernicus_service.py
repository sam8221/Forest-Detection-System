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
    - Download only the bands analysis needs, resumably.
    - Return product metadata.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Version:
    2.0.0
===========================================================
"""

from __future__ import annotations

import os
import re
import time
import zipfile
from pathlib import Path
from typing import Any, Callable

import requests

from app.core.config import get_settings


settings = get_settings()


class CopernicusAuthenticationError(RuntimeError):
    """A permanent Copernicus credential or token rejection."""


class CopernicusAuthenticationServiceError(RuntimeError):
    """A temporary Copernicus identity or product-service failure."""


class _RetryableTransfer(Exception):
    """Internal signal that one transfer attempt should be repeated.

    Never raised out of this module: the retry loop either succeeds or
    turns repeated failures into a RuntimeError.
    """


class CopernicusAuthorizationError(RuntimeError):
    """Copernicus authenticated the account but denied product access."""


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
    # BAND-WISE ACQUISITION
    #
    # The whole .SAFE.zip is assembled from many objects on
    # request, so Copernicus refuses Range on it:
    #
    #   HTTP 416 DAT-ZIP-116
    #   "Range requests are not supported for multi-object
    #    downloads"
    #
    # With no Accept-Ranges and no ETag there is nothing to
    # resume from, so a connection reset at 70% discards
    # every byte. On a link that drops every 15-30 minutes a
    # ~1 GB product can never finish.
    #
    # The individual band nodes DO advertise
    # Accept-Ranges: bytes and answer 206 with a correct
    # Content-Range, and analysis only reads three of them:
    # B04 and B08 at 10 m for NDVI, and the 20 m SCL for
    # cloud masking. Fetching those three is ~257 MB instead
    # of ~1.1 GB, and each one can resume where it stopped.
    # =====================================================

    REQUIRED_BAND_NODES = (
        ("R10m", "_B04_10m.jp2"),
        ("R10m", "_B08_10m.jp2"),
        ("R20m", "_SCL_20m.jp2"),
    )

    # Attempts per band before the transfer is reported as
    # failed. Each attempt resumes rather than restarting, so
    # these are cheap; only a link that never holds still
    # exhausts them.
    BAND_ATTEMPT_LIMIT = 8

    NODE_LISTING_TIMEOUT = 60

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
        self._refresh_token: str | None = None
        self._token_expires_at: float | None = None

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
            self._clear_tokens()
            raise CopernicusAuthenticationError(
                "Copernicus credentials are not configured on the backend. "
                "Set COPERNICUS_USERNAME and COPERNICUS_PASSWORD, then restart FastAPI."
            )

        data = self._request_token(
            {
                "client_id": "cdse-public",
                "grant_type": "password",
                "username": username,
                "password": password,
            }
        )
        return self._store_token_response(data)

    def _request_token(self, form_data: dict[str, str]) -> dict[str, Any]:
        """Request an OAuth token without exposing provider response data."""

        try:
            response = requests.post(
                self.TOKEN_URL,
                data=form_data,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                timeout=self.AUTH_TIMEOUT,
            )
        except requests.exceptions.Timeout as exc:
            raise CopernicusAuthenticationServiceError(
                f"Copernicus authentication timed out after {self.AUTH_TIMEOUT} seconds."
            ) from exc
        except requests.exceptions.RequestException as exc:
            raise CopernicusAuthenticationServiceError(
                "Unable to connect to the Copernicus authentication service."
            ) from exc

        if response.status_code in (400, 401, 403):
            self._clear_tokens()
            raise CopernicusAuthenticationError(
                "Copernicus rejected the configured server credentials. "
                "Check COPERNICUS_USERNAME and COPERNICUS_PASSWORD, then restart FastAPI."
            )
        if response.status_code == 429 or response.status_code >= 500:
            raise CopernicusAuthenticationServiceError(
                "Copernicus authentication is temporarily unavailable. Retry later."
            )
        if response.status_code != 200:
            raise CopernicusAuthenticationServiceError(
                f"Copernicus authentication returned HTTP {response.status_code}."
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise CopernicusAuthenticationServiceError(
                "Copernicus authentication returned an invalid response."
            ) from exc
        if not isinstance(data, dict):
            raise CopernicusAuthenticationServiceError(
                "Copernicus authentication returned an invalid response."
            )
        return data

    def _store_token_response(self, data: dict[str, Any]) -> str:
        token = data.get("access_token")
        if not isinstance(token, str) or not token.strip():
            raise CopernicusAuthenticationServiceError(
                "Copernicus authentication did not return an access token."
            )

        self._access_token = token
        refresh_token = data.get("refresh_token")
        self._refresh_token = (
            refresh_token
            if isinstance(refresh_token, str) and refresh_token.strip()
            else None
        )
        try:
            expires_in = float(data.get("expires_in"))
        except (TypeError, ValueError):
            expires_in = 0
        self._token_expires_at = (
            time.monotonic() + expires_in
            if expires_in > 0
            else None
        )
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        return token

    def _clear_tokens(self) -> None:
        self._access_token = None
        self._refresh_token = None
        self._token_expires_at = None
        self.session.headers.pop("Authorization", None)

    def _refresh_or_authenticate(self) -> None:
        """Use the supported refresh grant, falling back to password grant."""

        refresh_token = self._refresh_token
        self._clear_tokens()
        if refresh_token:
            try:
                data = self._request_token(
                    {
                        "client_id": "cdse-public",
                        "grant_type": "refresh_token",
                        "refresh_token": refresh_token,
                    }
                )
                self._store_token_response(data)
                return
            except CopernicusAuthenticationError:
                # An expired/revoked refresh token can be replaced with a
                # fresh password grant. Temporary identity errors propagate.
                pass
        self.authenticate()

    # =====================================================
    # ENSURE AUTHENTICATED
    # =====================================================

    def _ensure_authenticated(self) -> None:
        """
        Ensure that the HTTP session has a valid
        Copernicus access token.
        """

        token_is_near_expiry = (
            self._token_expires_at is not None
            and self._token_expires_at <= time.monotonic() + 60
        )
        if token_is_near_expiry:
            self._refresh_or_authenticate()
        elif not self._access_token:
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

                self._refresh_or_authenticate()

                response = self.session.get(
                    url,

                    params=params,

                    timeout=self.SEARCH_TIMEOUT,
                )

            if response.status_code == 401:
                raise CopernicusAuthenticationError(
                    "Copernicus rejected the renewed access token. "
                    "Check the server-side Copernicus account configuration."
                )

            if response.status_code == 403:
                raise CopernicusAuthorizationError(
                    "Copernicus denied access to the catalogue request."
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

            raise RuntimeError(
                "Copernicus catalogue request failed. "
                f"HTTP {status_code}."
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

    @staticmethod
    def normalise_tile_id(
        tile_id: str | None,
    ) -> str | None:
        """
        Return a Sentinel-2 tile identifier in one form.

        Args:
            tile_id:
                Identifier as supplied by Copernicus, which
                may be "35LPF" or "T35LPF".

        Returns:
            The identifier as "T35LPF", or None when it
            cannot be recognised.

        Two images can only be compared pixel by pixel when
        they come from the same tile, and that comparison is
        a string equality. Storing the same tile under two
        spellings silently prevented every such pair from
        being found.
        """

        if not tile_id:
            return None

        cleaned = tile_id.strip().upper()

        match = re.search(
            r"(\d{2}[A-Z]{3})",
            cleaned,
        )

        if not match:
            return None

        return f"T{match.group(1)}"

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

        # -------------------------------------------------
        # Normalise the tile identifier
        #
        # Copernicus reports the same tile in two different
        # forms depending on which route the value came
        # from. The tileId attribute gives "35LPF" while the
        # product name gives "T35LPF".
        #
        # Analysis pairs two images by comparing their tile
        # identifiers exactly, so the two spellings never
        # matched. Images of the same ground were treated as
        # different tiles and every analysis over them
        # failed with "no compatible previous image".
        #
        # One canonical form is stored: T followed by the
        # MGRS reference, upper case.
        # -------------------------------------------------

        tile_id = self.normalise_tile_id(tile_id)

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
        progress_callback: Callable[[str, int, int | None], None] | None = None,
    ) -> Path:
        """
        Stream a Sentinel-2 product and report measured transfer bytes.
        """

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self._ensure_authenticated()

        partial_destination = destination.with_suffix(
            destination.suffix + ".part"
        )

        def stream_response(response) -> tuple[int, int | None]:
            if response.status_code == 401:
                raise CopernicusAuthenticationError(
                    "Copernicus rejected the access token for this download. "
                    "Check COPERNICUS_USERNAME and COPERNICUS_PASSWORD on the backend."
                )
            if response.status_code == 403:
                raise CopernicusAuthorizationError(
                    "Copernicus denied access to this product for the configured account."
                )
            if response.status_code == 429 or response.status_code >= 500:
                raise CopernicusAuthenticationServiceError(
                    "Copernicus download service is temporarily unavailable. Retry later."
                )
            if response.status_code < 200 or response.status_code >= 300:
                raise RuntimeError(
                    f"Copernicus product download failed (HTTP {response.status_code})."
                )
            try:
                declared_size = int(response.headers.get("Content-Length", ""))
            except (TypeError, ValueError):
                declared_size = 0
            total_bytes = declared_size if declared_size > 0 else None
            downloaded_bytes = 0

            if progress_callback is not None:
                progress_callback("DOWNLOADING", 0, total_bytes)

            with partial_destination.open("wb") as file:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    file.write(chunk)
                    downloaded_bytes += len(chunk)
                    if progress_callback is not None:
                        progress_callback(
                            "DOWNLOADING",
                            downloaded_bytes,
                            total_bytes,
                        )

            if total_bytes is not None and downloaded_bytes != total_bytes:
                raise RuntimeError(
                    "The downloaded byte count did not match the server's declared size."
                )

            return downloaded_bytes, total_bytes

        try:
            with self.session.get(
                download_url,
                stream=True,
                timeout=self.DOWNLOAD_TIMEOUT,
            ) as response:
                if response.status_code == 401:
                    self._refresh_or_authenticate()
                    with self.session.get(
                        download_url,
                        stream=True,
                        timeout=self.DOWNLOAD_TIMEOUT,
                    ) as retry_response:
                        downloaded_bytes, total_bytes = stream_response(
                            retry_response
                        )
                else:
                    downloaded_bytes, total_bytes = stream_response(response)

            if downloaded_bytes <= 0 or not partial_destination.is_file():
                raise RuntimeError("Copernicus returned an empty product.")

            os.replace(partial_destination, destination)

            if progress_callback is not None:
                progress_callback(
                    "VALIDATING",
                    downloaded_bytes,
                    total_bytes,
                )
        except requests.exceptions.Timeout as exc:
            partial_destination.unlink(missing_ok=True)
            raise RuntimeError(
                "Sentinel-2 download timed out."
            ) from exc
        except requests.exceptions.RequestException as exc:
            partial_destination.unlink(missing_ok=True)
            raise RuntimeError(
                "Failed to download Sentinel-2 product: unable to connect to "
                "the Copernicus product download service."
            ) from exc
        except Exception:
            partial_destination.unlink(missing_ok=True)
            raise

        return destination

    # =====================================================
    # DOWNLOAD PRODUCT
    # =====================================================

    def download_product(
        self,
        product_id: str,
        destination: Path,
        progress_callback: Callable[[str, int, int | None], None] | None = None,
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
            progress_callback=progress_callback,
        )

    # =====================================================
    # LOCATE THE BANDS ANALYSIS NEEDS
    # =====================================================

    def _node_path(self, product_id: str, *names: str) -> str:
        """Build an OData Nodes(...) path inside one product."""

        return (
            f"{self.DOWNLOAD_URL}/Products({product_id})"
            + "".join(f"/Nodes({name})" for name in names)
        )

    def _list_nodes(self, url: str) -> list[dict[str, Any]]:
        """List one level of a product's internal structure."""

        self._ensure_authenticated()

        def request_listing():
            return self.session.get(
                f"{url}/Nodes",
                timeout=self.NODE_LISTING_TIMEOUT,
            )

        try:
            response = request_listing()

            if response.status_code == 401:
                self._refresh_or_authenticate()
                response = request_listing()

        except requests.exceptions.RequestException as exc:
            raise RuntimeError(
                "Unable to read the Sentinel-2 product structure from the "
                "Copernicus download service."
            ) from exc

        if response.status_code == 401:
            raise CopernicusAuthenticationError(
                "Copernicus rejected the access token while reading the "
                "product structure. Check COPERNICUS_USERNAME and "
                "COPERNICUS_PASSWORD on the backend."
            )

        if response.status_code == 403:
            raise CopernicusAuthorizationError(
                "Copernicus denied access to this product for the "
                "configured account."
            )

        if response.status_code != 200:
            raise RuntimeError(
                "Could not read the Sentinel-2 product structure "
                f"(HTTP {response.status_code})."
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError(
                "The Copernicus product structure response was not "
                "valid JSON."
            ) from exc

        entries = payload.get("result") if isinstance(payload, dict) else None

        return [
            entry
            for entry in entries or []
            if isinstance(entry, dict)
        ]

    def _probe_node_size(self, url: str) -> int | None:
        """Read one band's declared size without transferring it.

        Copernicus does not answer HEAD on these nodes, so the stream is
        opened for its headers and closed before any body is read. The
        size is what makes a real percentage possible; without it the job
        reports indeterminate progress rather than an invented number.
        """

        self._ensure_authenticated()

        try:
            with self.session.get(
                url,
                stream=True,
                timeout=self.DOWNLOAD_TIMEOUT,
            ) as response:
                if response.status_code not in (200, 206):
                    return None
                try:
                    declared = int(response.headers.get("Content-Length", ""))
                except (TypeError, ValueError):
                    return None
        except requests.exceptions.RequestException:
            return None

        return declared if declared > 0 else None

    def locate_required_band_nodes(
        self,
        product_id: str,
        product_name: str,
    ) -> list[dict[str, Any]]:
        """Resolve the three required bands to downloadable node URLs.

        The granule directory carries an identifier that cannot be
        derived from the product name, so the tree is walked rather
        than guessed.
        """

        granules = self._list_nodes(
            self._node_path(product_id, product_name, "GRANULE")
        )

        granule_names = [
            str(entry["Name"])
            for entry in granules
            if entry.get("Name")
        ]

        if not granule_names:
            raise RuntimeError(
                "The Sentinel-2 product contains no granule directory."
            )

        granule = granule_names[0]

        located: list[dict[str, Any]] = []
        listings: dict[str, list[dict[str, Any]]] = {}

        for resolution, suffix in self.REQUIRED_BAND_NODES:

            if resolution not in listings:
                listings[resolution] = self._list_nodes(
                    self._node_path(
                        product_id,
                        product_name,
                        "GRANULE",
                        granule,
                        "IMG_DATA",
                        resolution,
                    )
                )

            match = next(
                (
                    entry
                    for entry in listings[resolution]
                    if str(entry.get("Name", "")).endswith(suffix)
                ),
                None,
            )

            if match is None:
                raise RuntimeError(
                    "The Sentinel-2 product is missing a band required for "
                    "analysis. A Level-1C product carries no SCL band."
                )

            file_name = str(match["Name"])

            try:
                declared_size = int(match.get("ContentLength"))
            except (TypeError, ValueError):
                declared_size = 0

            url = (
                self._node_path(
                    product_id,
                    product_name,
                    "GRANULE",
                    granule,
                    "IMG_DATA",
                    resolution,
                    file_name,
                )
                + "/$value"
            )

            located.append(
                {
                    "file_name": file_name,
                    "url": url,
                    "size": declared_size if declared_size > 0 else None,
                    # Mirrors the SAFE layout, so an assembled archive
                    # extracts exactly like a whole product download.
                    "archive_path": (
                        f"{product_name}/GRANULE/{granule}"
                        f"/IMG_DATA/{resolution}/{file_name}"
                    ),
                }
            )

        return located

    # =====================================================
    # RESUMABLE SINGLE-BAND TRANSFER
    # =====================================================

    def _download_node_resumable(
        self,
        url: str,
        part_path: Path,
        expected_size: int | None,
        on_progress: Callable[[int], None],
    ) -> int:
        """Transfer one band, resuming after a dropped connection."""

        part_path.parent.mkdir(parents=True, exist_ok=True)
        attempt = 0

        while True:

            resume_from = (
                part_path.stat().st_size
                if part_path.is_file()
                else 0
            )

            if expected_size is not None:

                if resume_from == expected_size:
                    on_progress(expected_size)
                    return expected_size

                if resume_from > expected_size:
                    # More bytes on disk than the band holds: the file is
                    # left over from something else and must not be
                    # mistaken for a finished transfer.
                    part_path.unlink(missing_ok=True)
                    resume_from = 0

            attempt += 1
            self._ensure_authenticated()

            headers = (
                {"Range": f"bytes={resume_from}-"}
                if resume_from
                else {}
            )

            try:
                with self.session.get(
                    url,
                    stream=True,
                    headers=headers,
                    timeout=self.DOWNLOAD_TIMEOUT,
                ) as response:

                    if response.status_code == 401:
                        self._refresh_or_authenticate()
                        raise _RetryableTransfer("access token refreshed")

                    if response.status_code == 403:
                        raise CopernicusAuthorizationError(
                            "Copernicus denied access to this product for "
                            "the configured account."
                        )

                    if response.status_code == 416:
                        # The offset lies past the object's end, so the
                        # bytes on disk cannot belong to this band.
                        part_path.unlink(missing_ok=True)
                        raise _RetryableTransfer("stale partial file")

                    if (
                        response.status_code == 429
                        or response.status_code >= 500
                    ):
                        raise _RetryableTransfer(
                            f"HTTP {response.status_code}"
                        )

                    if response.status_code not in (200, 206):
                        raise RuntimeError(
                            "Copernicus band download failed "
                            f"(HTTP {response.status_code})."
                        )

                    # A 200 reply to a Range request means the server
                    # ignored it and restarted the object, so the bytes
                    # already on disk must not be appended to.
                    append = resume_from > 0 and response.status_code == 206

                    if resume_from > 0 and not append:
                        resume_from = 0

                    downloaded = resume_from
                    on_progress(downloaded)

                    with part_path.open(
                        "ab" if append else "wb"
                    ) as band_file:
                        for chunk in response.iter_content(
                            chunk_size=1024 * 1024
                        ):
                            if not chunk:
                                continue
                            band_file.write(chunk)
                            downloaded += len(chunk)
                            on_progress(downloaded)

                if expected_size is not None and downloaded < expected_size:
                    raise _RetryableTransfer("transfer ended early")

                return downloaded

            except (
                _RetryableTransfer,
                requests.exceptions.RequestException,
            ) as exc:

                if attempt >= self.BAND_ATTEMPT_LIMIT:
                    raise RuntimeError(
                        "A Sentinel-2 band could not be transferred: the "
                        "connection to Copernicus kept dropping. The bytes "
                        "already received are kept, so retrying the "
                        "acquisition resumes instead of starting again."
                    ) from exc

                # A short, growing pause lets a flapping link settle
                # without stalling the job for minutes.
                time.sleep(min(2 ** attempt, 30))

    # =====================================================
    # DOWNLOAD REQUIRED BANDS AND ASSEMBLE A PRODUCT
    # =====================================================

    def download_product_bands(
        self,
        product_id: str,
        product_name: str,
        destination: Path,
        progress_callback: Callable[[str, int, int | None], None] | None = None,
    ) -> Path:
        """Fetch the bands analysis needs and assemble a .SAFE.zip.

        The archive carries the same internal paths as a product
        downloaded whole, so extraction, validation and the NDVI
        pipeline behave identically and need no change.

        Partly transferred bands are deliberately kept when a transfer
        fails. Copernicus will not resume the whole-product download, so
        the only way an unreliable link can ever finish is for a retry
        to continue from the bytes already on disk.
        """

        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)

        bands = self.locate_required_band_nodes(product_id, product_name)

        for band in bands:
            if band["size"] is None:
                band["size"] = self._probe_node_size(band["url"])

        sizes = [band["size"] for band in bands]
        total_bytes = (
            sum(sizes)
            if sizes and all(size is not None for size in sizes)
            else None
        )

        staging = destination.parent / f"{destination.name}.bands"
        staging.mkdir(parents=True, exist_ok=True)

        completed_bytes = 0

        if progress_callback is not None:
            progress_callback("DOWNLOADING", 0, total_bytes)

        for band in bands:

            part_path = staging / f"{band['file_name']}.part"
            band["part_path"] = part_path

            def report(band_bytes: int, base: int = completed_bytes) -> None:
                if progress_callback is not None:
                    progress_callback(
                        "DOWNLOADING",
                        base + band_bytes,
                        total_bytes,
                    )

            transferred = self._download_node_resumable(
                url=band["url"],
                part_path=part_path,
                expected_size=band["size"],
                on_progress=report,
            )

            if transferred <= 0 or not part_path.is_file():
                raise RuntimeError(
                    "Copernicus returned an empty Sentinel-2 band."
                )

            completed_bytes += transferred

        if progress_callback is not None:
            progress_callback("VALIDATING", completed_bytes, total_bytes)

        archive_part = destination.with_suffix(destination.suffix + ".part")

        try:
            # Stored, not deflated: JPEG 2000 imagery is already
            # compressed, so deflating ~257 MB would cost minutes of CPU
            # and save almost nothing.
            with zipfile.ZipFile(
                archive_part,
                "w",
                compression=zipfile.ZIP_STORED,
                allowZip64=True,
            ) as archive:
                for band in bands:
                    archive.write(
                        band["part_path"],
                        arcname=band["archive_path"],
                    )

            os.replace(archive_part, destination)

        except Exception:
            archive_part.unlink(missing_ok=True)
            raise

        # Only now are the staged bands redundant.
        for band in bands:
            band["part_path"].unlink(missing_ok=True)
        try:
            staging.rmdir()
        except OSError:
            # Something else is in the directory; leaving it is harmless
            # and safer than removing files this transfer did not create.
            pass

        return destination

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

