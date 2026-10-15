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


# --- the nightly job --------------------------------------------------------------------------


class _Settings:
    is_sqlite = True
    backup_keep = 2

    def __init__(self, database_url):
        self.database_url = database_url


def test_the_nightly_job_writes_beside_the_database_and_keeps_only_the_newest(
    tmp_path, monkeypatch
):
    from app import scheduler

    source = tmp_path / "data" / "uniquepredict.db"
    source.parent.mkdir()
    _database(source).close()
    monkeypatch.setattr(scheduler, "get_settings", lambda: _Settings(f"sqlite:///{source}"))

    # Snapshots are named to the second, so earlier ones are planted rather than slept for.
    out = source.parent / "backups"
    out.mkdir()
    for stamp in ("20260101-020000", "20260102-020000", "20260103-020000"):
        (out / f"uniquepredict-{stamp}.db").write_bytes(b"old")

    scheduler.nightly_backup_job()

    names = sorted(p.name for p in out.glob("uniquepredict-*.db"))
    assert len(names) == 2  # keep=2: the newest planted one and today's
    assert names[0] == "uniquepredict-20260103-020000.db"
    assert sqlite3.connect(out / names[1]).execute("SELECT COUNT(*) FROM t").fetchone()[0] == 3


def test_the_nightly_job_will_not_fill_the_disk(tmp_path, monkeypatch):
    import shutil
    from collections import namedtuple

    from app import scheduler

    source = tmp_path / "uniquepredict.db"
    _database(source).close()
    monkeypatch.setattr(scheduler, "get_settings", lambda: _Settings(f"sqlite:///{source}"))
    usage = namedtuple("usage", "total used free")
    monkeypatch.setattr(shutil, "disk_usage", lambda path: usage(100, 100, 0))

    scheduler.nightly_backup_job()  # logs and returns; must not raise

    assert not (tmp_path / "backups").exists()


def test_a_missing_database_is_logged_not_raised(tmp_path, monkeypatch):
    from app import scheduler

    monkeypatch.setattr(
        scheduler, "get_settings", lambda: _Settings(f"sqlite:///{tmp_path / 'gone.db'}")
    )

    scheduler.nightly_backup_job()
