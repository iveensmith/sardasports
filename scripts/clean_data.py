"""Clean and normalize raw Football-Data.co.uk CSVs into one unified dataset.

Reads every `data/raw/*.csv` (as produced by `scripts/download_data.py`),
maps the source's columns onto our schema, normalizes team names, drops
duplicates/invalid rows, and writes the result to `data/processed/matches.csv`.

Supports incremental updates: re-running with new raw files re-derives the
full processed dataset (dedup makes this idempotent), so there's no separate
"append" code path to keep in sync.

Usage:
    uv run python scripts/clean_data.py
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from app.utils.team_names import normalize_team_name

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"

# Keep in sync with scripts/download_data.py's KNOWN_LEAGUES and
# ml/training/common.py's KNOWN_COMPETITIONS.
LEAGUE_NAMES = {
    "E0": "English Premier League",
    "E1": "English Championship",
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
    # Not from download_data.py's direct per-season Football-Data.co.uk URLs —
    # these two are populated by scripts/fetch_extra_league.py (MLS1) and
    # scripts/fetch_api_football_league.py (SAU1) instead, since neither
    # source fits that script's assumptions (see each script's docstring).
    "MLS1": "Major League Soccer",
    "SAU1": "Saudi Pro League",
    # International (national-team) competitions, from
    # scripts/fetch_international.py. Filed under a plain four-digit
    # tournament year rather than a split-season code — see _season_label.
    "WC": "FIFA World Cup",
    "EURO": "UEFA European Championship",
    "UNL": "UEFA Nations League",
    "COPA": "Copa America",
    "AFCON": "Africa Cup of Nations",
    "AFCONQ": "Africa Cup of Nations Qualifiers",
    "FRND": "International Friendlies",
}

# Competitions played on neutral ground, where the "home" team is only a
# fixture-list label (see ml/elo/engine.py's `neutral_venue`). The Nations
# League and friendlies are genuinely home-and-away, so they're absent here.
#
# Known, bounded approximation: the host nation's own matches at a tournament
# *are* real home games, and this marks them neutral anyway — a handful of
# matches per edition. Erring toward neutral is the safer direction: it
# declines to credit an advantage rather than inventing one.
NEUTRAL_VENUE_COMPETITIONS = {
    "FIFA World Cup",
    "UEFA European Championship",
    "Copa America",
    "Africa Cup of Nations",
    # Note the absence of "Africa Cup of Nations Qualifiers": the finals are
    # a single-host tournament, but the qualifiers are played home-and-away
    # like any normal national-team fixture, so they keep home advantage.
}

# Football-Data.co.uk source column -> our column name.
COLUMN_MAP = {
    "Date": "match_date_raw",
    "HomeTeam": "home_team",
    "AwayTeam": "away_team",
    "FTHG": "home_score",
    "FTAG": "away_score",
    "HTHG": "home_ht_goals",
    "HTAG": "away_ht_goals",
    "HS": "home_shots",
    "AS": "away_shots",
    "HST": "home_shots_on_target",
    "AST": "away_shots_on_target",
    "HC": "home_corners",
    "AC": "away_corners",
    "HY": "home_yellow_cards",
    "AY": "away_yellow_cards",
    "HR": "home_red_cards",
    "AR": "away_red_cards",
    "Referee": "referee",
    # Market-average closing odds preferred; Bet365 kept as a fallback for
    # any season file that lacks the "Avg*" columns (both used only for
    # Step-5 value detection, never as a training feature).
    "AvgH": "avg_odds_home_win",
    "AvgD": "avg_odds_draw",
    "AvgA": "avg_odds_away_win",
    "B365H": "b365_odds_home_win",
    "B365D": "b365_odds_draw",
    "B365A": "b365_odds_away_win",
}

REQUIRED_SOURCE_COLUMNS = ["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"]
OUTPUT_COLUMNS = [
    "external_id",
    "match_date",
    "competition",
    "season",
    "neutral_venue",
    "home_team",
    "away_team",
    "home_score",
    "away_score",
    "home_ht_goals",
    "away_ht_goals",
    "home_shots",
    "away_shots",
    "home_shots_on_target",
    "away_shots_on_target",
    "home_corners",
    "away_corners",
    "home_yellow_cards",
    "away_yellow_cards",
    "home_red_cards",
    "away_red_cards",
    "referee",
    "odds_home_win",
    "odds_draw",
    "odds_away_win",
]


def _parse_filename(path: Path) -> tuple[str, str]:
    """`E0_2324.csv` -> ("E0", "2324")."""
    stem = path.stem
    league, _, season = stem.partition("_")
    return league, season


def _season_label(season_code: str) -> str:
    """`2324` -> "2023-2024"; `2022` -> "2022".

    Domestic leagues use a two-digit split-year code (`2324`). International
    tournaments don't span two calendar years, so they're filed under a plain
    four-digit year (`WC_2022.csv`) — which is also four digits and also all
    numeric, so the two are told apart by whether the halves are consecutive:
    `2324` is 23->24, but `2022` would be 20->22, which is no season at all.
    Without this a World Cup would be labelled "2020-2022".
    """
    if len(season_code) == 4 and season_code.isdigit():
        start = int(season_code[:2])
        end = int(season_code[2:])
        if end != (start + 1) % 100:
            return season_code
        start_year = 2000 + start
        end_year = 2000 + end
        return f"{start_year}-{end_year}"
    return season_code


def load_raw_file(path: Path) -> pd.DataFrame | None:
    league, season_code = _parse_filename(path)
    try:
        df = pd.read_csv(path, encoding="latin-1")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not read %s: %s", path, exc)
        return None

    missing = [c for c in REQUIRED_SOURCE_COLUMNS if c not in df.columns]
    if missing:
        logger.warning("Skipping %s — missing required columns %s", path, missing)
        return None

    available = {src: dst for src, dst in COLUMN_MAP.items() if src in df.columns}
    df = df[list(available)].rename(columns=available)

    df["match_date"] = pd.to_datetime(df["match_date_raw"], dayfirst=True, errors="coerce")
    df = df.drop(columns=["match_date_raw"])

    df["competition"] = LEAGUE_NAMES.get(league, league)
    df["season"] = _season_label(season_code)
    df["neutral_venue"] = df["competition"].isin(NEUTRAL_VENUE_COMPETITIONS)
    return df


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Deduplicate, normalize, validate, and select the final output columns."""
    df = df.copy()

    # Drop rows with a missing team name BEFORE normalizing, not after:
    # `.astype(str)` on an object-dtype column does not reliably turn a NaN
    # float into the string "nan" (pandas leaves it as NaN in practice), so
    # normalize_team_name would otherwise crash on a raw `float` — this was
    # a real crash once a Ligue 1 season file with a blank team name field
    # (multi-league ingestion surfaced it; a single clean league file hadn't).
    df = df.dropna(subset=["home_team", "away_team"])

    # Normalize team names.
    df["home_team"] = df["home_team"].astype(str).map(normalize_team_name)
    df["away_team"] = df["away_team"].astype(str).map(normalize_team_name)

    # Validate: require a parseable date, both teams, and both goal counts.
    df = df.dropna(subset=["match_date", "home_team", "away_team", "home_score", "away_score"])
    df = df[(df["home_team"] != "") & (df["away_team"] != "")]
    df = df[df["home_team"] != df["away_team"]]

    for col in ["home_score", "away_score"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["home_score", "away_score"])
    df["home_score"] = df["home_score"].astype(int)
    df["away_score"] = df["away_score"].astype(int)

    for col in [
        "home_ht_goals",
        "away_ht_goals",
        "home_shots",
        "away_shots",
        "home_shots_on_target",
        "away_shots_on_target",
        "home_corners",
        "away_corners",
        "home_yellow_cards",
        "away_yellow_cards",
        "home_red_cards",
        "away_red_cards",
    ]:
        if col not in df.columns:
            df[col] = pd.NA
        else:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "referee" not in df.columns:
        df["referee"] = pd.NA

    # Odds: prefer the market average, fall back to Bet365, tolerate either
    # being entirely absent from an older/thinner source file.
    for src_a, src_b, dst in [
        ("avg_odds_home_win", "b365_odds_home_win", "odds_home_win"),
        ("avg_odds_draw", "b365_odds_draw", "odds_draw"),
        ("avg_odds_away_win", "b365_odds_away_win", "odds_away_win"),
    ]:
        col_a = pd.to_numeric(df[src_a], errors="coerce") if src_a in df.columns else pd.NA
        col_b = pd.to_numeric(df[src_b], errors="coerce") if src_b in df.columns else pd.NA
        df[dst] = col_a if src_a in df.columns else pd.NA
        if src_b in df.columns:
            df[dst] = df[dst].fillna(col_b) if src_a in df.columns else col_b

    df["external_id"] = (
        df["competition"].str.replace(" ", "-")
        + "_"
        + df["match_date"].dt.strftime("%Y-%m-%d")
        + "_"
        + df["home_team"].str.replace(" ", "-")
        + "_vs_"
        + df["away_team"].str.replace(" ", "-")
    )

    df = df.drop_duplicates(subset=["external_id"])
    df["match_date"] = df["match_date"].dt.strftime("%Y-%m-%d")

    return df[OUTPUT_COLUMNS].sort_values("match_date").reset_index(drop=True)


def main() -> None:
    if not RAW_DIR.exists() or not any(RAW_DIR.glob("*.csv")):
        raise SystemExit(f"No raw CSVs found in {RAW_DIR} — run scripts/download_data.py first.")

    frames = []
    for path in sorted(RAW_DIR.glob("*.csv")):
        df = load_raw_file(path)
        if df is not None and not df.empty:
            frames.append(df)
            logger.info("Loaded %d rows from %s", len(df), path.name)

    if not frames:
        raise SystemExit("No valid raw files could be parsed.")

    combined = pd.concat(frames, ignore_index=True)
    cleaned = clean(combined)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / "matches.csv"
    cleaned.to_csv(out_path, index=False)
    logger.info("Wrote %d cleaned matches to %s", len(cleaned), out_path)


if __name__ == "__main__":
    main()
