"""Prediction service — orchestrates DB reads, the ML ensemble, and persistence.

This is the only layer that touches both the database and `ml.prediction`,
keeping the `ml/` package itself free of any SQLAlchemy dependency.
"""

from __future__ import annotations

import bisect
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from time import monotonic

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import EloHistory, Match, ModelVersion, Prediction, PredictionHistory, Team
from app.services.elo_service import get_team_elo_before
from app.utils.cache import get_cache
from app.utils.coalesce import CoalescingCache
from app.utils.config import get_settings
from app.utils.logging import get_logger
from ml.feature_engineering.features import build_team_history_index
from ml.prediction.predict import (
    CARDS_LINES,
    CORNERS_LINES,
    GOALS_LINES,
    HT_GOALS_LINES,
    build_shared_fit,
    build_shared_fits,
    load_lightgbm_artifact,
    load_sklearn_pickle_artifact,
    load_xgboost_artifact,
    predict_match,
)
from ml.prediction.predict_basketball import NBA_COMPETITION, TOTAL_POINTS_LINES, predict_game
from ml.prediction.predict_tennis import TOTAL_GAMES_LINES, build_surface_elo
from ml.prediction.predict_tennis import predict_match as predict_tennis_match
from ml.training.train_basketball_totals import (
    model_name_for_line as basketball_total_model_name_for_line,
)
from ml.training.train_basketball_winner import MODEL_NAME as BASKETBALL_WINNER_MODEL_NAME
from ml.training.train_btts import MODEL_NAME as BTTS_MODEL_NAME
from ml.training.train_cards import model_name_for_line as cards_model_name_for_line
from ml.training.train_corners import model_name_for_line as corners_model_name_for_line
from ml.training.train_ht_goals import model_name_for_line as ht_goals_model_name_for_line
from ml.training.train_match_result import MODEL_NAME as MATCH_RESULT_MODEL_NAME
from ml.training.train_over_under import model_name_for_line as goals_model_name_for_line
from ml.training.train_tennis_totals import (
    model_name_for_line as tennis_total_model_name_for_line,
)
from ml.training.train_tennis_winner import MODEL_NAME as TENNIS_WINNER_MODEL_NAME

logger = get_logger(__name__)

CACHE_TTL_SECONDS = 600


class MatchNotFoundError(Exception):
    pass


def _scaler_path_for(artifact_path: str) -> str:
    """`foo/bar_v1.json` -> `foo/bar_v1_scaler.json` (works for any artifact extension)."""
    path = Path(artifact_path)
    return str(path.with_name(f"{path.stem}_scaler.json"))


# Sized above the number of distinct artifacts in play, not arbitrarily: a
# football prediction alone touches 11 models (match result, BTTS, 2 goals
# lines, 1 half-time line, 3 corners, 3 cards) and basketball/tennis add 8
# more. At maxsize=4 every prediction evicted models it was about to need
# again, so the boosters were re-parsed from disk ~90 times per board.
@lru_cache(maxsize=32)
def _load_xgboost_cached(model_path: str, scaler_path: str):
    return load_xgboost_artifact(model_path, scaler_path)


@lru_cache(maxsize=32)
def _load_lightgbm_cached(model_path: str, scaler_path: str):
    return load_lightgbm_artifact(model_path, scaler_path)


@lru_cache(maxsize=32)
def _load_sklearn_pickle_cached(model_path: str, scaler_path: str):
    return load_sklearn_pickle_artifact(model_path, scaler_path)


#
# Which version is active changes only when something retrains, so resolving
# it is cached for a short window. Without this every football prediction
# issued eleven ModelVersion queries (one per model and per market line) —
# a 40-fixture board spent ~480 round trips re-answering the same question.
# The TTL is deliberately short so a retrain is picked up within seconds
# rather than requiring a restart.
_ACTIVE_MODEL_TTL_SECONDS = 30.0


@dataclass(frozen=True)
class ActiveVersion:
    """A detached-safe snapshot of the active `ModelVersion` row.

    Caching the ORM instance itself does not work: once the session that
    loaded it closes, every attribute access raises `DetachedInstanceError`.
    That is exactly what happened to `/model/roi-backtest`, which runs long
    enough to outlive the session the cache was populated from — it failed
    after twenty minutes of real work. Plain fields cannot detach.
    """

    id: int
    version: str
    artifact_path: str


_active_model_cache: dict[str, tuple[float, ActiveVersion | None]] = {}


def _active_version(session: Session, model_name: str) -> ActiveVersion | None:
    now = monotonic()
    hit = _active_model_cache.get(model_name)
    if hit is not None and now - hit[0] < _ACTIVE_MODEL_TTL_SECONDS:
        return hit[1]
    row = (
        session.query(ModelVersion.id, ModelVersion.version, ModelVersion.artifact_path)
        .filter(ModelVersion.model_name == model_name, ModelVersion.is_active.is_(True))
        .order_by(ModelVersion.trained_at.desc())
        .first()
    )
    snapshot = (
        None
        if row is None
        else ActiveVersion(id=row.id, version=row.version, artifact_path=row.artifact_path)
    )
    _active_model_cache[model_name] = (now, snapshot)
    return snapshot


def clear_active_model_cache() -> None:
    """Drop the cached lookups — called after a retrain so the new version
    is served immediately instead of waiting out the TTL."""
    _active_model_cache.clear()


def _get_active_model(session: Session, model_name: str, loader):
    """Fetch the active `ModelVersion` row for `model_name` and load its artifact.

    Returns (model, scaler_params, model_version) — all `None`/(None, None,
    version) if no model of that name has been trained yet, or if loading
    the artifact fails (logged, never raised — predictions must still work
    with the models that *are* available).
    """
    version = _active_version(session, model_name)
    if version is None:
        return None, None, None

    scaler_path = _scaler_path_for(version.artifact_path)
    try:
        model, scaler_params = loader(str(version.artifact_path), scaler_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to load model artifact %s: %s", version.artifact_path, exc)
        return None, None, version
    return model, scaler_params, version


def _get_active_model_uncached(session: Session, model_name: str, loader):
    """The original, query-every-time path. Retained for tests that assert
    on model-selection behaviour without the TTL in the way."""
    version = (
        session.query(ModelVersion)
        .filter(ModelVersion.model_name == model_name, ModelVersion.is_active.is_(True))
        .order_by(ModelVersion.trained_at.desc())
        .first()
    )
    if version is None:
        return None, None, None

    scaler_path = _scaler_path_for(version.artifact_path)
    try:
        model, scaler_params = loader(str(version.artifact_path), scaler_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to load model artifact %s: %s", version.artifact_path, exc)
        return None, None, version
    return model, scaler_params, version


def _load_full_history(session: Session, sport: str) -> tuple[list[datetime], list[dict]]:
    """Every completed match **in one sport**, ascending by date, with its dates alone.

    Loaded once and kept briefly; `_all_completed_history` cuts windows from it.

    The sport filter is load-bearing, not tidiness. This history is what the
    Poisson baselines are fitted on and what the form features are computed
    from, so letting basketball rows through would feed ~113-point
    "scorelines" into a goal model that truncates at 8 — silently wrecking
    every football prediction the moment a second sport was ingested.
    """
    # Columns, not entities. Hydrating 64,000 full ORM `Match` objects to
    # read a dozen attributes cost ~5 seconds per call and dominated the
    # board; a column query skips instance construction and identity-map
    # bookkeeping entirely for rows nothing ever mutates.
    rows = (
        session.query(
            Match.home_team_id,
            Match.away_team_id,
            Match.home_score,
            Match.away_score,
            Match.match_date,
            Match.competition,
            Match.neutral_venue,
            Match.home_ht_goals,
            Match.away_ht_goals,
            Match.home_corners,
            Match.away_corners,
            Match.home_yellow_cards,
            Match.away_yellow_cards,
            Match.home_red_cards,
            Match.away_red_cards,
            Match.surface,
            Match.home_games,
            Match.away_games,
        )
        .filter(
            Match.sport == sport,
            Match.status == "completed",
        )
        .order_by(Match.match_date.asc())
        .all()
    )
    id_to_name = dict(session.query(Team.id, Team.name).all())

    rows_out = [
        {
            "home_team": id_to_name[m.home_team_id],
            "away_team": id_to_name[m.away_team_id],
            "home_score": m.home_score,
            "away_score": m.away_score,
            "match_date": m.match_date,
            "competition": m.competition,
            # Tournament football is played on neutral ground, where the Elo
            # home-advantage offset shouldn't be credited — see
            # ml/elo/engine.py's `neutral_venue`.
            "neutral_venue": m.neutral_venue,
            # Not every match has these (see docs/architecture.md's "Corners
            # and cards" and "Half-time goals" sections) — left as
            # None/missing rather than defaulted, so ml.prediction.predict's
            # Poisson baselines correctly skip them instead of treating a
            # missing stat as zero.
            "home_ht_goals": m.home_ht_goals,
            "away_ht_goals": m.away_ht_goals,
            "home_corners": m.home_corners,
            "away_corners": m.away_corners,
            "home_yellow_cards": m.home_yellow_cards,
            "away_yellow_cards": m.away_yellow_cards,
            "home_red_cards": m.home_red_cards,
            "away_red_cards": m.away_red_cards,
            # Tennis-only; None elsewhere. Surface drives the per-surface
            # rating pools and games price the totals market.
            "surface": m.surface,
            "home_games": m.home_games,
            "away_games": m.away_games,
        }
        for m in rows
    ]
    return [r.match_date for r in rows], rows_out


class HistoryWindow(list):
    """A sport's completed matches before one day, shared by everything pricing that day.

    A list, so every consumer that takes a history takes this unchanged. It also carries the
    football Poisson fits built from it (`shared`), because those depend only on the window
    and the competition, not on the fixture, and they cost seconds to build.
    """

    def __init__(self, rows: list[dict]):
        super().__init__(rows)
        self.shared: dict = {}


# Loading a sport's whole history (118,000 football rows) takes about nine seconds, and every
# page that prices a match used to pay it again. A crawler visiting a few hundred match pages
# therefore kept the engine busy for an hour and starved everything else. The full history is
# now loaded once and kept for two minutes, windows cut from it are shared by every request
# for the same day, and simultaneous cold requests wait for one load instead of each making
# their own. Ten minutes is short enough that a new result is priced in soon after it arrives.
_HISTORY_TTL_SECONDS = 600
_FULL_HISTORY = CoalescingCache(
    _HISTORY_TTL_SECONDS, max_entries=4, max_concurrent=1, copy_results=False
)
_WINDOWS = CoalescingCache(
    _HISTORY_TTL_SECONDS, max_entries=16, max_concurrent=2, copy_results=False
)


def _all_completed_history(
    session: Session, before_date: datetime, sport: str = "football"
) -> HistoryWindow:
    """Prior completed matches **in one sport**, ascending by date.

    Cut at the start of `before_date`'s day, so every match on a day shares one window. That
    is the cut the board already used (the earliest kick-off of the day, which no earlier
    match on the same day precedes), so a match page now agrees with the board it came from.
    The window is read-only: it is shared between requests.

    The sport filter is load-bearing, not tidiness: basketball rows in a football history
    would feed ~113-point "scorelines" into a goal model that truncates at 8.
    """
    day = datetime.combine(before_date.date(), datetime.min.time())

    def build() -> HistoryWindow:
        dates, rows = _FULL_HISTORY.get_or_compute(
            sport, lambda: _load_full_history(session, sport)
        )
        return HistoryWindow(rows[: bisect.bisect_left(dates, day)])

    return _WINDOWS.get_or_compute((sport, day), build)


def _shared_fits_for(history: list[dict], competitions: list[str | None]) -> dict:
    """The football Poisson fits for several competitions, building only those not yet built."""
    if not isinstance(history, HistoryWindow):
        return build_shared_fits(history, competitions)
    missing = [c for c in competitions if c not in history.shared]
    if missing:
        history.shared.update(build_shared_fits(history, missing))
    return {c: history.shared[c] for c in competitions}


def _shared_fit_for(history: list[dict], competition: str | None):
    """The football Poisson fits for one competition over a history, built once per window."""
    if not isinstance(history, HistoryWindow):
        return build_shared_fit(history, competition)
    fit = history.shared.get(competition)
    if fit is None:
        fit = history.shared[competition] = build_shared_fit(history, competition)
    return fit


# Pricing a basketball or tennis match replays the sport's whole history into a per-team
# index (and, for tennis, a surface rating table). That is the expensive part, and a board
# prices dozens of matches against the same history, so the last one built is kept and
# reused for as long as the same history is being passed in.
_SPORT_STATE: dict = {}
_SPORT_STATE_LOCK = threading.Lock()


def _history_key(history) -> tuple:
    """Identifies a history list well enough to know whether a built index still fits it."""
    if not history:
        return (id(history), 0, None, None)
    return (id(history), len(history), history[0]["match_date"], history[-1]["match_date"])


def _indexed_history(history):
    """The history as a per-team index, built once per distinct history."""
    key = _history_key(history)
    with _SPORT_STATE_LOCK:
        if _SPORT_STATE.get("index_key") != key:
            _SPORT_STATE["index_key"] = key
            _SPORT_STATE["index"] = build_team_history_index(history)
        return _SPORT_STATE["index"]


def _tennis_ratings(history):
    """Overall and per-surface ratings replayed from the history, built once per history."""
    key = _history_key(history)
    with _SPORT_STATE_LOCK:
        if _SPORT_STATE.get("elo_key") != key:
            _SPORT_STATE["elo_key"] = key
            _SPORT_STATE["elo"] = build_surface_elo(history)
        return _SPORT_STATE["elo"]


def _predict_basketball(session: Session, match, home_team, away_team, history=None) -> dict:
    """The basketball branch of `predict_for_match`.

    Deliberately does not write to `predictions`/`prediction_history`: those
    tables are shaped around football's three-way outcome and goal markets
    (`home_win`/`draw`/`away_win`, `goals_markets`, ...), and persisting a
    basketball row into them would mean either fabricating a draw
    probability or leaving required columns empty. Basketball predictions are
    served and cached, not stored, until those tables are generalised too —
    which is a schema change worth doing deliberately, not as a side effect.
    """
    settings = get_settings()
    if history is None:
        history = _all_completed_history(session, before_date=match.match_date, sport=match.sport)

    winner_model, winner_scaler, model_version = _get_active_model(
        session, BASKETBALL_WINNER_MODEL_NAME, _load_lightgbm_cached
    )
    total_models = {}
    for line in TOTAL_POINTS_LINES:
        model, scaler, _v = _get_active_model(
            session, basketball_total_model_name_for_line(line), _load_lightgbm_cached
        )
        if model is not None:
            total_models[line] = (model, scaler)

    # Outside the NBA the trained totals do not apply; price totals statistically from
    # the league's own scoring record (see ml.prediction.predict_basketball).
    league_totals = None
    if match.competition != NBA_COMPETITION:
        count, mean, mean_square = (
            session.query(
                func.count(Match.id),
                func.avg(Match.home_score + Match.away_score),
                func.avg(
                    (Match.home_score + Match.away_score) * (Match.home_score + Match.away_score)
                ),
            )
            .filter(
                Match.sport == "basketball",
                Match.competition == match.competition,
                Match.status == "completed",
                Match.match_date < match.match_date,
            )
            .one()
        )
        std = 0.0 if not count else max(0.0, float(mean_square) - float(mean) ** 2) ** 0.5
        league_totals = {"n": count, "mean": float(mean or 0), "std": std}

    result = predict_game(
        home_team=home_team.name,
        away_team=away_team.name,
        match_date=match.match_date,
        history=_indexed_history(history),
        elo_home=get_team_elo_before(session, home_team.id, match.match_date),
        elo_away=get_team_elo_before(session, away_team.id, match.match_date),
        elo_home_advantage=settings.elo_home_advantage,
        winner_model=winner_model,
        winner_scaler_params=winner_scaler,
        total_models=total_models,
        league_totals=league_totals,
    )

    return {
        "match_id": match.id,
        "sport": match.sport,
        "home_team": result.home_team,
        "away_team": result.away_team,
        "match_date": match.match_date.isoformat(),
        "competition": match.competition,
        "home_win": result.home_win,
        "away_win": result.away_win,
        "expected_points_home": result.expected_points_home,
        "expected_points_away": result.expected_points_away,
        "expected_total_points": result.expected_total_points,
        "total_points_markets": [
            {
                "line": m.line,
                "prob_over": m.prob_over,
                "prob_under": m.prob_under,
                "model_used": m.model_used,
                "source": m.source,
            }
            for m in result.total_points_markets
        ],
        "confidence": result.confidence,
        "confidence_label": result.confidence_label,
        "model_version": model_version.version if model_version else None,
        "winner_model_used": result.winner_model_used,
        "thin_history": result.thin_history,
        "ratings_age_days": result.ratings_age_days,
        "stale_ratings": result.stale_ratings,
        "generated_at": datetime.now(UTC).isoformat(),
    }


def _predict_tennis(session: Session, match, home_player, away_player, history=None) -> dict:
    """The tennis branch of `predict_for_match`.

    Like the basketball branch, this serves and caches without writing to
    `predictions`/`prediction_history` — those tables are football-shaped
    (three-way outcome, goal markets) and a tennis row would have to invent
    a draw probability to fit.
    """
    if history is None:
        history = _all_completed_history(session, before_date=match.match_date, sport=match.sport)

    winner_model, winner_scaler, model_version = _get_active_model(
        session, TENNIS_WINNER_MODEL_NAME, _load_lightgbm_cached
    )
    total_models = {}
    for line in TOTAL_GAMES_LINES:
        model, scaler, _v = _get_active_model(
            session, tennis_total_model_name_for_line(line), _load_lightgbm_cached
        )
        if model is not None:
            total_models[line] = (model, scaler)

    result = predict_tennis_match(
        home_player=home_player.name,
        away_player=away_player.name,
        match_date=match.match_date,
        surface=match.surface,
        best_of=match.best_of,
        history=_indexed_history(history),
        elo=_tennis_ratings(history),
        winner_model=winner_model,
        winner_scaler_params=winner_scaler,
        total_models=total_models,
    )

    return {
        "match_id": match.id,
        "sport": match.sport,
        "home_player": result.home_player,
        "away_player": result.away_player,
        "match_date": match.match_date.isoformat(),
        "competition": match.competition,
        "surface": result.surface,
        "best_of": result.best_of,
        "home_win": result.home_win,
        "away_win": result.away_win,
        "elo_home": result.elo_home,
        "elo_away": result.elo_away,
        "elo_surface_home": result.elo_surface_home,
        "elo_surface_away": result.elo_surface_away,
        "expected_total_games": result.expected_total_games,
        "total_games_markets": [
            {
                "line": m.line,
                "prob_over": m.prob_over,
                "prob_under": m.prob_under,
                "model_used": m.model_used,
            }
            for m in result.total_games_markets
        ],
        "confidence": result.confidence,
        "confidence_label": result.confidence_label,
        "model_version": model_version.version if model_version else None,
        "winner_model_used": result.winner_model_used,
        "thin_history": result.thin_history,
        "generated_at": datetime.now(UTC).isoformat(),
    }


def predict_for_match(session: Session, match_id: int, history=None, shared=None) -> dict:
    """Compute (or return the cached) ensemble prediction for one match.

    `history` may be supplied by a caller predicting several matches that
    share a cut-off date. Loading it is O(all completed matches in the
    sport) — ~64k rows for football — so paying that once per *board*
    instead of once per *fixture* is the difference between a page that
    renders and one that times out. When omitted it is loaded as before, so
    single-match callers are unaffected.
    """
    cache = get_cache()
    cache_key = f"prediction:{match_id}"
    cached = cache.get_json(cache_key)
    if cached is not None:
        return cached

    match = session.get(Match, match_id)
    if match is None:
        raise MatchNotFoundError(f"Match {match_id} not found")

    home_team = session.get(Team, match.home_team_id)
    away_team = session.get(Team, match.away_team_id)

    # Basketball is a genuinely different prediction (two-way, no Poisson,
    # different markets), so it dispatches to its own pipeline rather than
    # threading `if sport ==` conditionals through the football one.
    if match.sport == "basketball":
        payload = _predict_basketball(session, match, home_team, away_team, history=history)
        cache.set_json(cache_key, payload, ttl_seconds=CACHE_TTL_SECONDS)
        return payload
    if match.sport == "tennis":
        payload = _predict_tennis(session, match, home_team, away_team, history=history)
        cache.set_json(cache_key, payload, ttl_seconds=CACHE_TTL_SECONDS)
        return payload

    # Once a match has kicked off, what was published is what is served; a
    # fresh compute would show a number the site never called.
    published = _published_payload(session, match, home_team, away_team)
    if published is not None:
        cache.set_json(cache_key, published, ttl_seconds=CACHE_TTL_SECONDS)
        return published

    settings = get_settings()
    if history is None:
        history = _all_completed_history(session, before_date=match.match_date, sport=match.sport)
    if shared is None:
        shared = _shared_fit_for(history, match.competition)
    elo_home = get_team_elo_before(session, home_team.id, match.match_date)
    elo_away = get_team_elo_before(session, away_team.id, match.match_date)

    xgb_model, xgb_scaler, model_version = _get_active_model(
        session, MATCH_RESULT_MODEL_NAME, _load_xgboost_cached
    )
    btts_model, btts_scaler, _btts_version = _get_active_model(
        session, BTTS_MODEL_NAME, _load_sklearn_pickle_cached
    )

    def _load_line_models(lines, model_name_for_line, loader):
        """One dedicated model per offered line — a line with no trained
        model simply isn't in the dict, and
        ml.prediction.predict.predict_match falls back to the Poisson
        baseline alone for that line, same as any other untrained dedicated
        model."""
        models = {}
        for line in lines:
            model, scaler, _version = _get_active_model(session, model_name_for_line(line), loader)
            if model is not None:
                models[line] = (model, scaler)
        return models

    goals_models = _load_line_models(GOALS_LINES, goals_model_name_for_line, _load_lightgbm_cached)
    ht_goals_models = _load_line_models(
        HT_GOALS_LINES, ht_goals_model_name_for_line, _load_lightgbm_cached
    )
    corners_models = _load_line_models(
        CORNERS_LINES, corners_model_name_for_line, _load_lightgbm_cached
    )
    cards_models = _load_line_models(
        CARDS_LINES, cards_model_name_for_line, _load_sklearn_pickle_cached
    )

    result = predict_match(
        home_team=home_team.name,
        away_team=away_team.name,
        match_date=match.match_date,
        history=history,
        elo_home=elo_home,
        elo_away=elo_away,
        elo_k_factor=settings.elo_k_factor,
        elo_home_advantage=settings.elo_home_advantage,
        competition=match.competition,
        xgb_model=xgb_model,
        xgb_scaler_params=xgb_scaler,
        btts_model=btts_model,
        btts_scaler_params=btts_scaler,
        goals_models=goals_models,
        ht_goals_models=ht_goals_models,
        corners_models=corners_models,
        cards_models=cards_models,
        shared=shared,
    )

    # Built before the row is stored: committing expires every ORM object in the
    # session, and reading names and dates back afterwards would be a round trip
    # per attribute (and one more place a lock could bite).
    payload = {
        "match_id": match.id,
        "home_team": home_team.name,
        "away_team": away_team.name,
        "match_date": match.match_date.isoformat(),
        "competition": match.competition,
        "home_win": result.home_win,
        "draw": result.draw,
        "away_win": result.away_win,
        "expected_goals_home": result.expected_goals_home,
        "expected_goals_away": result.expected_goals_away,
        "top_scorelines": result.top_scorelines,
        "btts_yes": result.prob_btts_yes,
        "btts_no": result.prob_btts_no,
        # Each a list of {"line", "prob_over", "prob_under", "model_used"} —
        # one entry per offered line (GOALS_LINES/HT_GOALS_LINES/
        # CORNERS_LINES/CARDS_LINES), with prob_over/prob_under None for a
        # competition with no data for that stat at all (see
        # ml.prediction.predict._build_market_lines).
        "goals_markets": result.goals_markets,
        "ht_goals_markets": result.ht_goals_markets,
        "corners_markets": result.corners_markets,
        "cards_markets": result.cards_markets,
        "confidence": result.confidence,
        "confidence_label": result.confidence_label,
        "model_version": model_version.version if model_version else None,
        "model_weights_used": result.model_weights_used,
        # Each estimator's own view before blending. The blend is the answer;
        # this is how the answer was reached, and where the three disagree is
        # real signal the blend necessarily averages away.
        "estimator_probs": result.estimator_probs,
        "btts_model_used": btts_model is not None,
        "explanation": result.explanation,
        "generated_at": datetime.now(UTC).isoformat(),
    }
    _persist_prediction(session, match, result, model_version)
    cache.set_json(cache_key, payload, ttl_seconds=CACHE_TTL_SECONDS)
    return payload


# SQLite allows one writer at a time, and a board stores a prediction per fixture, so
# several boards loading together used to fight over the write lock: each loser waited
# out the busy timeout and then lost its prediction. Taking this lock first makes the
# threads of this process queue in Python instead, where waiting is free; the busy
# timeout is then only ever spent on a writer from *another* process.
_WRITE_LOCK = threading.Lock()


def _has_kicked_off(match: Match) -> bool:
    """True once the match is under way or played: its stored call is final.

    `match_date` is naive UTC, like `Prediction.created_at` (the database's own
    clock), which is what makes "stored before kick-off" a plain comparison.
    """
    if match.status == "completed":
        return True
    return match.match_date <= datetime.now(UTC).replace(tzinfo=None)


def _published_payload(
    session: Session, match: Match, home_team: Team, away_team: Team
) -> dict | None:
    """The prediction as it was published, for a match that has kicked off.

    None when there is no stored row (a played match nobody predicted yet,
    which then gets a backtest row computed and persisted as before).

    Rebuilt from the row alone, so the fields the row never recorded are left
    empty rather than recomputed: `estimator_probs`, `model_weights_used`,
    `explanation`, and whether the BTTS model was used. Recomputing them would
    describe the engine as it is now, next to numbers it produced earlier.
    """
    stored = session.query(Prediction).filter(Prediction.match_id == match.id).one_or_none()
    if stored is None or not _has_kicked_off(match):
        return None

    version = (
        session.get(ModelVersion, stored.model_version_id) if stored.model_version_id else None
    )
    generated = stored.updated_at or stored.created_at
    return {
        "match_id": match.id,
        "home_team": home_team.name,
        "away_team": away_team.name,
        "match_date": match.match_date.isoformat(),
        "competition": match.competition,
        # Stored as 0-1 fractions; the payload speaks percentages.
        "home_win": round(stored.prob_home * 100, 6),
        "draw": round(stored.prob_draw * 100, 6),
        "away_win": round(stored.prob_away * 100, 6),
        "expected_goals_home": stored.expected_goals_home,
        "expected_goals_away": stored.expected_goals_away,
        "top_scorelines": stored.top_scorelines or [],
        "btts_yes": round(stored.prob_btts_yes * 100, 6),
        "btts_no": round(stored.prob_btts_no * 100, 6),
        "goals_markets": stored.goals_markets or [],
        "ht_goals_markets": stored.ht_goals_markets or [],
        "corners_markets": stored.corners_markets or [],
        "cards_markets": stored.cards_markets or [],
        "confidence": stored.confidence,
        "confidence_label": stored.confidence_label,
        "model_version": version.version if version else None,
        "model_weights_used": {},
        "estimator_probs": {},
        "btts_model_used": None,
        "explanation": None,
        "generated_at": generated.replace(tzinfo=UTC).isoformat(),
    }


def _persist_prediction(session: Session, match: Match, result, model_version) -> None:
    common_fields = dict(
        prob_home=result.home_win / 100,
        prob_draw=result.draw / 100,
        prob_away=result.away_win / 100,
        expected_goals_home=result.expected_goals_home,
        expected_goals_away=result.expected_goals_away,
        top_scorelines=result.top_scorelines,
        prob_btts_yes=result.prob_btts_yes / 100,
        prob_btts_no=result.prob_btts_no / 100,
        # Stored as the same percentage-scale dicts the API returns (unlike
        # the fields above, which are stored as 0-1 fractions) — each line's
        # own prob_over/prob_under can be None, so there's no single
        # "divide by 100" that works uniformly across the list.
        goals_markets=result.goals_markets,
        ht_goals_markets=result.ht_goals_markets,
        corners_markets=result.corners_markets,
        cards_markets=result.cards_markets,
        confidence=result.confidence,
        confidence_label=result.confidence_label,
        model_version_id=model_version.id if model_version else None,
    )

    # Storing is a side effect of predicting, not the point of it: if it fails the
    # prediction that was just computed is still correct and is still returned, and
    # the row is simply stored by the next request. Failing the read because the
    # bookkeeping could not be written is what turned lock contention into rows
    # with no prediction.
    with _WRITE_LOCK:
        try:
            existing = (
                session.query(Prediction).filter(Prediction.match_id == match.id).one_or_none()
            )
            if existing is None:
                session.add(Prediction(match_id=match.id, **common_fields))
            elif _has_kicked_off(match):
                # The track record grades this row and calls it live when it was
                # stored before kick-off. Overwriting it afterwards would leave
                # `created_at` untouched while changing what was predicted, so a
                # recompute (a retrain, say) could quietly replace a published call
                # and still count as one. Once the match is under way the row is
                # final, and the history table gets no snapshot either: it is a
                # timeline of what was produced before the game, not of what the
                # engine says in hindsight.
                return
            else:
                for key, value in common_fields.items():
                    setattr(existing, key, value)
                # Stamped explicitly. `onupdate` only fires when a column's value
                # changed, and a recomputed-but-identical prediction changes none,
                # which would leave the row looking older than the data it was
                # just checked against and force a recompute on every view.
                existing.updated_at = func.now()

            session.add(
                PredictionHistory(
                    match_id=match.id,
                    actual_home_goals=match.home_score,
                    actual_away_goals=match.away_score,
                    **common_fields,
                )
            )
            session.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not store the prediction for match %s: %s", match.id, exc)
            session.rollback()


def get_prediction_timeline(session: Session, match_id: int) -> list[PredictionHistory]:
    return (
        session.query(PredictionHistory)
        .filter(PredictionHistory.match_id == match_id)
        .order_by(PredictionHistory.created_at.asc())
        .all()
    )


def _inputs_watermark(session: Session, sport: str, cutoff: datetime) -> datetime | None:
    """The newest moment anything a prediction is computed from changed.

    A stored prediction written after this moment was computed from the data as it
    still is. The three inputs that can move under it:

    - a completed match before the cut-off was added or corrected (form, Poisson
      baselines and Elo all read the history before kick-off);
    - Elo was rebuilt (`EloHistory` is deleted and rewritten, so its newest
      `created_at` is the rebuild);
    - a model was registered or retrained.

    Deliberately conservative: it can say "changed" when nothing a particular
    prediction reads did, which costs one recompute, and never the reverse.
    """
    stamps = (
        session.query(func.max(Match.updated_at))
        .filter(Match.sport == sport, Match.status == "completed", Match.match_date < cutoff)
        .scalar(),
        session.query(func.max(EloHistory.created_at)).scalar(),
        session.query(func.max(ModelVersion.created_at))
        .filter(ModelVersion.is_active.is_(True))
        .scalar(),
    )
    return max((stamp for stamp in stamps if stamp is not None), default=None)


def _stored_is_current(
    stored: Prediction,
    match: Match,
    watermark: datetime | None,
    active: ActiveVersion | None,
) -> bool:
    """Would recomputing this match today reproduce the stored row?

    The row must come from the model that is active now, be newer than every input
    change (`_inputs_watermark`), and be newer than the last edit to the fixture
    itself — its teams, competition or kick-off can change.

    A match that has kicked off is the exception: its stored row is final (see
    `_persist_prediction`), so it is current whatever has happened since. A result
    arriving, a retrain or a data refresh must not make it look stale, or every view
    of a played match would go on recomputing a number that is never written back.
    """
    if _has_kicked_off(match):
        return True
    if stored.updated_at is None:
        return False
    if stored.model_version_id != (active.id if active else None):
        return False
    if watermark is not None and stored.updated_at < watermark:
        return False
    return not (match.updated_at is not None and stored.updated_at < match.updated_at)


def _stored_payload(
    session: Session, stored: Prediction, match: Match, active: ActiveVersion | None
) -> dict:
    """A stored row, back in the shape `predict_for_match` returns.

    Only what was stored is returned. The row has no per-estimator split, model
    weights or explanation (they are not columns), so those keys are absent rather
    than guessed: a caller that needs them must not ask for stored predictions.
    Percentages are stored as 0-1 fractions of values rounded to one decimal place,
    so scaling back and rounding to one place restores the exact original numbers.
    """
    home_team = session.get(Team, match.home_team_id)
    away_team = session.get(Team, match.away_team_id)

    def pct(fraction: float) -> float:
        return round(fraction * 100, 1)

    return {
        "match_id": match.id,
        "home_team": home_team.name,
        "away_team": away_team.name,
        "match_date": match.match_date.isoformat(),
        "competition": match.competition,
        "home_win": pct(stored.prob_home),
        "draw": pct(stored.prob_draw),
        "away_win": pct(stored.prob_away),
        "expected_goals_home": stored.expected_goals_home,
        "expected_goals_away": stored.expected_goals_away,
        "top_scorelines": stored.top_scorelines or [],
        "btts_yes": pct(stored.prob_btts_yes),
        "btts_no": pct(stored.prob_btts_no),
        "goals_markets": stored.goals_markets or [],
        "ht_goals_markets": stored.ht_goals_markets or [],
        "corners_markets": stored.corners_markets or [],
        "cards_markets": stored.cards_markets or [],
        "confidence": stored.confidence,
        "confidence_label": stored.confidence_label,
        "model_version": active.version if active else None,
        "generated_at": stored.updated_at.isoformat(),
    }


def _serve_stored(
    session: Session,
    group: list[Match],
    cutoff: datetime,
    results: dict[int, dict | None],
) -> list[Match]:
    """Fill `results` from stored predictions that are still current; return the rest.

    This is the cheap path a board should take almost every time: one query for the
    rows, three `max()` lookups for the watermark, and no writes. Only fixtures with
    no row, or a row `_stored_is_current` rejects, go on to be recomputed.
    """
    stored_by_match = {
        row.match_id: row
        for row in session.query(Prediction).filter(Prediction.match_id.in_([m.id for m in group]))
    }
    if not stored_by_match:
        return group

    watermark = _inputs_watermark(session, group[0].sport, cutoff)
    active = _active_version(session, MATCH_RESULT_MODEL_NAME)

    pending: list[Match] = []
    for match in group:
        stored = stored_by_match.get(match.id)
        if stored is not None and _stored_is_current(stored, match, watermark, active):
            results[match.id] = _stored_payload(session, stored, match, active)
        else:
            pending.append(match)
    return pending


def predict_for_matches(
    session: Session, matches: list[Match], *, allow_stored: bool = False
) -> list[dict | None]:
    """Predict several matches, loading each sport's history exactly once.

    `predict_for_match` loads every completed match in the sport to build
    its Poisson baselines and form features. That is fine for one fixture
    and quadratic-feeling for a board: a 40-fixture card was re-reading
    ~64,000 football rows forty times, which measured at 27-40 seconds per
    prediction under concurrency and made the page unusable.

    Grouping by (sport, cut-off date) is safe because the leakage rule is
    "matches strictly before this one". Fixtures sharing a date share an
    identical history window, so one load serves them all — the predictions
    are byte-for-byte what the per-match path produces, just without
    re-reading the table each time.

    With `allow_stored=True` a football fixture whose stored prediction is still
    current is served from that row instead of being recomputed — see
    `_stored_is_current` for what "current" means. The payload then carries the
    headline numbers and markets but not the per-estimator split or explanation
    (those are not stored), so only callers that read nothing beyond the markets
    and confidence should opt in. The default keeps the old behaviour.

    A fixture the engine cannot price yields None rather than failing the
    batch: one bad row is a gap in a list, not an outage.
    """
    by_window: dict[tuple[str, object], list[Match]] = {}
    for match in matches:
        by_window.setdefault((match.sport, match.match_date.date()), []).append(match)

    results: dict[int, dict | None] = {}
    for (sport, _day), group in by_window.items():
        # The window must cover every fixture in the group, so use the
        # earliest kick-off: anything later would leak a same-day result
        # into a fixture that kicks off before it. It is taken over the whole
        # group even when only some fixtures still need computing, so a
        # fixture's prediction does not depend on how many of its neighbours
        # happened to be stored already.
        cutoff = min(m.match_date for m in group)

        pending = group
        if allow_stored and sport == "football":
            try:
                pending = _serve_stored(session, group, cutoff, results)
            except Exception as exc:  # noqa: BLE001
                # The stored path is an optimisation. If it cannot run, compute.
                logger.warning("Reading stored predictions failed for %s: %s", _day, exc)
                session.rollback()
                pending = [m for m in group if m.id not in results]
            if not pending:
                continue

        try:
            history = _all_completed_history(session, before_date=cutoff, sport=sport)

            # The reusable fits depend on (history, competition), not on the
            # fixture, so they're built once for the whole group — sharing
            # the one history index across every league on the card.
            # Football only: the basketball and tennis paths have no Poisson
            # baseline and build their far cheaper state internally.
            shared_by_competition: dict[str | None, object] = {}
            if sport == "football":
                shared_by_competition = _shared_fits_for(
                    history, sorted({m.competition for m in pending}, key=str)
                )
        except Exception as exc:  # noqa: BLE001
            # A transient failure here (a concurrent writer holding SQLite's
            # single write lock, say) would otherwise take out this whole
            # group rather than the one fixture that hit it — worse than the
            # per-match case below, since nothing in the group ever got a
            # chance to run. Roll back for the same reason as the per-match
            # branch: a failed statement leaves the session unable to run
            # another one until it does.
            logger.warning(
                "Batch prediction setup failed for %s fixtures on %s: %s", sport, _day, exc
            )
            session.rollback()
            for match in pending:
                results[match.id] = None
            continue

        for match in pending:
            try:
                results[match.id] = predict_for_match(
                    session,
                    match.id,
                    history=history,
                    shared=shared_by_competition.get(match.competition),
                )
            except Exception as exc:  # noqa: BLE001
                # Roll back before the next match, not just log and move on:
                # a failed statement (a lock timeout, say) leaves the session
                # unable to run another one until it does, which would
                # otherwise fail every match after the first one in this
                # group too — cascading one bad fixture into an empty board.
                logger.warning("Batch prediction failed for match %s: %s", match.id, exc)
                session.rollback()
                results[match.id] = None

    return [results.get(m.id) for m in matches]
