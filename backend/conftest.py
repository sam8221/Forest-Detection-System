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

import pytest

from app.core import geospatial_env
from app.services import sms_service as sms_service_module

geospatial_env.configure()


#: What a test is told when nothing stubbed the provider.
#:
#: Deliberately not a working channel. A test that has not
#: said what the provider answers must not be handed a
#: passing one.
PROVIDER_NOT_CONTACTED = sms_service_module.ProviderCheck(
    status=sms_service_module.SmsSystemStatus.PROVIDER_ERROR,
    detail=(
        "The test suite does not contact the SMS provider."
    ),
)


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "sms_credential_check: this test exercises "
        "SmsService.check_credentials itself and stubs the "
        "provider SDK for it, so the suite-wide stand-in "
        "answer is not installed.",
    )


@pytest.fixture(autouse=True)
def sms_provider_is_never_contacted(request, monkeypatch):
    """
    Keep the test suite off the network and off the provider.

    The settings endpoint asks Africa's Talking whether the
    configured credentials work, because a key being present
    is not evidence that it is a valid one. That check is
    right in the running system and wrong in a test: a unit
    test would make a real request to a third party,
    costing several seconds, failing on a machine with no
    internet, and varying with an account this project does
    not control.

    The dissertation requires the tests to run without a
    network, so the check is answered locally for every
    test. A test that cares what the provider says replaces
    this with its own answer; monkeypatch in the test
    applies after this fixture, so it wins.

    The cache is cleared on both sides so that no remembered
    answer, real or stubbed, can leak from one test into
    another.

    A test marked sms_credential_check is testing that
    method and supplies its own stubbed SDK, so it is left
    alone.
    """

    sms_service_module.reset_sms_system_status_cache()

    if request.node.get_closest_marker("sms_credential_check") is None:
        monkeypatch.setattr(
            sms_service_module.SmsService,
            "check_credentials",
            lambda self: PROVIDER_NOT_CONTACTED,
        )

    yield

    sms_service_module.reset_sms_system_status_cache()
