"""Train the tennis match-winner model.

Binary, like basketball, and for a stronger reason: every completed tennis
match has a winner on sets, so there is no third class even in principle.

**The baseline this is measured against is the important part.** The
home/away slots here are an arbitrary de-leaking hash (see
`scripts/fetch_tennis.py`), so "always pick home" is a genuine coin flip at
~50% and tells you nothing. The meaningful comparison is **"always pick the
higher-Elo player"**, which is already a strong tennis heuristic. A model
that can't beat that has learned nothing worth having, so it's computed and
recorded next to the accuracy rather than left for a reader to wonder about.

Usage:
    uv run python -m ml.training.train_tennis_winner
    uv run python -m ml.training.train_tennis_winner --tour ATP
"""

from __future__ import annotations

import argparse
import json
import logging

import lightgbm as lgb
from sklearn.metrics import accuracy_score, log_loss
from sklearn.preprocessing import StandardScaler

from app.utils.config import get_settings
from ml.feature_engineering.tennis import FEATURE_COLUMNS
from ml.training.common import new_version_string, register_model_version, time_based_split
from ml.training.tennis_common import (
    build_feature_frame,
    compute_feature_summary,
    load_tennis_matches,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

MODEL_NAME = "lightgbm_tennis_winner"

# A player needs some history before their rating and form mean anything.
# Matches where either side is below this are dropped from training rather
# than fed in with placeholder ratings.
MIN_PRIOR_MATCHES = 5


def train(min_matches: int = 100, test_fraction: float = 0.2, tour: str | None = None) -> dict:
    settings = get_settings()
    matches = load_tennis_matches(min_matches, tour=tour)

    logger.info("Building leakage-safe tennis frame from %d matches...", len(matches))
    frame = build_feature_frame(matches)
    before = len(frame)
    frame = frame[
        (frame["home_matches_played"] >= MIN_PRIOR_MATCHES)
        & (frame["away_matches_played"] >= MIN_PRIOR_MATCHES)
    ]
    logger.info(
        "%d of %d matches usable (both players have >=%d prior matches)",
        len(frame),
        before,
        MIN_PRIOR_MATCHES,
    )

    train_df, test_df = time_based_split(frame, test_fraction)
    logger.info("Train: %d rows, Test: %d rows", len(train_df), len(test_df))

    X_train = train_df[FEATURE_COLUMNS].fillna(0.0)
    y_train = train_df["home_won"]
    X_test = test_df[FEATURE_COLUMNS].fillna(0.0)
    y_test = test_df["home_won"]

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    model = lgb.LGBMClassifier(
        objective="binary",
        n_estimators=200,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_samples=25,
        reg_lambda=1.0,
        random_state=42,
        verbosity=-1,
    )
    model.fit(X_train_scaled, y_train)

    y_pred_proba = model.predict_proba(X_test_scaled)[:, 1]
    y_pred = (y_pred_proba >= 0.5).astype(int)

    # "Always pick the higher-Elo player" — the heuristic worth beating.
    elo_pick = (test_df["elo_diff"] > 0).astype(int)
    elo_baseline = float((elo_pick == y_test).mean())
    # Surface-specific Elo as a second, harder baseline.
    surface_pick = (test_df["elo_surface_diff"] > 0).astype(int)
    surface_baseline = float((surface_pick == y_test).mean())
    # The slot assignment is a hash, so this should sit at ~50%. If it
    # drifts far from that, de-leaking has broken.
    home_slot_rate = float(y_test.mean())

    metrics = {
        "accuracy": round(float(accuracy_score(y_test, y_pred)), 4),
        "log_loss": round(float(log_loss(y_test, y_pred_proba)), 4),
        "elo_baseline_accuracy": round(elo_baseline, 4),
        "surface_elo_baseline_accuracy": round(surface_baseline, 4),
        "home_slot_win_rate": round(home_slot_rate, 4),
        "num_train_samples": len(train_df),
        "num_test_samples": len(test_df),
        "feature_columns": FEATURE_COLUMNS,
        "positive_class": "home_slot_win",
        "tour": tour or "ALL",
        "feature_summary": compute_feature_summary(train_df),
    }
    logger.info(
        "Test accuracy=%.4f log_loss=%.4f | elo baseline=%.4f surface-elo baseline=%.4f "
        "| home-slot rate=%.4f (should be ~0.50)",
        metrics["accuracy"],
        metrics["log_loss"],
        elo_baseline,
        surface_baseline,
        home_slot_rate,
    )

    version = new_version_string()
    artifact_dir = settings.model_artifact_dir
    artifact_dir.mkdir(parents=True, exist_ok=True)
    model_path = artifact_dir / f"{MODEL_NAME}_{version}.txt"
    scaler_path = artifact_dir / f"{MODEL_NAME}_{version}_scaler.json"

    model.booster_.save_model(str(model_path))
    scaler_path.write_text(
        json.dumps({"mean": scaler.mean_.tolist(), "scale": scaler.scale_.tolist()}),
        encoding="utf-8",
    )

    register_model_version(MODEL_NAME, version, str(model_path), metrics, len(frame))
    metrics["version"] = version
    metrics["model_name"] = MODEL_NAME
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the tennis match-winner model")
    parser.add_argument("--tour", help="Restrict to one tour, e.g. ATP or WTA")
    parser.add_argument("--min-matches", type=int, default=100)
    parser.add_argument("--test-fraction", type=float, default=0.2)
    args = parser.parse_args()
    train(min_matches=args.min_matches, test_fraction=args.test_fraction, tour=args.tour)


if __name__ == "__main__":
    main()
