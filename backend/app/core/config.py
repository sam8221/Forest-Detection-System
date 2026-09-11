"""Application configuration loaded from environment variables."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""

    return Settings()