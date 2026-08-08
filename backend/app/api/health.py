"""Unauthenticated operational-health endpoint."""
from fastapi import APIRouter, status
from pydantic import BaseModel

router = APIRouter(tags=["operations"])

class HealthResponse(BaseModel):
    status: str

@router.get("/health", response_model=HealthResponse, status_code=status.HTTP_200_OK)
def health_check() -> HealthResponse:
    """Confirm that the API process is serving requests."""
    return HealthResponse(status="ok")