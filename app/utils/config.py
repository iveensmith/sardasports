"""Centralized application configuration.

All configuration comes from environment variables (optionally loaded from a
local `.env` file). Nothing is hardcoded here — see `.env.example` for the
full list of supported variables and their defaults.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, populated from environment variables / .env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = "sqlite:///./data/uniquepredict.db"

    # Cache
    redis_url: str | None = "redis://localhost:6379/0"

    # Vector DB (RAG knowledge base)
    chroma_url: str | None = None
    chroma_persist_dir: Path = Path("rag/chroma_store")

    # App
    app_env: str = "development"
    log_level: str = "INFO"
    api_rate_limit_per_minute: int = 60

    # AI analyst agent (app/agents/analyst.py) — requires your own key from
    # console.anthropic.com. Unset by default; the agent stays honest about
    # being unconfigured (503, not a crash) until this is set.
    anthropic_api_key: str | None = None
    analyst_model: str = "claude-sonnet-5"

    # Scheduler (app/scheduler.py) — off by default so tests/scripts never
    # accidentally start background jobs. What it fetches and how often is not
    # configured here: the daily refresh walks every league and the current
    # season, and the API jobs follow the account's own plan and remaining quota
    # (see app/services/api_budget.py).
    enable_scheduler: bool = False

    # Injuries (scripts/sync_injuries.py) — requires your own key from
    # dashboard.api-football.com. Unset by default; get_injuries stays
    # honest about unavailability until this is configured and synced.
    api_football_key: str | None = None
    api_football_base_url: str = "https://v3.football.api-sports.io"
    # None = auto-detect the current season from today's date (see
    # scripts/sync_injuries.py::current_api_football_season) rather than a
    # hardcoded year that goes stale every summer. Set explicitly to query a
    # past season instead.
    api_football_season: int | None = None

    # Elo defaults
    elo_k_factor: float = 20.0
    elo_home_advantage: float = 60.0
    elo_initial_rating: float = 1500.0

    # ML
    model_artifact_dir: Path = Path("ml/models")

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (env is only read once per process)."""
    return Settings()
