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
