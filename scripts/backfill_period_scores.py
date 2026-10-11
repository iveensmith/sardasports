"""Fill `matches.period_scores` for games already in the database, from files already on disk.

Basketball: every finished game in `data/raw/basketball/*.json` carries its quarter scores,
matched to the stored row by `external_id` (`bball-<id>`).
Tennis: the tennis-data workbooks in `data/raw/tennis/*.xlsx` carry each set's games, matched
by `external_id` (`tennis-<tour>-<year>-<row>`) with the same home/away slot orientation the
loader gave the row (see `scripts.fetch_tennis.rows_from_frame`).

It spends no API requests and is safe to run again: rows are only updated when the stored value
differs, and a row the source has no detail for is left empty.

    python -m scripts.backfill_period_scores            # both sports
    python -m scripts.backfill_period_scores --sport tennis
"""

from __future__ import annotations

import argparse
import glob
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy.orm import Session  # noqa: E402

from app.database.session import SessionLocal  # noqa: E402
from app.models.match import Match  # noqa: E402
from ml.period_scores import basketball_periods  # noqa: E402

logger = logging.getLogger(__name__)
RAW = ROOT / "data" / "raw"
FINISHED = {"FT", "AOT"}


def backfill_basketball(session: Session) -> dict:
    found: dict[str, dict] = {}
    for path in glob.glob(str(RAW / "basketball" / "*.json")):
        name = Path(path).name
        if name.startswith("_"):
            continue
        try:
            games = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            logger.warning("could not read %s", path)
            continue
        for game in games if isinstance(games, list) else []:
            if (game.get("status") or {}).get("short") not in FINISHED:
                continue
            periods = basketball_periods(game.get("scores"))
            if periods is not None and game.get("id") is not None:
                found[f"bball-{game['id']}"] = periods
    updated = 0
    for match in session.query(Match).filter(
        Match.sport == "basketball", Match.status == "completed"
    ):
        periods = found.get(match.external_id or "")
        if periods is not None and match.period_scores != periods:
            match.period_scores = periods
            updated += 1
    session.commit()
    return {"in_files": len(found), "updated": updated}


def backfill_tennis(session: Session) -> dict:
    import pandas as pd

    from scripts.fetch_tennis import rows_from_frame

    found: dict[str, dict] = {}
    seen: set[str] = set()
    for path in sorted(glob.glob(str(RAW / "tennis" / "*.xlsx"))):
        stem = Path(path).stem  # ATP_2024
        tour, _, year = stem.partition("_")
        if not year.isdigit():
            continue
        try:
            frame = pd.read_excel(path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("could not read %s: %s", path, exc)
            continue
        for row in rows_from_frame(frame, tour, int(year)):
            seen.add(row["external_id"])
            if row.get("period_scores"):
                found[row["external_id"]] = row["period_scores"]
    updated = 0
    for match in session.query(Match).filter(Match.sport == "tennis", Match.status == "completed"):
        key = match.external_id or ""
        if key not in seen:
            continue
        periods = found.get(key)  # None for a row whose sets contradict its result
        if match.period_scores != periods:
            match.period_scores = periods
            updated += 1
    session.commit()
    return {"in_files": len(found), "updated": updated}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sport", choices=["basketball", "tennis"])
    args = parser.parse_args()
    session = SessionLocal()
    try:
        if args.sport in (None, "basketball"):
            print("basketball:", backfill_basketball(session))
        if args.sport in (None, "tennis"):
            print("tennis:", backfill_tennis(session))
    finally:
        session.close()


if __name__ == "__main__":
    main()
