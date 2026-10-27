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

from app.core.constants import is_level_2a
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

    @staticmethod
    def analysis_readiness(
        image: SatelliteImage,
        local_files_available: bool,
    ) -> tuple[bool, str | None]:
        """Explain whether one registered image can enter the existing pipeline."""

        if not image.is_active:
            return False, "This observation is inactive."
        if not image.is_downloaded:
            return False, "This observation has not been downloaded."
        if not is_level_2a(image.processing_level):
            return False, "Analysis requires Sentinel-2 Level-2A imagery."
        if not local_files_available:
            return False, "Local product files are missing; reacquire this observation."
        return True, None

    @staticmethod
    def validate_explicit_pair(
        previous_image: SatelliteImage | None,
        recent_image: SatelliteImage | None,
        forest_area_id: int,
    ) -> None:
        """Fail closed when a user-selected pair is incomplete or incompatible."""

        if previous_image is None or recent_image is None:
            raise ValueError("Both selected Sentinel-2 observations must exist.")
        if previous_image.id == recent_image.id:
            raise ValueError("Select two different Sentinel-2 observations.")
        if (
            previous_image.forest_area_id != forest_area_id
            or recent_image.forest_area_id != forest_area_id
        ):
            raise ValueError(
                "Both observations must belong to the selected forest area."
            )
        if not all(
            image.is_active and image.is_downloaded
            for image in (previous_image, recent_image)
        ):
            raise ValueError(
                "Both observations must be active and downloaded."
            )
        if previous_image.tile_id != recent_image.tile_id:
            raise ValueError(
                "The selected observations have incompatible Sentinel-2 tile coverage."
            )
        if previous_image.acquisition_date >= recent_image.acquisition_date:
            raise ValueError(
                "The previous observation must have an earlier acquisition date."
            )
        if not (
            is_level_2a(previous_image.processing_level)
            and is_level_2a(recent_image.processing_level)
        ):
            raise ValueError(
                "Both observations must use Sentinel-2 Level-2A processing."
            )

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

        Only Level-2A products are considered. A Level-1C
        product carries no SCL band, so it can be neither
        cloud-masked nor differenced against a surface
        reflectance scene; selecting one here would hand the
        pipeline an input it cannot process.

        The level is recognised in Python rather than matched
        in SQL because the same level is stored under several
        spellings. See is_level_2a.
        """

        candidates = (
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

        return next(
            (
                image
                for image in candidates
                if is_level_2a(image.processing_level)
            ),
            None,
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

        Restricted to Level-2A for the reason given on
        get_latest_image: a baseline that cannot be cloud
        masked is not a usable baseline.
        """

        candidates = (
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
            .all()
        )

        return next(
            (
                image
                for image in candidates
                if is_level_2a(image.processing_level)
            ),
            None,
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

        Both halves of the pair must be Level-2A: the
        candidates are filtered here and get_previous_image
        applies the same rule to the baseline it finds.
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

            if not is_level_2a(latest_image.processing_level):
                continue

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
        - both be Sentinel-2 Level-2A
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

        # Repeated here even though the candidate queries
        # already exclude anything that is not Level-2A. This
        # method is the last gate before a pair is handed to
        # the pipeline, and a caller that assembles a pair by
        # some other route must not be able to bypass the
        # rule that both scenes carry an SCL band.
        if not (
            is_level_2a(previous_image.processing_level)
            and is_level_2a(latest_image.processing_level)
        ):

            raise ValueError(
                "Both Sentinel-2 images must use "
                "Level-2A processing."
            )
