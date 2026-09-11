"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Satellite Image Selection Service

Purpose:
    Select valid Sentinel-2 image pairs for forest
    change detection.

Responsibilities:
    - Find the newest usable Sentinel-2 image.
    - Find a compatible previous image.
    - Ensure both images belong to the same forest area.
    - Ensure both images use the same Sentinel-2 tile.
    - Ensure the previous image is older than the latest.
    - Prefer the newest image that has a valid baseline.
    - Prevent invalid cross-tile comparisons.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Version:
    1.1.0
===========================================================
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.satellite_image import SatelliteImage


class SatelliteImageSelectionService:
    """
    Selects compatible Sentinel-2 images for
    multi-date forest change detection.
    """

    def __init__(
        self,
        db: Session,
    ) -> None:
        self.db = db

    # =========================================================
    # FIND LATEST IMAGE
    # =========================================================

    def get_latest_image(
        self,
        forest_area_id: int,
    ) -> SatelliteImage | None:
        """
        Return the newest downloaded Sentinel-2 image
        for a forest area.
        """

        return (
            self.db.query(SatelliteImage)
            .filter(
                SatelliteImage.forest_area_id
                == forest_area_id,

                SatelliteImage.is_downloaded.is_(True),

                SatelliteImage.is_active.is_(True),
            )
            .order_by(
                SatelliteImage.acquisition_date.desc(),
                SatelliteImage.id.desc(),
            )
            .first()
        )

    # =========================================================
    # FIND PREVIOUS COMPATIBLE IMAGE
    # =========================================================

    def get_previous_image(
        self,
        latest_image: SatelliteImage,
    ) -> SatelliteImage | None:
        """
        Find the most recent image before the latest image
        using the same Sentinel-2 tile.
        """

        return (
            self.db.query(SatelliteImage)
            .filter(
                SatelliteImage.forest_area_id
                == latest_image.forest_area_id,

                SatelliteImage.tile_id
                == latest_image.tile_id,

                SatelliteImage.acquisition_date
                < latest_image.acquisition_date,

                SatelliteImage.is_downloaded.is_(True),

                SatelliteImage.is_active.is_(True),
            )
            .order_by(
                SatelliteImage.acquisition_date.desc(),
                SatelliteImage.id.desc(),
            )
            .first()
        )

    # =========================================================
    # FIND NEWEST IMAGE WITH A VALID BASELINE
    # =========================================================

    def get_latest_compatible_pair(
        self,
        forest_area_id: int,
    ) -> tuple[
        SatelliteImage,
        SatelliteImage,
    ] | None:
        """
        Search downloaded images from newest to oldest and
        return the newest image that has an older image
        from the same Sentinel-2 tile.
        """

        images = (
            self.db.query(SatelliteImage)
            .filter(
                SatelliteImage.forest_area_id
                == forest_area_id,

                SatelliteImage.is_downloaded.is_(True),

                SatelliteImage.is_active.is_(True),
            )
            .order_by(
                SatelliteImage.acquisition_date.desc(),
                SatelliteImage.id.desc(),
            )
            .all()
        )

        for latest_image in images:

            previous_image = (
                self.get_previous_image(
                    latest_image=latest_image,
                )
            )

            if previous_image is not None:

                return (
                    previous_image,
                    latest_image,
                )

        return None

    # =========================================================
    # SELECT IMAGE PAIR
    # =========================================================

    def select_image_pair(
        self,
        forest_area_id: int,
    ) -> tuple[
        SatelliteImage,
        SatelliteImage,
    ]:
        """
        Select the newest valid previous/latest
        Sentinel-2 image pair.

        The two images must:

        - belong to the same forest area
        - use the same Sentinel-2 tile
        - have different acquisition dates
        - have the previous image older than the latest
        - both be downloaded
        - both be active
        """

        latest_image = self.get_latest_image(
            forest_area_id=forest_area_id,
        )

        if latest_image is None:

            raise ValueError(
                "No downloaded Sentinel-2 image is "
                "available for this forest area."
            )

        previous_image = self.get_previous_image(
            latest_image=latest_image,
        )

        if previous_image is not None:

            self._validate_pair(
                previous_image=previous_image,
                latest_image=latest_image,
            )

            return (
                previous_image,
                latest_image,
            )

        compatible_pair = (
            self.get_latest_compatible_pair(
                forest_area_id=forest_area_id,
            )
        )

        if compatible_pair is None:

            raise ValueError(
                "No compatible previous Sentinel-2 image "
                "was found for this forest area. "
                "At least two downloaded images from the "
                "same Sentinel-2 tile are required."
            )

        (
            previous_image,
            latest_compatible_image,
        ) = compatible_pair

        self._validate_pair(
            previous_image=previous_image,
            latest_image=latest_compatible_image,
        )

        return (
            previous_image,
            latest_compatible_image,
        )

    # =========================================================
    # VALIDATE IMAGE PAIR
    # =========================================================

    def _validate_pair(
        self,
        previous_image: SatelliteImage,
        latest_image: SatelliteImage,
    ) -> None:
        """
        Perform final safety validation before analysis.
        """

        if (
            previous_image.forest_area_id
            != latest_image.forest_area_id
        ):

            raise ValueError(
                "Previous and latest images belong "
                "to different forest areas."
            )

        if (
            previous_image.tile_id
            != latest_image.tile_id
        ):

            raise ValueError(
                "Previous and latest images use "
                "different Sentinel-2 tiles."
            )

        if (
            previous_image.acquisition_date
            >= latest_image.acquisition_date
        ):

            raise ValueError(
                "Previous image must have an earlier "
                "acquisition date than the latest image."
            )

        if not previous_image.is_downloaded:

            raise ValueError(
                "The previous Sentinel-2 image "
                "has not been downloaded."
            )

        if not latest_image.is_downloaded:

            raise ValueError(
                "The latest Sentinel-2 image "
                "has not been downloaded."
            )

    # =========================================================
    # RETURN IMAGE INFORMATION
    # =========================================================

    def get_image_pair_summary(
        self,
        forest_area_id: int,
    ) -> dict[str, object]:
        """
        Return a clean summary of the selected image pair.
        """

        (
            previous_image,
            latest_image,
        ) = self.select_image_pair(
            forest_area_id=forest_area_id,
        )

        return {
            "forest_area_id": forest_area_id,

            "previous_image_id": (
                previous_image.id
            ),

            "previous_product_id": (
                previous_image.product_id
            ),

            "previous_tile_id": (
                previous_image.tile_id
            ),

            "previous_acquisition_date": (
                previous_image.acquisition_date
            ),

            "latest_image_id": (
                latest_image.id
            ),

            "latest_product_id": (
                latest_image.product_id
            ),

            "latest_tile_id": (
                latest_image.tile_id
            ),

            "latest_acquisition_date": (
                latest_image.acquisition_date
            ),

            "same_tile": (
                previous_image.tile_id
                == latest_image.tile_id
            ),

            "days_between": (
                latest_image.acquisition_date
                - previous_image.acquisition_date
            ).days,
        }