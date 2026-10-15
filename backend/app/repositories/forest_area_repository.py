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

from sqlalchemy import false
from sqlalchemy.orm import Query, Session

from app.models.district import District
from app.models.enums import ProtectedStatus, UserRole
from app.models.forest_area import ForestArea
from app.models.user import User


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
    # Jurisdiction Scoping
    # ---------------------------------------------------------
    def scope_to_jurisdiction(
        self,
        query: Query,
        user: User,
    ) -> Query:
        """
        Restrict a forest area query to a user's jurisdiction.

        Args:
            query:
                Query selecting ForestArea rows.

            user:
                Officer whose jurisdiction applies.

        Returns:
            The query with the jurisdiction filter applied.

        This is the enforcement point for requirement FR-04.
        Filtering here rather than in the endpoint means an
        out-of-jurisdiction forest area cannot be returned by
        any caller of these methods, whatever the request
        asked for, including a request that names the record
        by its identifier. A user interface that merely hides
        rows is not access control.

        An officer with no jurisdiction assigned matches
        nothing. That case is rejected explicitly rather than
        left to a NULL comparison: SQLAlchemy renders
        `column == None` as `IS NULL`, which would match rows
        whose district is unset instead of matching none. An
        unassigned account is treated as not yet authorised.
        """

        # -----------------------------------------------------
        # Administrators are unrestricted
        # -----------------------------------------------------

        if user.role == UserRole.ADMIN:
            return query

        # -----------------------------------------------------
        # Provincial officers: every district in the province
        #
        # The join is needed only here, because a forest area
        # records its district directly but not its province.
        # -----------------------------------------------------

        if user.role == UserRole.PROVINCIAL_FORESTRY_OFFICER:

            if user.province_id is None:
                return query.filter(false())

            return (
                query
                .join(
                    District,
                    District.id
                    == ForestArea.district_id,
                )
                .filter(
                    District.province_id
                    == user.province_id,
                )
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
    # Get Active within Jurisdiction
    # ---------------------------------------------------------
    def get_all_active_for_user(
        self,
        user: User,
    ) -> list[ForestArea]:
        """
        Retrieve active forest areas the user may see.

        Args:
            user:
                Officer making the request.

        Returns:
            Active forest areas inside the officer's
            jurisdiction, ordered by name. Empty when the
            officer has no jurisdiction assigned.
        """

        query = self.db.query(ForestArea).filter(
            ForestArea.is_active.is_(True),
        )

        return (
            self.scope_to_jurisdiction(query, user)
            .order_by(ForestArea.name)
            .all()
        )

    # ---------------------------------------------------------
    # Get by ID within Jurisdiction
    # ---------------------------------------------------------
    def get_by_id_for_user(
        self,
        forest_area_id: int,
        user: User,
    ) -> ForestArea | None:
        """
        Retrieve one forest area the user may see.

        Args:
            forest_area_id:
                Identifier requested.

            user:
                Officer making the request.

        Returns:
            The forest area, or None when it does not exist
            OR lies outside the officer's jurisdiction.

        The two cases are deliberately not distinguished.
        Answering "it exists but is not yours" would confirm
        to an officer that a forest area is registered in a
        district they do not cover, which is itself
        information about where the department is watching.
        """

        query = self.db.query(ForestArea).filter(
            ForestArea.id == forest_area_id,
        )

        return self.scope_to_jurisdiction(
            query,
            user,
        ).first()

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