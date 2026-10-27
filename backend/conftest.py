"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Test Session Configuration

Purpose:
    Repair the PROJ and GDAL data paths before any test
    module is imported.

Why this file is needed as well as app/__init__.py:

    The application repairs those paths in app/__init__.py,
    which is early enough there because every module that
    touches rasterio lives under app. A test module is not
    bound by that order. Several of them import rasterio
    directly, at module scope, before they import anything
    from app:

        import rasterio
        from rasterio.crs import CRS
        ...
        from app.core.constants import NDVI_NODATA

    GDAL reads PROJ_DATA once, when it initialises on that
    first rasterio import, so by the time app is reached the
    damage is done and

        TEST_CRS = CRS.from_epsg(32735)

    fails during collection with

        proj.db contains DATABASE.LAYOUT.VERSION.MINOR = 2
        whereas a number >= 6 is expected.

    pytest imports conftest.py before the test modules it
    applies to, which makes this the one place that runs
    early enough for all of them. The repair itself lives in
    app.core.geospatial_env and is not duplicated here; that
    module explains what is wrong with the machine
    environment and why.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Version:
    1.0.0
===========================================================
"""

from app.core import geospatial_env

geospatial_env.configure()
