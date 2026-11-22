"""Runtime settings, read from ``FQ_*`` environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_SQLALCHEMY_DRIVER_SUFFIX = "+psycopg"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FQ_", extra="ignore")

    # SecretStr keeps the password out of repr(), logs and validation errors.
    database_url: SecretStr
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    env: Literal["local", "ci", "prod"] = "local"
    ingest_max_upload_mb: int = 50

    @field_validator("database_url")
    @classmethod
    def _needs_psycopg_driver(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().startswith("postgresql+psycopg://"):
            raise ValueError("must start with postgresql+psycopg://")
        return value

    @property
    def sqlalchemy_url(self) -> str:
        """URL with the SQLAlchemy driver suffix, as given."""
        return self.database_url.get_secret_value()

    @property
    def psycopg_dsn(self) -> str:
        """Plain libpq URL for psycopg and Procrastinate (no SQLAlchemy driver suffix)."""
        return self.sqlalchemy_url.replace(_SQLALCHEMY_DRIVER_SUFFIX, "", 1)


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # database_url comes from the environment
