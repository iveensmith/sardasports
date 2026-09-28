"""Train a tennis Total Games Over/Under model for one specific line.

This is the market where a model can actually earn its place in tennis. The
winner market is dominated by rating difference — a plain "pick the higher
Elo" rule is already strong there (see `train_tennis_winner.py`, which
measures itself against exactly that). Total games is different: Elo ranks
players but says nothing about how *long* a match runs, so there is no
trivial heuristic to beat and the features have real work to do.

`best_of` matters more here than anywhere else in the feature set. WTA is
always best-of-3 and averages 21.8 total games; ATP plays best-of-5 at Grand
Slams and averages 25.9. A model blind to the format would systematically
under-price a men's Slam.

Lines come from this dataset's own distribution (mean 23.9, median 22), not
from guesswork — 21.5 splits it closest to even at 53.2% over.

Usage:
    uv run python -m ml.training.train_tennis_totals --line 21.5
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
from ml.training.train_tennis_winner import MIN_PRIOR_MATCHES

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def model_name_for_line(line: float) -> str:
    """`21.5` -> `"lightgbm_tennis_total_games_21_5"` — keep in sync with
    `ml.prediction.predict_tennis.TOTAL_GAMES_LINES`."""
    return f"lightgbm_tennis_total_games_{str(line).replace('.', '_')}"


def train(line: float, min_matches: int = 100, test_fraction: float = 0.2) -> dict:
    settings = get_settings()
    matches = load_tennis_matches(min_matches)

    logger.info("Building leakage-safe tennis frame from %d matches...", len(matches))
    frame = build_feature_frame(matches)
    frame = frame[
        (frame["home_matches_played"] >= MIN_PRIOR_MATCHES)
        & (frame["away_matches_played"] >= MIN_PRIOR_MATCHES)
        & frame["total_games"].notna()
    ]
    frame["label"] = (frame["total_games"] > line).astype(int)
    logger.info(
        "%d matches usable; %.1f%% went over %s", len(frame), 100 * frame["label"].mean(), line
    )

    train_df, test_df = time_based_split(frame, test_fraction)

    X_train = train_df[FEATURE_COLUMNS].fillna(0.0)
    y_train = train_df["label"]
    X_test = test_df[FEATURE_COLUMNS].fillna(0.0)
    y_test = test_df["label"]

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
    base_rate = float(max(y_test.mean(), 1 - y_test.mean()))

    metrics = {
        "accuracy": round(float(accuracy_score(y_test, y_pred)), 4),
        "log_loss": round(float(log_loss(y_test, y_pred_proba)), 4),
        "majority_class_base_rate": round(base_rate, 4),
        "num_train_samples": len(train_df),
        "num_test_samples": len(test_df),
        "feature_columns": FEATURE_COLUMNS,
        "positive_class": f"over_{line}_games",
        "line": line,
        "feature_summary": compute_feature_summary(train_df),
    }
    logger.info(
        "line=%s Test accuracy=%.4f log_loss=%.4f (majority-class baseline=%.4f)",
        line,
        metrics["accuracy"],
        metrics["log_loss"],
        base_rate,
    )

    model_name = model_name_for_line(line)
    version = new_version_string()
    artifact_dir = settings.model_artifact_dir
    artifact_dir.mkdir(parents=True, exist_ok=True)
    model_path = artifact_dir / f"{model_name}_{version}.txt"
    scaler_path = artifact_dir / f"{model_name}_{version}_scaler.json"

    model.booster_.save_model(str(model_path))
    scaler_path.write_text(
        json.dumps({"mean": scaler.mean_.tolist(), "scale": scaler.scale_.tolist()}),
        encoding="utf-8",
    )

    register_model_version(model_name, version, str(model_path), metrics, len(frame))
    metrics["version"] = version
    metrics["model_name"] = model_name
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Train a tennis total-games model per line")
    parser.add_argument("--line", type=float, required=True, help="Total games line, e.g. 21.5")
    parser.add_argument("--min-matches", type=int, default=100)
    parser.add_argument("--test-fraction", type=float, default=0.2)
    args = parser.parse_args()
    train(line=args.line, min_matches=args.min_matches, test_fraction=args.test_fraction)


if __name__ == "__main__":
    main()
