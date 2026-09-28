"""Fetch a league's historical results from API-Football and normalize them
into the same per-season raw CSV shape `scripts/download_data.py` produces,
so it flows through the existing `clean_data.py` -> `load_to_db.py`
pipeline unchanged.

For leagues Football-Data.co.uk doesn't publish at all (Saudi Pro League,
confirmed absent from their full country list — see docs/roadmap.md), this
is our only real source. Requires `API_FOOTBALL_KEY` in `.env` on a plan
with enough request quota — the free tier's daily cap makes ~10 seasons'
worth of `/fixtures` calls impractical; this script does one request per
season (not per fixture), so a paid tier's higher quota covers it easily.

`fixture.date`, `teams.home/away.name`, `goals.home/away`, and
`score.halftime.home/away` are pulled from each fixture — the last one is
in the same `/fixtures` response, so it's free; everything else (shots/
corners/cards, odds) would need a separate per-fixture call each
(`/fixtures/statistics`, `/odds`), multiplying request count by the
fixture count for data this pipeline doesn't use as a training feature
anyway (odds are used for value detection only, not training) — those
matches just won't have `has_odds=True`/half-time data, same as any other
match lacking that stat.

Usage:
    uv run python scripts/fetch_api_football_league.py --league-id 307 \\
        --code SAU1 --seasons 2016,2017,2018,2019,2020,2021,2022,2023,2024,2025
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
FINISHED_STATUSES = {"FT", "AET", "PEN"}  # full-time, after extra time, after penalties


def _season_code(api_season_year: int) -> str:
    """API-Football's `season` is the split-year start (2023 -> 2023-24),
    same convention as Football-Data.co.uk's own leagues -> "2324"."""
    start = str(api_season_year)[2:]
    end = str(api_season_year + 1)[2:]
    return f"{start}{end}"


def fetch_season(
    league_id: int, season: int, api_key: str, base_url: str, timeout: int = 30
) -> list[dict]:
    response = requests.get(
        f"{base_url}/fixtures",
        headers={"x-apisports-key": api_key},
        params={"league": league_id, "season": season},
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("errors"):
        raise SystemExit(
            f"API-Football error for league={league_id} season={season}: {payload['errors']}"
        )

    rows = []
    for item in payload.get("response", []):
        status = item.get("fixture", {}).get("status", {}).get("short")
        if status not in FINISHED_STATUSES:
            continue
        date_raw = item.get("fixture", {}).get("date")
        home = item.get("teams", {}).get("home", {}).get("name")
        away = item.get("teams", {}).get("away", {}).get("name")
        home_score = item.get("goals", {}).get("home")
        away_score = item.get("goals", {}).get("away")
        if not (date_raw and home and away and home_score is not None and away_score is not None):
            continue
        match_date = datetime.fromisoformat(date_raw.replace("Z", "+00:00"))
        # Half-time score is in the same response, no extra request needed —
        # unlike shots/corners/cards/odds (see the module docstring), so
        # there's no reason to skip it. Can genuinely be missing/null even
        # on a finished fixture in practice, so pulled defensively.
        halftime = item.get("score", {}).get("halftime", {})
        row = {
            "Date": match_date.strftime("%d/%m/%Y"),
            "HomeTeam": home,
            "AwayTeam": away,
            "FTHG": home_score,
            "FTAG": away_score,
        }
        ht_home, ht_away = halftime.get("home"), halftime.get("away")
        if ht_home is not None and ht_away is not None:
            row["HTHG"] = ht_home
            row["HTAG"] = ht_away
        rows.append(row)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch a league from API-Football, split by season"
    )
    parser.add_argument(
        "--league-id", type=int, required=True, help="API-Football league id, e.g. 307"
    )
    parser.add_argument("--code", required=True, help="Our internal league code, e.g. SAU1")
    parser.add_argument(
        "--seasons",
        required=True,
        help="Comma-separated API-Football season years, e.g. 2016,2017,2018",
    )
    args = parser.parse_args()

    settings = get_settings()
    if not settings.api_football_key:
        raise SystemExit(
            "API_FOOTBALL_KEY is not set. Add it to .env — this script needs a paid-tier "
            "quota for ~10 seasons of /fixtures calls."
        )

    years = [int(s.strip()) for s in args.seasons.split(",") if s.strip()]
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    saved = []
    for i, year in enumerate(years):
        logger.info("Fetching league=%s season=%s ...", args.league_id, year)
        rows = fetch_season(
            args.league_id, year, settings.api_football_key, settings.api_football_base_url
        )
        if not rows:
            logger.warning(
                "No finished fixtures for league=%s season=%s — skipping", args.league_id, year
            )
        else:
            dest = RAW_DIR / f"{args.code}_{_season_code(year)}.csv"
            pd.DataFrame(rows).to_csv(dest, index=False)
            saved.append(dest)
            logger.info("Saved %s (%d finished matches)", dest, len(rows))
        if i < len(years) - 1:
            time.sleep(REQUEST_DELAY_SECONDS)

    if not saved:
        raise SystemExit("No seasons written — check --league-id/--seasons and API key/plan.")
    logger.info("Wrote %d season file(s) into %s", len(saved), RAW_DIR)


if __name__ == "__main__":
    main()
