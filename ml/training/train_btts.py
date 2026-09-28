"""Train the Gradient Boosting Both-Teams-To-Score model (Model 3 of the spec).

Same leakage-safe walk-forward features as the other two trainers (see
`ml.training.common`); binary target = did both teams score at least one
goal? Blended into the ensemble alongside the Poisson-derived BTTS
probability once trained (see `ml/ensemble.py`).

Usage:
    uv run python -m ml.training.train_btts
"""

from __future__ import annotations

import argparse
import json
import logging
import pickle

from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import accuracy_score, log_loss
from sklearn.preprocessing import StandardScaler

from app.utils.config import get_settings
from ml.training.common import (
    FEATURE_COLUMNS,
    build_feature_frame,
    compute_feature_summary,
    load_processed_matches,
    new_version_string,
    register_model_version,
    time_based_split,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

MODEL_NAME = "gbm_btts"


def train(min_matches: int = 100, test_fraction: float = 0.2) -> dict:
    settings = get_settings()
    matches = load_processed_matches(min_matches)

    logger.info("Building leakage-safe training frame from %d matches...", len(matches))
    frame = build_feature_frame(matches, settings)
    frame["label"] = ((frame["home_score"] > 0) & (frame["away_score"] > 0)).astype(int)
    frame = frame.dropna(subset=["elo_diff"])

    train_df, test_df = time_based_split(frame, test_fraction)
    logger.info("Train: %d rows, Test: %d rows", len(train_df), len(test_df))

    X_train = train_df[FEATURE_COLUMNS].fillna(0.0)
    y_train = train_df["label"]
    X_test = test_df[FEATURE_COLUMNS].fillna(0.0)
    y_test = test_df["label"]

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    # Kept shallow/small for the same reason as the LightGBM O/U model: with
    # ~900 training rows, a deeper config overfits and produces a worse
    # (higher) test log-loss than a constant-probability baseline.
    model = GradientBoostingClassifier(
        n_estimators=120,
        max_depth=2,
        learning_rate=0.05,
        subsample=0.8,
        min_samples_leaf=20,
        random_state=42,
    )
    model.fit(X_train_scaled, y_train)

    y_pred_proba = model.predict_proba(X_test_scaled)[:, 1]
    y_pred = (y_pred_proba >= 0.5).astype(int)

    metrics = {
        "accuracy": round(float(accuracy_score(y_test, y_pred)), 4),
        "log_loss": round(float(log_loss(y_test, y_pred_proba)), 4),
        "num_train_samples": len(train_df),
        "num_test_samples": len(test_df),
        "feature_columns": FEATURE_COLUMNS,
        "positive_class": "btts_yes",
        "feature_summary": compute_feature_summary(train_df),
    }
    logger.info("Test accuracy=%.4f log_loss=%.4f", metrics["accuracy"], metrics["log_loss"])

    version = new_version_string()
    artifact_dir = settings.model_artifact_dir
    artifact_dir.mkdir(parents=True, exist_ok=True)
    model_path = artifact_dir / f"{MODEL_NAME}_{version}.pkl"
    scaler_path = artifact_dir / f"{MODEL_NAME}_{version}_scaler.json"

    with open(model_path, "wb") as f:
        pickle.dump(model, f)
    scaler_path.write_text(
        json.dumps({"mean": scaler.mean_.tolist(), "scale": scaler.scale_.tolist()}),
        encoding="utf-8",
    )

    register_model_version(MODEL_NAME, version, str(model_path), metrics, len(frame))
    metrics["version"] = version
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the Gradient Boosting BTTS model")
    parser.add_argument("--min-matches", type=int, default=100)
    parser.add_argument("--test-fraction", type=float, default=0.2)
    args = parser.parse_args()
    train(min_matches=args.min_matches, test_fraction=args.test_fraction)


if __name__ == "__main__":
    main()
