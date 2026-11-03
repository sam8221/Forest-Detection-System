"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Cloud Monitoring Schemas

Purpose:
    Shapes of the cloud monitoring responses.

Note on the optional percentages:

    Every percentage in this module may be null, and that is
    the point of the design rather than an oversight. A card
    that cannot report a figure says so and sends nothing in
    its place. A zero would read as a clear sky.

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

from pydantic import BaseModel, ConfigDict, Field


class DistrictOption(BaseModel):
    """A district the officer may monitor."""

    id: int

    name: str

    code: str


class ObservationPointResponse(BaseModel):
    """Where the current reading was taken for."""

    latitude: float

    longitude: float

    source: str = Field(
        description=(
            "monitored_areas when derived from the geometry "
            "of the forest areas monitored in the district, "
            "district_reference when the district has none "
            "and its town was used instead. Reported "
            "because the two are not equally close to the "
            "forest being watched."
        ),
    )

    monitored_area_count: int = Field(
        description=(
            "How many monitored areas the point was derived "
            "from. Zero for a reference point."
        ),
    )


class CurrentCloudResponse(BaseModel):
    """Cloud cover now, from the weather provider."""

    available: bool = Field(
        description=(
            "False when the provider could not be reached "
            "or is switched off. The interface must show "
            "the reason rather than an empty gauge."
        ),
    )

    unavailable_reason: str | None = None

    percentage: float | None = Field(
        default=None,
        description=(
            "Sky covered, 0 to 100. Null when there is no "
            "reading; never a substituted zero."
        ),
    )

    condition: str = Field(
        description=(
            "CLEAR, PARTLY_CLOUDY, CLOUDY, VERY_CLOUDY or "
            "UNKNOWN, on the okta boundaries in "
            "app.core.config."
        ),
    )

    condition_label: str

    observed_at: str | None = Field(
        default=None,
        description=(
            "The provider's own timestamp for the reading, "
            "in Zambian local time. Not the time this "
            "system asked."
        ),
    )

    retrieved_at: str | None = Field(
        default=None,
        description=(
            "When this system received the reading. Differs "
            "from observed_at for a cached reading, and the "
            "interface shows both so a stale one is "
            "visible."
        ),
    )

    provider: str | None = None

    latitude: float | None = Field(
        default=None,
        description=(
            "The grid point the provider answered for, which "
            "may differ from the point requested."
        ),
    )

    longitude: float | None = None


class SatelliteObservationResponse(BaseModel):
    """One Sentinel-2 observation and its recorded cloud cover."""

    image_id: int

    product_id: str

    acquisition_date: str | None = Field(
        default=None,
        description=(
            "When the satellite passed. Always shown beside "
            "the figure, so a recent observation is not "
            "read as current conditions."
        ),
    )

    percentage: float

    condition: str

    condition_label: str

    forest_area_name: str

    is_processed: bool

    suitable_for_analysis: bool | None = Field(
        default=None,
        description=(
            "Whether the scene is within "
            "MAX_CLOUD_COVER_PERCENTAGE. Null when no cloud "
            "figure was recorded: that is 'cannot say', not "
            "'unsuitable', and an officer acts differently "
            "on each."
        ),
    )


class SatelliteCloudResponse(BaseModel):
    """The Sentinel-2 half of the card."""

    available: bool

    unavailable_reason: str | None = None

    latest: SatelliteObservationResponse | None = None

    observations: list[SatelliteObservationResponse] = []

    suitable_count: int

    observation_count: int

    suitability_threshold: float


class CloudMonitoringResponse(BaseModel):
    """Everything the cloud monitoring card displays."""

    district_id: int

    district_name: str

    observation_point: ObservationPointResponse | None = None

    current: CurrentCloudResponse

    satellite: SatelliteCloudResponse

    generated_at: str = Field(
        description=(
            "When this report was assembled. Distinct from "
            "both the weather observation time and any "
            "acquisition date."
        ),
    )

    model_config = ConfigDict(
        from_attributes=True,
    )


class CloudMonitoringDistrictsResponse(BaseModel):
    """The districts available, and which to show first."""

    districts: list[DistrictOption]

    default_district_id: int | None = None
