"""Shared pytest fixtures.

Forces a throwaway SQLite file as the test database and disables Redis
*before* any `app.*` module is imported, so `app.utils.config.get_settings()`
(which is process-cached) picks up test-safe values from the very first call.

Every override below sets the env var to an explicit empty string rather
than deleting it. That matters: pydantic-settings' precedence is env var >
`.env` file, so an *unset* os.environ entry falls through to whatever real
value `.env` has (e.g. real API keys a developer added for their own local
testing) — only an explicit empty-string override reliably beats it.
"""

from __future__ import annotations

import os
from pathlib import Path

TEST_DB_PATH = Path(__file__).resolve().parent / "test_uniquepredict.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"
os.environ["REDIS_URL"] = ""  # falsy -> app.utils.cache.Cache becomes a permanent no-op
os.environ["CHROMA_URL"] = ""  # falsy -> rag.retriever uses a local PersistentClient, no network
os.environ["ANTHROPIC_API_KEY"] = ""  # falsy -> the AI analyst's "not configured" path
os.environ["API_FOOTBALL_KEY"] = ""  # falsy -> injuries sync stays unreachable in tests

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.models  # noqa: E402, F401 - registers all models on Base.metadata
from app.database.base import Base  # noqa: E402
from app.database.session import SessionLocal, get_engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _test_database():
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()


@pytest.fixture(autouse=True)
def _clean_tables(_test_database):
    """Empty every table after each test so tests never see another test's data.

    Individual tests commit (e.g. to exercise real API request/response
    cycles against the DB), so a session rollback alone isn't enough —
    committed rows must be deleted explicitly between tests.
    """
    yield
    engine = get_engine()
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())


@pytest.fixture
def db_session(_test_database):
    session = SessionLocal()
    try:
        yield session
        session.rollback()
    finally:
        session.close()


@pytest.fixture
def client(_test_database):
    return TestClient(app)
