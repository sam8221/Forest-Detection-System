"""API response schema for satellite download progress."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SatelliteDownloadJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    job_id: str
    forest_area_id: int
    product_id: str
    product_name: str
    status: str
    downloaded_bytes: int = Field(ge=0)
    total_bytes: int | None = Field(default=None, ge=1)
    progress_percentage: float | None = Field(default=None, ge=0, le=100)
    satellite_image_id: int | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
