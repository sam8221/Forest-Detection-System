"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Satellite Image Repository

Purpose:
    Provides database operations for Sentinel-2
    satellite images.

Responsibilities:
    - Register downloaded images.
    - Retrieve satellite images.
    - Update processing status.
    - Count satellite images.
    - Delete satellite images.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Version:
    1.0.0
===========================================================
"""

from sqlalchemy.orm import Session

from app.models.satellite_image import SatelliteImage


class SatelliteImageRepository:
    """
    Handles database operations for satellite images.
    """

    def __init__(
        self,
        db: Session,
    ):
        self.db = db

    # ---------------------------------------------------------
    # Create
    # ---------------------------------------------------------
    def create(
        self,
        image: SatelliteImage,
    ) -> SatelliteImage:
        """
        Save a new satellite image.
        """

        self.db.add(image)
        self.db.commit()
        self.db.refresh(image)

        return image

    # ---------------------------------------------------------
    # Get by ID
    # ---------------------------------------------------------
    def get_by_id(
        self,
        image_id: int,
    ) -> SatelliteImage | None:
        """
        Retrieve a satellite image by ID.
        """

        return (
            self.db.query(SatelliteImage)
            .filter(
                SatelliteImage.id == image_id,
            )
            .first()
        )

    # ---------------------------------------------------------
    # Get by Product ID
    # ---------------------------------------------------------
    def get_by_product_id(
        self,
        product_id: str,
    ) -> SatelliteImage | None:
        """
        Retrieve a satellite image by its Sentinel
        product identifier.
        """

        return (
            self.db.query(SatelliteImage)
            .filter(
                SatelliteImage.product_id == product_id,
            )
            .first()
        )

    # ---------------------------------------------------------
    # Check Existence
    # ---------------------------------------------------------
    def exists(
        self,
        product_id: str,
    ) -> bool:
        """
        Check whether a Sentinel product already exists.
        """

        return (
            self.get_by_product_id(product_id)
            is not None
        )

    # ---------------------------------------------------------
    # Get All
    # ---------------------------------------------------------
    def get_all(
        self,
    ) -> list[SatelliteImage]:
        """
        Retrieve all satellite images.
        """

        return (
            self.db.query(SatelliteImage)
            .order_by(
                SatelliteImage.acquisition_date.desc(),
            )
            .all()
        )

    # ---------------------------------------------------------
    # Get Images for Forest Area
    # ---------------------------------------------------------
    def get_by_forest_area(
        self,
        forest_area_id: int,
    ) -> list[SatelliteImage]:
        """
        Retrieve all satellite images belonging
        to a forest area.
        """

        return (
            self.db.query(SatelliteImage)
            .filter(
                SatelliteImage.forest_area_id
                == forest_area_id,
            )
            .order_by(
                SatelliteImage.acquisition_date.desc(),
            )
            .all()
        )

    # ---------------------------------------------------------
    # Get Latest Image
    # ---------------------------------------------------------
    def get_latest_image(
        self,
        forest_area_id: int,
    ) -> SatelliteImage | None:
        """
        Retrieve the latest satellite image for a
        forest area.
        """

        return (
            self.db.query(SatelliteImage)
            .filter(
                SatelliteImage.forest_area_id
                == forest_area_id,
            )
            .order_by(
                SatelliteImage.acquisition_date.desc(),
            )
            .first()
        )

    # ---------------------------------------------------------
    # Count Images
    # ---------------------------------------------------------
    def count(
        self,
    ) -> int:
        """
        Return total number of satellite images.
        """

        return (
            self.db.query(SatelliteImage)
            .count()
        )

    # ---------------------------------------------------------
    # Count Processed Images
    # ---------------------------------------------------------
    def count_processed(
        self,
    ) -> int:
        """
        Return number of processed satellite images.
        """

        return (
            self.db.query(SatelliteImage)
            .filter(
                SatelliteImage.is_processed.is_(True),
            )
            .count()
        )

    # ---------------------------------------------------------
    # Count Unprocessed Images
    # ---------------------------------------------------------
    def count_unprocessed(
        self,
    ) -> int:
        """
        Return number of unprocessed satellite images.
        """

        return (
            self.db.query(SatelliteImage)
            .filter(
                SatelliteImage.is_processed.is_(False),
            )
            .count()
        )

    # ---------------------------------------------------------
    # Update
    # ---------------------------------------------------------
    def update(
        self,
        image: SatelliteImage,
    ) -> SatelliteImage:
        """
        Update an existing satellite image.
        """

        self.db.commit()
        self.db.refresh(image)

        return image

    # ---------------------------------------------------------
    # Delete
    # ---------------------------------------------------------
    def delete(
        self,
        image: SatelliteImage,
    ) -> None:
        """
        Permanently delete a satellite image.
        """

        self.db.delete(image)
        self.db.commit()