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
    - Restrict results to an officer's jurisdiction.
    - Count satellite images.
    - Delete satellite images.

Note:
    Methods whose name ends in _for_user apply jurisdiction
    scoping (requirement FR-04) and are what the API layer
    calls. The unscoped methods remain for system-level
    work, such as the download worker registering a product
    it has just fetched.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Version:
    1.0.0
===========================================================
"""

from sqlalchemy import false
from sqlalchemy.orm import Query, Session

from app.models.district import District
from app.models.enums import UserRole
from app.models.forest_area import ForestArea
from app.models.satellite_image import SatelliteImage
from app.models.user import User


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
    # Jurisdiction Scoping
    # ---------------------------------------------------------
    def scope_to_jurisdiction(
        self,
        query: Query,
        user: User,
    ) -> Query:
        """
        Restrict a satellite image query to a jurisdiction.

        Args:
            query:
                Query selecting SatelliteImage rows.

            user:
                Officer whose jurisdiction applies.

        Returns:
            The query with the jurisdiction filter applied.

        An image is acquired for a forest area, which belongs
        to a district, which belongs to a province, so scoping
        joins through both.

        This is the enforcement point for requirement FR-04.
        The imagery holdings for an area disclose which ground
        the department has acquired coverage of and over which
        dates, so they are restricted on the same basis as the
        detections drawn from them.

        An officer with no jurisdiction assigned matches
        nothing. That case is rejected explicitly rather than
        left to a NULL comparison: SQLAlchemy renders
        `column == None` as `IS NULL`, which would match rows
        whose district is unset instead of matching none.
        """

        # -----------------------------------------------------
        # Administrators are unrestricted
        # -----------------------------------------------------

        if user.role == UserRole.ADMIN:
            return query

        query = (
            query
            .join(
                ForestArea,
                ForestArea.id
                == SatelliteImage.forest_area_id,
            )
            .join(
                District,
                District.id
                == ForestArea.district_id,
            )
        )

        # -----------------------------------------------------
        # Provincial officers: every district in the province
        # -----------------------------------------------------

        if user.role == UserRole.PROVINCIAL_FORESTRY_OFFICER:

            if user.province_id is None:
                return query.filter(false())

            return query.filter(
                District.province_id
                == user.province_id,
            )

        # -----------------------------------------------------
        # District officers: their district only
        # -----------------------------------------------------

        if user.role == UserRole.DISTRICT_FORESTRY_OFFICER:

            if user.district_id is None:
                return query.filter(false())

            return query.filter(
                ForestArea.district_id
                == user.district_id,
            )

        # -----------------------------------------------------
        # Unknown role: return nothing
        # -----------------------------------------------------

        return query.filter(false())

    # ---------------------------------------------------------
    # Get All within Jurisdiction
    # ---------------------------------------------------------
    def get_all_for_user(
        self,
        user: User,
    ) -> list[SatelliteImage]:
        """
        Retrieve all satellite images the user may see.
        """

        query = self.db.query(SatelliteImage)

        return (
            self.scope_to_jurisdiction(query, user)
            .order_by(
                SatelliteImage.acquisition_date.desc(),
            )
            .all()
        )

    # ---------------------------------------------------------
    # Get by ID within Jurisdiction
    # ---------------------------------------------------------
    def get_by_id_for_user(
        self,
        image_id: int,
        user: User,
    ) -> SatelliteImage | None:
        """
        Retrieve one satellite image the user may see.

        Returns None when the image does not exist OR lies
        outside the user's jurisdiction, so that probing for
        identifiers reveals nothing about imagery held for
        other districts.
        """

        query = self.db.query(SatelliteImage).filter(
            SatelliteImage.id == image_id,
        )

        return (
            self.scope_to_jurisdiction(query, user)
            .first()
        )

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