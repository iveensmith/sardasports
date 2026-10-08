"""Tennis prediction: two-way winner plus total-games markets.

Shares the shape of `predict_basketball` — two outcomes, dedicated models,
no Poisson — and differs in the one way tennis always differs: **ratings are
kept per surface**, so the prediction needs a surface-aware Elo state rather
than a single stored rating per competitor.

That's why this rebuilds `SurfaceElo` by replaying prior matches rather than
reading `elo_history` the way the football path does. `elo_history` stores
one rating per competitor, which is the right model for a football club and
the wrong one for a tennis player: it cannot express "1900 on clay, 1650 on
grass", and collapsing the two would discard the single most useful feature
in the sport. The replay is bounded by the match date and the result is
cached by the calling service.

**The home/away slots carry no meaning here.** They're a deterministic hash
assigned at ingest to de-leak the source's winner/loser columns (see
`scripts/fetch_tennis.py`), which is why no home-advantage term appears
anywhere below. Adding one would be modelling a hash function.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

from ml.feature_engineering.tennis import FEATURE_COLUMNS, SurfaceElo, build_match_features

# Offered total-games lines, from the ingested ATP+WTA distribution (mean
# 23.9, median 22): 21.5 splits it closest to even at 53.8% over, with one
# line either side. Keep in sync with
# ml.training.train_tennis_totals.model_name_for_line.
TOTAL_GAMES_LINES = [19.5, 21.5, 23.5]

DEDICATED_MODEL_WEIGHT = 0.6

# A player with fewer recent matches than this on record (a qualifier, a debut) has a
# default rating and empty form: nothing there to base a prediction on.
MIN_PRIOR_MATCHES = 5


@dataclass
class MarketLine:
    line: float
    prob_over: float | None
    prob_under: float | None
    model_used: bool


@dataclass
class TennisPrediction:
    home_player: str
    away_player: str
    surface: str | None
    best_of: int | None
    home_win: float
    away_win: float
    expected_total_games: float
    total_games_markets: list[MarketLine] = field(default_factory=list)
    winner_model_used: bool = False
    elo_home: float = 0.0
    elo_away: float = 0.0
    elo_surface_home: float = 0.0
    elo_surface_away: float = 0.0
    confidence: float = 0.0
    confidence_label: str = "Low"
    # True when a player has too little recent history to be priced; no picks are stored.
    thin_history: bool = False


def build_surface_elo(history: list[dict]) -> SurfaceElo:
    """Replay `history` (already filtered to matches before the target) into
    overall and per-surface rating pools."""
    elo = SurfaceElo()
    for m in history:
        if m.get("home_score") is None or m.get("away_score") is None:
            continue
        if m["home_score"] > m["away_score"]:
            winner, loser = m["home_team"], m["away_team"]
        else:
            winner, loser = m["away_team"], m["home_team"]
        elo.apply(winner, loser, m.get("surface"))
    return elo


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


def predict_match(
    home_player: str,
    away_player: str,
    match_date: datetime,
    surface: str | None,
    best_of: int | None,
    history: list[dict],
    elo: SurfaceElo | None = None,
    winner_model=None,
    winner_scaler_params: dict | None = None,
    total_models: dict[float, tuple] | None = None,
) -> TennisPrediction:
    """Full tennis prediction for one match, from prior matches only."""
    elo = elo or build_surface_elo(history)

    features = build_match_features(
        home_player=home_player,
        away_player=away_player,
        match_date=match_date,
        surface=surface,
        history=history,
        elo=elo,
        best_of=best_of,
    )
    feature_values = [float(features.get(c, 0.0) or 0.0) for c in FEATURE_COLUMNS]

    # Baseline: surface-specific Elo where we have it, overall otherwise.
    # This is a strong baseline in tennis, not a token fallback — the winner
    # model beats it only marginally (see train_tennis_winner.py).
    elo_home_win = SurfaceElo.expected(features["elo_surface_home"], features["elo_surface_away"])

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

    # Expected total games from both players' rolling games-per-match rates.
    expected_total = (
        features["home_avg_games_won"]
        + features["home_avg_games_lost"]
        + features["away_avg_games_won"]
        + features["away_avg_games_lost"]
    ) / 2

    markets = []
    for line in TOTAL_GAMES_LINES:
        entry = (total_models or {}).get(line)
        if entry is None:
            markets.append(MarketLine(line=line, prob_over=None, prob_under=None, model_used=False))
            continue
        model, scaler_params = entry
        scaled = _apply_scaler(feature_values, scaler_params)
        prob_over = min(max(float(model.predict(scaled)[0]), 0.01), 0.99)
        markets.append(
            MarketLine(
                line=line,
                prob_over=round(prob_over * 100, 1),
                prob_under=round((1 - prob_over) * 100, 1),
                model_used=True,
            )
        )

    confidence = round(abs(home_win - 0.5) * 200, 1)

    return TennisPrediction(
        home_player=home_player,
        away_player=away_player,
        surface=surface,
        best_of=best_of,
        home_win=round(home_win * 100, 1),
        away_win=round((1 - home_win) * 100, 1),
        expected_total_games=round(expected_total, 1),
        total_games_markets=markets,
        winner_model_used=winner_model_used,
        elo_home=round(features["elo_home"], 1),
        elo_away=round(features["elo_away"], 1),
        elo_surface_home=round(features["elo_surface_home"], 1),
        elo_surface_away=round(features["elo_surface_away"], 1),
        confidence=confidence,
        confidence_label=_confidence_label(confidence),
        thin_history=(
            features["home_matches_played"] < MIN_PRIOR_MATCHES
            or features["away_matches_played"] < MIN_PRIOR_MATCHES
        ),
    )
