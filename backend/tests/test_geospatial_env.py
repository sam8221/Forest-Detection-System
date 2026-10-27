"""
Repair of the PROJ and GDAL data paths.

A PostGIS installation sets PROJ_LIB machine-wide to its own
proj.db, which is an older schema than the rasterio wheel
accepts. Every lookup by EPSG code then fails. These tests
cover the decision this module makes - replace an older PROJ
directory, leave a current one alone - and then confirm that
on this machine an EPSG lookup actually works.
"""

from __future__ import annotations

import sqlite3
from importlib.util import find_spec
from pathlib import Path

import pytest

from app.core import geospatial_env


RASTERIO_ROOT = Path(find_spec("rasterio").origin).parent

BUNDLED_PROJ = RASTERIO_ROOT / "proj_data"

BUNDLED_GDAL = RASTERIO_ROOT / "gdal_data"


def write_proj_database(path: Path, major: int, minor: int) -> Path:
    """Create a proj.db carrying only its layout version."""

    path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE metadata (key TEXT, value TEXT)")
        connection.executemany(
            "INSERT INTO metadata (key, value) VALUES (?, ?)",
            [
                ("DATABASE.LAYOUT.VERSION.MAJOR", str(major)),
                ("DATABASE.LAYOUT.VERSION.MINOR", str(minor)),
            ],
        )
        connection.commit()
    finally:
        connection.close()

    return path


# =========================================================
# READING A PROJ DATABASE
# =========================================================

def test_layout_version_is_read_from_the_database(tmp_path):
    database = write_proj_database(tmp_path / "proj.db", 1, 6)

    assert geospatial_env._proj_layout_version(database) == (1, 6)


@pytest.mark.parametrize("contents", [b"", b"not a database at all"])
def test_a_file_that_is_not_a_proj_database_has_no_version(tmp_path, contents):
    database = tmp_path / "proj.db"
    database.write_bytes(contents)

    assert geospatial_env._proj_layout_version(database) is None


def test_a_database_without_a_recorded_version_has_no_version(tmp_path):
    database = tmp_path / "proj.db"
    connection = sqlite3.connect(database)
    try:
        connection.execute("CREATE TABLE metadata (key TEXT, value TEXT)")
        connection.commit()
    finally:
        connection.close()

    assert geospatial_env._proj_layout_version(database) is None


def test_a_missing_file_has_no_version(tmp_path):
    assert geospatial_env._proj_layout_version(tmp_path / "absent.db") is None


# =========================================================
# WHICH DIRECTORY IS KEPT
# =========================================================

def test_an_older_proj_directory_is_not_accepted(tmp_path):
    """
    This is the PostGIS case: the directory holds a real
    proj.db, so testing only for the file's presence would
    accept it. Its layout is 1.2 where 1.6 is required.
    """

    write_proj_database(tmp_path / "proj.db", 1, 2)

    assert geospatial_env._proj_directory_is_current(
        str(tmp_path), required=(1, 6)
    ) is False


@pytest.mark.parametrize("layout", [(1, 6), (1, 7), (2, 0)])
def test_a_current_or_newer_proj_directory_is_accepted(tmp_path, layout):
    """An operator maintaining their own newer PROJ keeps it."""

    write_proj_database(tmp_path / "proj.db", *layout)

    assert geospatial_env._proj_directory_is_current(
        str(tmp_path), required=(1, 6)
    ) is True


def test_a_directory_with_no_proj_database_is_not_accepted(tmp_path):
    assert geospatial_env._proj_directory_is_current(
        str(tmp_path), required=(1, 6)
    ) is False


@pytest.mark.parametrize("directory", [None, ""])
def test_an_unset_proj_variable_is_not_accepted(directory):
    assert geospatial_env._proj_directory_is_current(
        directory, required=(1, 6)
    ) is False


# =========================================================
# WHAT CONFIGURE DOES TO THE ENVIRONMENT
# =========================================================

def test_configure_replaces_an_older_proj_directory(tmp_path, monkeypatch):
    """The failure this module exists to prevent."""

    postgis = tmp_path / "postgis-proj"
    write_proj_database(postgis / "proj.db", 1, 2)

    monkeypatch.setenv("PROJ_LIB", str(postgis))
    monkeypatch.delenv("PROJ_DATA", raising=False)

    geospatial_env.configure()

    import os

    # Both names are rewritten. Leaving a stale PROJ_LIB
    # behind would let it win on an older PROJ build.
    assert Path(os.environ["PROJ_DATA"]) == BUNDLED_PROJ
    assert Path(os.environ["PROJ_LIB"]) == BUNDLED_PROJ


def test_configure_leaves_a_current_proj_directory_alone(tmp_path, monkeypatch):
    required = geospatial_env._proj_layout_version(BUNDLED_PROJ / "proj.db")
    assert required is not None, "rasterio's bundled proj.db should be readable"

    operators_own = tmp_path / "operator-proj"
    write_proj_database(
        operators_own / "proj.db", required[0], required[1] + 1
    )

    monkeypatch.setenv("PROJ_DATA", str(operators_own))
    monkeypatch.setenv("PROJ_LIB", str(operators_own))

    geospatial_env.configure()

    import os

    assert Path(os.environ["PROJ_DATA"]) == operators_own


def test_configure_sets_gdal_data_when_it_is_unset(monkeypatch):
    monkeypatch.delenv("GDAL_DATA", raising=False)

    geospatial_env.configure()

    import os

    assert Path(os.environ["GDAL_DATA"]) == BUNDLED_GDAL


def test_configure_leaves_a_populated_gdal_directory_alone(monkeypatch):
    monkeypatch.setenv("GDAL_DATA", str(BUNDLED_GDAL))

    geospatial_env.configure()

    import os

    assert Path(os.environ["GDAL_DATA"]) == BUNDLED_GDAL


def test_configure_can_be_called_repeatedly(monkeypatch):
    monkeypatch.delenv("PROJ_DATA", raising=False)
    monkeypatch.delenv("PROJ_LIB", raising=False)

    geospatial_env.configure()

    import os

    first = os.environ["PROJ_DATA"]

    geospatial_env.configure()

    assert os.environ["PROJ_DATA"] == first


# =========================================================
# THE OUTCOME THAT MATTERS
# =========================================================

def test_epsg_lookups_work_in_this_process():
    """
    The whole point. EPSG:32735 is WGS 84 / UTM zone 35S, the
    projection the system measures detection areas in, and
    this lookup is what raised CRSError before the repair.

    conftest.py has already called configure() for the test
    session, so this asserts the repair holds in practice and
    not only in isolation.
    """

    from rasterio.crs import CRS

    assert CRS.from_epsg(32735).to_epsg() == 32735
    assert CRS.from_epsg(4326).to_epsg() == 4326
