"""Prediction response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ScorelineOut(BaseModel):
    score: str
    probability: float


class FeatureImpactOut(BaseModel):
    feature: str
    impact_percentage_points: float  # signed: + pushes toward the predicted outcome, - away from it


class MarketLineOut(BaseModel):
    """One Over/Under line for a multi-line market (goals, half-time goals,
    corners, cards).

    `prob_over`/`prob_under` are None when this match's competition has no
    data for the stat at all (e.g. MLS for any of the four; historically
    the Saudi Pro League for corners/cards/half-time goals) — a genuinely
    unavailable market, not a zero or a guess. See docs/architecture.md's
    "Corners and cards" and "Half-time goals" sections.
    """

    line: float
    prob_over: float | None
    prob_under: float | None
    model_used: bool


class BasketballPredictionOut(BaseModel):
    """A basketball prediction — a different shape from `PredictionOut`, not
    a subset of it.

    There is no `draw` field because basketball has no draws (zero ties in
    4,149 ingested NBA games; the leagues play overtime until someone wins),
    so `home_win` and `away_win` sum to 100 on their own. There are no goal,
    half-time, corner or card markets either — those stats don't exist in
    this sport, which is different from a football competition that merely
    lacks the data for them, and is why they're absent here rather than
    present-and-null.
    """

    match_id: int
    sport: str = "basketball"
    home_team: str
    away_team: str
    match_date: datetime
    competition: str

    home_win: float
    away_win: float

    expected_points_home: float
    expected_points_away: float
    expected_total_points: float

    # One entry per ml.prediction.predict_basketball.TOTAL_POINTS_LINES line.
    total_points_markets: list[MarketLineOut]

    confidence: float
    confidence_label: str

    model_version: str | None
    winner_model_used: bool
    generated_at: datetime


class TennisPredictionOut(BaseModel):
    """A tennis prediction.

    Like basketball there is no `draw` (every completed match has a winner
    on sets), and additionally no home advantage: `home_player`/`away_player`
    are an arbitrary, deterministic slot assignment made at ingest to
    de-leak the source's winner/loser columns, not a venue. `surface` and
    `best_of` are surfaced because both materially change the prediction —
    ratings are kept per surface, and the format caps total games.
    """

    match_id: int
    sport: str = "tennis"
    home_player: str
    away_player: str
    match_date: datetime
    competition: str
    surface: str | None
    best_of: int | None

    home_win: float
    away_win: float

    elo_home: float
    elo_away: float
    elo_surface_home: float
    elo_surface_away: float

    expected_total_games: float
    # One entry per ml.prediction.predict_tennis.TOTAL_GAMES_LINES line.
    total_games_markets: list[MarketLineOut]

    confidence: float
    confidence_label: str

    model_version: str | None
    winner_model_used: bool
    generated_at: datetime


class PredictionOut(BaseModel):
    match_id: int
    sport: str = "football"
    home_team: str
    away_team: str
    match_date: datetime

    home_win: float
    draw: float
    away_win: float

    expected_goals_home: float
    expected_goals_away: float
    top_scorelines: list[ScorelineOut]

    btts_yes: float
    btts_no: float

    # One entry per offered line (ml.prediction.predict.GOALS_LINES/
    # HT_GOALS_LINES/CORNERS_LINES/CARDS_LINES) — e.g. goals_markets ==
    # [{"line": 1.5, ...}, {"line": 2.5, ...}].
    goals_markets: list[MarketLineOut]
    ht_goals_markets: list[MarketLineOut]
    corners_markets: list[MarketLineOut]
    cards_markets: list[MarketLineOut]

    confidence: float
    confidence_label: str

    model_version: str | None
    model_weights_used: dict
    # {"elo": [home, draw, away], "poisson": [...], "xgboost": [...]} — each
    # independent estimator before blending. Absent for a model that is not
    # trained yet, rather than zero-filled.
    estimator_probs: dict = {}
    btts_model_used: bool
    explanation: list[FeatureImpactOut] | None = None
    generated_at: datetime


class PredictionHistoryPointOut(BaseModel):
    home_win: float
    draw: float
    away_win: float
    confidence: float
    created_at: datetime


class PredictionHistoryOut(BaseModel):
    match_id: int
    timeline: list[PredictionHistoryPointOut]
