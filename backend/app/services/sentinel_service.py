"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Sentinel Service

Purpose:
    Handles communication with the Copernicus
    Sentinel-2 platform.

Responsibilities:
    - Search Sentinel-2 imagery.
    - Download image metadata.
    - Save satellite images.
    - Prepare imagery for NDVI analysis.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia
===========================================================
"""

from datetime import date

from sqlalchemy.orm import Session

from app.models.forest_area import ForestArea
from app.models.satellite_image import SatelliteImage


class SentinelService:
    """
    Handles Sentinel-2 operations.
    """

    def __init__(self, db: Session):
        self.db = db

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
        Register a downloaded Sentinel image.
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

        self.db.add(image)
        self.db.commit()
        self.db.refresh(image)

        return image
        def image_exists(
        self,
        product_id: str,
    ) -> bool:
           """
          Check whether a Sentinel image has already
        been registered.
        """

        return (
            self.db.query(SatelliteImage)
            .filter(
                SatelliteImage.product_id == product_id,
            )
            .first()
            is not None
        )

    def mark_as_processed(
        self,
        image: SatelliteImage,
    ) -> SatelliteImage:
        """
        Mark an image as processed.
        """

        image.is_processed = True

        self.db.commit()
        self.db.refresh(image)

        return image

    def get_latest_image(
        self,
        forest_area_id: int,
    ) -> SatelliteImage | None:
        """
        Return the most recent processed image
        for a forest area.
        """

        return (
            self.db.query(SatelliteImage)
            .filter(
                SatelliteImage.forest_area_id == forest_area_id,
                SatelliteImage.is_downloaded.is_(True),
            )
            .order_by(
                SatelliteImage.acquisition_date.desc(),
            )
            .first()
        )

    def get_previous_image(
        self,
        forest_area_id: int,
        latest_image_id: int,
    ) -> SatelliteImage | None:
        """
        Return the previous image before the latest one.
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