"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Database Session

Purpose:
    Configures the SQLAlchemy database engine and
    session management for the application.

Responsibilities:
    - Create the PostgreSQL/PostGIS engine.
    - Configure SQLAlchemy sessions.
    - Provide the Declarative Base class.
    - Provide FastAPI database dependency.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Version:
    1.0.0
===========================================================
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import (
    DeclarativeBase,
    Session,
    sessionmaker,
)

from app.core.config import get_settings

# ---------------------------------------------------------
# Load application settings
# ---------------------------------------------------------
settings = get_settings()

# ---------------------------------------------------------
# Database Engine
# ---------------------------------------------------------
engine = create_engine(
    settings.database_url,

    # Statement echoing is a setting of its own rather than
    # following development mode, and is off unless asked
    # for. A single analysis run emits more than a hundred
    # kilobytes of SQL, which buries its own progress and
    # makes a failure hard to find; the log can be turned
    # back up when a query genuinely needs inspecting.
    echo=settings.database_echo,

    future=True,
)

# ---------------------------------------------------------
# Session Factory
# ---------------------------------------------------------
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


# ---------------------------------------------------------
# Declarative Base
# ---------------------------------------------------------
class Base(DeclarativeBase):
    """
    Base class for all SQLAlchemy ORM models.
    """

    pass


# ---------------------------------------------------------
# Database Dependency
# ---------------------------------------------------------
def get_db() -> Generator[Session, None, None]:
    """
    FastAPI database dependency.

    Creates one SQLAlchemy session per request and
    automatically closes it afterwards.
    """

    db = SessionLocal()

    try:
        yield db

    finally:
        db.close()