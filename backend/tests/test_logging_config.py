"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Tests: Logging configuration

What these protect:

    Sixteen modules in this application report through
    logging.getLogger(__name__). Nothing configured the
    logging module, so the root logger had no handler and
    Python's fallback emits WARNING and above. Every
    logger.info and logger.debug in the codebase was
    discarded.

    The visible symptom was the SMS scheduler. It announced
    its start, its shutdown and every failed cycle, and the
    console showed none of it, while the email scheduler
    used print() and was plainly visible. An administrator
    could not tell whether SMS was running.

    These tests keep the configuration doing the one thing
    that was missing: making those messages appear.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia
===========================================================
"""

import io
import logging

import pytest

from app.core.logging_config import (
    HANDLER_NAME,
    configure_logging,
    resolve_level,
)


@pytest.fixture
def pristine_root_logger():
    """
    Restore the root logger after a test reconfigures it.

    These tests install real handlers, so the state they
    leave behind would otherwise follow the rest of the
    suite.
    """

    root = logging.getLogger()

    saved_handlers = list(root.handlers)

    saved_level = root.level

    yield root

    root.handlers[:] = saved_handlers

    root.setLevel(saved_level)


def forestwatch_handlers(root):
    return [
        handler
        for handler in root.handlers
        if getattr(handler, "name", None) == HANDLER_NAME
    ]


# =========================================================
# LEVELS
# =========================================================


def test_a_level_name_is_understood_whatever_its_case():
    assert resolve_level("debug") == logging.DEBUG

    assert resolve_level("INFO") == logging.INFO

    assert resolve_level("  Warning  ") == logging.WARNING


def test_an_unrecognised_level_falls_back_rather_than_raising():
    """
    A misspelt LOG_LEVEL costs the level that was asked
    for, not the ability to start the application. A system
    that refuses to boot over a logging setting is worse
    than one that logs at the wrong level.
    """

    assert resolve_level("verbose") == logging.INFO

    assert resolve_level("") == logging.INFO

    assert resolve_level(None) == logging.INFO


# =========================================================
# THE FAULT THIS FIXES
# =========================================================


def test_an_info_message_reaches_the_console(
    pristine_root_logger,
):
    """
    The whole point. Before this configuration existed, a
    logger.info call produced nothing at all.
    """

    configure_logging("INFO")

    stream = io.StringIO()

    handler = forestwatch_handlers(pristine_root_logger)[0]

    handler.setStream(stream)

    logging.getLogger("app.services.sms_scheduler").info(
        "SMS scheduler started (interval=%ss).",
        30,
    )

    written = stream.getvalue()

    assert "SMS scheduler started (interval=30s)." in written

    # The logger name is carried, because that is how a
    # reader tells the SMS scheduler from the analysis
    # scheduler when both write to one console from
    # different threads.
    assert "app.services.sms_scheduler" in written


def test_the_level_controls_what_appears(
    pristine_root_logger,
):
    configure_logging("INFO")

    stream = io.StringIO()

    forestwatch_handlers(pristine_root_logger)[0].setStream(stream)

    logging.getLogger("app.services.cloud_mask_service").debug(
        "SCL bounds: %s",
        "(0, 0, 10, 10)",
    )

    assert stream.getvalue() == ""

    configure_logging("DEBUG")

    forestwatch_handlers(pristine_root_logger)[0].setStream(stream)

    logging.getLogger("app.services.cloud_mask_service").debug(
        "SCL bounds: %s",
        "(0, 0, 10, 10)",
    )

    assert "SCL bounds" in stream.getvalue()


def test_configuring_twice_does_not_duplicate_every_line(
    pristine_root_logger,
):
    """
    The application configures logging when it is created,
    and a test suite may import the application repeatedly.
    A second handler would print every message twice.
    """

    configure_logging("INFO")

    configure_logging("INFO")

    configure_logging("DEBUG")

    assert len(forestwatch_handlers(pristine_root_logger)) == 1


def test_a_repeat_call_still_changes_the_level(
    pristine_root_logger,
):
    configure_logging("WARNING")

    configure_logging("DEBUG")

    handler = forestwatch_handlers(pristine_root_logger)[0]

    assert handler.level == logging.DEBUG

    assert pristine_root_logger.level == logging.DEBUG


def test_loggers_that_already_exist_keep_working(
    pristine_root_logger,
):
    """
    Uvicorn configures its own loggers before this
    application is imported. Disabling them would silence
    the request lines an operator reads the console for.
    """

    uvicorn_logger = logging.getLogger("uvicorn.error")

    configure_logging("INFO")

    assert uvicorn_logger.disabled is False
