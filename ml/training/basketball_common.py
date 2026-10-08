"""Shared loading/feature-frame plumbing for the basketball trainers.

Mirrors `ml.training.common` in shape — walk-forward frame, chronological
split, versioned registration — while differing everywhere the sport
genuinely differs. Two differences are worth naming because they aren't
stylistic:

**Source.** Football trains off `data/processed/matches.csv`, which exists
to reconcile 18 leagues of inconsistent CSV dialects. Basketball comes from
one already-consistent API and is written straight to the `matches` table
(see `scripts/fetch_basketball.py`), so this reads the DB directly. There is
no intermediate CSV to keep in sync, and inventing one would just add a
staleness failure mode of exactly the kind that broke the football pipeline
when `home_goals` was renamed.

**Elo.** The rating pool is filtered to `sport="basketball"` before a single
result is applied. Sharing one engine across sports would merge same-named
competitors and produce ratings that aren't comparable anyway — the same
reason `load_to_db.rebuild_elo_history` runs one engine per sport.

The leakage rule is unchanged and non-negotiable: features for a game are
built only from games strictly before it, and the train/test split is
chronological, never random.
"""

from __future__ import annotations

import logging

import pandas as pd

from app.database.session import SessionLocal
from app.models.match import Match
from app.models.team import Team
from ml.elo.engine import EloEngine, MatchResult
from ml.feature_engineering.basketball import FEATURE_COLUMNS, build_game_features
from ml.feature_engineering.features import build_team_history_index

logger = logging.getLogger(__name__)

SPORT = "basketball"


def load_basketball_matches(min_matches: int = 100) -> list[dict]:
    """Every completed basketball game, ascending by date, as plain dicts."""
    session = SessionLocal()
    try:
        rows = (
            session.query(Match, Team.name.label("home_name"))
            .join(Team, Team.id == Match.home_team_id)
            .filter(Match.sport == SPORT, Match.status == "completed")
            .order_by(Match.match_date.asc(), Match.id.asc())
            .all()
        )
        team_names = {t.id: t.name for t in session.query(Team).filter(Team.sport == SPORT).all()}
        matches = [
            {
                "match_id": m.id,
                "match_date": m.match_date,
                "competition": m.competition,
                "season": m.season,
                "home_team": team_names.get(m.home_team_id, ""),
                "away_team": team_names.get(m.away_team_id, ""),
                "home_score": m.home_score,
                "away_score": m.away_score,
            }
            for m, _ in rows
        ]
    finally:
        session.close()

    if len(matches) < min_matches:
        raise SystemExit(
            f"Only {len(matches)} basketball games available, need at least {min_matches}. "
            "Run scripts/fetch_basketball.py first."
        )
    return matches


def build_feature_frame(matches: list[dict], settings) -> pd.DataFrame:
    """Walk-forward feature frame: one row per game, features from prior games only."""
    history_index = build_team_history_index(matches)
    elo_engine = EloEngine(
        k_factor=settings.elo_k_factor,
        home_advantage=settings.elo_home_advantage,
        initial_rating=settings.elo_initial_rating,
    )

    rows = []
    for m in matches:
        features = build_game_features(
            home_team=m["home_team"],
            away_team=m["away_team"],
            match_date=m["match_date"],
            history=history_index,
            elo_home=elo_engine.get_rating(m["home_team"]),
            elo_away=elo_engine.get_rating(m["away_team"]),
        )
        features["match_date"] = m["match_date"]
        features["match_id"] = m["match_id"]
        features["competition"] = m["competition"]
        features["home_score"] = m["home_score"]
        features["away_score"] = m["away_score"]
        features["total_points"] = m["home_score"] + m["away_score"]
        features["home_won"] = int(m["home_score"] > m["away_score"])
        rows.append(features)

        # Advance Elo only after this game's features were taken from the
        # state that preceded it — the walk-forward invariant.
        elo_engine.apply_result(
            MatchResult(
                home_team=m["home_team"],
                away_team=m["away_team"],
                home_score=m["home_score"],
                away_score=m["away_score"],
                match_date=m["match_date"],
            )
        )

    return pd.DataFrame(rows)


def compute_feature_summary(df: pd.DataFrame) -> dict:
    """Per-feature mean/std, stored with the run so drift can be checked later."""
    summary = {}
    for column in FEATURE_COLUMNS:
        if column in df.columns:
            summary[column] = {
                "mean": round(float(df[column].mean()), 4),
                "std": round(float(df[column].std()), 4),
            }
    return summary
