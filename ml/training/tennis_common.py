"""Shared loading/feature-frame plumbing for the tennis trainers.

Same contract as `ml.training.basketball_common` — DB source, walk-forward
frame, chronological split — with the surface-aware Elo described in
`ml.feature_engineering.tennis`.

The walk-forward invariant matters more here than anywhere else in this
codebase, because tennis has the strongest per-competitor signal of the
three sports: a player's rating *is* most of the prediction. Reading a
single future result into a rating would leak the answer directly, so
ratings are advanced strictly after each match's features are taken.
"""

from __future__ import annotations

import logging

import pandas as pd

from app.database.session import SessionLocal
from app.models.match import Match
from app.models.team import Team
from ml.feature_engineering.features import build_team_history_index
from ml.feature_engineering.tennis import FEATURE_COLUMNS, SurfaceElo, build_match_features

logger = logging.getLogger(__name__)

SPORT = "tennis"


def load_tennis_matches(min_matches: int = 100, tour: str | None = None) -> list[dict]:
    """Every completed tennis match, ascending by date, as plain dicts."""
    session = SessionLocal()
    try:
        query = session.query(Match).filter(Match.sport == SPORT, Match.status == "completed")
        if tour:
            query = query.filter(Match.competition == tour)
        rows = query.order_by(Match.match_date.asc(), Match.id.asc()).all()
        names = {t.id: t.name for t in session.query(Team).filter(Team.sport == SPORT).all()}
        matches = [
            {
                "match_id": m.id,
                "match_date": m.match_date,
                "competition": m.competition,
                "season": m.season,
                "surface": m.surface,
                "best_of": m.best_of,
                "home_team": names.get(m.home_team_id, ""),
                "away_team": names.get(m.away_team_id, ""),
                "home_score": m.home_score,
                "away_score": m.away_score,
                "home_games": m.home_games,
                "away_games": m.away_games,
            }
            for m in rows
        ]
    finally:
        session.close()

    if len(matches) < min_matches:
        raise SystemExit(
            f"Only {len(matches)} tennis matches available, need at least {min_matches}. "
            "Run scripts/fetch_tennis.py first."
        )
    return matches


def build_feature_frame(matches: list[dict]) -> pd.DataFrame:
    """Walk-forward frame: features from prior matches, then advance Elo."""
    history_index = build_team_history_index(matches)
    elo = SurfaceElo()

    rows = []
    for m in matches:
        features = build_match_features(
            home_player=m["home_team"],
            away_player=m["away_team"],
            match_date=m["match_date"],
            surface=m["surface"],
            history=history_index,
            elo=elo,
            best_of=m["best_of"],
        )
        features["match_date"] = m["match_date"]
        features["match_id"] = m["match_id"]
        features["surface"] = m["surface"]
        features["home_won"] = int(m["home_score"] > m["away_score"])
        if m["home_games"] is not None and m["away_games"] is not None:
            features["total_games"] = m["home_games"] + m["away_games"]
        else:
            features["total_games"] = None
        rows.append(features)

        # Advance ratings only after this match's features were read.
        if m["home_score"] > m["away_score"]:
            winner, loser = m["home_team"], m["away_team"]
        else:
            winner, loser = m["away_team"], m["home_team"]
        elo.apply(winner, loser, m["surface"])

    return pd.DataFrame(rows)


def compute_feature_summary(df: pd.DataFrame) -> dict:
    summary = {}
    for column in FEATURE_COLUMNS:
        if column in df.columns:
            summary[column] = {
                "mean": round(float(df[column].mean()), 4),
                "std": round(float(df[column].std()), 4),
            }
    return summary
