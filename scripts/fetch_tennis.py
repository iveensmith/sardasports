"""Fetch ATP/WTA tennis results from tennis-data.co.uk into `matches` as
`sport="tennis"`.

Source note: this is the same publisher as football-data.co.uk, which this
pipeline already relies on for 16 of its 18 domestic leagues — so the
provenance and terms are the ones the project already operates under. It
replaced the original plan (Jeff Sackmann's ATP/WTA repos), which turned out
to be unavailable: `JeffSackmann/tennis_atp` now 404s and the surviving
mirrors carry two years of a fifty-year dataset under a relicensed MIT
label. See docs/roadmap.md.

It is also the better fit here: it ships **bookmaker odds** (B365 / Pinnacle
/ market average), which feed the existing value-detection and ROI backtest
paths, and a `Comment` column that distinguishes a real result from a
retirement or walkover.

**The one thing that must not be got wrong: winner/loser leakage.**

The source records a `Winner` and a `Loser` column, not "player 1" and
"player 2". Loading those straight into `home_team`/`away_team` would mean
the home player won 100% of matches, and any model trained on it would score
a perfect 100% by learning nothing except "home always wins" — the classic
way tennis datasets are misused. So each match's two players are assigned to
the home/away slots by a **deterministic hash of the match's identity**
(`_slot_swap`), which:

- splits the label ~50/50, so the target carries real signal;
- is stable across re-runs, so a re-ingest doesn't silently relabel history
  and invalidate every previously-trained model;
- doesn't depend on `random`, so no seed handling and no ordering effects.

Everything downstream (`home_score`, ranks, odds) is swapped in step with it.

**Sets are the score; games are a separate market.** Tennis is won on
sets, not games: a player can win fewer games and still win the match. On
this dataset a games-based winner label would be wrong for 2.00% of matches
and undefined (an exact games tie) for a further 2.82% — 4.81% corrupted
labels. So `home_score`/`away_score` hold *sets*, keeping "the higher score
won" true in every sport, while total games (summed over the `W1/L1`...
`W5/L5` columns) go to `home_games`/`away_games` to price the total-games
market.

Usage:
    uv run python scripts/fetch_tennis.py                      # ATP+WTA, recent years
    uv run python scripts/fetch_tennis.py --tours ATP --years 2020,2021
"""

from __future__ import annotations

import argparse
import hashlib
import io
import logging
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import requests
from sqlalchemy import or_

from app.database.session import SessionLocal
from app.models.match import Match
from app.models.team import Team

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "tennis"
BASE_URL = "http://www.tennis-data.co.uk/hrjk-85HytOjkhth76j_ygh4jf7"
REQUEST_DELAY_SECONDS = 1.0
SPORT = "tennis"

# Only genuinely-completed matches. A retirement or walkover has a real
# winner but not a real scoreline, so training a games-total model on one
# would teach it that matches routinely end 6-2 1-0. Excluded outright.
VALID_COMMENTS = {"Completed"}

TOURS = {"ATP": "", "WTA": "w"}  # tennis-data.co.uk suffixes the WTA path with "w"
DEFAULT_YEARS = list(range(2015, 2026))

SET_COLUMNS = [("W1", "L1"), ("W2", "L2"), ("W3", "L3"), ("W4", "L4"), ("W5", "L5")]


def _slot_swap(tour: str, year: int, index: int, winner: str, loser: str) -> bool:
    """Whether the loser takes the "home" slot for this match.

    Deterministic in the match's own identity, so it is stable across
    re-ingests but uncorrelated with who actually won. See the module
    docstring for why this exists at all.
    """
    key = f"{tour}|{year}|{index}|{winner}|{loser}".encode()
    return hashlib.sha256(key).digest()[0] % 2 == 1


def _sets_won(row) -> tuple[int, int] | None:
    """(winner sets, loser sets) — what actually decides a tennis match."""
    won, lost = row.get("Wsets"), row.get("Lsets")
    if pd.isna(won) or pd.isna(lost):
        return None
    return int(won), int(lost)


def _games_won(row) -> tuple[int, int] | None:
    """(winner games, loser games) summed over the played sets, or None."""
    w_total = l_total = 0
    played = 0
    for w_col, l_col in SET_COLUMNS:
        won, lost = row.get(w_col), row.get(l_col)
        if pd.isna(won) or pd.isna(lost):
            continue
        w_total += int(won)
        l_total += int(lost)
        played += 1
    if played == 0:
        return None
    return w_total, l_total


def _float_or_none(value) -> float | None:
    return None if pd.isna(value) else float(value)


def fetch_year(
    tour: str, year: int, timeout: int = 90, max_age_hours: float | None = None
) -> pd.DataFrame | None:
    """Download one tour-year workbook, cached to disk so a re-load is free.

    A finished year never changes, so its cached file is used as is. The current year
    keeps growing, so pass `max_age_hours` to fetch it again once the cached copy is
    older than that.
    """
    suffix = TOURS[tour]
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    cached = RAW_DIR / f"{tour}_{year}.xlsx"
    if cached.exists():
        age_hours = (time.time() - cached.stat().st_mtime) / 3600
        if max_age_hours is None or age_hours < max_age_hours:
            return pd.read_excel(cached)

    for ext in ("xlsx", "xls"):
        url = f"{BASE_URL}/{year}{suffix}/{year}.{ext}"
        response = requests.get(url, timeout=timeout)
        if response.status_code != 200:
            continue
        cached.write_bytes(response.content)
        return pd.read_excel(io.BytesIO(response.content))

    logger.warning("%s %s: not published at %s", tour, year, BASE_URL)
    return None


def rows_from_frame(df: pd.DataFrame, tour: str, year: int) -> list[dict]:
    """Flatten one tour-year into `matches` rows, with slots de-leaked."""
    rows = []
    for index, row in df.iterrows():
        if str(row.get("Comment", "")).strip() not in VALID_COMMENTS:
            continue
        winner, loser = row.get("Winner"), row.get("Loser")
        date = row.get("Date")
        if pd.isna(winner) or pd.isna(loser) or pd.isna(date):
            continue
        games = _games_won(row)
        sets = _sets_won(row)
        if games is None or sets is None:
            continue
        winner_games, loser_games = games
        winner_sets, loser_sets = sets
        # A completed match the winner didn't actually win on sets is
        # contradictory source data, not a result to train on.
        if winner_sets <= loser_sets:
            continue

        swap = _slot_swap(tour, year, int(index), str(winner), str(loser))
        if swap:
            home, away = str(loser).strip(), str(winner).strip()
            home_games, away_games = loser_games, winner_games
            home_sets, away_sets = loser_sets, winner_sets
            home_odds, away_odds = row.get("AvgL"), row.get("AvgW")
        else:
            home, away = str(winner).strip(), str(loser).strip()
            home_games, away_games = winner_games, loser_games
            home_sets, away_sets = winner_sets, loser_sets
            home_odds, away_odds = row.get("AvgW"), row.get("AvgL")

        surface = row.get("Surface")
        rows.append(
            {
                "external_id": f"tennis-{tour}-{year}-{index}",
                "tournament": (
                    None if pd.isna(row.get("Tournament")) else str(row["Tournament"]).strip()
                ),
                "match_date": pd.to_datetime(date).to_pydatetime(),
                "competition": tour,
                "season": str(year),
                "surface": None if pd.isna(surface) else str(surface).strip(),
                "best_of": None if pd.isna(row.get("Best of")) else int(row["Best of"]),
                "home_team": home,
                "away_team": away,
                # Sets decide the match; games price the totals market.
                "home_score": home_sets,
                "away_score": away_sets,
                "home_games": home_games,
                "away_games": away_games,
                "odds_home_win": _float_or_none(home_odds),
                "odds_away_win": _float_or_none(away_odds),
            }
        )
    return rows


def _get_or_create_player(session, cache: dict, name: str, tour: str) -> Team:
    key = (SPORT, name)
    if key in cache:
        return cache[key]
    player = session.query(Team).filter(Team.sport == SPORT, Team.name == name).one_or_none()
    if player is None:
        player = Team(name=name, league=tour, sport=SPORT)
        session.add(player)
        session.flush()
    cache[key] = player
    return player


ESPN_PREFIX = "espn-tennis-"
SAME_MATCH_DAYS = 4


def _adopt_espn_row(session, row: dict, home: Team, away: Team) -> bool:
    """If ESPN already holds this match, make that row the tennis-data one, in place.

    The ESPN feed puts fixtures and fresh results in before this source publishes them.
    When the same match arrives here (same two players within a few days), the existing
    row is updated with the fuller record (surface, set-by-set games, odds) and given
    this source's id, rather than a second row being added. Keeping the row keeps its
    id, so anything stored against the match still points at it.
    """
    window = timedelta(days=SAME_MATCH_DAYS)
    existing = (
        session.query(Match)
        .filter(
            Match.sport == SPORT,
            Match.external_id.like(f"{ESPN_PREFIX}%"),
            Match.match_date >= row["match_date"] - window,
            Match.match_date <= row["match_date"] + window,
            or_(
                (Match.home_team_id == home.id) & (Match.away_team_id == away.id),
                (Match.home_team_id == away.id) & (Match.away_team_id == home.id),
            ),
        )
        .first()
    )
    if existing is None:
        return False
    same_orientation = existing.home_team_id == home.id
    existing.external_id = row["external_id"]
    existing.match_date = row["match_date"]
    existing.season = row["season"]
    existing.surface = row["surface"] or existing.surface
    existing.best_of = row["best_of"] or existing.best_of
    existing.tournament = row.get("tournament") or existing.tournament
    existing.status = "completed"
    if same_orientation:
        existing.home_score, existing.away_score = row["home_score"], row["away_score"]
        existing.home_games, existing.away_games = row["home_games"], row["away_games"]
        existing.odds_home_win, existing.odds_away_win = row["odds_home_win"], row["odds_away_win"]
    else:
        existing.home_score, existing.away_score = row["away_score"], row["home_score"]
        existing.home_games, existing.away_games = row["away_games"], row["home_games"]
        existing.odds_home_win, existing.odds_away_win = row["odds_away_win"], row["odds_home_win"]
    return True


def load_rows(session, rows: list[dict]) -> int:
    existing = {
        e for (e,) in session.query(Match.external_id).filter(Match.sport == SPORT).all() if e
    }
    cache: dict = {}
    inserted = 0
    for row in rows:
        if row["external_id"] in existing:
            continue
        home = _get_or_create_player(session, cache, row["home_team"], row["competition"])
        away = _get_or_create_player(session, cache, row["away_team"], row["competition"])
        if _adopt_espn_row(session, row, home, away):
            existing.add(row["external_id"])
            continue
        session.add(
            Match(
                external_id=row["external_id"],
                sport=SPORT,
                match_date=row["match_date"],
                competition=row["competition"],
                season=row["season"],
                surface=row["surface"],
                best_of=row["best_of"],
                tournament=row.get("tournament"),
                # Tennis has no home advantage: the slots are an arbitrary
                # ordering this script assigned, not a venue. Marking every
                # match neutral is what stops the Elo home-advantage offset
                # being credited to whichever player the hash happened to
                # put first.
                neutral_venue=True,
                home_team_id=home.id,
                away_team_id=away.id,
                home_score=row["home_score"],
                away_score=row["away_score"],
                home_games=row["home_games"],
                away_games=row["away_games"],
                odds_home_win=row["odds_home_win"],
                odds_away_win=row["odds_away_win"],
                status="completed",
            )
        )
        existing.add(row["external_id"])
        inserted += 1
    return inserted


def backfill_tournaments(session, years: list[int]) -> int:
    """Fill in the tournament name on matches loaded before it was kept (cached files only)."""
    updated = 0
    for tour in TOURS:
        for year in years:
            cached = RAW_DIR / f"{tour}_{year}.xlsx"
            if not cached.exists():
                continue
            for row in rows_from_frame(pd.read_excel(cached), tour, year):
                if not row.get("tournament"):
                    continue
                updated += (
                    session.query(Match)
                    .filter(
                        Match.external_id == row["external_id"],
                        Match.tournament.is_(None),
                    )
                    .update({Match.tournament: row["tournament"]}, synchronize_session=False)
                )
    session.commit()
    return updated


def refresh_current_year(session, max_age_hours: float = 20.0) -> int:
    """Re-read this year's workbooks if they are stale, and load any new matches.

    The scheduler calls this daily. The files are small (about 400 KB each). Returns the
    number of matches inserted or adopted from the other feed.
    """
    year = datetime.now(UTC).year
    rows: list[dict] = []
    for tour in TOURS:
        frame = fetch_year(tour, year, max_age_hours=max_age_hours)
        if frame is not None:
            rows.extend(rows_from_frame(frame, tour, year))
    inserted = load_rows(session, rows)
    session.commit()
    return inserted


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch ATP/WTA tennis into the matches table")
    parser.add_argument("--tours", default="ATP,WTA", help="Comma-separated: ATP,WTA")
    parser.add_argument(
        "--years", help=f"Comma-separated (default {DEFAULT_YEARS[0]}-{DEFAULT_YEARS[-1]})"
    )
    args = parser.parse_args()

    tours = [t.strip().upper() for t in args.tours.split(",") if t.strip()]
    unknown = [t for t in tours if t not in TOURS]
    if unknown:
        raise SystemExit(f"Unknown tour(s) {unknown}; known: {list(TOURS)}")
    years = (
        [int(y.strip()) for y in args.years.split(",") if y.strip()]
        if args.years
        else DEFAULT_YEARS
    )

    all_rows: list[dict] = []
    for tour in tours:
        for year in years:
            df = fetch_year(tour, year)
            if df is None:
                continue
            rows = rows_from_frame(df, tour, year)
            logger.info(
                "%s %s: %d rows -> %d usable completed matches", tour, year, len(df), len(rows)
            )
            all_rows.extend(rows)
            time.sleep(REQUEST_DELAY_SECONDS)

    if not all_rows:
        raise SystemExit("No tennis matches fetched — nothing to load.")

    session = SessionLocal()
    try:
        inserted = load_rows(session, all_rows)
        session.commit()
    finally:
        session.close()

    logger.info(
        "Inserted %d new tennis matches (of %d fetched). "
        "Run scripts/load_to_db.py to rebuild Elo across all sports.",
        inserted,
        len(all_rows),
    )


if __name__ == "__main__":
    main()
