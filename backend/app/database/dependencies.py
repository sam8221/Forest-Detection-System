"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Database Dependencies

Purpose:
    Provides reusable FastAPI database dependencies.

Responsibilities:
    - Create database sessions.
    - Close database sessions.
    - Supply Session objects to API endpoints.

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

from sqlalchemy.orm import Session

from app.database.session import SessionLocal


def get_db() -> Generator[Session, None, None]:
    """
    Create a database session for one request.

    The session is automatically closed when
    the request finishes.
    """

    db = SessionLocal()

    try:
        yield db

    finally:
        db.close()