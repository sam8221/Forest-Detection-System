"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Forest Area Repository

Purpose:
    Provides database operations for forest areas.

Responsibilities:
    - Create forest areas.
    - Retrieve forest areas.
    - Update forest areas.
    - Activate/deactivate forest areas.
    - Count forest statistics.
    - Support dashboard reporting.

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

from app.models.enums import ProtectedStatus
from app.models.forest_area import ForestArea


class ForestAreaRepository:
    """
    Handles all database operations for Forest Areas.
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
        forest: ForestArea,
    ) -> ForestArea:
        """
        Save a new forest area.
        """

        self.db.add(forest)
        self.db.commit()
        self.db.refresh(forest)

        return forest

    # ---------------------------------------------------------
    # Get by ID
    # ---------------------------------------------------------
    def get_by_id(
        self,
        forest_area_id: int,
    ) -> ForestArea | None:
        """
        Retrieve a forest area by ID.
        """

        return (
            self.db.query(ForestArea)
            .filter(
                ForestArea.id == forest_area_id,
            )
            .first()
        )

    # ---------------------------------------------------------
    # Get by Code
    # ---------------------------------------------------------
    def get_by_code(
        self,
        forest_code: str,
    ) -> ForestArea | None:
        """
        Retrieve a forest area by its code.
        """

        return (
            self.db.query(ForestArea)
            .filter(
                ForestArea.forest_code == forest_code,
            )
            .first()
        )

    # ---------------------------------------------------------
    # Get by Name
    # ---------------------------------------------------------
    def get_by_name(
        self,
        name: str,
    ) -> ForestArea | None:
        """
        Retrieve a forest area by name.
        """

        return (
            self.db.query(ForestArea)
            .filter(
                ForestArea.name == name,
            )
            .first()
        )

    # ---------------------------------------------------------
    # Check Existence
    # ---------------------------------------------------------
    def exists(
        self,
        name: str,
    ) -> bool:
        """
        Check whether a forest area already exists.
        """

        return self.get_by_name(name) is not None

    # ---------------------------------------------------------
    # Get All
    # ---------------------------------------------------------
    def get_all(
        self,
    ) -> list[ForestArea]:
        """
        Retrieve all forest areas.
        """

        return (
            self.db.query(ForestArea)
            .order_by(
                ForestArea.name,
            )
            .all()
        )

    # ---------------------------------------------------------
    # Get Active
    # ---------------------------------------------------------
    def get_all_active(
        self,
    ) -> list[ForestArea]:
        """
        Retrieve all active forest areas.
        """

        return (
            self.db.query(ForestArea)
            .filter(
                ForestArea.is_active.is_(True),
            )
            .order_by(
                ForestArea.name,
            )
            .all()
        )

    # ---------------------------------------------------------
    # Get by District
    # ---------------------------------------------------------
    def get_by_district(
        self,
        district_id: int,
    ) -> list[ForestArea]:
        """
        Retrieve forest areas belonging to a district.
        """

        return (
            self.db.query(ForestArea)
            .filter(
                ForestArea.district_id == district_id,
            )
            .order_by(
                ForestArea.name,
            )
            .all()
        )

    # ---------------------------------------------------------
    # Count All
    # ---------------------------------------------------------
    def count(
        self,
    ) -> int:
        """
        Return total number of forest areas.
        """

        return (
            self.db.query(ForestArea)
            .count()
        )

    # ---------------------------------------------------------
    # Count Active
    # ---------------------------------------------------------
    def count_active(
        self,
    ) -> int:
        """
        Return total active forest areas.
        """

        return (
            self.db.query(ForestArea)
            .filter(
                ForestArea.is_active.is_(True),
            )
            .count()
        )

    # ---------------------------------------------------------
    # Count Inactive
    # ---------------------------------------------------------
    def count_inactive(
        self,
    ) -> int:
        """
        Return total inactive forest areas.
        """

        return (
            self.db.query(ForestArea)
            .filter(
                ForestArea.is_active.is_(False),
            )
            .count()
        )

    # ---------------------------------------------------------
    # Count Monitored
    # ---------------------------------------------------------
    def count_monitored(
        self,
    ) -> int:
        """
        Return total monitored forest areas.
        """

        return (
            self.db.query(ForestArea)
            .filter(
                ForestArea.monitoring_enabled.is_(True),
            )
            .count()
        )

    # ---------------------------------------------------------
    # Count Protected
    # ---------------------------------------------------------
    def count_protected(
        self,
    ) -> int:
        """
        Return total protected forest areas.
        """

        return (
            self.db.query(ForestArea)
            .filter(
                ForestArea.protected_status
                == ProtectedStatus.PROTECTED_FOREST,
            )
            .count()
        )

    # ---------------------------------------------------------
    # Update
    # ---------------------------------------------------------
    def update(
        self,
        forest: ForestArea,
    ) -> ForestArea:
        """
        Update an existing forest area.
        """

        self.db.commit()
        self.db.refresh(forest)

        return forest

    # ---------------------------------------------------------
    # Deactivate
    # ---------------------------------------------------------
    def deactivate(
        self,
        forest: ForestArea,
    ) -> ForestArea:
        """
        Soft delete a forest area.
        """

        forest.is_active = False

        self.db.commit()
        self.db.refresh(forest)

        return forest

    # ---------------------------------------------------------
    # Activate
    # ---------------------------------------------------------
    def activate(
        self,
        forest: ForestArea,
    ) -> ForestArea:
        """
        Reactivate a forest area.
        """

        forest.is_active = True

        self.db.commit()
        self.db.refresh(forest)

        return forest

    # ---------------------------------------------------------
    # Delete
    # ---------------------------------------------------------
    def delete(
        self,
        forest: ForestArea,
    ) -> None:
        """
        Permanently delete a forest area.
        """

        self.db.delete(forest)
        self.db.commit()