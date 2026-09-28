"""Train a LightGBM Over/Under half-time goals model for one specific line.

Same leakage-safe walk-forward features as the other trainers (see
`ml.training.common`); binary target: did the match finish the first half
with more than `line` total goals? `ml.prediction.predict.HT_GOALS_LINES`
(0.5) is the real bookmaker line this app offers for this market.
Half-time goals are, like full-time goals, a real goal-scoring process —
`ml.prediction.predict` fits a genuine second `PoissonModel` on half-time
scores specifically (not derived from the full-time one) for the same
reason corners/cards get their own Poisson fit: a half is not simply "half
the full match" statistically (teams often set up differently in the
second half), so reusing the full-time fit would misrepresent it.

Half-time score isn't recorded by every source: MLS's Football-Data.co.uk
file has no `HTHG`/`HTAG` columns at all (see `scripts/fetch_extra_league.py`);
everything else in this pipeline has it, including the Saudi Pro League,
where `scripts/fetch_api_football_league.py` pulls it from the same
`/fixtures` response used for full-time goals — see docs/architecture.md's
"Half-time goals" section. Rows without a `total_ht_goals` value are
dropped before training, same as any other row missing its label.

Usage:
    uv run python -m ml.training.train_ht_goals --line 0.5
"""

from __future__ import annotations

import argparse
import json
import logging

import lightgbm as lgb
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


def model_name_for_line(line: float) -> str:
    """`0.5` -> `"lightgbm_over_under_ht_goals_0_5"` — keep in sync with
    `ml.prediction.predict.HT_GOALS_LINES`, the canonical line list."""
    return f"lightgbm_over_under_ht_goals_{str(line).replace('.', '_')}"


def train(line: float, min_matches: int = 100, test_fraction: float = 0.2) -> dict:
    settings = get_settings()
    matches = load_processed_matches(min_matches)

    logger.info("Building leakage-safe training frame from %d matches...", len(matches))
    frame = build_feature_frame(matches, settings)
    frame = frame.dropna(subset=["total_ht_goals", "elo_diff"])
    logger.info(
        "%d of %d matches have half-time score — training on those only",
        len(frame),
        len(matches),
    )
    frame["label"] = (frame["total_ht_goals"] > line).astype(int)

    train_df, test_df = time_based_split(frame, test_fraction)
    logger.info("Train: %d rows, Test: %d rows", len(train_df), len(test_df))

    X_train = train_df[FEATURE_COLUMNS].fillna(0.0)
    y_train = train_df["label"]
    X_test = test_df[FEATURE_COLUMNS].fillna(0.0)
    y_test = test_df["label"]

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    # Same shallow config as the full-time O/U goals model, for the same
    # reason: a deeper config overfits this many rows and produces a
    # worse-calibrated (higher log-loss) model than a simple base-rate
    # baseline.
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

    metrics = {
        "accuracy": round(float(accuracy_score(y_test, y_pred)), 4),
        "log_loss": round(float(log_loss(y_test, y_pred_proba)), 4),
        "majority_class_base_rate": round(majority_class_base_rate(y_test), 4),
        "num_train_samples": len(train_df),
        "num_test_samples": len(test_df),
        "feature_columns": FEATURE_COLUMNS,
        "positive_class": f"over_{line}_ht_goals",
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
    parser = argparse.ArgumentParser(
        description="Train a LightGBM Over/Under half-time goals model for one line"
    )
    parser.add_argument("--line", type=float, required=True, help="Half-time goals line, e.g. 0.5")
    parser.add_argument("--min-matches", type=int, default=100)
    parser.add_argument("--test-fraction", type=float, default=0.2)
    args = parser.parse_args()
    train(line=args.line, min_matches=args.min_matches, test_fraction=args.test_fraction)


if __name__ == "__main__":
    main()
