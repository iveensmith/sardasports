"""Download real historical match data from Football-Data.co.uk.

Football-Data.co.uk publishes free, no-auth CSV files per league/season at
predictable URLs, e.g.:

    https://www.football-data.co.uk/mmz4281/2324/E0.csv

`2324` means season 2023-2024, `E0` means English Premier League. Files are
saved verbatim under `data/raw/` — cleaning/normalization happens later in
`scripts/clean_data.py`, keeping raw and processed data separate per the
pipeline requirements.

Usage:
    uv run python scripts/download_data.py --league E0 --seasons 2223,2324,2425
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BASE_URL = "https://www.football-data.co.uk/mmz4281"
RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"

# Football-Data.co.uk league codes that share the same per-season CSV
# format/URL pattern. The "big 5" top flights plus their second divisions,
# plus a handful of other major European top flights.
KNOWN_LEAGUES = {
    "E0": "English Premier League",
    "E1": "English Championship",
    "E2": "English League One",
    "E3": "English League Two",
    "EC": "English National League",
    "SP1": "Spanish La Liga",
    "SP2": "Spanish Segunda Division",
    "D1": "German Bundesliga",
    "D2": "German 2. Bundesliga",
    "I1": "Italian Serie A",
    "I2": "Italian Serie B",
    "F1": "French Ligue 1",
    "F2": "French Ligue 2",
    "N1": "Dutch Eredivisie",
    "B1": "Belgian Pro League",
    "P1": "Portuguese Primeira Liga",
    "T1": "Turkish Super Lig",
    "G1": "Greek Super League",
    "SC0": "Scottish Premiership",
}


def download_season(
    league: str, season: str, dest_dir: Path = RAW_DIR, timeout: int = 30
) -> Path | None:
    """Download one league/season CSV. Returns the saved path, or None on failure."""
    url = f"{BASE_URL}/{season}/{league}.csv"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{league}_{season}.csv"

    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.error("Failed to download %s: %s", url, exc)
        return None

    if not response.content or b"HomeTeam" not in response.content[:2000]:
        logger.warning("Unexpected content from %s (not a match CSV) — skipping", url)
        return None

    dest.write_bytes(response.content)
    logger.info("Saved %s (%d bytes)", dest, len(response.content))
    return dest


def main() -> None:
    parser = argparse.ArgumentParser(description="Download Football-Data.co.uk season CSVs")
    parser.add_argument(
        "--league", default="E0", help=f"League code, e.g. {', '.join(KNOWN_LEAGUES)}"
    )
    parser.add_argument(
        "--seasons",
        default="2223,2324,2425",
        help="Comma-separated season codes, e.g. 2223 = 2022-2023",
    )
    args = parser.parse_args()

    seasons = [s.strip() for s in args.seasons.split(",") if s.strip()]
    saved = []
    for season in seasons:
        path = download_season(args.league, season)
        if path:
            saved.append(path)

    if not saved:
        raise SystemExit("No files downloaded — check network access and league/season codes.")
    logger.info("Downloaded %d file(s) into %s", len(saved), RAW_DIR)


if __name__ == "__main__":
    main()
