"""Convenience script: create tables for local dev if they don't exist yet.

For real historical data, use the actual pipeline instead:
    uv run python scripts/download_data.py
    uv run python scripts/clean_data.py
    uv run python scripts/load_to_db.py

This script only guarantees the schema exists (handy right after cloning,
before running Alembic migrations, or for `sqlite` local dev where you just
want tables without a full migration history).

Usage:
    uv run python scripts/seed_dev_db.py
"""

from __future__ import annotations

import logging

import app.models  # noqa: F401 - registers all models on Base.metadata
from app.database.base import Base
from app.database.session import get_engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    logger.info("Schema ready at %s", engine.url)


if __name__ == "__main__":
    main()
