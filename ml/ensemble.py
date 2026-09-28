"""Ensemble engine.

Combines the three independent result estimators (Elo, Poisson, XGBoost) into
one calibrated-ish output via weighted voting, and derives a 0-100 confidence
score from how much the models agree plus how complete the input features
were. Nothing here invents a number that isn't derived from the underlying
models — see `docs/architecture.md` for the exact formula.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

DEFAULT_WEIGHTS = {"elo": 0.25, "poisson": 0.35, "xgboost": 0.40}


@dataclass
class EnsembleInput:
    elo_probs: tuple[float, float, float]  # (home, draw, away)
    poisson_probs: tuple[float, float, float]
    xgboost_probs: tuple[float, float, float] | None  # None if no trained model available yet
    expected_goals_home: float
    expected_goals_away: float
    top_scorelines: list[dict]
    prob_btts_yes: float
    feature_completeness: float  # 0-1, from ml.feature_engineering.features.feature_completeness


@dataclass
class EnsembleOutput:
    home_win: float  # percentage points, 0-100
    draw: float
    away_win: float
    confidence: float  # 0-100
    confidence_label: str
    expected_goals_home: float
    expected_goals_away: float
    top_scorelines: list[dict]
    prob_btts_yes: float
    prob_btts_no: float
    model_weights_used: dict = field(default_factory=dict)
    # Each estimator's own (home, draw, away) before blending, keyed by name.
    #
    # The blend is the answer, but it hides the interesting part: these three
    # are genuinely independent estimators, and where they *disagree* is real
    # signal rather than noise to be averaged away. Surfacing them lets a
    # caller say "all three like the home side" or "Elo and the model
    # disagree here" without re-deriving anything.
    estimator_probs: dict = field(default_factory=dict)
    explanation: list[dict] | None = None  # set by ml.prediction.predict, SHAP permitting
    # Set by ml.prediction.predict after combine() returns — goals/half-time
    # goals/corners/cards each offer several lines, so each is a list of
    # {"line", "prob_over", "prob_under", "model_used"} dicts, already-
    # computed real Poisson (+ blended dedicated model) numbers, not
    # something combine() itself needs to know how to weight/average. Each
    # entry's `prob_over`/`prob_under` are `None` (not the whole list
    # omitted) when this competition has no data for that stat at all — see
    # ml.prediction.predict._build_market_lines.
    goals_markets: list[dict] = field(default_factory=list)
    ht_goals_markets: list[dict] = field(default_factory=list)
    corners_markets: list[dict] = field(default_factory=list)
    cards_markets: list[dict] = field(default_factory=list)


def confidence_label(confidence: float) -> str:
    if confidence >= 90:
        return "Very High"
    if confidence >= 75:
        return "High"
    if confidence >= 60:
        return "Medium"
    return "Low"


def _weighted_average(
    probs_list: list[tuple[float, float, float]], weights: list[float]
) -> tuple[float, float, float]:
    arr = np.average(np.array(probs_list), axis=0, weights=weights)
    arr = arr / arr.sum()  # renormalize for safety against float drift
    return float(arr[0]), float(arr[1]), float(arr[2])


def _agreement_score(probs_list: list[tuple[float, float, float]]) -> float:
    """1.0 = models fully agree on the predicted outcome's probability; lower = disagreement.

    Computed as 1 minus the mean pairwise absolute difference across the
    home/draw/away probability vectors, averaged over all model pairs.
    """
    if len(probs_list) < 2:
        return 1.0
    diffs = []
    for i in range(len(probs_list)):
        for j in range(i + 1, len(probs_list)):
            a, b = np.array(probs_list[i]), np.array(probs_list[j])
            diffs.append(float(np.abs(a - b).sum()) / 2)  # /2: total variation distance in [0, 1]
    mean_diff = float(np.mean(diffs))
    return max(0.0, 1.0 - mean_diff)


def combine(inputs: EnsembleInput, weights: dict[str, float] | None = None) -> EnsembleOutput:
    """Combine Elo/Poisson/XGBoost result probabilities into a final ensemble prediction."""
    weights = dict(weights or DEFAULT_WEIGHTS)

    probs_list = [inputs.elo_probs, inputs.poisson_probs]
    weight_list = [weights["elo"], weights["poisson"]]
    used_weights = {"elo": weights["elo"], "poisson": weights["poisson"]}

    if inputs.xgboost_probs is not None:
        probs_list.append(inputs.xgboost_probs)
        weight_list.append(weights["xgboost"])
        used_weights["xgboost"] = weights["xgboost"]

    home, draw, away = _weighted_average(probs_list, weight_list)
    agreement = _agreement_score(probs_list)

    estimator_probs = {
        "elo": [round(p * 100, 1) for p in inputs.elo_probs],
        "poisson": [round(p * 100, 1) for p in inputs.poisson_probs],
    }
    if inputs.xgboost_probs is not None:
        estimator_probs["xgboost"] = [round(p * 100, 1) for p in inputs.xgboost_probs]

    # Confidence blends model agreement (60%) and how complete the feature
    # vector was (40%) — a prediction where models disagree heavily or where
    # key features (form, Elo, rest days) are missing should score lower.
    confidence = 100 * (0.6 * agreement + 0.4 * inputs.feature_completeness)
    confidence = round(max(0.0, min(100.0, confidence)), 1)

    return EnsembleOutput(
        home_win=round(home * 100, 1),
        draw=round(draw * 100, 1),
        away_win=round(away * 100, 1),
        confidence=confidence,
        confidence_label=confidence_label(confidence),
        expected_goals_home=round(inputs.expected_goals_home, 2),
        expected_goals_away=round(inputs.expected_goals_away, 2),
        top_scorelines=inputs.top_scorelines,
        prob_btts_yes=round(inputs.prob_btts_yes * 100, 1),
        prob_btts_no=round((1 - inputs.prob_btts_yes) * 100, 1),
        model_weights_used=used_weights,
        estimator_probs=estimator_probs,
    )
