"""The database backup: a consistent, verified copy, with old ones pruned."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

import pytest

from scripts.backup_db import backup, sqlite_path


def _database(path, rows=3):
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("CREATE TABLE t (n INTEGER)")
    connection.executemany("INSERT INTO t VALUES (?)", [(i,) for i in range(rows)])
    connection.commit()
    return connection


def test_the_copy_holds_everything_including_what_is_still_in_the_wal(tmp_path):
    source = tmp_path / "live.db"
    live = _database(source, rows=5)  # left open: part of the data is in the -wal file

    copy = backup(source, tmp_path / "out")
    live.close()

    assert sqlite3.connect(copy).execute("SELECT COUNT(*) FROM t").fetchone()[0] == 5


def test_only_the_newest_snapshots_are_kept(tmp_path):
    source = tmp_path / "live.db"
    _database(source).close()
    start = datetime(2026, 10, 1, 3, 0, 0)

    for day in range(5):
        backup(source, tmp_path / "out", keep=3, now=start + timedelta(days=day))

    names = sorted(p.name for p in (tmp_path / "out").glob("*.db"))
    assert names == [
        "uniquepredict-20261003-030000.db",
        "uniquepredict-20261004-030000.db",
        "uniquepredict-20261005-030000.db",
    ]


def test_a_missing_database_is_an_error_not_an_empty_backup(tmp_path):
    with pytest.raises(SystemExit):
        backup(tmp_path / "nope.db", tmp_path / "out")


def test_only_sqlite_urls_are_accepted():
    with pytest.raises(SystemExit):
        sqlite_path("postgresql://u:p@h/db")
    assert str(sqlite_path("sqlite:///./data/x.db")).endswith("x.db")
