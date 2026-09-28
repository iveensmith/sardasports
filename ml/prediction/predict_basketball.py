"""Basketball prediction: two-way winner plus total-points markets.

Deliberately not a branch inside `ml.prediction.predict`. That module is
built around a three-way outcome blended with a Poisson goal model, and
almost every line of it would need a sport conditional to serve basketball —
which is how a clear model turns into a thicket of `if sport ==` checks. The
two share what is genuinely shared (Elo, the leakage-safe history index) and
diverge where the sports do.

Three differences drive everything here:

- **Two outcomes, not three.** `EloEngine.result_probabilities` deliberately
  carves a draw band out of the Elo expectation, which is right for football
  and wrong here: basketball plays overtime until someone wins (zero ties in
  4,149 ingested NBA games). So this uses the raw logistic expectation,
  `expected_score`, which is already exactly a two-way probability.
- **No Poisson baseline.** A ~226-point total has nothing to do with a
  goal model truncated at 8. Without a statistical fallback, an untrained
  line is genuinely unpredictable rather than degraded, and says so
  (`prob_over: None`) instead of inventing a number.
- **Expected points come from pace, not from a fitted scoreline matrix.**
  A team's expected points is the average of what it scores and what its
  opponent concedes — a real estimate off both teams' rolling form.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

from ml.elo.engine import EloEngine
from ml.feature_engineering.basketball import FEATURE_COLUMNS, build_game_features
from ml.feature_engineering.features import TeamHistoryIndex

# The offered total-points lines. Chosen from the ingested NBA distribution
# (mean 227.3, median 227), not guessed: 225.5 splits it almost exactly in
# half (53.2% over), which is why it's the real bookmaker centre line, with
# one line either side. Keep in sync with
# ml.training.train_basketball_totals.model_name_for_line.
TOTAL_POINTS_LINES = [215.5, 225.5, 235.5]

# How much the trained model is trusted against the Elo-implied baseline for
# the winner market, matching the football stack's DEDICATED_MODEL_WEIGHT so
# the two sports blend on the same principle.
DEDICATED_MODEL_WEIGHT = 0.6


@dataclass
class MarketLine:
    line: float
    prob_over: float | None
    prob_under: float | None
    model_used: bool


@dataclass
class BasketballPrediction:
    home_team: str
    away_team: str
    home_win: float
    away_win: float
    expected_points_home: float
    expected_points_away: float
    expected_total_points: float
    total_points_markets: list[MarketLine] = field(default_factory=list)
    winner_model_used: bool = False
    confidence: float = 0.0
    confidence_label: str = "Low"


def _apply_scaler(values: list[float], scaler_params: dict | None) -> np.ndarray:
    row = np.array([values], dtype=float)
    if not scaler_params:
        return row
    mean = np.array(scaler_params["mean"], dtype=float)
    scale = np.array(scaler_params["scale"], dtype=float)
    return (row - mean) / scale


def _confidence_label(confidence: float) -> str:
    if confidence >= 75:
        return "Very High"
    if confidence >= 60:
        return "High"
    if confidence >= 45:
        return "Medium"
    return "Low"


def predict_game(
    home_team: str,
    away_team: str,
    match_date: datetime,
    history: list[dict] | TeamHistoryIndex,
    elo_home: float,
    elo_away: float,
    elo_home_advantage: float = 60.0,
    winner_model=None,
    winner_scaler_params: dict | None = None,
    total_models: dict[float, tuple] | None = None,
) -> BasketballPrediction:
    """Full basketball prediction for one game, from prior games only."""
    features = build_game_features(
        home_team=home_team,
        away_team=away_team,
        match_date=match_date,
        history=history,
        elo_home=elo_home,
        elo_away=elo_away,
    )
    feature_values = [float(features.get(c, 0.0) or 0.0) for c in FEATURE_COLUMNS]

    # Elo baseline: the raw two-way expectation, with no draw band carved
    # out of it (see module docstring).
    elo_home_win = EloEngine.expected_score(elo_home + elo_home_advantage, elo_away)

    winner_model_used = False
    home_win = elo_home_win
    if winner_model is not None:
        scaled = _apply_scaler(feature_values, winner_scaler_params)
        model_home_win = float(winner_model.predict(scaled)[0])
        home_win = (
            DEDICATED_MODEL_WEIGHT * model_home_win + (1 - DEDICATED_MODEL_WEIGHT) * elo_home_win
        )
        winner_model_used = True

    home_win = min(max(home_win, 0.01), 0.99)

    # Expected points: what each side scores blended with what the other
    # concedes. Falls back to the other side of the blend if a team has no
    # rolling history yet, rather than averaging in a zero.
    def _expected(scored: float, conceded: float) -> float:
        parts = [p for p in (scored, conceded) if p > 0]
        return sum(parts) / len(parts) if parts else 0.0

    exp_home = _expected(features["home_avg_points_scored"], features["away_avg_points_conceded"])
    exp_away = _expected(features["away_avg_points_scored"], features["home_avg_points_conceded"])
    expected_total = exp_home + exp_away

    markets = []
    for line in TOTAL_POINTS_LINES:
        entry = (total_models or {}).get(line)
        if entry is None:
            # No statistical fallback exists for this market (no Poisson
            # equivalent), so an untrained line is genuinely unknown and
            # reports as such rather than guessing from expected_total.
            markets.append(MarketLine(line=line, prob_over=None, prob_under=None, model_used=False))
            continue
        model, scaler_params = entry
        scaled = _apply_scaler(feature_values, scaler_params)
        prob_over = float(model.predict(scaled)[0])
        prob_over = min(max(prob_over, 0.01), 0.99)
        markets.append(
            MarketLine(
                line=line,
                prob_over=round(prob_over * 100, 1),
                prob_under=round((1 - prob_over) * 100, 1),
                model_used=True,
            )
        )

    # Confidence: how far the two-way call sits from a coin flip, scaled to
    # 0-100. A 50/50 game is 0; a 90/10 game is 80.
    confidence = round(abs(home_win - 0.5) * 200, 1)

    return BasketballPrediction(
        home_team=home_team,
        away_team=away_team,
        home_win=round(home_win * 100, 1),
        away_win=round((1 - home_win) * 100, 1),
        expected_points_home=round(exp_home, 1),
        expected_points_away=round(exp_away, 1),
        expected_total_points=round(expected_total, 1),
        total_points_markets=markets,
        winner_model_used=winner_model_used,
        confidence=confidence,
        confidence_label=_confidence_label(confidence),
    )
