"""Train a Gradient Boosting Over/Under cards model for one specific line.

Same leakage-safe walk-forward features as the other trainers (see
`ml.training.common`); binary target: did the match finish with more than
`line` total cards (yellow + red, both teams)?
`ml.prediction.predict.CARDS_LINES` (2.5, 3.5, 4.5) are the real bookmaker
lines this app offers — each is its own genuine market, so each needs its
own trained classifier; run this script once per line (see Usage). The
Poisson baseline in `ml.prediction.predict`, by contrast, is one fit
*reused* across every line, since `prob_over_under(line=...)` is a real
calculation off the same fitted scoreline matrix regardless of which line
is asked for.

Deliberately doesn't get its own rolling cards-form feature the way corners
does — cards are driven heavily by referee tendency and match context
(a genuine derby, a relegation six-pointer) that a team-level rolling
average captures far more weakly than it does for corners, which are a
more stable team-attacking-intent signal. Trained on the same
`FEATURE_COLUMNS` as the other models regardless, so it still benefits from
elo/form context. Not every league/season records cards (same gap as
corners — see docs/architecture.md's "Corners and cards" section); rows
missing a `total_cards` value are dropped before training.

Usage:
    uv run python -m ml.training.train_cards --line 2.5
    uv run python -m ml.training.train_cards --line 3.5
    uv run python -m ml.training.train_cards --line 4.5
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


def model_name_for_line(line: float) -> str:
    """`2.5` -> `"gbm_over_under_cards_2_5"` — keep in sync with
    `ml.prediction.predict.CARDS_LINES`, the canonical line list."""
    return f"gbm_over_under_cards_{str(line).replace('.', '_')}"


def train(line: float, min_matches: int = 100, test_fraction: float = 0.2) -> dict:
    settings = get_settings()
    matches = load_processed_matches(min_matches)

    logger.info("Building leakage-safe training frame from %d matches...", len(matches))
    frame = build_feature_frame(matches, settings)
    frame = frame.dropna(subset=["total_cards", "elo_diff"])
    logger.info(
        "%d of %d matches have card data — training on those only", len(frame), len(matches)
    )
    frame["label"] = (frame["total_cards"] > line).astype(int)

    train_df, test_df = time_based_split(frame, test_fraction)
    logger.info("Train: %d rows, Test: %d rows", len(train_df), len(test_df))

    X_train = train_df[FEATURE_COLUMNS].fillna(0.0)
    y_train = train_df["label"]
    X_test = test_df[FEATURE_COLUMNS].fillna(0.0)
    y_test = test_df["label"]

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    # Same shallow config as the BTTS model, for the same reason: a deeper
    # config overfits and produces a worse (higher) test log-loss than a
    # simple base-rate baseline.
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
        "positive_class": f"over_{line}_cards",
        "line": line,
        "feature_summary": compute_feature_summary(train_df),
    }
    logger.info(
        "line=%s Test accuracy=%.4f log_loss=%.4f", line, metrics["accuracy"], metrics["log_loss"]
    )

    model_name = model_name_for_line(line)
    version = new_version_string()
    artifact_dir = settings.model_artifact_dir
    artifact_dir.mkdir(parents=True, exist_ok=True)
    model_path = artifact_dir / f"{model_name}_{version}.pkl"
    scaler_path = artifact_dir / f"{model_name}_{version}_scaler.json"

    with open(model_path, "wb") as f:
        pickle.dump(model, f)
    scaler_path.write_text(
        json.dumps({"mean": scaler.mean_.tolist(), "scale": scaler.scale_.tolist()}),
        encoding="utf-8",
    )

    register_model_version(model_name, version, str(model_path), metrics, len(frame))
    metrics["version"] = version
    metrics["model_name"] = model_name
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Train a Gradient Boosting Over/Under cards model for one line"
    )
    parser.add_argument(
        "--line", type=float, required=True, help="Cards line, e.g. 2.5, 3.5, or 4.5"
    )
    parser.add_argument("--min-matches", type=int, default=100)
    parser.add_argument("--test-fraction", type=float, default=0.2)
    args = parser.parse_args()
    train(line=args.line, min_matches=args.min_matches, test_fraction=args.test_fraction)


if __name__ == "__main__":
    main()
