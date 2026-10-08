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

import math
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

from ml.elo.engine import EloEngine
from ml.feature_engineering.basketball import FEATURE_COLUMNS, build_game_features
from ml.feature_engineering.features import TeamHistoryIndex, _team_matches_before

# The offered total-points lines. Chosen from the ingested NBA distribution
# (mean 227.3, median 227), not guessed: 225.5 splits it almost exactly in
# half (53.2% over), which is why it's the real bookmaker centre line, with
# one line either side. Keep in sync with
# ml.training.train_basketball_totals.model_name_for_line.
TOTAL_POINTS_LINES = [215.5, 225.5, 235.5]

# The trained totals models are for the NBA, whose games average about 227 points. Every
# other league scores differently (about 160 in the EuroLeague, about 165 in the WNBA),
# so its totals are priced statistically instead: a normal distribution around the
# expected total (the blend of what each side scores and what the other concedes), with
# the league's own spread. Measured on games the method never saw, across 21 non-NBA
# competitions, its calls at the league's average line were right 61% of the time
# against 51% for always picking the more common side, and its probabilities were
# calibrated within a point or two at every confidence band, including at lines 6
# points either side. Offered as three lines, five points apart, around the expectation.
NBA_COMPETITION = "NBA"
STATISTICAL_LINE_STEP = 5.0
# The spread to use for a league with too little history to measure its own.
DEFAULT_TOTAL_SPREAD = 18.5
MIN_LEAGUE_GAMES_FOR_SPREAD = 30
MIN_SPREAD = 12.0

# A side with fewer prior games than this has no basis for a prediction: its ratings and
# averages are defaults, not evidence. A side whose newest game is very old has little
# more. Between those, ratings that are merely out of date are used, pulled towards a
# coin flip in proportion to how old they are, and flagged so the page can say so.
MIN_PRIOR_GAMES = 6
UNUSABLE_AFTER_DAYS = 800
STALE_AFTER_DAYS = 300
STALE_SHRINK = 0.8

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
    # "model" for a trained model, "statistical" for the normal-distribution estimate.
    source: str = "model"


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
    # True when one side has too little recent history to be priced; no picks are stored.
    thin_history: bool = False
    # Days since the older of the two sides' last games, and whether that is old enough
    # that the winner probability was pulled towards 50%.
    ratings_age_days: int | None = None
    stale_ratings: bool = False


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
    league_totals: dict | None = None,
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

    thin = False
    age_days = 0
    for team in (home_team, away_team):
        prior = _team_matches_before(team, history, match_date)
        if not prior:
            thin = True
            continue
        age = (match_date - prior[-1]["match_date"]).days
        age_days = max(age_days, age)
        if len(prior) < MIN_PRIOR_GAMES or age > UNUSABLE_AFTER_DAYS:
            thin = True
    stale = age_days > STALE_AFTER_DAYS and not thin
    if stale:
        home_win = 0.5 + (home_win - 0.5) * STALE_SHRINK

    markets = []
    if league_totals is not None:
        # Statistical totals for a league the trained models do not cover.
        if not thin and expected_total > 0:
            spread = (
                max(MIN_SPREAD, float(league_totals["std"]))
                if league_totals.get("n", 0) >= MIN_LEAGUE_GAMES_FOR_SPREAD
                else DEFAULT_TOTAL_SPREAD
            )
            centre = math.floor(expected_total) + 0.5
            for line in (
                centre - STATISTICAL_LINE_STEP,
                centre,
                centre + STATISTICAL_LINE_STEP,
            ):
                z = (line - expected_total) / spread
                over = min(max(0.5 * math.erfc(z / math.sqrt(2)), 0.01), 0.99)
                markets.append(
                    MarketLine(
                        line=line,
                        prob_over=round(over * 100, 1),
                        prob_under=round((1 - over) * 100, 1),
                        model_used=False,
                        source="statistical",
                    )
                )
    for line in [] if league_totals is not None else TOTAL_POINTS_LINES:
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
        thin_history=thin,
        ratings_age_days=age_days if not thin else None,
        stale_ratings=stale,
    )
