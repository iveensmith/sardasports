"""Fetch basketball games from API-Basketball into the multi-sport `matches`
table as `sport="basketball"`.

Why this doesn't go through `clean_data.py` like football does: that script
exists to reconcile 18 leagues' worth of inconsistent Football-Data.co.uk
CSV dialects (differing column sets, date formats, odds providers) into one
shape. API-Basketball returns one already-consistent JSON shape, so there is
no dialect to reconcile — inserting a `clean` step here would be ceremony,
not cleaning. The raw responses are still written to `data/raw/basketball/`
so a re-load never needs to re-hit the API (and re-spend quota).

What carries over from football and what doesn't:

- **Carries over:** Elo. It's sport-agnostic — a margin-weighted rating
  update over an ordered sequence of results. `load_to_db.rebuild_elo_history`
  runs a *separate* engine per sport, so basketball ratings never mix with
  football ones.
- **Does not carry over:** everything goal-shaped. A basketball game has no
  draws (of 1,311 finished NBA games in one season: zero), no half-time
  "goals", no corners or cards, and averages ~226 total points where the
  football Poisson model truncates at 8. Those columns stay NULL and the
  goal markets report as genuinely unavailable for these rows, exactly as
  they already do for a league with no corner data.

Quota: one `/games` request per league-season. A free plan serves seasons
2022-2024 only; it rejects anything older with a `plan` error, which is
skipped rather than treated as a failure.

Usage:
    uv run python scripts/fetch_basketball.py                     # NBA, default seasons
    uv run python scripts/fetch_basketball.py --league 120 --name EuroLeague \\
        --seasons 2022-2023,2023-2024
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import datetime
from pathlib import Path

import requests

from app.database.session import SessionLocal
from app.models.match import Match
from app.models.team import Team
from app.utils.config import get_settings
from ml.period_scores import basketball_periods

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "basketball"
BASE_URL = "https://v1.basketball.api-sports.io"
REQUEST_DELAY_SECONDS = 1.0
SPORT = "basketball"

# API-Basketball marks a finished game "FT"; overtime finishes report "AOT".
FINISHED_STATUSES = {"FT", "AOT"}

DEFAULT_LEAGUE_ID = 12
DEFAULT_LEAGUE_NAME = "NBA"
DEFAULT_SEASONS = ["2022-2023", "2023-2024", "2024-2025"]


def fetch_season(league_id: int, season: str, api_key: str, timeout: int = 40) -> list[dict]:
    """One league-season's games, as raw API items (cached to disk by caller)."""
    response = requests.get(
        f"{BASE_URL}/games",
        headers={"x-apisports-key": api_key},
        params={"league": league_id, "season": season},
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    errors = payload.get("errors")
    if errors:
        if isinstance(errors, dict) and "plan" in errors:
            logger.warning(
                "league=%s season=%s not available on this plan (%s) — skipping",
                league_id,
                season,
                errors["plan"],
            )
            return []
        raise SystemExit(f"API-Basketball error league={league_id} season={season}: {errors}")
    return payload.get("response", [])


def _rows_from_items(items: list[dict], competition: str, season: str) -> list[dict]:
    """Finished games only, flattened to the columns `matches` actually stores."""
    rows = []
    for item in items:
        if item.get("status", {}).get("short") not in FINISHED_STATUSES:
            continue
        scores = item.get("scores", {})
        home_total = (scores.get("home") or {}).get("total")
        away_total = (scores.get("away") or {}).get("total")
        home = (item.get("teams", {}).get("home") or {}).get("name")
        away = (item.get("teams", {}).get("away") or {}).get("name")
        date_raw = item.get("date")
        if not (date_raw and home and away and home_total is not None and away_total is not None):
            continue
        rows.append(
            {
                "external_id": f"bball-{item.get('id')}",
                "match_date": datetime.fromisoformat(date_raw.replace("Z", "+00:00")).replace(
                    tzinfo=None
                ),
                "competition": competition,
                "season": season,
                "home_team": home,
                "away_team": away,
                "home_score": int(home_total),
                "away_score": int(away_total),
                "period_scores": basketball_periods(scores),
            }
        )
    return rows


def _get_or_create_team(session, cache: dict, name: str, league: str) -> Team:
    key = (SPORT, name)
    if key in cache:
        return cache[key]
    team = session.query(Team).filter(Team.sport == SPORT, Team.name == name).one_or_none()
    if team is None:
        team = Team(name=name, league=league, sport=SPORT)
        session.add(team)
        session.flush()
    cache[key] = team
    return team


def load_rows(session, rows: list[dict]) -> int:
    """Insert rows not already present, keyed on external_id. Returns inserted count."""
    existing = {
        e for (e,) in session.query(Match.external_id).filter(Match.sport == SPORT).all() if e
    }
    cache: dict = {}
    inserted = 0
    for row in rows:
        if row["external_id"] in existing:
            continue
        home = _get_or_create_team(session, cache, row["home_team"], row["competition"])
        away = _get_or_create_team(session, cache, row["away_team"], row["competition"])
        session.add(
            Match(
                external_id=row["external_id"],
                sport=SPORT,
                match_date=row["match_date"],
                competition=row["competition"],
                season=row["season"],
                home_team_id=home.id,
                away_team_id=away.id,
                home_score=row["home_score"],
                away_score=row["away_score"],
                period_scores=row.get("period_scores"),
                # Football-only stats stay NULL rather than 0 — see module
                # docstring. A zero here would read as "no corners taken",
                # not "this sport has no corners".
                status="completed",
            )
        )
        existing.add(row["external_id"])
        inserted += 1
    return inserted


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch basketball games into the matches table")
    parser.add_argument("--league", type=int, default=DEFAULT_LEAGUE_ID)
    parser.add_argument("--name", default=DEFAULT_LEAGUE_NAME, help="Competition name to store")
    parser.add_argument("--seasons", help="Comma-separated, e.g. 2022-2023,2023-2024")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.api_football_key:
        raise SystemExit("API_FOOTBALL_KEY is not set — the api-sports key covers basketball too.")

    seasons = (
        [s.strip() for s in args.seasons.split(",") if s.strip()]
        if args.seasons
        else DEFAULT_SEASONS
    )
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    all_rows: list[dict] = []
    for season in seasons:
        items = fetch_season(args.league, season, settings.api_football_key)
        if not items:
            time.sleep(REQUEST_DELAY_SECONDS)
            continue
        raw_path = RAW_DIR / f"{args.name}_{season}.json"
        raw_path.write_text(json.dumps(items), encoding="utf-8")
        rows = _rows_from_items(items, args.name, season)
        logger.info(
            "%s %s: %d games returned, %d finished with scores -> %s",
            args.name,
            season,
            len(items),
            len(rows),
            raw_path.name,
        )
        all_rows.extend(rows)
        time.sleep(REQUEST_DELAY_SECONDS)

    if not all_rows:
        raise SystemExit("No games fetched — nothing to load.")

    session = SessionLocal()
    try:
        inserted = load_rows(session, all_rows)
        session.commit()
    finally:
        session.close()

    logger.info(
        "Inserted %d new basketball matches (of %d fetched). "
        "Run scripts/load_to_db.py to rebuild Elo across all sports.",
        inserted,
        len(all_rows),
    )


if __name__ == "__main__":
    main()
