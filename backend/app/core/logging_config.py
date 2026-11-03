"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Logging Configuration

Purpose:
    Gives the application one place where log output is
    turned on, so that what the background services report
    actually reaches the console.

Why this exists:
    Sixteen modules create a logger with
    logging.getLogger(__name__) and report through it, but
    nothing ever configured the logging module. Python's
    root logger has no handler by default and its fallback
    handler emits WARNING and above, so every logger.info
    and logger.debug in this codebase was discarded.

    The visible consequence: the SMS scheduler announced its
    start, its shutdown and every failed cycle through
    logger.info and logger.exception, and none of it
    appeared. An administrator reading the console could not
    tell whether SMS was running at all, while the email
    scheduler, which used print(), was plainly visible. The
    two were reporting through different mechanisms and only
    one of them worked.

    So the application configures logging once, here, and
    the services report through loggers rather than print().

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

import logging
import logging.config

from app.core.config import get_settings


#: Marks the handler this module installs.
#:
#: configure_logging may be called more than once in one
#: process: the application configures logging when it is
#: created, and a test suite may import the application
#: repeatedly. Without a way to recognise its own handler,
#: each call would attach another one and every line would
#: be printed as many times as the function had run.
HANDLER_NAME = "forestwatch-console"


#: Format of one console line.
#:
#: Time, level, logger name, message. The logger name is
#: included because the name is how a reader tells the SMS
#: scheduler from the analysis scheduler when both are
#: writing to the same console from different threads.
LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s | %(message)s"

TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def resolve_level(name: str | None) -> int:
    """
    Turn a configured level name into a logging level.

    Args:
        name:
            A level name such as "INFO" or "debug", or None.

    Returns:
        The matching logging level, or logging.INFO when the
        name is empty or not a level.

    An unrecognised value falls back rather than raising. A
    misspelt LOG_LEVEL should cost the operator the level
    they asked for, not the ability to start the system.
    """

    if not name:
        return logging.INFO

    level = logging.getLevelName(
        str(name).strip().upper()
    )

    # getLevelName returns the string "Level X" for anything
    # it does not know, so an int is the test for a real one.
    if isinstance(level, int):
        return level

    return logging.INFO


def configure_logging(level: str | None = None) -> None:
    """
    Install console logging for the whole application.

    Args:
        level:
            Level name to use. Defaults to the LOG_LEVEL
            setting, which defaults to INFO.

    Safe to call more than once: a second call updates the
    level of the handler already installed instead of adding
    a second one.

    Loggers that already exist are left enabled. Uvicorn
    configures its own loggers before importing this
    application, and they do not propagate to the root
    logger, so uvicorn's request lines continue to appear
    exactly as before and are not printed twice.
    """

    resolved = resolve_level(
        level
        if level is not None
        else get_settings().log_level
    )

    root = logging.getLogger()

    for handler in root.handlers:
        if getattr(handler, "name", None) == HANDLER_NAME:
            handler.setLevel(resolved)
            root.setLevel(resolved)

            return

    logging.config.dictConfig(
        {
            "version": 1,
            # Uvicorn's loggers are configured before this
            # application is imported. Disabling existing
            # loggers would silence its startup and access
            # lines.
            "disable_existing_loggers": False,
            "formatters": {
                "forestwatch": {
                    "format": LOG_FORMAT,
                    "datefmt": TIME_FORMAT,
                },
            },
            "handlers": {
                HANDLER_NAME: {
                    "class": "logging.StreamHandler",
                    "formatter": "forestwatch",
                    # stderr, matching uvicorn, so that
                    # redirecting one stream captures the
                    # whole startup story rather than half
                    # of it.
                    "stream": "ext://sys.stderr",
                    "level": resolved,
                },
            },
            "root": {
                "handlers": [HANDLER_NAME],
                "level": resolved,
            },
        }
    )
    # dictConfig names each handler it builds after its key,
    # which is what the repeat-call check above looks for.
