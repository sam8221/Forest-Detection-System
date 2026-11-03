"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Geospatial Data Paths

Purpose:
    Point PROJ and GDAL at the coordinate reference data
    that ships with the installed rasterio wheel, before
    rasterio is first imported.

Why this module exists:

    PROJ finds its coordinate reference database, proj.db,
    through the PROJ_DATA environment variable, falling back
    to the older PROJ_LIB. GDAL finds its own data through
    GDAL_DATA. Those variables are global to the machine,
    and a PostGIS installation sets them: on the development
    machine for this project, the PostgreSQL installer left

        PROJ_LIB=D:\\Database\\share\\contrib\\postgis-3.5\\proj
        GDAL_DATA=D:\\Database\\gdal-data

    pointing at the PROJ database that PostGIS bundles.

    PostGIS and the rasterio wheel do not ship the same PROJ
    release, and proj.db is versioned. rasterio then reads
    PostGIS's older database and refuses it:

        proj.db contains DATABASE.LAYOUT.VERSION.MINOR = 2
        whereas a number >= 6 is expected.
        It comes from another PROJ installation.

    Every lookup by EPSG code fails with that error, so
    CRS.from_epsg(32735) - UTM 35S, the projection the whole
    system measures areas in - raises CRSError. The raster
    services work around it by building their projections
    from self-contained PROJ strings, which need no database
    at all. That keeps the pipeline running but does not help
    anything that legitimately asks for an EPSG code, and the
    raster tests cannot even be collected.

    The fix belongs here rather than in each caller: the
    variables are repaired once, at the bottom of the import
    graph, so both the application and the test suite get a
    working PROJ without every module having to avoid EPSG
    codes.

What this deliberately does not do:

    It does not touch a PROJ_DATA or GDAL_DATA that already
    points at a usable directory for this interpreter. An
    operator who has configured a PROJ installation of their
    own keeps it; only a path that does not contain the file
    PROJ needs is replaced.

    It also cannot help if rasterio has already been
    imported, because GDAL reads these variables once when
    it initialises. configure() is therefore called from
    app/__init__.py, which Python executes before any
    app.services module can import rasterio.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Version:
    1.0.0
===========================================================
"""

from __future__ import annotations

import os
import sqlite3
from importlib.util import find_spec
from pathlib import Path

#: Variables PROJ reads, in the order PROJ itself prefers.
#: PROJ_LIB is the historical name and is still honoured, so
#: both are set; leaving a stale PROJ_LIB behind would let it
#: win on an older PROJ build.
_PROJ_VARIABLES = ("PROJ_DATA", "PROJ_LIB")

#: The file whose presence makes a directory a usable PROJ
#: data directory.
_PROJ_DATABASE = "proj.db"

#: A file GDAL ships in its data directory, used the same way
#: to tell a real GDAL_DATA from an empty or wrong one. The
#: better known gcs.csv is not used: GDAL 3 moved the EPSG
#: tables into proj.db and no longer ships it, so testing for
#: it would condemn every modern GDAL data directory.
_GDAL_MARKER = "header.dxf"


def _rasterio_data_directory(name: str) -> Path | None:
    """
    Locate a data directory inside the installed rasterio.

    find_spec is used rather than an import, because importing
    rasterio is the thing that must not happen until the
    environment has been repaired.
    """

    spec = find_spec("rasterio")

    if spec is None or not spec.origin:
        return None

    candidate = Path(spec.origin).parent / name

    return candidate if candidate.is_dir() else None


def _is_usable(directory: str | None, marker: str) -> bool:
    """Report whether a configured directory holds its data."""

    if not directory:
        return False

    try:
        return (Path(directory) / marker).exists()
    except OSError:
        # An unreadable or malformed path is not usable, and
        # is not a reason to fail the import.
        return False


def _proj_layout_version(database: Path) -> tuple[int, int] | None:
    """
    Read the schema version recorded inside a proj.db.

    proj.db is an SQLite database holding its own layout
    version in a metadata table. PROJ refuses a database
    whose layout is older than the one the library was built
    for, which is the whole failure this module exists to
    prevent, so the version is the only honest way to tell a
    usable PROJ directory from one that merely contains a
    file of the right name.

    Returns None when the file cannot be read as a PROJ
    database, which is treated the same as being too old.
    """

    try:
        connection = sqlite3.connect(
            f"file:{database}?mode=ro",
            uri=True,
        )
    except sqlite3.Error:
        return None

    try:
        recorded = dict(
            connection.execute(
                "SELECT key, value FROM metadata "
                "WHERE key IN ("
                "  'DATABASE.LAYOUT.VERSION.MAJOR',"
                "  'DATABASE.LAYOUT.VERSION.MINOR'"
                ")"
            ).fetchall()
        )
    except sqlite3.Error:
        return None
    finally:
        connection.close()

    try:
        return (
            int(recorded["DATABASE.LAYOUT.VERSION.MAJOR"]),
            int(recorded["DATABASE.LAYOUT.VERSION.MINOR"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _proj_directory_is_current(
    directory: str | None,
    required: tuple[int, int] | None,
) -> bool:
    """
    Report whether a PROJ directory is new enough to use.

    A directory qualifies when it holds a proj.db whose
    layout version is at least the one rasterio's own
    database declares. Equal or newer is accepted, so an
    operator who maintains a more recent PROJ installation
    keeps it; only an older database is replaced.
    """

    if not directory:
        return False

    if required is None:
        # Without a reference version there is nothing to
        # compare against, so presence is all that can be
        # checked and the configured value is left alone.
        return _is_usable(directory, _PROJ_DATABASE)

    try:
        database = Path(directory) / _PROJ_DATABASE

        if not database.exists():
            return False
    except OSError:
        return False

    configured = _proj_layout_version(database)

    return configured is not None and configured >= required


def configure() -> None:
    """
    Repair PROJ and GDAL data paths for this process.

    Safe to call more than once, and safe to call on a
    machine where nothing is misconfigured: in that case
    every variable already points at a usable directory and
    nothing is changed.
    """

    # ---------------------------------------------------------
    # PROJ
    #
    # Replaced only when no configured variable resolves to a
    # proj.db at least as new as rasterio's own. pyproj's
    # bundled directory would serve equally well; rasterio's
    # is chosen because rasterio is what reads and writes
    # every raster in this system, so its GDAL and its PROJ
    # stay matched.
    #
    # Comparing versions rather than merely testing for the
    # file is what makes this work at all: the PostGIS
    # directory does contain a proj.db, and that is precisely
    # the problem. It is layout 1.2 where rasterio needs 1.6.
    # ---------------------------------------------------------

    bundled_proj = _rasterio_data_directory("proj_data")

    required_layout = (
        _proj_layout_version(bundled_proj / _PROJ_DATABASE)
        if bundled_proj is not None
        else None
    )

    proj_configured = any(
        _proj_directory_is_current(
            os.environ.get(variable),
            required_layout,
        )
        for variable in _PROJ_VARIABLES
    )

    if not proj_configured and bundled_proj is not None and (
        bundled_proj / _PROJ_DATABASE
    ).exists():

        for variable in _PROJ_VARIABLES:
            os.environ[variable] = str(bundled_proj)

    # ---------------------------------------------------------
    # GDAL
    #
    # GDAL_DATA was not the cause of the failure described
    # above; PROJ_LIB was. It is repaired on the same principle
    # only so that an unset or empty GDAL_DATA cannot become
    # the next version-mismatch of the same kind. A directory
    # that does hold GDAL's data is left alone, including the
    # one PostGIS installs.
    # ---------------------------------------------------------

    if not _is_usable(os.environ.get("GDAL_DATA"), _GDAL_MARKER):

        bundled_gdal = _rasterio_data_directory("gdal_data")

        if bundled_gdal is not None:
            os.environ["GDAL_DATA"] = str(bundled_gdal)


#: GDAL settings that affect only how fast a raster is read,
#: never what it contains. Each is applied once, before
#: rasterio is imported, and only when the environment does
#: not already set it, so a deployment can still override any
#: of them.
#:
#: GDAL_NUM_THREADS
#:     JPEG 2000 decoding is the single most expensive step in
#:     this pipeline: every Sentinel-2 band is a JP2, and NDVI,
#:     the cloud mask and the true-colour preview each decode
#:     one. Left unset, GDAL decodes on one core while the rest
#:     of the machine idles.
#:
#: GDAL_CACHEMAX
#:     Block cache, in megabytes. The pipeline reads the same
#:     window of the same band more than once - NDVI, then the
#:     mask, then the preview - and a cache large enough to
#:     hold that window serves the later reads from memory.
#:
#: VSI_CACHE / VSI_CACHE_SIZE
#:     Caches file reads beneath the block cache, which is what
#:     makes reading a band out of a .SAFE.zip through
#:     /vsizip/ reasonable.
_RASTER_PERFORMANCE_DEFAULTS = {
    "GDAL_NUM_THREADS": "ALL_CPUS",
    "GDAL_CACHEMAX": "512",
    "VSI_CACHE": "TRUE",
    "VSI_CACHE_SIZE": "67108864",
}


def configure_raster_performance() -> None:
    """
    Apply GDAL read-performance settings for this process.

    These change how long a raster takes to read, not what is
    read. Values already present in the environment are left
    alone, so a deployment that needs different limits sets
    them there and this does nothing.

    Safe to call more than once.
    """

    for name, value in _RASTER_PERFORMANCE_DEFAULTS.items():

        if not os.environ.get(name):
            os.environ[name] = value
