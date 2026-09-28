"""Train the XGBoost match-result model (Model 1: Home Win / Draw / Away Win).

Walk-forward, leakage-safe training via `ml.training.common` — see that
module's docstring for how features and the train/test split avoid leaking
future information. Produces a versioned artifact under `ml/models/` and
registers the run in `model_versions`/`training_runs`. Existing model
artifacts are never overwritten — every run gets a new version.

Usage:
    uv run python -m ml.training.train_match_result
"""

from __future__ import annotations

import argparse
import json
import logging

import numpy as np
import xgboost as xgb
from sklearn.metrics import accuracy_score, log_loss
from sklearn.preprocessing import StandardScaler

from app.utils.config import get_settings
from ml.training.common import (
    FEATURE_COLUMNS,
    build_feature_frame,
    compute_feature_summary,
    load_processed_matches,
    majority_class_base_rate,
    new_version_string,
    register_model_version,
    time_based_split,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

MODEL_NAME = "xgboost_match_result"
RESULT_LABELS = {"H": 0, "D": 1, "A": 2}  # home win / draw / away win
LABEL_NAMES = ["home_win", "draw", "away_win"]


def _result_label(home_score: int, away_score: int) -> str:
    if home_score > away_score:
        return "H"
    if home_score < away_score:
        return "A"
    return "D"


def train(min_matches: int = 100, test_fraction: float = 0.2) -> dict:
    settings = get_settings()
    matches = load_processed_matches(min_matches)

    logger.info("Building leakage-safe training frame from %d matches...", len(matches))
    frame = build_feature_frame(matches, settings)
    frame["label"] = frame.apply(
        lambda r: RESULT_LABELS[_result_label(r["home_score"], r["away_score"])], axis=1
    )
    frame = frame.dropna(subset=["elo_diff"])  # first match for a brand-new team has no prior Elo

    train_df, test_df = time_based_split(frame, test_fraction)
    logger.info("Train: %d rows, Test: %d rows", len(train_df), len(test_df))

    X_train = train_df[FEATURE_COLUMNS].fillna(0.0)
    y_train = train_df["label"]
    X_test = test_df[FEATURE_COLUMNS].fillna(0.0)
    y_test = test_df["label"]

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    model = xgb.XGBClassifier(
        objective="multi:softprob",
        num_class=3,
        n_estimators=300,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        eval_metric="mlogloss",
        random_state=42,
    )
    model.fit(X_train_scaled, y_train)

    y_pred_proba = model.predict_proba(X_test_scaled)
    y_pred = np.argmax(y_pred_proba, axis=1)

    metrics = {
        "accuracy": round(float(accuracy_score(y_test, y_pred)), 4),
        "log_loss": round(float(log_loss(y_test, y_pred_proba, labels=[0, 1, 2])), 4),
        "majority_class_base_rate": round(majority_class_base_rate(y_test), 4),
        "num_train_samples": len(train_df),
        "num_test_samples": len(test_df),
        "feature_columns": FEATURE_COLUMNS,
        "class_labels": LABEL_NAMES,
        "feature_summary": compute_feature_summary(train_df),
    }
    logger.info("Test accuracy=%.4f log_loss=%.4f", metrics["accuracy"], metrics["log_loss"])

    version = new_version_string()
    artifact_dir = settings.model_artifact_dir
    artifact_dir.mkdir(parents=True, exist_ok=True)
    model_path = artifact_dir / f"{MODEL_NAME}_{version}.json"
    scaler_path = artifact_dir / f"{MODEL_NAME}_{version}_scaler.json"

    model.save_model(model_path)
    scaler_path.write_text(
        json.dumps({"mean": scaler.mean_.tolist(), "scale": scaler.scale_.tolist()}),
        encoding="utf-8",
    )

    register_model_version(MODEL_NAME, version, str(model_path), metrics, len(frame))
    metrics["version"] = version
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the XGBoost match-result model")
    parser.add_argument("--min-matches", type=int, default=100)
    parser.add_argument("--test-fraction", type=float, default=0.2)
    args = parser.parse_args()
    train(min_matches=args.min_matches, test_fraction=args.test_fraction)


if __name__ == "__main__":
    main()
