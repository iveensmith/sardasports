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
    # SQLite only. WAL lets readers run while a writer commits, which is what stops a
    # board request reading while another stores predictions from failing with
    # "database is locked"; it is a property of the file, so it sticks once set.
    # The busy timeout is how long a writer waits for another writer before giving up.
    sqlite_wal: bool = True
    sqlite_busy_timeout_seconds: float = 30.0

    # Cache
    redis_url: str | None = "redis://localhost:6379/0"

    # Vector DB (RAG knowledge base)
    chroma_url: str | None = None
    chroma_persist_dir: Path = Path("rag/chroma_store")

    # App
    app_env: str = "development"
    log_level: str = "INFO"
    # The engine is an internal service: its only client is the website's server, so every
    # request arrives from one address. A low per-address limit therefore throttles the whole
    # site (60 a minute turned a crawler's first visit into hundreds of 429s), and abuse is
    # limited at the website or the CDN in front of it instead. This is a ceiling against a
    # runaway caller, not a visitor limit.
    api_rate_limit_per_minute: int = 6000

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
    # Retrains every model inside the engine's process, Mondays 04:00. Off by default: it is
    # heavy enough to freeze a small server (see app/scheduler.py), and models are normally
    # trained elsewhere and uploaded.
    enable_weekly_retrain: bool = False
    # How many nightly database snapshots to keep (see `nightly_backup_job`). One a night, so
    # this is also how many nights back a mistake can be undone.
    backup_keep: int = 14
    # Where uploaded blog images are kept. Empty means an `uploads` folder beside the database,
    # which in production is the mounted data volume (see app/services/media_service.py).
    uploads_dir: str = ""

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

    # --- Accounts, e-mail and payments -------------------------------------------------
    # The public address of the website, used to build the links in e-mails (verify your
    # address, reset your password). It is never taken from a request: a header a caller can
    # set must not decide where a password-reset link points.
    public_site_url: str = ""
    # How long a signed-in browser stays signed in, and how long an e-mailed link works.
    session_days: int = 30
    verify_token_hours: int = 48
    reset_token_hours: int = 1

    # Outgoing mail. Unset: mail is written to the outbox table (the administrator can read
    # it there) and not sent. Any SMTP service works (Resend, Postmark, the domain's mailbox).
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""

    # Payment providers. Each is used only when its secret is set; a plan can always be
    # granted by hand from the admin dashboard.
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    paystack_secret_key: str = ""

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
