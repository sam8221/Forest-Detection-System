"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Sentinel Service

Purpose:
    Handles communication with the Copernicus
    Sentinel-2 platform.

Responsibilities:
    - Register Sentinel-2 image metadata.
    - Check whether an image already exists.
    - Retrieve the latest image.
    - Retrieve the previous image.
    - Mark images as processed.
    - Prepare imagery for NDVI analysis.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Version:
    1.0.0
===========================================================
"""

from datetime import date

from sqlalchemy.orm import Session

from app.models.forest_area import ForestArea
from app.models.satellite_image import SatelliteImage
from app.repositories.satellite_image_repository import (
    SatelliteImageRepository,
)


class SentinelService:
    """
    Handles Sentinel-2 image operations.
    """

    def __init__(
        self,
        db: Session,
    ):
        """
        Initialize the Sentinel service.
        """

        self.db = db
        self.repository = SatelliteImageRepository(db)

    # ---------------------------------------------------------
    # Register Satellite Image
    # ---------------------------------------------------------
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
    ) -> SatelliteImage:
        """
        Register a downloaded Sentinel-2 image.
        """

        image = SatelliteImage(
            forest_area_id=forest_area.id,
            product_id=product_id,
            tile_id=tile_id,
            acquisition_date=acquisition_date,
            cloud_cover_percentage=cloud_cover,
            file_name=file_name,
            storage_path=storage_path,
            file_size_mb=file_size_mb,
            is_downloaded=True,
            is_processed=False,
        )

        return self.repository.create(image)

    # ---------------------------------------------------------
    # Check Existing Image
    # ---------------------------------------------------------
    def image_exists(
        self,
        product_id: str,
    ) -> bool:
        """
        Check whether a Sentinel image
        has already been registered.
        """

        return (
            self.repository.get_by_product_id(
                product_id,
            )
            is not None
        )

    # ---------------------------------------------------------
    # Mark as Processed
    # ---------------------------------------------------------
    def mark_as_processed(
        self,
        image: SatelliteImage,
    ) -> SatelliteImage:
        """
        Mark a satellite image as processed.
        """

        image.is_processed = True

        return self.repository.update(image)

    # ---------------------------------------------------------
    # Get Latest Image
    # ---------------------------------------------------------
    def get_latest_image(
        self,
        forest_area_id: int,
    ) -> SatelliteImage | None:
        """
        Retrieve the latest downloaded image
        for a forest area.
        """

        return self.repository.get_latest_image(
            forest_area_id,
        )

    # ---------------------------------------------------------
    # Get Previous Image
    # ---------------------------------------------------------
    def get_previous_image(
        self,
        forest_area_id: int,
        latest_image_id: int,
    ) -> SatelliteImage | None:
        """
        Retrieve the previous downloaded image
        before the latest one.
        """

        return (
            self.db.query(SatelliteImage)
            .filter(
                SatelliteImage.forest_area_id == forest_area_id,
                SatelliteImage.id != latest_image_id,
                SatelliteImage.is_downloaded.is_(True),
            )
            .order_by(
                SatelliteImage.acquisition_date.desc(),
            )
            .first()
        )