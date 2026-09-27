"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Package: app.core

Purpose:
    Cross-cutting concerns that the rest of the application
    depends on but which belong to no single feature.

Contents:
    config.py    Settings loaded from the environment, and
                 every configurable threshold in the system.
    security.py  Password hashing and JWT creation.

Note:
    Nothing here imports from app.api, app.services or
    app.repositories. This package sits at the bottom of the
    dependency graph; an import in the other direction
    creates a cycle.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia
===========================================================
"""
