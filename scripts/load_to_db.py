"""Load cleaned match data into the database and rebuild Elo history.

Reads `data/processed/matches.csv`, upserts `teams` and `matches`, then
replays every completed match in chronological order through `EloEngine` to
(re)build the `elo_history` table and each team's current `elo_rating`. Safe
to re-run: existing matches (matched by `external_id`) are skipped, and Elo
history for teams present in the file is rebuilt from scratch so re-running
never double-applies updates.

Usage:
    uv run python scripts/load_to_db.py
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

from app.database.base import Base
from app.database.session import SessionLocal, get_engine
from app.models import EloHistory, Match, Team
from app.utils.config import get_settings
from ml.elo.engine import EloEngine, MatchResult

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

PROCESSED_PATH = Path(__file__).resolve().parent.parent / "data" / "processed" / "matches.csv"


def _get_or_create_team(
    session, cache: dict[str, Team], name: str, league: str, sport: str = "football"
) -> Team:
    # Scoped by sport, matching the UNIQUE(sport, name) the multi-sport
    # migration put on `teams`: the same string can name a football club and
    # a basketball franchise, and merging their rating histories would be a
    # real bug, not a tidy deduplication.
    key = (sport, name)
    if key in cache:
        return cache[key]
    team = session.query(Team).filter(Team.sport == sport, Team.name == name).one_or_none()
    if team is None:
        team = Team(name=name, league=league, sport=sport)
        session.add(team)
        session.flush()
    cache[key] = team
    return team


def load_matches(session, df: pd.DataFrame) -> tuple[list[Match], int]:
    team_cache: dict[str, Team] = {}
    inserted: list[Match] = []
    odds_backfilled = 0
    ht_goals_backfilled = 0

    existing_by_external_id = {m.external_id: m for m in session.query(Match).all()}

    for row in df.itertuples(index=False):
        if row.external_id in existing_by_external_id:
            # Already loaded — but a later pipeline run may add columns (e.g.
            # bookmaker odds, half-time score) that an earlier run didn't
            # have. Backfill those without touching anything else, so
            # re-running stays idempotent.
            existing = existing_by_external_id[row.external_id]
            new_odds = (
                _safe_float(row.odds_home_win),
                _safe_float(row.odds_draw),
                _safe_float(row.odds_away_win),
            )
            if existing.odds_home_win is None and any(o is not None for o in new_odds):
                existing.odds_home_win, existing.odds_draw, existing.odds_away_win = new_odds
                odds_backfilled += 1

            new_ht_goals = (_safe_int(row.home_ht_goals), _safe_int(row.away_ht_goals))
            if existing.home_ht_goals is None and all(g is not None for g in new_ht_goals):
                existing.home_ht_goals, existing.away_ht_goals = new_ht_goals
                ht_goals_backfilled += 1
            continue

        home = _get_or_create_team(session, team_cache, row.home_team, row.competition)
        away = _get_or_create_team(session, team_cache, row.away_team, row.competition)

        match = Match(
            external_id=row.external_id,
            match_date=datetime.strptime(row.match_date, "%Y-%m-%d"),
            competition=row.competition,
            season=row.season,
            # Written by clean_data from NEUTRAL_VENUE_COMPETITIONS; guarded
            # with getattr so a processed CSV produced before this column
            # existed still loads as ordinary home games.
            neutral_venue=bool(getattr(row, "neutral_venue", False)),
            home_team_id=home.id,
            away_team_id=away.id,
            home_score=int(row.home_score),
            away_score=int(row.away_score),
            home_ht_goals=_safe_int(row.home_ht_goals),
            away_ht_goals=_safe_int(row.away_ht_goals),
            home_shots=_safe_int(row.home_shots),
            away_shots=_safe_int(row.away_shots),
            home_shots_on_target=_safe_int(row.home_shots_on_target),
            away_shots_on_target=_safe_int(row.away_shots_on_target),
            home_corners=_safe_int(row.home_corners),
            away_corners=_safe_int(row.away_corners),
            home_yellow_cards=_safe_int(row.home_yellow_cards),
            away_yellow_cards=_safe_int(row.away_yellow_cards),
            home_red_cards=_safe_int(row.home_red_cards),
            away_red_cards=_safe_int(row.away_red_cards),
            referee=None if pd.isna(row.referee) else str(row.referee),
            odds_home_win=_safe_float(row.odds_home_win),
            odds_draw=_safe_float(row.odds_draw),
            odds_away_win=_safe_float(row.odds_away_win),
            status="completed",
        )
        session.add(match)
        inserted.append(match)

    session.flush()
    return inserted, odds_backfilled, ht_goals_backfilled


def _safe_int(value) -> int | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return int(value)


def _safe_float(value) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return float(value)


def rebuild_elo_history(session, settings) -> None:
    """Replay every completed match chronologically to rebuild Elo state.

    One engine **per sport**, not one shared engine. The engine keys its
    rating table by team name, so a single engine across sports would merge
    a football club and a basketball franchise that happen to share a name
    into one rating history — the exact collision `UNIQUE(sport, name)` on
    `teams` exists to prevent, which a name-keyed dict would quietly
    reintroduce. Ratings also aren't comparable across sports (an Elo of
    1700 means different things in each), so there is nothing to gain from
    a shared pool even when names don't collide.
    """
    session.query(EloHistory).delete()

    matches = (
        session.query(Match)
        .filter(Match.status == "completed")
        .order_by(Match.match_date.asc(), Match.id.asc())
        .all()
    )
    team_by_id = {t.id: t for t in session.query(Team).all()}

    engines: dict[str, EloEngine] = {}

    def engine_for(sport: str) -> EloEngine:
        if sport not in engines:
            engines[sport] = EloEngine(
                k_factor=settings.elo_k_factor,
                home_advantage=settings.elo_home_advantage,
                initial_rating=settings.elo_initial_rating,
            )
        return engines[sport]

    for match in matches:
        engine = engine_for(match.sport)
        home_name = team_by_id[match.home_team_id].name
        away_name = team_by_id[match.away_team_id].name

        update = engine.apply_result(
            MatchResult(
                home_team=home_name,
                away_team=away_name,
                home_score=match.home_score,
                away_score=match.away_score,
                match_date=match.match_date,
                neutral_venue=match.neutral_venue,
            )
        )

        session.add(
            EloHistory(
                team_id=match.home_team_id,
                match_id=match.id,
                match_date=match.match_date,
                rating_before=update.home_rating_before,
                rating_after=update.home_rating_after,
                opponent_team_id=match.away_team_id,
                was_home=True,
            )
        )
        session.add(
            EloHistory(
                team_id=match.away_team_id,
                match_id=match.id,
                match_date=match.match_date,
                rating_before=update.away_rating_before,
                rating_after=update.away_rating_after,
                opponent_team_id=match.home_team_id,
                was_home=False,
            )
        )

    for team in team_by_id.values():
        team.elo_rating = engine.get_rating(team.name)

    session.flush()
    logger.info(
        "Rebuilt Elo history from %d completed matches across %d teams",
        len(matches),
        len(team_by_id),
    )


def main() -> None:
    if not PROCESSED_PATH.exists():
        raise SystemExit(f"{PROCESSED_PATH} not found — run scripts/clean_data.py first.")

    settings = get_settings()
    Base.metadata.create_all(bind=get_engine())

    df = pd.read_csv(PROCESSED_PATH)
    session = SessionLocal()
    try:
        inserted, odds_backfilled, ht_goals_backfilled = load_matches(session, df)
        logger.info("Inserted %d new matches (of %d in file)", len(inserted), len(df))
        if odds_backfilled:
            logger.info("Backfilled odds onto %d previously-loaded matches", odds_backfilled)
        if ht_goals_backfilled:
            logger.info(
                "Backfilled half-time score onto %d previously-loaded matches",
                ht_goals_backfilled,
            )
        rebuild_elo_history(session, settings)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
