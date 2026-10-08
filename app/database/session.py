"""Database engine/session management.

`DATABASE_URL` drives everything: point it at SQLite for local dev/tests or
Postgres for production (docker-compose). The rest of the app never branches
on which one is active.
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.utils.config import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


def _is_sqlite_file(database_url: str) -> bool:
    return database_url.startswith("sqlite") and ":memory:" not in database_url


def _enable_wal(dbapi_connection, _record) -> None:
    """Switch the file to write-ahead logging.

    Without it a committing writer takes an exclusive lock that turns away every
    reader, so a board being read while another request stores predictions fails
    with "database is locked". The mode is stored in the file, so after the first
    time this is a no-op. If it cannot be set now (another process holds the file
    open mid-transaction) the connection simply carries on in the old mode.
    """
    try:
        dbapi_connection.execute("PRAGMA journal_mode=WAL")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not enable SQLite WAL mode: %s", exc)


def _build_engine(database_url: str) -> Engine:
    settings = get_settings()
    connect_args: dict = {}
    if database_url.startswith("sqlite"):
        # `timeout` is sqlite3's busy timeout, in seconds: how long a writer waits
        # for the write lock before raising. The default of 5 is shorter than a
        # busy board's write burst.
        connect_args = {
            "check_same_thread": False,
            "timeout": settings.sqlite_busy_timeout_seconds,
        }
    engine = create_engine(database_url, connect_args=connect_args, pool_pre_ping=True, future=True)
    if settings.sqlite_wal and _is_sqlite_file(database_url):
        event.listen(engine, "connect", _enable_wal)
    return engine


_engine: Engine = _build_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)


def get_engine() -> Engine:
    return _engine


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a request-scoped DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
