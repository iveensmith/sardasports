"""Fetch international (national-team) football from API-Football into the
same raw per-season CSV shape `scripts/download_data.py` produces, so it
flows through `clean_data.py` -> `load_to_db.py` unchanged.

Football-Data.co.uk publishes domestic leagues only — it has no
international competitions at all — so API-Football is the source here, the
same way it is for the Saudi Pro League (`fetch_api_football_league.py`).
This script is separate from that one because internationals differ in two
ways that script has no concept of:

- **A tournament is one calendar year, not a split season.** The World Cup
  2022 is filed as `WC_2022.csv`, not `WC_2223.csv`. `clean_data._season_label`
  tells the two apart by whether the two halves are consecutive years.
- **Tournament football is played on neutral ground.** The "home" team in a
  World Cup group game is a fixture-list label, nothing more. Marking those
  matches neutral is what stops the Elo home-advantage offset being credited
  to whichever side the schedule listed first — see `ml/elo/engine.py`'s
  `neutral_venue` and `clean_data.NEUTRAL_VENUE_COMPETITIONS`.

Quota: one `/fixtures` request per competition-season (not per fixture), so
the full default set below is ~30 requests — comfortably inside even the
free tier's 100/day. Half-time scores come back in the same response for
free; shots/corners/cards and odds would each need a per-fixture call, so
they're left out for the same reason as `fetch_api_football_league.py`, and
those markets simply report as unavailable for these competitions.

Usage:
    uv run python scripts/fetch_international.py                  # all, default seasons
    uv run python scripts/fetch_international.py --only WC,EURO
"""

from __future__ import annotations

import argparse
import logging
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

from app.utils.config import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
REQUEST_DELAY_SECONDS = 1.0
FINISHED_STATUSES = {"FT", "AET", "PEN"}

# API-Football league ids for national-team competitions, with the seasons
# that source actually publishes (verified against /leagues rather than
# assumed). Our internal code is the raw-CSV filename prefix and must match
# a key in clean_data.LEAGUE_NAMES.
#
# The season lists are what a *free* API-Football plan can actually fetch:
# it rejects anything outside 2022-2024 ("Free plans do not have access to
# this season"). The competitions themselves go back much further (the World
# Cup to 2010, the Euros to 2008 — verified against /leagues), so a paid plan
# widens these lists and nothing else needs to change. Pass --seasons to
# override once the plan allows it.
COMPETITIONS = {
    "WC": {"league_id": 1, "name": "FIFA World Cup", "seasons": [2022]},
    "EURO": {"league_id": 4, "name": "UEFA European Championship", "seasons": [2024]},
    "UNL": {"league_id": 5, "name": "UEFA Nations League", "seasons": [2022, 2024]},
    "COPA": {"league_id": 9, "name": "Copa America", "seasons": [2024]},
    # AFCON runs on an odd-year cycle (2015, 2017, 2019, 2021, 2023, 2025),
    # and the 2023 edition was actually played in Jan-Feb 2024 — API-Football
    # still files it under season 2023, which is what matters here.
    "AFCON": {"league_id": 6, "name": "Africa Cup of Nations", "seasons": [2023]},
    # The qualifiers are a separate competition, not more tournament matches:
    # they're played home-and-away over two years, so they are deliberately
    # *not* in NEUTRAL_VENUE_COMPETITIONS the way the finals are.
    "AFCONQ": {
        "league_id": 36,
        "name": "Africa Cup of Nations Qualifiers",
        "seasons": [2023],
    },
    "FRND": {
        "league_id": 10,
        "name": "International Friendlies",
        "seasons": [2022, 2023, 2024],
    },
}


def fetch_season(
    league_id: int, season: int, api_key: str, base_url: str, timeout: int = 30
) -> list[dict]:
    """One competition-season's finished fixtures, as Football-Data-shaped rows."""
    response = requests.get(
        f"{base_url}/fixtures",
        headers={"x-apisports-key": api_key},
        params={"league": league_id, "season": season},
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    errors = payload.get("errors")
    if errors:
        # A plan restriction is a fact about the subscription, not a bug in
        # the request — skip that season and keep going, so a free-tier run
        # still ingests everything it *is* entitled to instead of aborting
        # the whole fetch on the first out-of-range year.
        if isinstance(errors, dict) and "plan" in errors:
            logger.warning(
                "league=%s season=%s not available on this plan (%s) — skipping",
                league_id,
                season,
                errors["plan"],
            )
            return []
        raise SystemExit(f"API-Football error for league={league_id} season={season}: {errors}")

    return rows_from_items(payload.get("response", []))


def ninety_minute_score(item: dict) -> tuple[int | None, int | None]:
    """The score after 90 minutes, which is what the 1X2 market is about.

    The API's top-level `goals` includes extra time, so a final won after 120
    minutes carries a winner it did not have at 90. `score.fulltime` is the
    90-minute score. This loader used `goals` for its first 1,798 matches, and
    ten of them — among them the 2022 World Cup final, stored 3-3 when it was
    2-2 — held an extra-time score; see docs/roadmap.md. `goals` is only a
    fallback for a payload with no `fulltime`.
    """
    full = (item.get("score") or {}).get("fulltime") or {}
    if full.get("home") is not None and full.get("away") is not None:
        return full["home"], full["away"]
    goals = item.get("goals") or {}
    return goals.get("home"), goals.get("away")


def rows_from_items(items: list[dict]) -> list[dict]:
    """Finished fixtures as Football-Data-shaped rows."""
    rows = []
    for item in items:
        if item.get("fixture", {}).get("status", {}).get("short") not in FINISHED_STATUSES:
            continue
        date_raw = item.get("fixture", {}).get("date")
        home = item.get("teams", {}).get("home", {}).get("name")
        away = item.get("teams", {}).get("away", {}).get("name")
        home_score, away_score = ninety_minute_score(item)
        if not (date_raw and home and away and home_score is not None and away_score is not None):
            continue
        match_date = datetime.fromisoformat(date_raw.replace("Z", "+00:00"))
        row = {
            "Date": match_date.strftime("%d/%m/%Y"),
            "HomeTeam": home,
            "AwayTeam": away,
            "FTHG": home_score,
            "FTAG": away_score,
        }
        # Same free-in-this-response half-time score as the domestic adapter.
        # The score above is the 90-minute one, so extra time and the shootout
        # are never seen by the 1X2 or goals models.
        halftime = item.get("score", {}).get("halftime", {})
        ht_home, ht_away = halftime.get("home"), halftime.get("away")
        if ht_home is not None and ht_away is not None:
            row["HTHG"] = ht_home
            row["HTAG"] = ht_away
        rows.append(row)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch international football from API-Football")
    parser.add_argument(
        "--only",
        help=f"Comma-separated subset of {','.join(COMPETITIONS)} (default: all)",
    )
    parser.add_argument(
        "--seasons",
        help="Override seasons for the selected competitions, comma-separated years",
    )
    args = parser.parse_args()

    settings = get_settings()
    if not settings.api_football_key:
        raise SystemExit("API_FOOTBALL_KEY is not set. Add it to .env — see docs/setup_guide.md.")

    codes = [c.strip().upper() for c in args.only.split(",")] if args.only else list(COMPETITIONS)
    unknown = [c for c in codes if c not in COMPETITIONS]
    if unknown:
        raise SystemExit(f"Unknown competition code(s) {unknown}; known: {list(COMPETITIONS)}")

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    total = 0
    for code in codes:
        spec = COMPETITIONS[code]
        seasons = (
            [int(s.strip()) for s in args.seasons.split(",") if s.strip()]
            if args.seasons
            else spec["seasons"]
        )
        for season in seasons:
            rows = fetch_season(
                spec["league_id"], season, settings.api_football_key, settings.api_football_base_url
            )
            if not rows:
                logger.warning("%s %s: no finished fixtures returned, skipping", code, season)
                time.sleep(REQUEST_DELAY_SECONDS)
                continue
            out = RAW_DIR / f"{code}_{season}.csv"
            pd.DataFrame(rows).to_csv(out, index=False)
            logger.info("%s %s: wrote %d matches to %s", spec["name"], season, len(rows), out.name)
            total += len(rows)
            time.sleep(REQUEST_DELAY_SECONDS)

    logger.info("Done — %d international matches written to %s", total, RAW_DIR)


if __name__ == "__main__":
    main()
