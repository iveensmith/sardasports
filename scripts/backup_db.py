"""Take a consistent copy of the SQLite database, safely, while the engine is running.

Copying the .db file with `cp` or `rsync` while the engine runs can capture a half-written
page (the database is in WAL mode, so part of the data is in the -wal file). SQLite's backup
API copies a consistent snapshot without stopping anything. This uses it, checks the copy
opens and passes `PRAGMA integrity_check`, and keeps only the newest few.

Usage:
    python -m scripts.backup_db                       # to data/backups, keep 7
    python -m scripts.backup_db --out /tmp --keep 3
    docker compose -f docker-compose.prod.yml exec -T api python -m scripts.backup_db
"""

from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime
from pathlib import Path

from app.utils.config import get_settings

DEFAULT_KEEP = 7
PREFIX = "uniquepredict-"


def sqlite_path(database_url: str) -> Path:
    """The file behind a `sqlite:///...` URL (relative or absolute)."""
    if not database_url.startswith("sqlite:///"):
        raise SystemExit(f"Only SQLite databases can be backed up with this script: {database_url}")
    return Path(database_url.removeprefix("sqlite:///"))


def backup(
    source: Path, out_dir: Path, keep: int = DEFAULT_KEEP, now: datetime | None = None
) -> Path:
    """Write a verified snapshot of `source` into `out_dir`, prune old ones, return the path."""
    if not source.exists():
        raise SystemExit(f"No database at {source}")
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    target = out_dir / f"{PREFIX}{stamp}.db"
    partial = target.with_suffix(".db.partial")

    reader = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    writer = sqlite3.connect(partial)
    try:
        reader.backup(writer)
    finally:
        writer.close()
        reader.close()

    check = sqlite3.connect(partial)
    try:
        verdict = check.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        check.close()
    if verdict != "ok":
        partial.unlink(missing_ok=True)
        raise SystemExit(f"The backup failed its integrity check: {verdict}")
    partial.replace(target)

    snapshots = sorted(out_dir.glob(f"{PREFIX}*.db"))
    for old in snapshots[: max(0, len(snapshots) - keep)]:
        old.unlink()
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("data/backups"))
    parser.add_argument("--keep", type=int, default=DEFAULT_KEEP)
    args = parser.parse_args()
    source = sqlite_path(get_settings().database_url)
    target = backup(source, args.out, args.keep)
    print(f"{target} ({target.stat().st_size / 1_048_576:.1f} MB)")


if __name__ == "__main__":
    main()
