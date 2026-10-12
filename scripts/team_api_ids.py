"""Carry club API-Football ids from one database to another, as a small reviewable file.

The club-to-id mapping (`fetch_api_competitions --map-teams`) spends API requests and
writes ids straight into the `teams` table. The server's database is not the one it was
run against, and re-spending the requests there would pair the same clubs again for no
gain. So the result travels as `ml/team_api_ids.csv` (club name, id), which is committed
and can be read before it is trusted:

    python -m scripts.team_api_ids export     # write the CSV from this database
    python -m scripts.team_api_ids apply      # fill missing ids from the CSV, here

`apply` only ever *fills a gap*. A club that already has an id is never changed, even if
the file disagrees: a different id there is reported, not applied, because overwriting a
mapping that ingestion has been using would split that club's history in two.
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database.session import SessionLocal  # noqa: E402
from app.models.team import Team  # noqa: E402

CSV_PATH = ROOT / "ml" / "team_api_ids.csv"
FIELDS = ["name", "api_football_id"]

logger = logging.getLogger(__name__)


def export_rows(session) -> list[dict]:
    """Every football club that has an id, ordered by name."""
    teams = (
        session.query(Team)
        .filter(Team.sport == "football", Team.api_football_id.is_not(None))
        .order_by(Team.name.asc())
        .all()
    )
    return [{"name": t.name, "api_football_id": int(t.api_football_id)} for t in teams]


def apply_rows(session, rows: list[dict]) -> dict:
    """Fill missing ids from `rows`. Returns counts of what happened.

    `filled`: ids written. `already`: the club already had this id. `conflict`: the club has a
    different id and is left alone. `unknown`: no club of that name here.
    """
    counts = {"filled": 0, "already": 0, "conflict": 0, "unknown": 0}
    by_name = {t.name: t for t in session.query(Team).filter(Team.sport == "football").all()}
    for row in rows:
        team = by_name.get(row["name"])
        wanted = int(row["api_football_id"])
        if team is None:
            counts["unknown"] += 1
        elif team.api_football_id is None:
            team.api_football_id = wanted
            counts["filled"] += 1
        elif int(team.api_football_id) == wanted:
            counts["already"] += 1
        else:
            counts["conflict"] += 1
            logger.warning(
                "%s has id %s here but %s in the file; left as is",
                team.name,
                team.api_football_id,
                wanted,
            )
    return counts


def read_csv(path: Path = CSV_PATH) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return [
            {"name": r["name"], "api_football_id": int(r["api_football_id"])}
            for r in csv.DictReader(handle)
        ]


def write_csv(rows: list[dict], path: Path = CSV_PATH) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("action", choices=["export", "apply"])
    parser.add_argument("--file", default=str(CSV_PATH))
    args = parser.parse_args(argv)
    path = Path(args.file)

    session = SessionLocal()
    try:
        if args.action == "export":
            rows = export_rows(session)
            write_csv(rows, path)
            logger.info("wrote %d club ids to %s", len(rows), path)
        else:
            counts = apply_rows(session, read_csv(path))
            session.commit()
            logger.info("applied %s", counts)
    finally:
        session.close()


if __name__ == "__main__":
    main()
