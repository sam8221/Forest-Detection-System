"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: User Repository

Purpose:
    Provides database operations related to users.

Responsibilities:
    - Create users.
    - Retrieve users.
    - Retrieve users by email.
    - Retrieve all users.
    - Update users.
    - Delete users.
    - Check whether users exist.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Version:
    1.0.0
===========================================================
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.user import User


class UserRepository:
    """
    Handles all database operations related to users.
    """

    def __init__(
        self,
        db: Session,
    ) -> None:
        """
        Initialize the user repository.

        Args:
            db:
                SQLAlchemy database session.
        """

        self.db = db

    # ---------------------------------------------------------
    # CREATE
    # ---------------------------------------------------------
    def create(
        self,
        user: User,
    ) -> User:
        """
        Save a new user to the database.

        Args:
            user:
                User ORM object.

        Returns:
            The saved user.
        """

        self.db.add(user)

        self.db.commit()

        self.db.refresh(user)

        return user

    # ---------------------------------------------------------
    # READ - BY ID
    # ---------------------------------------------------------
    def get_by_id(
        self,
        user_id: int,
    ) -> User | None:
        """
        Retrieve a user by ID.

        Args:
            user_id:
                User primary key.

        Returns:
            User object if found, otherwise None.
        """

        return (
            self.db.query(User)
            .filter(
                User.id == user_id,
            )
            .first()
        )

    # ---------------------------------------------------------
    # READ - BY EMAIL
    # ---------------------------------------------------------
    def get_by_email(
        self,
        email: str,
    ) -> User | None:
        """
        Retrieve a user by email address.

        This method is used by the authentication
        service during login.
        """

        return (
            self.db.query(User)
            .filter(
                User.email == email,
            )
            .first()
        )

    # ---------------------------------------------------------
    # READ - ALL USERS
    # ---------------------------------------------------------
    def get_all(
        self,
    ) -> list[User]:
        """
        Retrieve all users.

        Returns:
            List of users ordered by full name.
        """

        return (
            self.db.query(User)
            .order_by(
                User.full_name,
            )
            .all()
        )

    # ---------------------------------------------------------
    # CHECK EMAIL
    # ---------------------------------------------------------
    def exists_by_email(
        self,
        email: str,
    ) -> bool:
        """
        Check whether a user with the given
        email address already exists.
        """

        return (
            self.db.query(User.id)
            .filter(
                User.email == email,
            )
            .first()
            is not None
        )

    # ---------------------------------------------------------
    # UPDATE
    # ---------------------------------------------------------
    def update(
        self,
        user: User,
    ) -> User:
        """
        Update an existing user.

        Args:
            user:
                User ORM object containing updated values.

        Returns:
            Updated user.
        """

        self.db.commit()

        self.db.refresh(user)

        return user

    # ---------------------------------------------------------
    # DELETE
    # ---------------------------------------------------------
    def delete(
        self,
        user: User,
    ) -> None:
        """
        Delete a user from the database.

        Args:
            user:
                User ORM object to delete.
        """

        self.db.delete(user)

        self.db.commit()

    # ---------------------------------------------------------
    # COUNT
    # ---------------------------------------------------------
    def count(
        self,
    ) -> int:
        """
        Return the total number of users.
        """

        return self.db.query(User).count()

    # ---------------------------------------------------------
    # COUNT ACTIVE USERS
    # ---------------------------------------------------------
    def count_active(
        self,
    ) -> int:
        """
        Return the number of active users.
        """

        return (
            self.db.query(User)
            .filter(
                User.is_active.is_(True),
            )
            .count()
        )