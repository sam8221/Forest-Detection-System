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

    # ------------------------------------------------------------------
    # Application
    # ------------------------------------------------------------------
    app_name: str = Field(default="Forest Detection API", alias="APP_NAME")
    app_version: str = Field(default="1.0.0", alias="APP_VERSION")
    environment: str = Field(default="development", alias="ENVIRONMENT")

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------
    api_v1_prefix: str = "/api/v1"

    # ------------------------------------------------------------------
    # Security
    # ------------------------------------------------------------------
    secret_key: str = Field(alias="SECRET_KEY")
    algorithm: str = Field(default="HS256", alias="ALGORITHM")
    access_token_expire_minutes: int = Field(
        default=60,
        alias="ACCESS_TOKEN_EXPIRE_MINUTES",
    )

    # ------------------------------------------------------------------
    # Database
    # ------------------------------------------------------------------
    database_url: str = Field(alias="DATABASE_URL")

    # ------------------------------------------------------------------
    # Allowed Hosts
    # ------------------------------------------------------------------
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


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
smtp_host: str
smtp_port: int
smtp_username: str
smtp_password: str
smtp_from_email: str
copernicus_client_id: str
copernicus_client_secret: str