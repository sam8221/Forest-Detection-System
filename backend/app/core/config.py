"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Application Configuration

Purpose:
    Single authoritative source for every setting and every
    tunable threshold in the system.

Responsibilities:
    - Load configuration from the environment.
    - Supply the detection thresholds the pipeline applies.
    - Resolve imagery storage paths and service endpoints.
    - Validate settings that can be written incorrectly.

How it works:
    Settings extends Pydantic's BaseSettings, which reads
    each field from the environment or from a .env file,
    coerces it to the declared type, and fails at startup if
    a required value is missing. A misconfigured deployment
    therefore refuses to start rather than failing later in
    the middle of an analysis run.

    get_settings() is wrapped in lru_cache, so the object is
    built once per process and every module that calls it
    receives the same instance.

Why thresholds live here and not in the services:
    Each detection threshold is defined once, here, rather
    than as a class constant in every service that reads it.
    A change therefore takes effect everywhere at once, and
    the dissertation can cite one authoritative source for
    each figure rather than several that might disagree.

    Two of them carry meaning beyond being adjustable:

      min_detection_area_hectares defaults to 0.50. That is
      50 Sentinel-2 pixels at 10 m resolution, and it is
      taken from the area threshold in the Forests Act No. 4
      of 2015, which defines a forest as land with "a tree
      canopy cover of more than ten percent and area of more
      than zero point five hectares". It also suppresses
      isolated noise pixels.

      Note what this threshold does and does not do. The Act
      defines a forest by three criteria: canopy cover, area
      and, for young stands, tree height. Only the area
      criterion is applied here. A detection is therefore
      not a finding that a forest as legally defined has
      been cleared; it is a patch large enough to be worth
      an officer's attention.

      Note also the boundary. The Act says "more than" 0.5
      hectares, while the filter in detection_service keeps
      a patch of exactly 0.5 hectares. Because pixel areas
      are whole multiples of 100 square metres, a 50-pixel
      patch lands exactly on the boundary and is kept. This
      is deliberate: the threshold exists to suppress noise,
      and excluding a patch for being one pixel short of a
      legal definition the system does not otherwise test
      would trade a real detection for false precision.

      ndvi_threshold is the decline in NDVI that counts as
      vegetation loss. It is configurable per analysis job,
      and this is the default when a job does not specify
      one.

Security:
    Credentials belong in the environment, never in source
    control. secret_key and database_url have no defaults, so
    the application will not start without them. The
    Copernicus credentials and the Sentinel Hub instance
    identifier default to empty and fail at the point of use
    with a message naming the missing variable.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia
===========================================================
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# ---------------------------------------------------------
# Backend package root
#
# This file lives at:
#
#     backend/app/core/config.py
#
# so parents[2] resolves to the "backend" directory itself.
#
# Resolving the root from the module location rather than the
# current working directory means storage paths stay correct
# no matter where the application or a management command is
# launched from.
# ---------------------------------------------------------

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --------------------------------------------------
    # Application
    # --------------------------------------------------

    app_name: str = Field(
        default="Forest Detection API",
        alias="APP_NAME",
    )

    app_version: str = Field(
        default="1.0.0",
        alias="APP_VERSION",
    )

    environment: str = Field(
        default="development",
        alias="ENVIRONMENT",
    )

    # --------------------------------------------------
    # API
    # --------------------------------------------------

    api_v1_prefix: str = "/api/v1"

    # --------------------------------------------------
    # Security
    # --------------------------------------------------

    secret_key: str = Field(
        alias="SECRET_KEY",
    )

    algorithm: str = Field(
        default="HS256",
        alias="ALGORITHM",
    )

    access_token_expire_minutes: int = Field(
        default=60,
        alias="ACCESS_TOKEN_EXPIRE_MINUTES",
    )

    # --------------------------------------------------
    # Database
    # --------------------------------------------------

    database_url: str = Field(
        alias="DATABASE_URL",
    )

    # Log every SQL statement. Useful when inspecting a
    # specific query, but it buries application output, so
    # it is off unless asked for.
    database_echo: bool = Field(
        default=False,
        alias="DATABASE_ECHO",
    )

    # --------------------------------------------------
    # Network
    # --------------------------------------------------

    allowed_hosts_raw: str = Field(
        default="localhost,127.0.0.1",
        alias="ALLOWED_HOSTS",
    )

    @property
    def allowed_hosts(self) -> list[str]:
        """Return allowed hosts as a list."""

        return [
            host.strip()
            for host in self.allowed_hosts_raw.split(",")
            if host.strip()
        ]

    @property
    def is_development(self) -> bool:
        """Check whether the application is running in development."""

        return self.environment.lower() == "development"

    # --------------------------------------------------
    # SMTP
    # --------------------------------------------------

    smtp_host: str = Field(
        default="",
        alias="SMTP_HOST",
    )

    smtp_port: int = Field(
        default=587,
        alias="SMTP_PORT",
    )

    smtp_username: str = Field(
        default="",
        alias="SMTP_USERNAME",
    )

    smtp_password: str = Field(
        default="",
        alias="SMTP_PASSWORD",
    )

    smtp_from_email: str = Field(
        default="",
        alias="SMTP_FROM_EMAIL",
    )

    # --------------------------------------------------
    # Copernicus OAuth
    # --------------------------------------------------

    copernicus_client_id: str = Field(
        default="",
        alias="COPERNICUS_CLIENT_ID",
    )

    copernicus_client_secret: str = Field(
        default="",
        alias="COPERNICUS_CLIENT_SECRET",
    )

    # --------------------------------------------------
    # Copernicus Account
    # --------------------------------------------------

    copernicus_username: str = Field(
        default="",
        alias="COPERNICUS_USERNAME",
    )

    copernicus_password: str = Field(
        default="",
        alias="COPERNICUS_PASSWORD",
    )

    # --------------------------------------------------
    # Detection thresholds
    #
    # Each value is defined once, here, rather than as a
    # class constant in every service that reads it, so a
    # single change is reflected everywhere and the
    # dissertation can cite one authoritative source for
    # each threshold.
    # --------------------------------------------------

    ndvi_threshold: float = Field(
        default=0.30,
        alias="NDVI_THRESHOLD",
    )

    min_detection_area_hectares: float = Field(
        default=0.50,
        alias="MIN_DETECTION_AREA_HECTARES",
    )

    max_cloud_cover_percentage: float = Field(
        default=30.0,
        alias="MAX_CLOUD_COVER_PERCENTAGE",
    )

    image_search_days: int = Field(
        default=30,
        alias="IMAGE_SEARCH_DAYS",
    )

    # --------------------------------------------------
    # Monitoring extent
    #
    # The geographic bounds the system monitors, as
    # "min_longitude,min_latitude,max_longitude,max_latitude"
    # in WGS84.
    #
    # The default covers the Copperbelt Province, which is
    # the study area for this dissertation. It is a setting
    # rather than a literal so the system can be pointed at
    # another province without a code change, which is the
    # first thing that would be asked of it if the Forestry
    # Department adopted it beyond the pilot.
    # --------------------------------------------------

    monitoring_bbox_raw: str = Field(
        default="27.20,-13.70,29.50,-11.70",
        alias="MONITORING_BBOX",
    )

    @property
    def monitoring_bbox(self) -> tuple[float, float, float, float]:
        """
        Return the monitoring extent as four floats.

        Returns:
            tuple[float, float, float, float]:
                Minimum longitude, minimum latitude,
                maximum longitude and maximum latitude.

        Raises:
            ValueError:
                The configured value is not four
                comma-separated numbers, or the bounds are
                inverted.
        """

        parts = [
            part.strip()
            for part in self.monitoring_bbox_raw.split(",")
            if part.strip()
        ]

        if len(parts) != 4:
            raise ValueError(
                "MONITORING_BBOX must be four "
                "comma-separated numbers: "
                "min_longitude,min_latitude,"
                "max_longitude,max_latitude."
            )

        try:
            min_lon, min_lat, max_lon, max_lat = (
                float(part) for part in parts
            )
        except ValueError as exc:
            raise ValueError(
                "MONITORING_BBOX contains a value that is "
                "not a number."
            ) from exc

        # Caught here rather than at the imagery provider,
        # which would answer an inverted box with an empty
        # result set and no explanation.
        if min_lon >= max_lon or min_lat >= max_lat:
            raise ValueError(
                "MONITORING_BBOX minimum bounds must be "
                "smaller than its maximum bounds."
            )

        return (min_lon, min_lat, max_lon, max_lat)

    # --------------------------------------------------
    # Microsoft Planetary Computer
    #
    # A secondary imagery catalogue, used by the dashboard
    # to show the most recent Sentinel-2 scene over the
    # monitoring extent.
    #
    # Copernicus remains the system's imagery source: it is
    # what the detection pipeline downloads from and what
    # the map renders through. This catalogue is consulted
    # only for the dashboard's scene summary, and the
    # dashboard is expected to remain usable when it cannot
    # be reached.
    # --------------------------------------------------

    planetary_stac_url: str = Field(
        default="https://planetarycomputer.microsoft.com/api/stac/v1",
        alias="PLANETARY_STAC_URL",
    )

    # Two requests are made in sequence, so this is the
    # ceiling on each rather than on the pair: the worst
    # case an officer waits is twice this figure. It is
    # deliberately short, because a dashboard that hangs on
    # a panel not essential to it is worse than one that
    # gives up and says so.
    planetary_timeout_seconds: float = Field(
        default=12.0,
        alias="PLANETARY_TIMEOUT_SECONDS",
    )

    # --------------------------------------------------
    # Sentinel Hub WMS
    #
    # The instance identifier selects a configured set of
    # visualisation layers in the Copernicus Data Space
    # Ecosystem. It is a credential: anyone holding it can
    # draw against the account's quota, so it belongs in the
    # environment rather than in source control.
    #
    # The layer names below must match the layers defined in
    # that instance's configuration.
    # --------------------------------------------------

    sentinel_wms_instance_id: str = Field(
        default="",
        alias="SENTINEL_WMS_INSTANCE_ID",
    )

    sentinel_wms_base_url: str = Field(
        default="https://sh.dataspace.copernicus.eu/ogc/wms",
        alias="SENTINEL_WMS_BASE_URL",
    )

    sentinel_layer_true_colour: str = Field(
        default="1_TRUE_COLOR",
        alias="SENTINEL_LAYER_TRUE_COLOUR",
    )

    sentinel_layer_false_colour: str = Field(
        default="2_FALSE_COLOR",
        alias="SENTINEL_LAYER_FALSE_COLOUR",
    )

    sentinel_layer_ndvi: str = Field(
        default="3_NDVI",
        alias="SENTINEL_LAYER_NDVI",
    )

    @property
    def sentinel_wms_url(self) -> str:
        """
        Return the full Sentinel Hub WMS endpoint.

        Raises:
            RuntimeError:
                No instance identifier is configured, so
                imagery cannot be requested.
        """

        if not self.sentinel_wms_instance_id:
            raise RuntimeError(
                "SENTINEL_WMS_INSTANCE_ID is not "
                "configured, so Sentinel-2 imagery cannot "
                "be requested."
            )

        return (
            f"{self.sentinel_wms_base_url.rstrip('/')}/"
            f"{self.sentinel_wms_instance_id}"
        )

    # --------------------------------------------------
    # Imagery storage
    # --------------------------------------------------

    satellite_image_storage_root: str = Field(
        default="storage/satellite_images",
        alias="SATELLITE_IMAGE_STORAGE_ROOT",
    )

    @property
    def satellite_image_storage_path(self) -> Path:
        """
        Return the imagery storage root as an absolute path.

        A relative configured value is resolved against the
        backend package root rather than the process working
        directory, so downloaded products and processed
        rasters always land in the same place.
        """

        configured = Path(self.satellite_image_storage_root)

        if configured.is_absolute():
            return configured

        return BACKEND_ROOT / configured


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""

    return Settings()