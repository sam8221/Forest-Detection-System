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

import os
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

    # How much the application writes to the console.
    #
    # One standard level name. Anything the logging module
    # does not recognise falls back to INFO rather than
    # raising, because a typo here must not stop the
    # application from starting: a system that refuses to
    # boot over a log setting is worse than one that logs
    # at the wrong level.
    log_level: str = Field(
        default="INFO",
        alias="LOG_LEVEL",
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

    support_attachment_directory: str = Field(
        default=str(BACKEND_ROOT / "data" / "support-attachments"),
        alias="SUPPORT_ATTACHMENT_DIRECTORY",
    )

    support_attachment_max_bytes: int = Field(
        default=10 * 1024 * 1024,
        alias="SUPPORT_ATTACHMENT_MAX_BYTES",
        ge=1,
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

    cors_origins_raw: str = Field(
        default=(
            "http://localhost:5173,"
            "http://127.0.0.1:5173,"
            "http://[::1]:5173"
        ),
        alias="CORS_ORIGINS",
    )

    @property
    def cors_origins(self) -> list[str]:
        """
        Return the browser origins permitted to call the API.

        A browser compares origins as literal strings, so
        `http://localhost:5173` and `http://[::1]:5173` are
        two different origins even when they reach the same
        server. The development server binds whichever of
        them the host resolves `localhost` to, so all three
        forms are permitted by default: omitting one makes
        the interface fail with a message about the backend
        being unreachable, which sends the officer looking
        for a stopped server rather than a refused origin.

        Listing them in configuration rather than in the
        application means a deployment can name its own
        origin without editing code.
        """

        return [
            origin.strip()
            for origin in self.cors_origins_raw.split(",")
            if origin.strip()
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
    # SMS notifications (Africa's Talking)
    #
    # SMS is the channel that interrupts an officer, so it
    # is reserved for alerts warranting a field response.
    # Email still goes out for every alert.
    #
    # Security: the API key is a credential. It is read from
    # the environment, defaults to empty, and must never be
    # logged, returned by an endpoint, or reach the browser.
    # It is sent to the provider in a request header, never
    # in a URL or a request body.
    # --------------------------------------------------

    africastalking_username: str = Field(
        default="sandbox",
        alias="AFRICASTALKING_USERNAME",
    )

    africastalking_api_key: str = Field(
        default="",
        alias="AFRICASTALKING_API_KEY",
    )

    # Which Africa's Talking environment to talk to.
    #
    # Anything other than the exact string "production"
    # means sandbox, and the SMS service overrides the
    # username to "sandbox" accordingly. Production is
    # therefore opt-in by one explicit value: a production
    # key left in a development .env still cannot reach a
    # real handset, which is what keeps development and
    # test runs from sending real messages.
    africastalking_environment: str = Field(
        default="sandbox",
        alias="AFRICASTALKING_ENVIRONMENT",
    )

    # Registered shortcode or alphanumeric sender ID. Empty
    # means the provider's default, which is what the
    # sandbox uses; a sandbox account has no sender ID of
    # its own.
    sms_sender_id: str = Field(
        default="",
        alias="SMS_SENDER_ID",
    )

    # Master switch. Off by default so that installing the
    # dependency and running a migration does not by itself
    # start sending messages.
    sms_enabled: bool = Field(
        default=False,
        alias="SMS_ENABLED",
    )

    # Lowest alert priority that earns an SMS, compared on
    # the LOW < MEDIUM < HIGH < CRITICAL ordering defined in
    # app.services.sms_service.
    sms_min_priority: str = Field(
        default="HIGH",
        alias="SMS_MIN_PRIORITY",
    )

    @property
    def africastalking_is_sandbox(self) -> bool:
        """
        Whether SMS is directed at the sandbox.

        True unless the environment names production.

        Case and surrounding whitespace are ignored, so
        "production", "Production" and " PRODUCTION " all
        mean production: writing some case of that word is a
        deliberate statement of intent, not a plausible
        slip. Anything else at all, including "prod",
        "live", an empty value and an unset variable,
        resolves to sandbox.

        Phrased as "not production" rather than "is sandbox"
        on purpose. The default for an unrecognised value is
        then the harmless one, so a leftover production
        username in a developer .env cannot by itself reach
        a real handset.
        """

        return (
            self.africastalking_environment.strip().lower()
            != "production"
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

    # The most products one catalogue search may return.
    #
    # Defined here rather than as a literal in the service
    # because it is a real limitation the interface states
    # to the officer, and because the API rejects a limit
    # outside 1 to 100. The two bounds have to agree: a
    # ceiling lower than the endpoint's would silently
    # return fewer products than the officer was told they
    # asked for.
    max_catalogue_results: int = Field(
        default=100,
        alias="MAX_CATALOGUE_RESULTS",
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

    # The smallest NDVI change worth calling a change at all.
    #
    # Distinct from ndvi_threshold above, and the distinction
    # is the point. ndvi_threshold asks "has this pixel been
    # cleared": a drop of 0.30 is most of a canopy gone, and
    # almost no pixel in a healthy scene reaches it. That is
    # correct for detection and useless for description.
    #
    # Used as the significance criterion, it reported a real
    # scene as 0.00 percent declined and 99.99 percent
    # unchanged while the difference map plainly showed red
    # and green across it. Measured against this threshold
    # the same scene is 1.99 percent declined and 25.59
    # percent greener, which is what the map shows.
    #
    # 0.05 is the conventional noise floor for differencing
    # Sentinel-2 surface-reflectance NDVI: below it a change
    # is not reliably distinguishable from atmospheric
    # correction residue, view-angle effects and sensor
    # noise, so calling it vegetation change would be
    # reporting measurement error as a finding.
    #
    # This threshold describes. It never detects: no
    # detection, alert or area in the detection path consults
    # it, and raising or lowering it cannot create or destroy
    # a single detection.
    ndvi_significant_change: float = Field(
        default=0.05,
        alias="NDVI_SIGNIFICANT_CHANGE",
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
    # Cloud condition classification
    #
    # Upper bounds, in percent, for the words the interface
    # puts on a cloud-cover figure.
    #
    # Taken from the okta scale, the eighths of sky covered
    # that meteorological observation has used since the
    # WMO adopted it, rather than from round numbers chosen
    # because they look tidy:
    #
    #     CLEAR          0 to 1 okta     up to 12.5 %
    #     PARTLY CLOUDY  2 to 4 oktas    up to 50 %
    #     CLOUDY         5 to 7 oktas    up to 87.5 %
    #     VERY CLOUDY    8 oktas         above 87.5 %
    #
    # The last band is overcast: sky wholly covered. It is
    # kept separate from "cloudy" because the difference
    # decides whether waiting a day is worth doing.
    #
    # These words describe the sky. Whether an image can be
    # analysed is a different question, answered by
    # max_cloud_cover_percentage above, and the two are not
    # merged: an officer may reasonably be told that
    # conditions are "partly cloudy" and that the scene is
    # still too cloudy to measure NDVI from.
    # --------------------------------------------------

    cloud_clear_max_percentage: float = Field(
        default=12.5,
        alias="CLOUD_CLEAR_MAX_PERCENTAGE",
    )

    cloud_partly_cloudy_max_percentage: float = Field(
        default=50.0,
        alias="CLOUD_PARTLY_CLOUDY_MAX_PERCENTAGE",
    )

    cloud_cloudy_max_percentage: float = Field(
        default=87.5,
        alias="CLOUD_CLOUDY_MAX_PERCENTAGE",
    )

    # --------------------------------------------------
    # Current weather provider
    #
    # Separate from Copernicus and deliberately so. A
    # Sentinel-2 product carries the cloud cover measured
    # when the satellite passed, which may be days old. It
    # is not the sky now, and the interface must not offer
    # it as though it were.
    #
    # Default provider is Open-Meteo, which needs no
    # credential. The key field exists for a provider that
    # does; it is read from the environment, defaults to
    # empty and is never logged or returned.
    #
    # LICENSING, and it matters here:
    #
    #     Open-Meteo is free for non-commercial use and
    #     charges for commercial use. This is the same
    #     restriction that ruled out Google Earth Engine
    #     for this project, which is built for a government
    #     department. The weather reading is a convenience
    #     and not part of the detection method, so the
    #     dependency is optional and the system states
    #     plainly when it is absent; but an operational
    #     deployment would need either a licence or a
    #     provider without that restriction, and the
    #     dissertation should say so rather than leave the
    #     same objection unanswered twice.
    # --------------------------------------------------

    weather_api_url: str = Field(
        default="https://api.open-meteo.com/v1/forecast",
        alias="WEATHER_API_URL",
    )

    weather_api_key: str = Field(
        default="",
        alias="WEATHER_API_KEY",
    )

    weather_provider_name: str = Field(
        default="Open-Meteo",
        alias="WEATHER_PROVIDER_NAME",
    )

    # How long a weather reading is reused before the
    # provider is asked again.
    #
    # Matched to the provider's own update interval, which
    # Open-Meteo reports as 900 seconds. Asking more often
    # than the data changes returns the same numbers and
    # spends somebody's rate limit to do it.
    weather_cache_seconds: int = Field(
        default=900,
        alias="WEATHER_CACHE_SECONDS",
    )

    # Whether the current-weather reading is offered at all.
    #
    # On by default because the default provider needs no
    # credential. An installation that must not make
    # outbound requests to a third party sets this to false
    # and keeps the satellite half of the feature, which
    # uses imagery the system already holds.
    weather_enabled: bool = Field(
        default=True,
        alias="WEATHER_ENABLED",
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

    # The ceiling on a single attempt, not on the lookup.
    # Two requests are made in sequence and each may be
    # attempted up to three times, all of it bounded by
    # PlanetaryService.TOTAL_BUDGET_SECONDS, which is what
    # actually limits how long an officer waits.
    #
    # Twenty seconds rather than twelve because twelve was
    # below what the catalogue takes when it is busy:
    # measured from this system, a search that had returned
    # in 1.8 seconds was answering in 12 to 16 seconds a
    # quarter of an hour later. A timeout shorter than the
    # service's own working latency abandons responses that
    # were about to arrive, which is a self-inflicted
    # failure rather than an upstream one.
    planetary_timeout_seconds: float = Field(
        default=20.0,
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

        Environment variables are expanded first. A relative
        value is resolved against the backend package root
        rather than the process working directory, so product
        and analysis paths use one canonical root.
        """

        configured = Path(
            os.path.expandvars(self.satellite_image_storage_root)
        ).expanduser()
        if not configured.is_absolute():
            configured = BACKEND_ROOT / configured

        return configured.resolve()


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""

    return Settings()
