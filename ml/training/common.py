"""Shared walk-forward training utilities used by every `ml/training/train_*.py` script.

Centralizing this keeps the leakage-safety guarantee (features built only
from strictly-prior matches, Elo advanced only *after* being read as a
feature) in exactly one place rather than re-implemented per model.
"""

from __future__ import annotations

import logging
import math
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from app.database.base import Base
from app.database.session import SessionLocal, get_engine
from app.models import ModelVersion, TrainingRun
from ml.elo.engine import EloEngine, MatchResult
from ml.feature_engineering.features import build_match_features, build_team_history_index

logger = logging.getLogger(__name__)

PROCESSED_PATH = (
    Path(__file__).resolve().parent.parent.parent / "data" / "processed" / "matches.csv"
)

# Fixed catalog, matching scripts/clean_data.py's LEAGUE_NAMES — a small,
# known set of leagues gets one-hot encoded rather than dynamically, so the
# feature schema stays identical between training and prediction regardless
# of which leagues happen to be in the dataset at any given moment. A
# competition outside this list simply gets an all-zero encoding rather than
# crashing — that's how a not-yet-ingested league is handled: `/predict`
# still works for it (falls back to the unscoped Elo+Poisson ensemble, see
# ml.prediction.predict), it just doesn't get a league-specific ML signal.
KNOWN_COMPETITIONS = [
    "English Premier League",
    "English Championship",
    "Spanish La Liga",
    "Spanish Segunda Division",
    "German Bundesliga",
    "German 2. Bundesliga",
    "Italian Serie A",
    "Italian Serie B",
    "French Ligue 1",
    "French Ligue 2",
    "Dutch Eredivisie",
    "Belgian Pro League",
    "Portuguese Primeira Liga",
    "Turkish Super Lig",
    "Greek Super League",
    "Scottish Premiership",
    "Major League Soccer",
    "Saudi Pro League",
    # International (national-team) competitions. These are football, so they
    # share the whole domestic pipeline — but they are their own competitions
    # for the one-hot feature and for the per-competition Poisson fit, which
    # matters more here than between two domestic leagues: national teams
    # meet far less often, and tournament football is lower-scoring than a
    # league season. Keep in sync with scripts/clean_data.LEAGUE_NAMES.
    "FIFA World Cup",
    "UEFA European Championship",
    "UEFA Nations League",
    "Copa America",
    "Africa Cup of Nations",
    "Africa Cup of Nations Qualifiers",
    "International Friendlies",
]


def _competition_column(competition: str) -> str:
    slug = competition.lower().replace(" ", "_")
    return f"competition_{slug}"


COMPETITION_COLUMNS = [_competition_column(c) for c in KNOWN_COMPETITIONS]

# Mixing several leagues into one training set means the model needs to know
# *which* league a match is from — leagues differ meaningfully in average
# goals and home advantage, and without this the model can't tell a
# high-scoring Bundesliga match from a low-scoring Serie A one apart from
# what form/Elo happen to imply. One-hot rather than a single label-encoded
# column, since league identity has no natural ordering.
FEATURE_COLUMNS = [
    "home_form5_points_per_game",
    "away_form5_points_per_game",
    "home_form5_goal_diff",
    "away_form5_goal_diff",
    "home_form10_points_per_game",
    "away_form10_points_per_game",
    "home_form10_avg_goals_scored",
    "away_form10_avg_goals_scored",
    "home_form10_avg_goals_conceded",
    "away_form10_avg_goals_conceded",
    "home_form10_clean_sheets",
    "away_form10_clean_sheets",
    "home_home_form_points_per_game",
    "away_away_form_points_per_game",
    "home_rest_days",
    "away_rest_days",
    "home_fixture_congestion",
    "away_fixture_congestion",
    "elo_home",
    "elo_away",
    "elo_diff",
    "h2h_home_team_wins",
    "h2h_draws",
    "h2h_away_team_wins",
    "home_avg_corners_won",
    "home_avg_corners_conceded",
    "away_avg_corners_won",
    "away_avg_corners_conceded",
    *COMPETITION_COLUMNS,
]


def one_hot_competition(competition: str) -> dict:
    """{"competition_english_premier_league": 1.0, ...all others 0.0}. A
    competition outside KNOWN_COMPETITIONS encodes as all-zero rather than
    raising — an unrecognized league shouldn't crash a prediction, it just
    won't get the benefit of a league-specific signal."""
    target = _competition_column(competition)
    return {col: (1.0 if col == target else 0.0) for col in COMPETITION_COLUMNS}


def load_processed_matches(min_matches: int = 100) -> list[dict]:
    """Read `data/processed/matches.csv`, failing loudly if it's missing/too small."""
    if not PROCESSED_PATH.exists():
        raise SystemExit(
            f"{PROCESSED_PATH} not found — run scripts/clean_data.py and load_to_db.py first."
        )

    raw = pd.read_csv(PROCESSED_PATH, parse_dates=["match_date"])
    matches = raw.to_dict("records")

    if len(matches) < min_matches:
        raise SystemExit(
            f"Only {len(matches)} matches available, need at least {min_matches} to train "
            "meaningfully. Download more seasons with scripts/download_data.py."
        )
    return matches


def _sum_if_both_present(a, b) -> float | None:
    """`a + b`, or `None` if either is missing/NaN — not every league/season
    records corners/cards (see ml.feature_engineering.features' `_is_missing`
    for the same NaN-from-pandas gotcha), and a training label derived from
    a silently-zeroed missing value would be wrong, not just imprecise."""
    if a is None or b is None:
        return None
    if (isinstance(a, float) and math.isnan(a)) or (isinstance(b, float) and math.isnan(b)):
        return None
    return a + b


def build_feature_frame(matches: list[dict], settings) -> pd.DataFrame:
    """Walk forward through `matches` in chronological order, building a leakage-safe
    feature row per match. Does not attach a label — each training script derives its
    own target column (result / goals / BTTS / corners / cards / half-time goals) from
    the raw columns this attaches (`home_score`/`away_score`/`total_corners`/
    `total_cards`/`total_ht_goals`). These "total_*" columns are the *target* match's
    own actual totals — used only for label derivation, deliberately never added to
    `FEATURE_COLUMNS`, since that would leak the outcome being predicted into the
    input."""
    matches = sorted(matches, key=lambda m: m["match_date"])
    # Built ONCE, O(n) — reused for every match in the loop below via O(log k)
    # bisect lookups instead of each of the ~9 feature lookups per match
    # re-scanning the entire (up to tens-of-thousands-of-rows) match list.
    # See ml.feature_engineering.features's module docstring for why this
    # matters: without it, this loop is O(n^2) and becomes impractically
    # slow once several leagues/seasons are ingested together.
    history_index = build_team_history_index(matches)
    elo_engine = EloEngine(
        k_factor=settings.elo_k_factor,
        home_advantage=settings.elo_home_advantage,
        initial_rating=settings.elo_initial_rating,
    )

    rows = []
    for m in matches:
        elo_home = elo_engine.get_rating(m["home_team"])
        elo_away = elo_engine.get_rating(m["away_team"])

        features = build_match_features(
            home_team=m["home_team"],
            away_team=m["away_team"],
            match_date=m["match_date"],
            history=history_index,  # index-accelerated; filters to strictly-prior matches itself
            elo_home=elo_home,
            elo_away=elo_away,
        )
        features.update(one_hot_competition(m["competition"]))
        features["match_date"] = m["match_date"]
        features["home_score"] = m["home_score"]
        features["away_score"] = m["away_score"]
        features["total_corners"] = _sum_if_both_present(
            m.get("home_corners"), m.get("away_corners")
        )
        features["total_cards"] = _sum_if_both_present(
            _sum_if_both_present(m.get("home_yellow_cards"), m.get("away_yellow_cards")),
            _sum_if_both_present(m.get("home_red_cards"), m.get("away_red_cards")),
        )
        features["total_ht_goals"] = _sum_if_both_present(
            m.get("home_ht_goals"), m.get("away_ht_goals")
        )
        rows.append(features)

        # Advance Elo state *after* using it as a feature for this match.
        elo_engine.apply_result(
            MatchResult(
                home_team=m["home_team"],
                away_team=m["away_team"],
                home_score=m["home_score"],
                away_score=m["away_score"],
                match_date=m["match_date"],
                # Absent for every domestic row written before the schema
                # went multi-sport, and for any source that doesn't set it —
                # defaulting to False keeps those as ordinary home games.
                neutral_venue=bool(m.get("neutral_venue", False)),
            )
        )

    return pd.DataFrame(rows)


def compute_feature_summary(df: pd.DataFrame, feature_columns: list[str] = FEATURE_COLUMNS) -> dict:
    """Mean/std per feature over the training rows — a lightweight distribution
    snapshot stored alongside a model's metrics, so a later training run can be
    compared against it to detect feature drift (see `ml.monitoring.drift`).
    """
    summary = {}
    for col in feature_columns:
        values = df[col].dropna()
        if values.empty:
            continue
        summary[col] = {
            "mean": round(float(values.mean()), 4),
            "std": round(float(values.std(ddof=0)), 4),
        }
    return summary


def time_based_split(
    df: pd.DataFrame, test_fraction: float = 0.2
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split chronologically: earliest matches train, most recent matches test."""
    df = df.sort_values("match_date").reset_index(drop=True)
    split_idx = int(len(df) * (1 - test_fraction))
    return df.iloc[:split_idx], df.iloc[split_idx:]


def register_model_version(
    model_name: str, version: str, artifact_path: str, metrics: dict, num_samples: int
) -> ModelVersion:
    """Deactivate previous versions of `model_name`, register the new one, and log the
    training run. Models are never overwritten — every call creates a new row."""
    Base.metadata.create_all(bind=get_engine())
    session = SessionLocal()
    try:
        session.query(ModelVersion).filter(ModelVersion.model_name == model_name).update(
            {"is_active": False}
        )

        model_version = ModelVersion(
            model_name=model_name,
            version=version,
            artifact_path=artifact_path,
            metrics=metrics,
            is_active=True,
            trained_at=datetime.now(UTC),
        )
        session.add(model_version)
        session.flush()

        session.add(
            TrainingRun(
                model_name=model_name,
                model_version_id=model_version.id,
                status="success",
                num_samples=num_samples,
                metrics=metrics,
                started_at=datetime.now(UTC),
                finished_at=datetime.now(UTC),
            )
        )
        session.commit()
        logger.info(
            "Registered model_version id=%s name=%s version=%s",
            model_version.id,
            model_name,
            version,
        )
        return model_version
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def new_version_string() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
