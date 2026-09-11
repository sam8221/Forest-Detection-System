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
from app.api.dashboard import router as dashboard_router
from app.api.detections import router as detections_router
from app.api.districts import router as districts_router
from app.api.forest_areas import router as forest_areas_router
from app.api.health import router as health_router
from app.api.planetary_computer import router as planetary_computer_router
from app.api.satellite_images import router as satellite_images_router
from app.api.sentinel_wms import router as sentinel_wms_router
from app.api.users import router as users_router

from app.core.config import get_settings
from app.services.email_scheduler import EmailScheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage the lifecycle of ForestWatch background services.
    """

    email_scheduler = EmailScheduler(
        interval_seconds=30
    )

    email_scheduler.start()

    print(
        "[ForestWatch] Email scheduler started."
    )

    try:
        yield

    finally:
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

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.allowed_hosts,
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
        alerts_router,
        prefix=settings.api_v1_prefix,
    )

    app.include_router(
        dashboard_router,
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