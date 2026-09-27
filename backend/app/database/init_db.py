"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Database Initializer

Purpose:
    Creates every database table defined by the SQLAlchemy
    models, in one step, from the model definitions.

Responsibilities:
    - Create all tables registered against the declarative
      Base.
    - Report success or fail loudly.

How it works:
    Base.metadata.create_all() inspects every model class
    that has been imported and issues CREATE TABLE for any
    that does not yet exist. Models must therefore be
    imported before it runs, which is why the User import
    below carries a noqa comment: it looks unused, but
    removing it would silently leave tables uncreated.

When to use this, and when not to:
    This is a convenience for standing up a throwaway
    database quickly, for example a local scratch instance
    or a test fixture.

    It is NOT how the real database is managed. Alembic
    migrations are, and they are the authoritative record of
    how the schema reached its current shape, which the
    dissertation relies on as evidence.

    The two disagree in an important way: create_all() only
    ever creates what is missing. It never alters an existing
    table, so running it against a database that is behind
    the models leaves it behind, silently and without error.
    Use "alembic upgrade head" for anything you intend to
    keep.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia
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