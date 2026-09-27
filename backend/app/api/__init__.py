"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Package: app.api

Purpose:
    FastAPI routers exposing the system over HTTP.

Responsibilities:
    - Authenticate and authorise the caller.
    - Validate requests through Pydantic schemas.
    - Delegate to a service.
    - Translate service errors into HTTP status codes.

Note:
    Routers hold no business logic. A router that computes
    something, or queries the database directly, belongs in
    app/services or app/repositories instead.

    Routers are registered in app/main.py. A module added
    here is not reachable until it is included there.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia
===========================================================
"""
