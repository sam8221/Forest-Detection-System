"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Application Entry Point

Purpose:
    Creates and configures the FastAPI application.

Responsibilities:
    - Configure FastAPI.
    - Register middleware.
    - Register API routers.
    - Load application settings.
    - Start and stop background services.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Version:
    1.0.0
===========================================================
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.api.alerts import router as alerts_router
from app.api.analysis import router as analysis_router
from app.api.auth import router as auth_router
from app.api.analytics import router as analytics_router
from app.api.monitoring import router as monitoring_router
from app.api.dashboard import router as dashboard_router
from app.api.detections import router as detections_router
from app.api.reports import router as reports_router
from app.api.districts import router as districts_router
from app.api.provinces import router as provinces_router
from app.api.forest_areas import router as forest_areas_router
from app.api.health import router as health_router
from app.api.planetary_computer import router as planetary_computer_router
from app.api.satellite_images import router as satellite_images_router
from app.api.sentinel_wms import router as sentinel_wms_router
from app.api.users import router as users_router

from app.core.config import get_settings
from app.services.analysis_scheduler import AnalysisScheduler
from app.services.analysis_worker import recover_abandoned_analysis_jobs
from app.services.email_scheduler import EmailScheduler
from app.services.sms_scheduler import SmsScheduler

def recover_abandoned_satellite_download_jobs() -> None:
    """Fail transfers whose worker was stopped with the API process."""

    from app.database.session import SessionLocal
    from app.services.satellite_download_job_service import (
        SatelliteDownloadJobService,
    )

    db = SessionLocal()
    try:
        recovered_count = SatelliteDownloadJobService(db).fail_abandoned()
        if recovered_count:
            print(
                "[ForestWatch] Recovered "
                f"{recovered_count} abandoned satellite download job(s)."
            )
    except Exception as exc:
        db.rollback()
        # This must not prevent startup when a deployment has not yet
        # applied the migration that creates the download-job table.
        print(
            "[ForestWatch] Could not recover abandoned satellite downloads "
            f"({type(exc).__name__})."
        )
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage the lifecycle of ForestWatch background services.
    """

    # Recover abandoned records before starting the database
    # queue worker. A live worker holds the matching advisory
    # lock, so a second API process will leave its job alone.

    try:
        recover_abandoned_analysis_jobs()
    except Exception as exc:
        # Keep the API available when recovery cannot reach PostgreSQL. The
        # scheduler retries recovery and queue polling in its normal loop.
        print(f"[ForestWatch] Could not recover analysis jobs: {type(exc).__name__}")
    recover_abandoned_satellite_download_jobs()

    analysis_scheduler = AnalysisScheduler(interval_seconds=1)
    app.state.analysis_scheduler = analysis_scheduler
    analysis_scheduler.start()

    email_scheduler = EmailScheduler(
        interval_seconds=30
    )

    email_scheduler.start()

    print(
        "[ForestWatch] Email scheduler started."
    )

    # -----------------------------------------------------
    # SMS notifications
    #
    # A second daemon thread in this process, not a second
    # deployed service. It reports for itself whether it
    # started: start() returns without running anything
    # when SMS_ENABLED is false, which is the default, so an
    # installation with no provider configured runs no SMS
    # thread.
    # -----------------------------------------------------

    sms_scheduler = SmsScheduler(
        interval_seconds=30
    )

    sms_scheduler.start()

    try:
        yield

    finally:
        analysis_scheduler.stop()

        sms_scheduler.stop()

        email_scheduler.stop()

        print(
            "[ForestWatch] Email scheduler stopped."
        )


def create_application() -> FastAPI:
    """
    Create and configure the ForestWatch FastAPI application.
    """

    settings = get_settings()

    app = FastAPI(
        title="ForestWatch Zambia API",
        version="1.0.0",
        description=(
            "REST API for the ForestWatch Zambia "
            "Deforestation Detection and Alert System."
        ),
        lifespan=lifespan,
        docs_url=(
            "/docs"
            if settings.is_development
            else None
        ),
        redoc_url=None,
        openapi_url=(
            "/openapi.json"
            if settings.is_development
            else None
        ),
    )

    # Order matters, and is the reverse of the order these
    # calls appear in: Starlette inserts each new middleware
    # at the front of the stack, so the one added last runs
    # outermost. TrustedHostMiddleware is therefore added
    # first and CORSMiddleware second, which puts CORS on
    # the outside.
    #
    # That way a request rejected for its Host still carries
    # the CORS headers on the way out. With the order
    # reversed, a rejection returns a bare 400 the browser
    # discards before any script can read it, and the
    # interface reports the server as unreachable rather
    # than reporting the refusal.
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.allowed_hosts,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(
        health_router,
        prefix=settings.api_v1_prefix,
    )

    app.include_router(
        auth_router,
        prefix=settings.api_v1_prefix,
    )

    app.include_router(
        users_router,
        prefix=settings.api_v1_prefix,
    )

    app.include_router(
        districts_router,
        prefix=settings.api_v1_prefix,
    )

    app.include_router(
        provinces_router,
        prefix=settings.api_v1_prefix,
    )

    app.include_router(
        forest_areas_router,
        prefix=settings.api_v1_prefix,
    )

    app.include_router(
        satellite_images_router,
        prefix=settings.api_v1_prefix,
    )

    app.include_router(
        analysis_router,
        prefix=settings.api_v1_prefix,
    )

    app.include_router(
        detections_router,
        prefix=settings.api_v1_prefix,
    )

    app.include_router(
        reports_router,
        prefix=settings.api_v1_prefix,
    )

    app.include_router(
        alerts_router,
        prefix=settings.api_v1_prefix,
    )

    app.include_router(
        dashboard_router,
        prefix=settings.api_v1_prefix,
    )

    app.include_router(
        analytics_router,
        prefix=settings.api_v1_prefix,
    )

    app.include_router(
        monitoring_router,
        prefix=settings.api_v1_prefix,
    )

    app.include_router(
        planetary_computer_router,
        prefix=settings.api_v1_prefix,
    )

    app.include_router(
        sentinel_wms_router,
        prefix=settings.api_v1_prefix,
    )

    return app


app = create_application()
