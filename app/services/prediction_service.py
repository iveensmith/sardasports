"""Prediction service — orchestrates DB reads, the ML ensemble, and persistence.

This is the only layer that touches both the database and `ml.prediction`,
keeping the `ml/` package itself free of any SQLAlchemy dependency.
"""

from __future__ import annotations

from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from time import monotonic

from sqlalchemy.orm import Session

from app.models import Match, ModelVersion, Prediction, PredictionHistory, Team
from app.services.elo_service import get_team_elo_before
from app.utils.cache import get_cache
from app.utils.config import get_settings
from app.utils.logging import get_logger
from ml.prediction.predict import (
    CARDS_LINES,
    CORNERS_LINES,
    GOALS_LINES,
    HT_GOALS_LINES,
    build_shared_fits,
    load_lightgbm_artifact,
    load_sklearn_pickle_artifact,
    load_xgboost_artifact,
    predict_match,
)
from ml.prediction.predict_basketball import TOTAL_POINTS_LINES, predict_game
from ml.prediction.predict_tennis import TOTAL_GAMES_LINES
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
_active_model_cache: dict[str, tuple[float, object]] = {}


def _active_version(session: Session, model_name: str):
    now = monotonic()
    hit = _active_model_cache.get(model_name)
    if hit is not None and now - hit[0] < _ACTIVE_MODEL_TTL_SECONDS:
        return hit[1]
    version = (
        session.query(ModelVersion)
        .filter(ModelVersion.model_name == model_name, ModelVersion.is_active.is_(True))
        .order_by(ModelVersion.trained_at.desc())
        .first()
    )
    _active_model_cache[model_name] = (now, version)
    return version


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


def _all_completed_history(
    session: Session, before_date: datetime, sport: str = "football"
) -> list[dict]:
    """Prior completed matches **in one sport**, ascending by date.

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
            Match.match_date < before_date,
        )
        .order_by(Match.match_date.asc())
        .all()
    )
    id_to_name = dict(session.query(Team.id, Team.name).all())

    return [
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

    result = predict_game(
        home_team=home_team.name,
        away_team=away_team.name,
        match_date=match.match_date,
        history=history,
        elo_home=get_team_elo_before(session, home_team.id, match.match_date),
        elo_away=get_team_elo_before(session, away_team.id, match.match_date),
        elo_home_advantage=settings.elo_home_advantage,
        winner_model=winner_model,
        winner_scaler_params=winner_scaler,
        total_models=total_models,
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
            }
            for m in result.total_points_markets
        ],
        "confidence": result.confidence,
        "confidence_label": result.confidence_label,
        "model_version": model_version.version if model_version else None,
        "winner_model_used": result.winner_model_used,
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
        history=history,
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

    settings = get_settings()
    if history is None:
        history = _all_completed_history(session, before_date=match.match_date, sport=match.sport)
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

    _persist_prediction(session, match, result, model_version)

    payload = {
        "match_id": match.id,
        "home_team": home_team.name,
        "away_team": away_team.name,
        "match_date": match.match_date.isoformat(),
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
        "btts_model_used": btts_model is not None,
        "explanation": result.explanation,
        "generated_at": datetime.now(UTC).isoformat(),
    }
    cache.set_json(cache_key, payload, ttl_seconds=CACHE_TTL_SECONDS)
    return payload


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

    existing = session.query(Prediction).filter(Prediction.match_id == match.id).one_or_none()
    if existing is None:
        session.add(Prediction(match_id=match.id, **common_fields))
    else:
        for key, value in common_fields.items():
            setattr(existing, key, value)

    session.add(
        PredictionHistory(
            match_id=match.id,
            actual_home_goals=match.home_score,
            actual_away_goals=match.away_score,
            **common_fields,
        )
    )
    session.commit()


def get_prediction_timeline(session: Session, match_id: int) -> list[PredictionHistory]:
    return (
        session.query(PredictionHistory)
        .filter(PredictionHistory.match_id == match_id)
        .order_by(PredictionHistory.created_at.asc())
        .all()
    )


def predict_for_matches(session: Session, matches: list[Match]) -> list[dict | None]:
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
        # into a fixture that kicks off before it.
        cutoff = min(m.match_date for m in group)
        history = _all_completed_history(session, before_date=cutoff, sport=sport)

        # The reusable fits depend on (history, competition), not on the
        # fixture, so they're built once for the whole group — sharing the
        # one history index across every league on the card. Football only:
        # the basketball and tennis paths have no Poisson baseline and build
        # their far cheaper state internally.
        shared_by_competition: dict[str | None, object] = {}
        if sport == "football":
            shared_by_competition = build_shared_fits(
                history, sorted({m.competition for m in group}, key=str)
            )

        for match in group:
            try:
                results[match.id] = predict_for_match(
                    session,
                    match.id,
                    history=history,
                    shared=shared_by_competition.get(match.competition),
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Batch prediction failed for match %s: %s", match.id, exc)
                results[match.id] = None

    return [results.get(m.id) for m in matches]
