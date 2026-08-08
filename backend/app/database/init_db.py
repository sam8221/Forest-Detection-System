"""
===========================================================
Forest Detection System
-----------------------------------------------------------
Module: Database Initializer

Purpose:
    Creates all database tables defined by SQLAlchemy models.
===========================================================
"""

from sqlalchemy.exc import SQLAlchemyError

from app.database.session import Base, engine

# Import models so SQLAlchemy registers them
from app.models.user import User  # noqa: F401


def create_tables() -> None:
    """Create all database tables."""

    try:
        print("=" * 60)
        print("Creating database tables...")
        print("=" * 60)

        Base.metadata.create_all(bind=engine)

        print("SUCCESS: Database tables created successfully.")
        print("=" * 60)

    except SQLAlchemyError as error:
        print("ERROR:", error)
        raise


if __name__ == "__main__":
    print("Running database initializer...")
    create_tables()