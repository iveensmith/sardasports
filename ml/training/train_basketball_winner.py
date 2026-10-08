"""Train the basketball match-winner model.

**Binary, not three-way.** This is the single biggest modelling difference
from football and the reason this can't reuse `train_match_result.py`: a
basketball game cannot end level. The leagues here play overtime until
somebody wins — a full checked NBA season had 1,311 finished games and zero
ties. Fitting the football model's three-class head would mean asking it to
predict a class that occurs zero times, which at best wastes capacity and at
worst produces a nonzero draw probability that no basketball market offers.

So the label is simply "did the home team win", and the output is a genuine
two-way split that sums to 100%.

Usage:
    uv run python -m ml.training.train_basketball_winner
"""

from __future__ import annotations

import argparse
import json
import logging

import lightgbm as lgb
from sklearn.metrics import accuracy_score, log_loss
from sklearn.preprocessing import StandardScaler

from app.utils.config import get_settings
from ml.feature_engineering.basketball import FEATURE_COLUMNS
from ml.training.basketball_common import (
    build_feature_frame,
    compute_feature_summary,
    load_basketball_matches,
)
from ml.training.common import new_version_string, register_model_version, time_based_split

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

MODEL_NAME = "lightgbm_basketball_winner"


def train(min_matches: int = 100, test_fraction: float = 0.2) -> dict:
    settings = get_settings()
    matches = load_basketball_matches(min_matches)

    logger.info("Building leakage-safe basketball frame from %d games...", len(matches))
    frame = build_feature_frame(matches, settings)
    # Drop the cold-start rows: a team's first games have no prior history,
    # so their rolling pace features are all zero and describe nothing.
    frame = frame[frame["home_avg_points_scored"] > 0]
    frame = frame[frame["away_avg_points_scored"] > 0]
    logger.info("%d games usable after dropping cold-start rows", len(frame))

    train_df, test_df = time_based_split(frame, test_fraction)
    logger.info("Train: %d rows, Test: %d rows", len(train_df), len(test_df))

    X_train = train_df[FEATURE_COLUMNS].fillna(0.0)
    y_train = train_df["home_won"]
    X_test = test_df[FEATURE_COLUMNS].fillna(0.0)
    y_test = test_df["home_won"]

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    # Same shallow configuration the football binary models settled on, for
    # the same reason: this is a few thousand rows, and the deeper config
    # overfits rather than generalizing.
    model = lgb.LGBMClassifier(
        objective="binary",
        n_estimators=120,
        max_depth=3,
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

    # The honest yardstick for this market: home teams win most NBA games, so
    # "always pick the home team" is a real baseline a model must beat to be
    # worth anything. Recorded alongside accuracy rather than left implicit.
    home_win_base_rate = float(y_test.mean())

    # The same model across very different competitions: report the NBA and everything
    # else separately, each against its own always-pick-home baseline.
    is_nba = (test_df["competition"] == "NBA").to_numpy()
    groups = {}
    for label, mask in (("nba", is_nba), ("other_leagues", ~is_nba)):
        if mask.sum() >= 50:
            groups[label] = {
                "accuracy": round(float(accuracy_score(y_test[mask], y_pred[mask])), 4),
                "home_win_base_rate": round(float(y_test[mask].mean()), 4),
                "num_test_samples": int(mask.sum()),
            }

    metrics = {
        "by_group": groups,
        "accuracy": round(float(accuracy_score(y_test, y_pred)), 4),
        "log_loss": round(float(log_loss(y_test, y_pred_proba)), 4),
        "home_win_base_rate": round(home_win_base_rate, 4),
        "num_train_samples": len(train_df),
        "num_test_samples": len(test_df),
        "feature_columns": FEATURE_COLUMNS,
        "positive_class": "home_win",
        "feature_summary": compute_feature_summary(train_df),
    }
    logger.info(
        "Test accuracy=%.4f log_loss=%.4f (always-home baseline=%.4f)",
        metrics["accuracy"],
        metrics["log_loss"],
        home_win_base_rate,
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
    parser = argparse.ArgumentParser(description="Train the basketball match-winner model")
    parser.add_argument("--min-matches", type=int, default=100)
    parser.add_argument("--test-fraction", type=float, default=0.2)
    args = parser.parse_args()
    train(min_matches=args.min_matches, test_fraction=args.test_fraction)


if __name__ == "__main__":
    main()
