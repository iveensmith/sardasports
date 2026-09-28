"""Train a basketball Total Points Over/Under model for one specific line.

The basketball equivalent of `train_over_under.py`, and the market that
makes clearest why the football stack couldn't simply be pointed at
basketball data: the football goals model is blended with a Poisson fit
truncated at 8 goals, while an NBA game averages **226 total points**. There
is no sensible way to reuse that fit, so this market is the dedicated model
alone — no Poisson baseline, and `model_used` is therefore always true when
a prediction is produced at all.

Lines are picked from this dataset's own distribution rather than guessed,
the same way the corners/cards lines were: see `scripts/inspect_totals.py`
output quoted in docs/architecture.md. Each line is its own genuine market
("Over 215.5" is not derivable from "Over 225.5"), so each gets its own
trained classifier registered under its own model name.

Usage:
    uv run python -m ml.training.train_basketball_totals --line 225.5
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


def model_name_for_line(line: float) -> str:
    """`225.5` -> `"lightgbm_basketball_total_225_5"` — keep in sync with
    `ml.prediction.predict_basketball.TOTAL_POINTS_LINES`."""
    return f"lightgbm_basketball_total_{str(line).replace('.', '_')}"


def train(line: float, min_matches: int = 100, test_fraction: float = 0.2) -> dict:
    settings = get_settings()
    matches = load_basketball_matches(min_matches)

    logger.info("Building leakage-safe basketball frame from %d games...", len(matches))
    frame = build_feature_frame(matches, settings)
    frame = frame[frame["home_avg_points_scored"] > 0]
    frame = frame[frame["away_avg_points_scored"] > 0]
    frame["label"] = (frame["total_points"] > line).astype(int)
    logger.info(
        "%d games usable; %.1f%% went over %s",
        len(frame),
        100 * frame["label"].mean(),
        line,
    )

    train_df, test_df = time_based_split(frame, test_fraction)
    logger.info("Train: %d rows, Test: %d rows", len(train_df), len(test_df))

    X_train = train_df[FEATURE_COLUMNS].fillna(0.0)
    y_train = train_df["label"]
    X_test = test_df[FEATURE_COLUMNS].fillna(0.0)
    y_test = test_df["label"]

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

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

    # A line far from the 50/50 split is an easier classification, so raw
    # accuracy alone would flatter the outer lines. The base rate of the
    # majority class is the honest comparison, recorded next to it.
    base_rate = float(max(y_test.mean(), 1 - y_test.mean()))

    metrics = {
        "accuracy": round(float(accuracy_score(y_test, y_pred)), 4),
        "log_loss": round(float(log_loss(y_test, y_pred_proba)), 4),
        "majority_class_base_rate": round(base_rate, 4),
        "num_train_samples": len(train_df),
        "num_test_samples": len(test_df),
        "feature_columns": FEATURE_COLUMNS,
        "positive_class": f"over_{line}_points",
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
    parser = argparse.ArgumentParser(description="Train a basketball total-points model per line")
    parser.add_argument("--line", type=float, required=True, help="Total points line, e.g. 225.5")
    parser.add_argument("--min-matches", type=int, default=100)
    parser.add_argument("--test-fraction", type=float, default=0.2)
    args = parser.parse_args()
    train(line=args.line, min_matches=args.min_matches, test_fraction=args.test_fraction)


if __name__ == "__main__":
    main()
