"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Package: app

Purpose:
    Root package of the ForestWatch Zambia backend.

Structure:
    api/           FastAPI routers. HTTP only, no business
                   logic.
    services/      Business logic. Runnable without a web
                   server, which is what makes the accuracy
                   evaluation possible as an isolated
                   exercise.
    repositories/  Data access. Every query lives here, and
                   so does jurisdiction filtering.
    models/        SQLAlchemy ORM entities.
    schemas/       Pydantic request and response contracts.
    core/          Configuration and security primitives.
    database/      Engine and session management.

Note:
    The layering is deliberate and dependencies run one way
    only: api -> services -> repositories -> models. A router
    that queries the database directly, or a service that
    imports FastAPI, breaks the property that detection logic
    can be run and tested without a network or a database.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia
===========================================================
"""

# ---------------------------------------------------------
# Coordinate reference data
#
# This runs before any other module in the package, which is
# the point: GDAL reads the PROJ and GDAL data paths once,
# when it initialises on the first rasterio import, so they
# have to be correct before app.services is reached. A
# PostGIS installation on the machine sets those paths to its
# own older PROJ database and every EPSG lookup then fails.
# See app/core/geospatial_env.py for the full account.
#
# app.core.geospatial_env imports only the standard library,
# so this does not give the package a heavyweight import or
# reach outside app.core.
# ---------------------------------------------------------

from app.core import geospatial_env as _geospatial_env

_geospatial_env.configure()
