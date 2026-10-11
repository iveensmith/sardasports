"""Prediction response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class BadgeOut(BaseModel):
    """What to render beside a team name: a flag, or initials for a club.

    Mirrors `ml.team_badges.Badge`. Kept as its own schema rather than a
    free-form dict so a client gets a typed contract for it, the same as
    every other field here.
    """

    kind: str  # "flag" | "crest" | "monogram"
    code: str | None = None
    initials: str | None = None
    logo: str | None = None


class ScorelineOut(BaseModel):
    score: str
    probability: float


class LiveOut(BaseModel):
    """A fixture in play: its minute and score so far. Never the final result."""

    status: str | None = None
    minute: int | None = None
    label: str
    home: int
    away: int


class ScoreOut(BaseModel):
    home: int
    away: int


class OddsOut(BaseModel):
    """Bookmaker 1X2 prices, read straight off the match row — the same
    numbers the board's odds columns show. `draw` is null for a sport with
    no draw market (basketball)."""

    home: float | None
    draw: float | None
    away: float | None


class ActualStatOut(BaseModel):
    """One stat, both sides, once the match has actually been played.

    Every field is independently nullable: a completed match with
    `stats_fetched_at` set but no possession reported (a competition that
    genuinely doesn't record it) shows `possession: None`, not a fabricated
    0-0.
    """

    home: int | None
    away: int | None


class ActualStatsOut(BaseModel):
    """What actually happened, alongside the prediction — see
    `scripts/fetch_match_stats.py`. Present only once the match is
    completed; a fixture still to be played has nothing here yet, which is
    different from a completed one whose competition reports none of this.
    """

    shots: ActualStatOut
    shots_on_target: ActualStatOut
    corners: ActualStatOut
    yellow_cards: ActualStatOut
    red_cards: ActualStatOut
    possession: ActualStatOut
    offsides: ActualStatOut
    fouls: ActualStatOut


class MatchEventOut(BaseModel):
    """One goal, in the order it happened — see `app.models.match_event`."""

    minute: int
    added_time: int | None
    side: str  # "home" | "away"
    player: str
    assist: str | None
    detail: str
    home_score_after: int
    away_score_after: int


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

    match_status: str = "scheduled"
    match_score: ScoreOut | None = None
    live: LiveOut | None = None
    odds_1x2: OddsOut | None = None

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

    match_status: str = "scheduled"
    match_score: ScoreOut | None = None
    live: LiveOut | None = None
    odds_1x2: OddsOut | None = None

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


class CallOut(BaseModel):
    """One market's call, with the context that makes it a claim.

    `probability` alone is not a prediction — over 1.5 goals lands in 74.8%
    of all matches, so a 76% reading says nothing. `base_rate` is how often
    this selection actually lands across completed matches and `lift` is the
    distance between them, which is the part that carries information.

    `base_rate` and `lift` are null for a market with too little history to
    judge, which is deliberately distinct from a lift of zero.
    """

    market: str
    market_name: str
    selection: str
    label: str
    probability: float
    base_rate: float | None = None
    lift: float | None = None
    notable: bool = False


class CallsOut(BaseModel):
    """What the engine calls across every market it can price."""

    # The fixture's one prediction: the likeliest selection across every
    # market. See ml.markets.headline_call.
    headline: CallOut | None = None
    # The strongest call in each market, in reading order. Fixture page only
    # — a board row listing several markets answers the question several
    # times over, which is not what a row is for.
    by_market: list[CallOut] = []


class ValueOut(BaseModel):
    """Where the market price looks wrong, and how much to trust that.

    Not a prediction. A long price on an unlikely outcome is worth surfacing
    and is routinely the *least* likely thing on the fixture, which is why it
    lives here rather than anywhere a reader looks for the call.

    `thin_evidence` is the field that matters. A large positive expected
    value usually means the model lacks history for a competitor rather than
    that the market is wrong — the engine's own backtest returns -6.74%
    against bookmaker odds — so it must never be presented as free money.
    """

    market: str
    selection: str
    label: str
    model_probability: float
    market_implied_probability: float
    fair_price: float
    offered_price: float
    expected_value: float
    positive_value: bool
    thin_evidence: bool
    min_competitor_matches: int | None = None
    candidates_considered: int = 0
    rationale: str


class PredictionOut(BaseModel):
    match_id: int
    sport: str = "football"
    home_team: str
    away_team: str
    # What to show beside each name: a flag for a national side, initials for
    # a club we have no licensed crest for. None only for a sport this is not
    # populated on yet.
    home_badge: BadgeOut | None = None
    away_badge: BadgeOut | None = None
    match_date: datetime
    competition: str

    match_status: str = "scheduled"
    match_score: ScoreOut | None = None
    live: LiveOut | None = None
    ht_score: ScoreOut | None = None
    odds_1x2: OddsOut | None = None

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
    # None for a prediction served from its stored row, which never recorded it.
    btts_model_used: bool | None = None
    explanation: list[FeatureImpactOut] | None = None
    # Every market's call, ranked by how far the model sits above that
    # selection's own base rate. Absent for sports with no base-rate table.
    calls: CallsOut | None = None
    # The market comparison. Shown on the fixture page only — it is a
    # different subject from the prediction and crowded the board row.
    value: ValueOut | None = None
    # What actually happened, once there is something to report — see
    # `ActualStatsOut`/`MatchEventOut` above. Both absent for a fixture yet
    # to be played, not zero-filled.
    actual_stats: ActualStatsOut | None = None
    events: list[MatchEventOut] = []
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
