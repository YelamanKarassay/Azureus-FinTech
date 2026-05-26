"""Application settings — loaded from process environment with `.env` fallback.

Local dev reads from `.env`; production uses real environment variables.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Project-wide settings.

    Fields map to env vars case-insensitively (`database_url` ← `DATABASE_URL`).
    Extra env vars are ignored so unrelated values in `.env` (e.g. frontend
    config) don't blow up instantiation.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    database_url: str = ""
    database_url_sync: str = ""
    redis_url: str = "redis://localhost:6379/0"
    mlflow_tracking_uri: str = "http://localhost:5000"
    mlflow_artifact_root: str = "/var/azureus/mlflow_artifacts"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings singleton — avoids re-reading `.env` on every access."""
    return Settings()
