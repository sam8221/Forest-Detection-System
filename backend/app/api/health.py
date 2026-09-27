"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Health Router

Purpose:
    Reports that the API process is running and serving
    requests.

Responsibilities:
    - Answer an unauthenticated liveness check.

How it works:
    This is the one endpoint in the system that requires no
    token. That is deliberate: a health check exists to be
    called by something that holds no credentials, such as a
    hosting platform deciding whether to route traffic to
    this process, or an officer confirming the server is up
    before reporting that the interface is broken.

    It is also the only endpoint safe to expose that way,
    because it reveals nothing. The response is a fixed
    string. It carries no version, no database state, no
    configuration and no record counts, so an unauthenticated
    caller learns only that a process answered.

    Note the limit of what this proves. A 200 here means the
    web process is alive; it does not mean the database is
    reachable, that Copernicus credentials are valid, or that
    analysis jobs are being processed. A deeper readiness
    check would have to touch those, and would then need
    authentication, because reporting which dependency is
    down tells an outsider about the system's internals.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia
===========================================================
"""

from fastapi import APIRouter, status
from pydantic import BaseModel


router = APIRouter(tags=["operations"])


class HealthResponse(BaseModel):
    """
    Response body of the health check.

    Attributes:
        status:
            Always the literal "ok". A failing process does
            not answer at all, so there is no second value
            for this field to take.
    """

    status: str


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
)
def health_check() -> HealthResponse:
    """
    Confirm that the API process is serving requests.

    Returns:
        HealthResponse: Always status "ok".

    Raises:
        Nothing. If this endpoint cannot answer, the process
        is not running, which is the condition the caller is
        testing for.
    """

    return HealthResponse(status="ok")
