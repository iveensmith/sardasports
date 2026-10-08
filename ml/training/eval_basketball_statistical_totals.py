"""Measure the statistical total-points method used outside the NBA, and register the result.

Leagues other than the NBA have no trained totals model. Their totals come from a normal
distribution around the expected total (see `ml.prediction.predict_basketball`), which
needs no training but does need measuring, because a method that is never checked
against results is only a guess. This replays every non-NBA game in order, prices the
total at the line nearest each league's own running average using only the games before
it, and records how often the over/under call was right beside how often always picking
the more common side would have been.

The comparison is made at the league's average line, where a coin flip is the honest
baseline; the same method is also scored 6 points either side of it, where the baseline
is much higher and the edge much smaller. All three are recorded so the site can show the
real picture rather than only the flattering line.

Usage:
    uv run python -m ml.training.eval_basketball_statistical_totals
"""

from __future__ import annotations

import logging
import math

import numpy as np
import pandas as pd

from app.utils.config import get_settings
from ml.prediction.predict_basketball import (
    DEFAULT_TOTAL_SPREAD,
    MIN_LEAGUE_GAMES_FOR_SPREAD,
    MIN_SPREAD,
    NBA_COMPETITION,
)
from ml.training.basketball_common import build_feature_frame, load_basketball_matches
from ml.training.common import new_version_string, register_model_version

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

MODEL_NAME = "statistical_basketball_totals"
MIN_PRIOR_LEAGUE_GAMES = 60
TEST_FRACTION = 0.3


def _part(a: float, b: float) -> float:
    values = [x for x in (a, b) if x > 0]
    return sum(values) / len(values) if values else float("nan")


def _score(frame: pd.DataFrame, offset: float) -> dict:
    line = np.floor(frame["lg_mean"] + offset) + 0.5
    spread = np.where(
        frame["lg_n"] >= MIN_LEAGUE_GAMES_FOR_SPREAD,
        np.maximum(MIN_SPREAD, frame["lg_std"]),
        DEFAULT_TOTAL_SPREAD,
    )
    z = (line - frame["pace"]) / spread
    over = np.clip(0.5 * np.array([math.erfc(v / math.sqrt(2)) for v in z]), 0.01, 0.99)
    y = (frame["total_points"] > line).astype(int).to_numpy()
    accuracy = float(((over >= 0.5) == y).mean())
    baseline = float(max(y.mean(), 1 - y.mean()))
    log_loss = float(-np.mean(y * np.log(over) + (1 - y) * np.log(1 - over)))
    return {
        "accuracy": round(accuracy, 4),
        "majority_class_base_rate": round(baseline, 4),
        "log_loss": round(log_loss, 4),
    }


def evaluate() -> dict:
    settings = get_settings()
    matches = load_basketball_matches(100)
    frame = build_feature_frame(matches, settings)
    frame = frame.sort_values(["match_date", "match_id"]).reset_index(drop=True)

    by_league = frame.groupby("competition")["total_points"]
    n = by_league.cumcount()
    prior_sum = by_league.cumsum() - frame["total_points"]
    prior_sq = (frame["total_points"] ** 2).groupby(frame["competition"]).cumsum() - (
        frame["total_points"] ** 2
    )
    frame["lg_n"] = n
    frame["lg_mean"] = prior_sum / n.replace(0, np.nan)
    frame["lg_std"] = np.sqrt(
        ((prior_sq / n.replace(0, np.nan)) - frame["lg_mean"] ** 2).clip(lower=1)
    )
    frame["pace"] = [
        _part(a, b) + _part(c, d)
        for a, b, c, d in zip(
            frame["home_avg_points_scored"],
            frame["away_avg_points_conceded"],
            frame["away_avg_points_scored"],
            frame["home_avg_points_conceded"],
            strict=True,
        )
    ]

    usable = frame[
        (frame["competition"] != NBA_COMPETITION)
        & (frame["lg_n"] >= MIN_PRIOR_LEAGUE_GAMES)
        & frame["pace"].notna()
        & (frame["home_avg_points_scored"] > 0)
        & (frame["away_avg_points_scored"] > 0)
    ]
    cut = usable["match_date"].quantile(1 - TEST_FRACTION)
    test = usable[usable["match_date"] >= cut]

    centre = _score(test, 0.0)
    metrics = {
        **centre,
        "num_test_samples": int(len(test)),
        "num_train_samples": int(len(usable) - len(test)),
        "competitions_tested": int(test["competition"].nunique()),
        "line": "league average",
        "below_line_6": _score(test, -6.0),
        "above_line_6": _score(test, 6.0),
        "method": "normal distribution around the expected total",
    }
    logger.info("statistical totals: %s", metrics)

    register_model_version(
        MODEL_NAME, new_version_string(), "n/a (statistical)", metrics, len(usable)
    )
    return metrics


if __name__ == "__main__":
    evaluate()
