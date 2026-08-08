"""
===========================================================
Forest Detection System
-----------------------------------------------------------
Module: User Repository

Purpose:
    Provides database operations related to users.

Responsibilities:
    - Create users.
    - Retrieve users.
    - Update users.
    - Delete users.
    - Check whether a user already exists.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Version:
    1.0.0
===========================================================
"""

from typing import Optional

from sqlalchemy.orm import Session

from app.models.user import User


class UserRepository:
    """
    Handles all database operations related to users.
    """

    def __init__(self, db: Session):
        """
        Initialize the repository.

        Args:
            db:
                SQLAlchemy database session.
        """
        self.db = db

    # ---------------------------------------------------------
    # CREATE
    # ---------------------------------------------------------
    def create(self, user: User) -> User:
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
    # READ
    # ---------------------------------------------------------
    def get_by_id(
        self,
        user_id: int,
        ) -> User | None:

     def get_by_email(
    self,
    email: str,
) -> User | None:
        """
        Retrieve a user using their email.
        """

        return (
            self.db.query(User)
            .filter(User.email == email)
            .first()
        )

    def get_all(self) -> list[User]:
        """
        Retrieve all users.
        """

        return (
            self.db.query(User)
            .order_by(User.full_name)
            .all()
        )

    # ---------------------------------------------------------
    # UPDATE
    # ---------------------------------------------------------
    def update(self, user: User) -> User:
        """
        Update an existing user.
        """

        self.db.commit()
        self.db.refresh(user)

        return user

    # ---------------------------------------------------------
    # DELETE
    # ---------------------------------------------------------
    def delete(self, user: User) -> None:
        """
        Delete a user.
        """

        self.db.delete(user)
        self.db.commit()