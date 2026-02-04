"""Configuration management for Tomorrow.io Weather Data Pipeline.

Uses Pydantic Settings for environment variable-based configuration
following 12-factor app principles.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    All configuration is loaded from environment variables or .env file.
    No hardcoded values - everything is configurable at runtime.

    Example:
        settings = get_settings()
        print(settings.tomorrow_api_key)
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # Ignore extra env vars not defined here
        populate_by_name=True,  # Allow both field name and alias
    )

    # Tomorrow.io API Configuration
    tomorrow_api_key: str = Field(
        ..., description="Tomorrow.io API key (required)", alias="TOMORROW_API_KEY"
    )

    tomorrow_api_base_url: str = Field(
        "https://api.tomorrow.io/v4",
        description="Tomorrow.io API base URL",
        alias="TOMORROW_API_BASE_URL",
    )

    tomorrow_api_timeout_seconds: int = Field(
        30,
        description="API request timeout in seconds",
        ge=5,
        le=300,
        alias="TOMORROW_API_TIMEOUT_SECONDS",
    )

    tomorrow_api_max_retries: int = Field(
        5,
        description="Maximum number of retries for failed API calls",
        ge=1,
        le=10,
        alias="TOMORROW_API_MAX_RETRIES",
    )

    tomorrow_api_retry_delay_seconds: float = Field(
        1.0,
        description="Initial retry delay in seconds (doubles with each retry)",
        ge=0.1,
        le=60.0,
        alias="TOMORROW_API_RETRY_DELAY_SECONDS",
    )

    # PostgreSQL Database Configuration
    pg_host: str = Field("localhost", description="PostgreSQL host", alias="PGHOST")

    pg_port: int = Field(
        5432, description="PostgreSQL port", ge=1, le=65535, alias="PGPORT"
    )

    pg_database: str = Field(
        "tomorrow", description="PostgreSQL database name", alias="PGDATABASE"
    )

    pg_user: str = Field("postgres", description="PostgreSQL username", alias="PGUSER")

    pg_password: str = Field(
        "postgres", description="PostgreSQL password", alias="PGPASSWORD"
    )

    pg_pool_size: int = Field(
        5,
        description="PostgreSQL connection pool size",
        ge=1,
        le=50,
        alias="PG_POOL_SIZE",
    )

    pg_pool_timeout_seconds: int = Field(
        30,
        description="PostgreSQL connection pool timeout",
        ge=1,
        le=300,
        alias="PG_POOL_TIMEOUT_SECONDS",
    )

    # Pipeline Configuration
    fetch_interval_minutes: int = Field(
        60,
        description="Interval between pipeline runs in minutes",
        ge=5,
        le=1440,
        alias="FETCH_INTERVAL_MINUTES",
    )

    fetch_forecast_hours: int = Field(
        120,  # 5 days
        description="Hours of forecast data to fetch",
        ge=1,
        le=336,  # 14 days max
        alias="FETCH_FORECAST_HOURS",
    )

    fetch_historical_hours: int = Field(
        24,
        description="Hours of historical data to fetch",
        ge=0,
        le=168,  # 7 days max
        alias="FETCH_HISTORICAL_HOURS",
    )

    data_granularity: Literal["minutely", "hourly", "daily"] = Field(
        "hourly",
        description="Data granularity for API requests",
        alias="DATA_GRANULARITY",
    )

    # Logging Configuration
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        "INFO", description="Logging level", alias="LOG_LEVEL"
    )

    log_format: Literal["json", "text"] = Field(
        "json", description="Log output format", alias="LOG_FORMAT"
    )

    # Environment
    environment: Literal["development", "staging", "production"] = Field(
        "development", description="Application environment", alias="ENVIRONMENT"
    )

    debug: bool = Field(False, description="Enable debug mode", alias="DEBUG")

    @field_validator("tomorrow_api_key")
    @classmethod
    def validate_api_key(cls, v: str) -> str:
        """Validate API key is not empty."""
        if not v or v.strip() == "":
            raise ValueError("TOMORROW_API_KEY cannot be empty")
        return v.strip()

    @field_validator("pg_password")
    @classmethod
    def validate_pg_password(cls, v: str) -> str:
        """Validate PostgreSQL password is not empty."""
        if not v or v.strip() == "":
            raise ValueError("PGPASSWORD cannot be empty")
        return v

    @property
    def database_url(self) -> str:
        """Construct PostgreSQL connection URL."""
        return (
            f"postgresql://{self.pg_user}:{self.pg_password}"
            f"@{self.pg_host}:{self.pg_port}/{self.pg_database}"
        )

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.environment == "development"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance.

    Uses LRU cache to avoid re-parsing environment variables
    on every call. Settings are loaded once at startup.

    Returns:
        Settings instance with all configuration values
    """
    return Settings()


def reload_settings() -> Settings:
    """Force reload settings from environment.

    Useful for testing or when environment variables change.
    Clears the cache and returns new settings.

    Returns:
        Fresh Settings instance
    """
    get_settings.cache_clear()
    return get_settings()
