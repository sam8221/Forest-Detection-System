"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Sentinel Service

Purpose:
    Handles Sentinel-2 image discovery, downloading,
    registration and retrieval for forest monitoring.

Responsibilities:
    - Search Copernicus for new Sentinel-2 imagery.
    - Automatically identify the newest suitable image.
    - Avoid duplicate satellite-image downloads.
    - Download new Sentinel-2 products.
    - Register imagery in PostgreSQL.
    - Search explicit seasonal windows for imagery.
    - Support automatic multi-date analysis.

Note:
    Selecting which stored images form an analysis pair is
    the responsibility of SatelliteImageSelectionService,
    which validates that both images come from the same
    Sentinel-2 tile.

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

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable
import logging
import os
import zipfile

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.constants import normalize_processing_level
from app.models.forest_area import ForestArea
from app.models.satellite_image import SatelliteImage

from app.repositories.satellite_image_repository import (
    SatelliteImageRepository,
)

from app.services.copernicus_service import (
    CopernicusService,
)
from app.services.sentinel_processor_service import (
    SentinelProcessorService,
)
from app.services.storage_paths import shared_extract_root


logger = logging.getLogger(__name__)


class SentinelService:
    """
    Handles Sentinel-2 image discovery, downloading,
    registration and retrieval.
    """

    # =========================================================
    # INITIALIZATION
    # =========================================================

    def __init__(
        self,
        db: Session,
    ) -> None:
        """
        Initialize Sentinel service.

        The imagery storage root, the maximum accepted cloud
        cover and the default search window all come from
        application settings rather than from constants
        declared here, so this service and DetectionService
        cannot disagree about where processed rasters live
        or which scenes are acceptable.
        """

        self.db = db

        self.settings = get_settings()

        self.repository = (
            SatelliteImageRepository(db)
        )

        self.copernicus = (
            CopernicusService()
        )

    @staticmethod
    def _validate_downloaded_product(downloaded_file: Path) -> None:
        """Check the saved archive and bands required by L2A analysis."""

        if (
            not downloaded_file.is_file()
            or downloaded_file.stat().st_size <= 0
            or not zipfile.is_zipfile(downloaded_file)
        ):
            raise RuntimeError(
                "The downloaded Sentinel-2 product is empty or is not a valid ZIP archive."
            )

        with zipfile.ZipFile(downloaded_file, "r") as archive:
            members = [
                member
                for member in archive.infolist()
                if not member.is_dir()
            ]
            corrupt_member = archive.testzip()

        if corrupt_member is not None:
            raise RuntimeError(
                "The downloaded Sentinel-2 product failed archive integrity validation."
            )

        # The full set the pipeline opens, not only the NDVI
        # bands. A product that passes here and is then rejected
        # as incomplete by the analysis has been downloaded for
        # nothing, which is what used to happen: acquisition
        # fetched three members while the pipeline required six.
        required_members = (
            "MTD_MSIL2A.XML",
            "_B02_10M.JP2",
            "_B03_10M.JP2",
            "_B04_10M.JP2",
            "_B08_10M.JP2",
            "_SCL_20M.JP2",
        )
        missing = [
            required
            for required in required_members
            if not any(
                member.filename.upper().endswith(required)
                and member.file_size > 0
                for member in members
            )
        ]
        if missing:
            raise RuntimeError(
                "The downloaded product is missing bands or Level-2A "
                "metadata required for analysis. The B02, B03, B04 and "
                "B08 bands at 10 m, the 20 m scene classification layer "
                "and MTD_MSIL2A.xml must all be present."
            )

    # =========================================================
    # LOCAL SENTINEL STORAGE
    # =========================================================

    @property
    def storage_root(self) -> Path:
        """
        Return the absolute imagery storage root.
        """

        return (
            self.settings
            .satellite_image_storage_path
        )

    def _resolve_max_cloud_cover(
        self,
        max_cloud_cover: float | None,
    ) -> float:
        """
        Return the caller's cloud-cover limit, falling back
        to the configured default when none was supplied.
        """

        if max_cloud_cover is not None:
            return max_cloud_cover

        return (
            self.settings
            .max_cloud_cover_percentage
        )

    # =========================================================
    # REGISTER SATELLITE IMAGE
    # =========================================================

    def register_satellite_image(
        self,
        forest_area: ForestArea,
        product_id: str,
        tile_id: str,
        acquisition_date: date,
        cloud_cover: float,
        file_name: str,
        storage_path: str,
        file_size_mb: float,
        processing_level: str = "L2A",
    ) -> SatelliteImage:
        """
        Register a downloaded Sentinel-2 image.
        """

        # -----------------------------------------------------
        # Protect against duplicate product
        # -----------------------------------------------------

        existing = (
            self.repository.get_by_product_id(
                product_id
            )
        )

        if existing is not None:
            return existing

        # -----------------------------------------------------
        # Create database record
        # -----------------------------------------------------

        image = SatelliteImage(
            forest_area_id=forest_area.id,

            product_id=product_id,

            tile_id=tile_id,

            satellite_name="Sentinel-2",

            acquisition_date=acquisition_date,

            # Stored in the canonical spelling. The Copernicus
            # catalogue reports Level-2A as "Level-2A" or as
            # the product type "S2MSI2A" depending on the
            # response, and this is the one place a product row
            # is created, so normalising here keeps every new
            # row consistent. Existing rows are left as they
            # were acquired; readers recognise either form.
            processing_level=normalize_processing_level(
                processing_level
            ),

            cloud_cover_percentage=cloud_cover,

            file_name=file_name,

            storage_path=storage_path,

            file_size_mb=file_size_mb,

            is_downloaded=True,

            is_processed=False,

            is_active=True,
        )

        return self.repository.create(
            image
        )

    # =========================================================
    # CHECK EXISTING IMAGE
    # =========================================================

    def image_exists(
        self,
        product_id: str,
    ) -> bool:
        """
        Check whether a Sentinel-2 product
        already exists in the database.
        """

        return (
            self.repository.get_by_product_id(
                product_id
            )
            is not None
        )

    # =========================================================
    # DOWNLOAD SENTINEL PRODUCT
    # =========================================================

    def download_product(
        self,
        forest_area: ForestArea,
        product_id: str,
        product_name: str,
        tile_id: str,
        acquisition_date: date,
        cloud_cover: float,
        processing_level: str = "L2A",
        progress_callback: Callable[[str, int, int | None], None] | None = None,
    ) -> SatelliteImage:
        """
        Download a Sentinel-2 product from Copernicus
        and register it in the database.
        """

        # -----------------------------------------------------
        # Check duplicate
        # -----------------------------------------------------

        existing = (
            self.repository.get_by_product_id(
                product_id
            )
        )

        # A registered product is reused only when the files it
        # points at are actually complete. A row marked
        # downloaded whose archive is missing an input the
        # pipeline opens is worse than no row at all: it is
        # accepted here, then rejected by the analysis, and
        # nothing ever replaces it because this is the only
        # place that would. Four such rows existed after the
        # downloaded set and the required set drifted apart.
        if existing is not None and self.local_product_is_complete(existing):
            return existing

        # -----------------------------------------------------
        # Create storage directory
        # -----------------------------------------------------

        destination_folder = (
            self.storage_root
            / str(forest_area.id)
        )

        destination_folder.mkdir(
            parents=True,
            exist_ok=True,
        )

        # -----------------------------------------------------
        # Create safe filename
        # -----------------------------------------------------

        file_name = (
            f"{product_name}.zip"
        )

        destination = (
            destination_folder
            / file_name
        )

        # -----------------------------------------------------
        # Download from Copernicus
        # -----------------------------------------------------

        # Only the bands analysis reads are fetched, and each one
        # resumes after a dropped connection. Copernicus refuses Range
        # on the whole .SAFE.zip, so a reset part-way through a ~1 GB
        # product discards every byte; on an unreliable link that
        # product can never finish. See CopernicusService
        # .REQUIRED_BAND_NODES for the reasoning and the measurements.
        # The staged member files are claimed rather than
        # discarded, so that once the image row exists they can
        # be moved into the directory the analysis pipeline
        # extracts into. See _claim_staged_product below.
        staged: dict[str, Path] = {}

        downloaded_file = (
            self.copernicus.download_product_bands(
                product_id=product_id,
                product_name=product_name,
                destination=destination,
                progress_callback=progress_callback,
                staged_band_sink=staged.update,
            )
        )

        self._validate_downloaded_product(downloaded_file)

        # -----------------------------------------------------
        # Calculate file size
        # -----------------------------------------------------

        file_size_mb = (
            downloaded_file.stat().st_size
            / (1024 * 1024)
        )

        # -----------------------------------------------------
        # Register database record
        # -----------------------------------------------------

        if existing is not None:

            # The row stays, so detections and jobs that cite
            # this product keep citing it. Only what describes
            # the file on disk is refreshed.
            existing.file_name = file_name
            existing.storage_path = str(downloaded_file)
            existing.file_size_mb = file_size_mb
            existing.is_downloaded = True
            self.db.commit()
            self.db.refresh(existing)

            self._claim_staged_product(existing, staged)

            return existing

        image = self.register_satellite_image(
            forest_area=forest_area,

            product_id=product_id,

            tile_id=tile_id,

            acquisition_date=acquisition_date,

            cloud_cover=cloud_cover,

            file_name=file_name,

            storage_path=str(
                downloaded_file
            ),

            file_size_mb=file_size_mb,

            processing_level=processing_level,
        )

        # The extraction directory is named after the image row,
        # so it can only be populated once that row exists.
        self._claim_staged_product(image, staged)

        return image

    def local_product_is_complete(
        self,
        image: SatelliteImage,
    ) -> bool:
        """
        Return whether this product's local files hold every
        input the analysis pipeline opens.

        The extracted tree is checked first because that is what
        the pipeline reads. The archive is checked from its
        central directory only, so this costs no more than
        opening the file however large the product is.
        """

        extract_root = shared_extract_root(
            forest_area_id=image.forest_area_id,
            satellite_image_id=image.id,
            storage_root=self.storage_root,
        )

        if SentinelProcessorService.has_complete_extracted_product(extract_root):
            return True

        file_name = Path(image.file_name or "")

        if not image.file_name or file_name.name != image.file_name:
            return False

        recorded = Path(image.storage_path).expanduser() if image.storage_path else None

        candidates = [
            path
            for path in (
                recorded,
                self.storage_root / str(image.forest_area_id) / file_name,
            )
            if path is not None and path.is_file()
        ]

        return any(
            SentinelProcessorService.archive_has_required_members(path)
            for path in candidates
        )

    def _claim_staged_product(
        self,
        image: SatelliteImage,
        staged: dict[str, Path],
    ) -> None:
        """
        Move freshly downloaded members into their extraction
        directory, so the first analysis need not unpack them.

        Args:
            image:
                The registered image the members belong to.

            staged:
                {path inside the archive: staged file}, as
                CopernicusService.download_product_bands
                reports it.

        The files are MOVED, not copied: staging and the
        extraction root are both under the imagery storage root
        and therefore on one volume, so each move is a rename
        and costs nothing. Extracting instead would read and
        write every one of those bytes again.

        A failure here is not a download failure. The archive is
        saved and valid, so the pipeline can still extract from
        it; all that is lost is the saving. It is logged rather
        than raised for exactly that reason.
        """

        if not staged:
            return

        try:
            extract_root = shared_extract_root(
                forest_area_id=image.forest_area_id,
                satellite_image_id=image.id,
                storage_root=self.storage_root,
            )

            for archive_path, staged_file in staged.items():

                target = extract_root / archive_path

                if target.is_file() and target.stat().st_size > 0:
                    staged_file.unlink(missing_ok=True)
                    continue

                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(staged_file, target)

            staging_directory = next(
                (path.parent for path in staged.values()),
                None,
            )

            if staging_directory is not None:
                try:
                    staging_directory.rmdir()
                except OSError:
                    # Another transfer's partly received band is
                    # still there. Leaving it is what lets that
                    # transfer resume.
                    pass

        except OSError:
            logger.exception(
                "Could not place the downloaded members of product %s into "
                "its extraction directory; the analysis will unpack them "
                "from the archive instead.",
                image.product_id,
            )

    # =========================================================
    # FIND NEWEST COPERNICUS PRODUCT
    # =========================================================

    def find_copernicus_product_in_window(
        self,
        forest_area: ForestArea,
        start_date: date,
        end_date: date,
        max_cloud_cover: float | None = None,
    ) -> dict | None:
        """
        Search Copernicus for the newest suitable Sentinel-2
        L2A image acquired inside an explicit date window.

        Args:
            forest_area:
                Forest area whose geometry bounds the search.

            start_date:
                First acquisition date to accept.

            end_date:
                Last acquisition date to accept.

            max_cloud_cover:
                Maximum accepted cloud cover. Falls back to
                the configured default when omitted.

        Returns:
            The newest matching Copernicus product, or None
            when the window contains no suitable imagery.

        Searching an explicit window (rather than "the last N
        days") is what makes seasonal comparison possible:
        miombo woodland NDVI falls across the whole province
        every dry season, so a baseline must be drawn from the
        SAME calendar window in an earlier year, never from
        the months immediately preceding the comparison.
        """

        if not forest_area.geometry:
            raise ValueError(
                "Forest area does not have a valid geometry."
            )

        if start_date > end_date:
            raise ValueError(
                "Search window start date cannot be after "
                "its end date."
            )

        max_cloud_cover = (
            self._resolve_max_cloud_cover(
                max_cloud_cover
            )
        )

        # -----------------------------------------------------
        # Convert PostGIS geometry to WKT
        # -----------------------------------------------------

        geometry = forest_area.geometry

        try:
            from geoalchemy2.shape import (
                to_shape,
            )

            geometry_wkt = (
                to_shape(
                    geometry
                ).wkt
            )

        except Exception as exc:

            raise ValueError(
                "Unable to convert forest geometry "
                "to WKT for Copernicus search."
            ) from exc

        # -----------------------------------------------------
        # Search Copernicus
        # -----------------------------------------------------

        products = (
            self.copernicus.search_products(
                start_date=start_date.isoformat(),

                end_date=end_date.isoformat(),

                cloud_cover=max_cloud_cover,

                geometry_wkt=geometry_wkt,

                limit=20,
            )
        )

        # -----------------------------------------------------
        # No imagery
        # -----------------------------------------------------

        if not products:
            return None

        # -----------------------------------------------------
        # Return newest product
        # -----------------------------------------------------

        return (
            self.copernicus.get_latest_product(
                products
            )
        )

    # =========================================================
    # FIND NEWEST PRODUCT IN A RELATIVE WINDOW
    # =========================================================

    def find_latest_copernicus_product(
        self,
        forest_area: ForestArea,
        max_cloud_cover: float | None = None,
        search_days: int | None = None,
    ) -> dict | None:
        """
        Search Copernicus for the newest suitable Sentinel-2
        L2A image acquired within the last `search_days`.

        This is a convenience wrapper over
        find_copernicus_product_in_window for callers that
        only want "something recent" and do not need a
        specific seasonal window.
        """

        if search_days is None:
            search_days = (
                self.settings.image_search_days
            )

        end_date = date.today()

        start_date = (
            end_date
            - timedelta(
                days=search_days
            )
        )

        return (
            self.find_copernicus_product_in_window(
                forest_area=forest_area,

                start_date=start_date,

                end_date=end_date,

                max_cloud_cover=max_cloud_cover,
            )
        )

    # =========================================================
    # DISCOVER AND REGISTER LATEST IMAGE
    # =========================================================

    def discover_latest_image(
        self,
        forest_area: ForestArea,
        max_cloud_cover: float | None = None,
        search_days: int | None = None,
    ) -> SatelliteImage | None:
        """
        Automatically search Copernicus for the newest
        suitable Sentinel-2 image.

        If the product is already registered, the existing
        database record is returned.

        If it is new, the product is downloaded and
        registered automatically.
        """

        product = (
            self.find_latest_copernicus_product(
                forest_area=forest_area,

                max_cloud_cover=max_cloud_cover,

                search_days=search_days,
            )
        )

        # -----------------------------------------------------
        # No new product
        # -----------------------------------------------------

        if product is None:
            return None

        return (
            self._register_discovered_product(
                forest_area=forest_area,

                product=product,
            )
        )

    # =========================================================
    # DISCOVER AND REGISTER AN IMAGE IN A SEASONAL WINDOW
    # =========================================================

    def discover_image_in_window(
        self,
        forest_area: ForestArea,
        start_date: date,
        end_date: date,
        max_cloud_cover: float | None = None,
    ) -> SatelliteImage | None:
        """
        Search Copernicus for a suitable Sentinel-2 image
        inside an explicit date window, then download and
        register it.

        Args:
            forest_area:
                Forest area whose geometry bounds the search.

            start_date:
                First acquisition date to accept.

            end_date:
                Last acquisition date to accept.

            max_cloud_cover:
                Maximum accepted cloud cover. Falls back to
                the configured default when omitted.

        Returns:
            The registered SatelliteImage, or None when no
            suitable imagery exists in the window.

        This is the entry point used for seasonal analysis,
        where the baseline and comparison periods are fixed
        calendar windows in different years.
        """

        product = (
            self.find_copernicus_product_in_window(
                forest_area=forest_area,

                start_date=start_date,

                end_date=end_date,

                max_cloud_cover=max_cloud_cover,
            )
        )

        # -----------------------------------------------------
        # Window contains no suitable imagery
        # -----------------------------------------------------

        if product is None:
            return None

        return (
            self._register_discovered_product(
                forest_area=forest_area,

                product=product,
            )
        )

    # =========================================================
    # REGISTER A DISCOVERED COPERNICUS PRODUCT
    # =========================================================

    def _register_discovered_product(
        self,
        forest_area: ForestArea,
        product: dict,
    ) -> SatelliteImage:
        """
        Convert a raw Copernicus product into a registered
        SatelliteImage record.

        Already-registered products are returned from the
        database instead of being downloaded again, so a
        baseline image shared by many analyses is fetched
        only once.
        """

        # -----------------------------------------------------
        # Convert Copernicus metadata
        # -----------------------------------------------------

        metadata = (
            self.copernicus
            .get_product_metadata(
                product
            )
        )

        product_id = (
            metadata.get(
                "product_id"
            )
        )

        product_name = (
            metadata.get(
                "product_name"
            )
        )

        tile_id = (
            metadata.get(
                "tile_id"
            )
        )

        acquisition_value = (
            metadata.get(
                "acquisition_date"
            )
        )

        cloud_cover = (
            metadata.get(
                "cloud_cover"
            )
            or 0.0
        )

        processing_level = (
            metadata.get(
                "processing_level"
            )
            or "L2A"
        )

        # -----------------------------------------------------
        # Validate product ID
        # -----------------------------------------------------

        if not product_id:
            raise RuntimeError(
                "Copernicus returned a product "
                "without a product ID."
            )

        # -----------------------------------------------------
        # Validate tile
        # -----------------------------------------------------

        if not tile_id:

            raise RuntimeError(
                "Copernicus returned a Sentinel-2 "
                "product without a tile ID."
            )

        # -----------------------------------------------------
        # Convert acquisition date
        # -----------------------------------------------------

        if not acquisition_value:

            raise RuntimeError(
                "Copernicus returned a product "
                "without an acquisition date."
            )

        try:

            acquisition_date = (
                datetime.fromisoformat(
                    acquisition_value.replace(
                        "Z",
                        "+00:00",
                    )
                ).date()
            )

        except (
            ValueError,
            TypeError,
        ) as exc:

            raise RuntimeError(
                "Unable to parse Sentinel-2 "
                "acquisition date."
            ) from exc

        # -----------------------------------------------------
        # Check existing database image
        # -----------------------------------------------------

        existing = (
            self.repository.get_by_product_id(
                product_id
            )
        )

        # Reused only when its local files hold every input the
        # analysis opens. A row whose product is incomplete must
        # fall through to the acquisition below, or nothing ever
        # replaces it: this check and the one in download_product
        # are the only two places that would.
        if existing is not None and self.local_product_is_complete(existing):
            return existing

        # -----------------------------------------------------
        # Validate product name
        # -----------------------------------------------------

        if not product_name:

            product_name = (
                f"Sentinel-2-{product_id}"
            )

        # -----------------------------------------------------
        # Download and register
        # -----------------------------------------------------

        return self.download_product(
            forest_area=forest_area,

            product_id=product_id,

            product_name=product_name,

            tile_id=tile_id,

            acquisition_date=acquisition_date,

            cloud_cover=float(
                cloud_cover
            ),

            processing_level=processing_level,
        )

    # =========================================================
    # UPDATE LATEST IMAGE
    # =========================================================

    def update_latest_image(
        self,
        forest_area: ForestArea,
        max_cloud_cover: float | None = None,
        search_days: int | None = None,
    ) -> SatelliteImage | None:
        """
        Check Copernicus for a newer Sentinel-2 image.

        This method is intended to be called before
        every automatic analysis.
        """

        return self.discover_latest_image(
            forest_area=forest_area,

            max_cloud_cover=max_cloud_cover,

            search_days=search_days,
        )

    # =========================================================
    # MARK AS PROCESSED
    # =========================================================

    def mark_as_processed(
        self,
        image: SatelliteImage,
    ) -> SatelliteImage:
        """
        Mark a satellite image as processed.
        """

        image.is_processed = True

        return self.repository.update(
            image
        )

