"""Fetch a league from Football-Data.co.uk's "extra" (non-European) country
files and normalize it into the same per-season raw CSV shape that
`scripts/download_data.py` produces, so it flows through the existing
`clean_data.py` -> `load_to_db.py` pipeline unchanged.

These countries (Argentina, Austria, Brazil, China, Denmark, Finland,
Ireland, Japan, Mexico, Norway, Poland, Romania, Russia, Sweden,
Switzerland, USA — see https://www.football-data.co.uk/data.php) publish
ONE file per country covering every season, with different column names
(`Home`/`Away`/`HG`/`AG` instead of `HomeTeam`/`AwayTeam`/`FTHG`/`FTAG`) and
no shots/corners/cards columns — genuinely incompatible with
`scripts/download_data.py`'s per-season-file assumption, not just a naming
difference. This script downloads the one country file, filters to the
requested seasons (and league, for a country with more than one), remaps
columns, and writes one CSV per season under `data/raw/` using the same
`{code}_{season}.csv` naming `clean_data.py` expects.

Season handling: most of these leagues (MLS included) run within a single
calendar year rather than spanning two (August-May) like the European
leagues we otherwise use, so `--seasons` here takes bare years (e.g. `2024`)
and each is written out with a same-year season code (`2424`, not `2425`) —
`_season_label` in clean_data.py then displays it as e.g. "2024-2024",
which is correct for these leagues, not a bug.

Usage:
    uv run python scripts/fetch_extra_league.py --country USA --league MLS \\
        --code MLS1 --seasons 2016,2017,2018,2019,2020,2021,2022,2023,2024,2025
"""

from __future__ import annotations

import argparse
import logging
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BASE_URL = "https://www.football-data.co.uk/new"
RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"

# This source's column names -> the standard names clean_data.py already
# expects from the regular per-season files. Odds columns here are closing
# odds (the "C" suffix) rather than the regular files' pre-match odds, but
# they're the same market/bookmaker, so map onto the same destination
# columns rather than dropping real odds data.
COLUMN_MAP = {
    "Date": "Date",
    "Home": "HomeTeam",
    "Away": "AwayTeam",
    "HG": "FTHG",
    "AG": "FTAG",
    "AvgCH": "AvgH",
    "AvgCD": "AvgD",
    "AvgCA": "AvgA",
    "B365CH": "B365H",
    "B365CD": "B365D",
    "B365CA": "B365A",
}


def _season_code(year: int) -> str:
    """`2024` -> "2424" (same-year pair — see module docstring)."""
    yy = str(year)[2:]
    return f"{yy}{yy}"


def fetch_country_file(country: str, timeout: int = 30) -> pd.DataFrame:
    url = f"{BASE_URL}/{country}.csv"
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    # utf-8-sig strips the BOM this source's first column header carries.
    df = pd.read_csv(StringIO(response.content.decode("utf-8-sig")))
    return df


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch a Football-Data.co.uk 'extra' country file, split by season"
    )
    parser.add_argument("--country", required=True, help="e.g. USA")
    parser.add_argument(
        "--league", default=None, help="Filter to this League column value (e.g. MLS)"
    )
    parser.add_argument("--code", required=True, help="Our internal league code, e.g. MLS1")
    parser.add_argument(
        "--seasons", required=True, help="Comma-separated bare years, e.g. 2016,2017,2018"
    )
    args = parser.parse_args()

    years = [int(s.strip()) for s in args.seasons.split(",") if s.strip()]

    logger.info("Downloading %s/%s.csv ...", BASE_URL, args.country)
    df = fetch_country_file(args.country)

    if args.league:
        before = len(df)
        df = df[df["League"] == args.league]
        logger.info("Filtered League=%s: %d -> %d rows", args.league, before, len(df))

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    saved = []
    for year in years:
        season_rows = df[df["Season"] == year]
        if season_rows.empty:
            logger.warning("No rows for %s season %s — skipping", args.country, year)
            continue

        available = {src: dst for src, dst in COLUMN_MAP.items() if src in season_rows.columns}
        out = season_rows[list(available.keys())].rename(columns=available)

        dest = RAW_DIR / f"{args.code}_{_season_code(year)}.csv"
        out.to_csv(dest, index=False)
        saved.append(dest)
        logger.info("Saved %s (%d matches)", dest, len(out))

    if not saved:
        raise SystemExit("No seasons written — check --country/--league/--seasons.")
    logger.info("Wrote %d season file(s) into %s", len(saved), RAW_DIR)


if __name__ == "__main__":
    main()
