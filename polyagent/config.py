"""Settings — provider config loaded from ``.env`` via pydantic-settings.

Keys are read with the ``DEEPSEEK_`` prefix (e.g. ``DEEPSEEK_API_KEY`` → ``api_key``).
``.env`` is gitignored; never commit real keys.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="DEEPSEEK_", extra="ignore")

    api_key: str = ""
    model: str = "deepseek-chat"
    base_url: str = "https://api.deepseek.com"


class ObservabilitySettings(BaseSettings):
    """Observability backend endpoints (OTLP collector + Prometheus pushgateway).

    Leave blank to keep traces/metrics in-memory. Set to export to real backends.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    otel_exporter_otlp_endpoint: str = ""
    prometheus_pushgateway: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_observability_settings() -> ObservabilitySettings:
    return ObservabilitySettings()
