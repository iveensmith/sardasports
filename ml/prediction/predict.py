"""Prediction orchestration — pure functions, no database access.

Combines Elo, Poisson, and (optionally) trained XGBoost/LightGBM/Gradient-
Boosting models into one `EnsembleOutput` for a single fixture. Callers
(typically `app.services.prediction_service`) are responsible for fetching
match history, Elo ratings, and the active model artifacts from the database
and passing them in — that keeps this module trivially testable without a DB.
"""

from __future__ import annotations

import json
import math
import pickle
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import lightgbm as lgb
import numpy as np
import xgboost as xgb

from ml.competitions import fit_pool
from ml.elo.engine import EloEngine
from ml.ensemble import EnsembleInput, EnsembleOutput, combine
from ml.feature_engineering.features import (
    TeamHistoryIndex,
    build_match_features,
    build_team_history_index,
    feature_completeness,
)
from ml.poisson.model import PoissonModel
from ml.prediction.explain import explain_prediction
from ml.training.common import FEATURE_COLUMNS, one_hot_competition

# Weight given to the dedicated ML model vs. the Poisson-derived probability
# once a model has actually been trained (see ml/training/train_over_under.py
# and ml/training/train_btts.py). Falls back to pure Poisson if untrained.
DEDICATED_MODEL_WEIGHT = 0.6

# Real bookmaker lines offered for these two markets — see
# ml/training/train_corners.py and ml/training/train_cards.py's docstrings
# for why these specific values (checked against our own data, not picked
# arbitrarily), and each of those modules' own model_name_for_line for the
# model-name convention each line uses. A dedicated ML model is trained per
# line (a market genuinely is "Over X.5", not a single number the API
# interpolates), but the Poisson baseline is one fit per stat, reused
# across every line — prob_over_under(line=...) is a real calculation off
# the same fitted scoreline matrix regardless of which line is asked for.
CORNERS_LINES = [7.5, 8.5, 9.5]
CARDS_LINES = [2.5, 3.5, 4.5]
# Truncation bound for the reused PoissonModel's scoreline matrix (see
# _count_stat_matches) — corners/cards run meaningfully higher than goals
# per side, so goals' default max_goals=8 would clip real high-corner/
# high-card matches. Chosen generously above the observed per-side max in
# our own data (individual-team corners rarely exceed ~15, cards ~10).
CORNERS_MAX = 15
CARDS_MAX = 10

# Full-time goals: reuses the *same* PoissonModel already fit below (no
# separate fit needed — a scoreline matrix works for any line). Half-time
# goals gets its own, genuinely separate Poisson fit (see
# ml/training/train_ht_goals.py's docstring for why a half isn't just
# "half the full-time fit" statistically) and its own truncation bound —
# generous above the observed per-side max in our own data (7).
GOALS_LINES = [1.5, 2.5]
HT_GOALS_LINES = [0.5]
HT_GOALS_MAX = 10


def load_xgboost_artifact(
    model_path: str | Path, scaler_path: str | Path
) -> tuple[xgb.XGBClassifier, dict]:
    """Load a saved XGBoost model + its feature scaler parameters."""
    model = xgb.XGBClassifier()
    model.load_model(str(model_path))
    return model, _load_scaler(scaler_path)


def load_lightgbm_artifact(
    model_path: str | Path, scaler_path: str | Path
) -> tuple[lgb.Booster, dict]:
    """Load a saved LightGBM booster + its feature scaler parameters."""
    booster = lgb.Booster(model_file=str(model_path))
    return booster, _load_scaler(scaler_path)


def load_sklearn_pickle_artifact(
    model_path: str | Path, scaler_path: str | Path
) -> tuple[object, dict]:
    """Load a pickled scikit-learn model (e.g. GradientBoostingClassifier) + its scaler.

    Only ever used to load artifacts this codebase itself trained and wrote
    to `ml/models/` (see `ml/training/train_btts.py`) — never an
    externally-supplied file, since unpickling untrusted data is unsafe.
    """
    with open(model_path, "rb") as f:
        model = pickle.load(f)  # noqa: S301 - trusted, self-produced artifact only
    return model, _load_scaler(scaler_path)


def _load_scaler(scaler_path: str | Path) -> dict:
    return json.loads(Path(scaler_path).read_text(encoding="utf-8"))


def _scale_features(scaler_params: dict, features: dict) -> np.ndarray:
    values = np.array(
        [[features.get(col) if features.get(col) is not None else 0.0 for col in FEATURE_COLUMNS]]
    )
    mean = np.array(scaler_params["mean"])
    scale = np.array(scaler_params["scale"])
    return (values - mean) / scale


def _xgboost_probs(
    model: xgb.XGBClassifier | None,
    scaler_params: dict | None,
    features: dict,
) -> tuple[float, float, float] | None:
    if model is None or scaler_params is None:
        return None
    scaled = _scale_features(scaler_params, features)
    proba = model.predict_proba(scaled)[0]  # [P(home), P(draw), P(away)]
    return float(proba[0]), float(proba[1]), float(proba[2])


def _lightgbm_binary_prob(
    model: lgb.Booster | None, scaler_params: dict | None, features: dict
) -> float | None:
    if model is None or scaler_params is None:
        return None
    scaled = _scale_features(scaler_params, features)
    return float(model.predict(scaled)[0])


def _sklearn_binary_prob(model, scaler_params: dict | None, features: dict) -> float | None:
    if model is None or scaler_params is None:
        return None
    scaled = _scale_features(scaler_params, features)
    return float(model.predict_proba(scaled)[0][1])


def _blend_with_dedicated_model(poisson_prob: float, model_prob: float | None) -> float:
    """Weighted-average a Poisson-derived probability with a dedicated ML model's,
    if one was trained; otherwise return the Poisson probability unchanged."""
    if model_prob is None:
        return poisson_prob
    return DEDICATED_MODEL_WEIGHT * model_prob + (1 - DEDICATED_MODEL_WEIGHT) * poisson_prob


def _is_missing(value) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def _corners_value(m: dict, is_home: bool) -> float | None:
    return m.get("home_corners" if is_home else "away_corners")


def _cards_value(m: dict, is_home: bool) -> float | None:
    """Yellow + red for one side, or None if either component is missing —
    there's no single combined column in the source data (see Match model),
    unlike corners which is one column per side."""
    prefix = "home" if is_home else "away"
    yellow, red = m.get(f"{prefix}_yellow_cards"), m.get(f"{prefix}_red_cards")
    if _is_missing(yellow) or _is_missing(red):
        return None
    return yellow + red


def _ht_goals_value(m: dict, is_home: bool) -> float | None:
    return m.get("home_ht_goals" if is_home else "away_ht_goals")


def _count_stat_matches(history: list[dict], competition: str | None, value_fn) -> list[dict]:
    """Relabel `history` onto the `home_score`/`away_score` shape `PoissonModel`
    expects, using `value_fn(match, is_home)` (corners, summed cards, or
    half-time goals) instead of full-time goals. Corners, cards, and
    half-time goals are all, like full-time goals, non-negative per-match
    count stats with a genuine team-level "attack/defense strength"
    structure (a team that wins a lot of corners tends to keep winning them
    against weak defensive sides) — the same Poisson machinery legitimately
    applies, it's not a goals-only trick. Matches missing the stat (not
    every league/season records corners/cards/half-time score — see
    docs/architecture.md's "Corners and cards" and "Half-time goals"
    sections) are skipped, not zero-filled."""
    result = []
    # Pooled, not raw: internationals all share one fit (see ml.competitions).
    pool = fit_pool(competition)
    for m in history:
        if pool is not None and fit_pool(m.get("competition")) != pool:
            continue
        home_value, away_value = value_fn(m, True), value_fn(m, False)
        if _is_missing(home_value) or _is_missing(away_value):
            continue
        result.append(
            {
                "home_team": m["home_team"],
                "away_team": m["away_team"],
                "home_score": home_value,
                "away_score": away_value,
            }
        )
    return result


@dataclass
class SharedFit:
    """Work that depends on (history, competition) but not on the fixture.

    Every fixture in one competition sharing a history window produces
    byte-identical values for all five of these, and each one costs a full
    pass over history. Computing them per fixture is what made a board of 40
    take minutes; computing them once per competition makes it linear in
    competitions instead of fixtures.

    Built by `build_shared_fit` and passed to `predict_match(shared=...)`.
    """

    history_index: TeamHistoryIndex
    poisson: PoissonModel
    corners_poisson: PoissonModel | None
    cards_poisson: PoissonModel | None
    ht_goals_poisson: PoissonModel | None


def build_shared_fit(history: list[dict], competition: str | None) -> SharedFit:
    """Fit everything reusable across fixtures in one competition."""
    return build_shared_fits(history, [competition])[competition]


def build_shared_fits(
    history: list[dict], competitions: list[str | None]
) -> dict[str | None, SharedFit]:
    """Shared fits for several competitions over one history window.

    Two things make this much cheaper than calling `build_shared_fit` per
    competition, and both matter at board scale:

    * **The team history index is competition-independent.** It indexes every
      team's matches regardless of league, so it is built once for the window
      rather than once per competition — it was the single largest repeated
      cost, rebuilt in full for each league on the card.
    * **History is bucketed by competition once**, so each league's four
      Poisson fits scan only their own rows instead of re-filtering all
      ~64,000 every time. Four leagues previously meant sixteen full passes.

    The resulting fits are identical to the per-competition path's; only the
    number of passes over `history` changes.
    """
    index = build_team_history_index(history)

    # Bucket by fitting pool rather than by raw competition name, so every
    # international competition lands in one bucket. Domestic leagues are
    # unaffected: their pool key *is* their competition name.
    by_pool: dict[str | None, list[dict]] = {}
    for match in history:
        by_pool.setdefault(fit_pool(match.get("competition")), []).append(match)

    fits: dict[str | None, SharedFit] = {}
    # One SharedFit per pool, reused by every competition mapping to it — so a
    # card with three international competitions on it fits once, not thrice.
    by_pool_fit: dict[str | None, SharedFit] = {}
    for competition in competitions:
        pool = fit_pool(competition)
        if pool in by_pool_fit:
            fits[competition] = by_pool_fit[pool]
            continue
        # `None` means "no league scoping" and keeps the pre-multi-league
        # behaviour of fitting on the whole window.
        scoped = history if pool is None else by_pool.get(pool, [])
        poisson_matches = [
            {
                "home_team": m["home_team"],
                "away_team": m["away_team"],
                "home_score": m["home_score"],
                "away_score": m["away_score"],
            }
            for m in scoped
        ]
        by_pool_fit[pool] = fits[competition] = SharedFit(
            history_index=index,
            poisson=(PoissonModel().fit(poisson_matches) if poisson_matches else PoissonModel()),
            # Scoping already happened, so these pass `None` to avoid a
            # second, redundant filter over the same rows.
            corners_poisson=_fit_count_stat_poisson(scoped, None, _corners_value, CORNERS_MAX),
            cards_poisson=_fit_count_stat_poisson(scoped, None, _cards_value, CARDS_MAX),
            ht_goals_poisson=_fit_count_stat_poisson(scoped, None, _ht_goals_value, HT_GOALS_MAX),
        )
    return fits


def _fit_count_stat_poisson(
    history: list[dict], competition: str | None, value_fn, max_per_side: int
) -> PoissonModel | None:
    """Fit one `PoissonModel` for a count stat (corners/cards), reused across
    every line that stat offers — the fit itself doesn't depend on which
    line is being asked about, only `prob_over_under`'s line argument does.
    None if there's no history with that stat recorded for this competition
    at all — an honest "unavailable," not a guess."""
    stat_matches = _count_stat_matches(history, competition, value_fn)
    if not stat_matches:
        return None
    return PoissonModel(max_goals=max_per_side).fit(stat_matches)


def _build_market_lines(
    poisson_model: PoissonModel | None,
    home_team: str,
    away_team: str,
    lines: list[float],
    dedicated_probs: dict[float, float | None],
) -> list[dict]:
    """One entry per line: `{"line", "prob_over", "prob_under", "model_used"}`,
    each a real Poisson calculation (blended with that line's own dedicated
    model, if trained) off the one fitted `poisson_model` — or all-`None`
    entries when `poisson_model` is None (this competition has no data for
    the stat at all), reported as genuinely unavailable rather than guessed."""
    entries = []
    for line in lines:
        if poisson_model is None:
            entries.append(
                {"line": line, "prob_over": None, "prob_under": None, "model_used": False}
            )
            continue
        poisson_prob_over, _ = poisson_model.prob_over_under(home_team, away_team, line=line)
        model_prob = dedicated_probs.get(line)
        prob_over = _blend_with_dedicated_model(poisson_prob_over, model_prob)
        entries.append(
            {
                "line": line,
                "prob_over": round(prob_over * 100, 1),
                "prob_under": round((1 - prob_over) * 100, 1),
                "model_used": model_prob is not None,
            }
        )
    return entries


def predict_match(
    home_team: str,
    away_team: str,
    match_date: datetime,
    history: list[dict],
    elo_home: float,
    elo_away: float,
    elo_k_factor: float,
    elo_home_advantage: float,
    competition: str | None = None,
    xgb_model: xgb.XGBClassifier | None = None,
    xgb_scaler_params: dict | None = None,
    btts_model=None,
    btts_scaler_params: dict | None = None,
    goals_models: dict[float, tuple[lgb.Booster, dict]] | None = None,
    ht_goals_models: dict[float, tuple[lgb.Booster, dict]] | None = None,
    corners_models: dict[float, tuple[lgb.Booster, dict]] | None = None,
    cards_models: dict[float, tuple[object, dict]] | None = None,
    shared: SharedFit | None = None,
) -> EnsembleOutput:
    """Produce a full ensemble prediction for one fixture.

    `history` must contain only *completed* matches (any date range is fine —
    feature/Poisson/Elo helpers all filter internally); `elo_home`/`elo_away`
    are the ratings as of just before `match_date`. `competition` scopes the
    Poisson fit to matches from the *same* league — mixing leagues into one
    goal-scoring baseline would blend genuinely different scoring
    environments (e.g. a high-scoring Bundesliga season averaged in with a
    low-scoring Serie A one) into a single, wrong "league average" for both.
    `competition=None` falls back to the pre-multi-league behavior (fit on
    all given history) for callers that don't have it.

    `goals_models`/`ht_goals_models`/`corners_models`/`cards_models` each map
    an offered line (see `GOALS_LINES`/`HT_GOALS_LINES`/`CORNERS_LINES`/
    `CARDS_LINES`) to that line's own `(model, scaler_params)` — a missing
    line just means that specific dedicated model isn't incorporated (falls
    back to the Poisson baseline alone for that line), same as any other
    untrained dedicated model.

    `shared` lets a caller predicting several fixtures reuse the work that
    depends only on (history, competition) rather than on the fixture: the
    team history index and the four Poisson fits. Both are identical for
    every fixture in the same competition sharing a history window, and both
    cost a full pass over history — five passes over ~64k rows per fixture,
    which is what made a 40-fixture board take minutes. Omitted, it is
    computed here exactly as before, so single-fixture callers are unchanged.
    See `build_shared_fit`.
    """
    # --- Elo-implied probabilities --------------------------------------
    elo_engine = EloEngine(k_factor=elo_k_factor, home_advantage=elo_home_advantage)
    elo_engine.set_rating(home_team, elo_home)
    elo_engine.set_rating(away_team, elo_away)
    elo_probs = elo_engine.result_probabilities(home_team, away_team)

    # --- Poisson model ----------------------------------------------------
    # Internationals pool into one fit; leagues keep their own. See
    # ml.competitions for the measurements behind that.
    _pool = fit_pool(competition)
    poisson_matches = [
        {
            "home_team": m["home_team"],
            "away_team": m["away_team"],
            "home_score": m["home_score"],
            "away_score": m["away_score"],
        }
        for m in history
        if _pool is None or fit_pool(m.get("competition")) == _pool
    ]
    # With no completed history yet (a brand-new league, or literally the
    # first match ever ingested), there's nothing to fit attack/defense
    # strengths from — fall back to the model's default league-average
    # parameters (a neutral "average team vs. average team" estimate) rather
    # than crashing the whole prediction.
    poisson = (
        shared.poisson
        if shared is not None
        else (PoissonModel().fit(poisson_matches) if poisson_matches else PoissonModel())
    )
    poisson_probs = poisson.result_probabilities(home_team, away_team)
    expected_home, expected_away = poisson.expected_goals(home_team, away_team)
    top_scorelines = poisson.top_scorelines(home_team, away_team, n=5)
    poisson_prob_btts_yes, _ = poisson.prob_btts(home_team, away_team)

    # --- Corners/cards/half-time-goals Poisson baselines --------------------
    # Corners and cards are, like goals, non-negative per-match count stats
    # with a real team-level "strength" structure, so the same PoissonModel
    # machinery is reused (relabeled onto its home_score/away_score shape) —
    # see _fit_count_stat_poisson. Half-time goals gets the same treatment
    # even though it *is* goals, because a half isn't simply "half the
    # full-time fit" statistically (see ml/training/train_ht_goals.py's
    # docstring) — it's fit fresh from half-time scores specifically, not
    # derived from `poisson` above. None when this competition has no
    # history with that stat recorded at all (e.g. MLS for corners/cards/HT,
    # or historically Saudi Pro League before its half-time score was added
    # — see docs/architecture.md) — every line for that market then reports
    # unavailable, not a guess.
    if shared is not None:
        corners_poisson = shared.corners_poisson
        cards_poisson = shared.cards_poisson
        ht_goals_poisson = shared.ht_goals_poisson
    else:
        corners_poisson = _fit_count_stat_poisson(history, competition, _corners_value, CORNERS_MAX)
        cards_poisson = _fit_count_stat_poisson(history, competition, _cards_value, CARDS_MAX)
        ht_goals_poisson = _fit_count_stat_poisson(
            history, competition, _ht_goals_value, HT_GOALS_MAX
        )

    # --- Feature engineering + dedicated ML models -------------------------
    # Index built once (O(n)) and reused across build_match_features' ~9
    # internal lookups, instead of each one independently re-scanning
    # `history` (see ml.feature_engineering.features's module docstring).
    history_index = (
        shared.history_index if shared is not None else build_team_history_index(history)
    )
    features = build_match_features(
        home_team=home_team,
        away_team=away_team,
        match_date=match_date,
        history=history_index,
        elo_home=elo_home,
        elo_away=elo_away,
    )
    if competition is not None:
        features.update(one_hot_competition(competition))
    xgboost_probs = _xgboost_probs(xgb_model, xgb_scaler_params, features)
    btts_model_prob = _sklearn_binary_prob(btts_model, btts_scaler_params, features)
    completeness = feature_completeness(features)

    prob_btts_yes = _blend_with_dedicated_model(poisson_prob_btts_yes, btts_model_prob)

    # Each line gets its own dedicated model's prediction (if that line was
    # trained), blended with its market's one shared Poisson fit above.
    # Goals reuses the main `poisson` fit (a scoreline matrix answers any
    # line); the other three each have their own fit computed above.
    goals_dedicated_probs = {
        line: _lightgbm_binary_prob(model, scaler, features)
        for line, (model, scaler) in (goals_models or {}).items()
    }
    ht_goals_dedicated_probs = {
        line: _lightgbm_binary_prob(model, scaler, features)
        for line, (model, scaler) in (ht_goals_models or {}).items()
    }
    corners_dedicated_probs = {
        line: _lightgbm_binary_prob(model, scaler, features)
        for line, (model, scaler) in (corners_models or {}).items()
    }
    cards_dedicated_probs = {
        line: _sklearn_binary_prob(model, scaler, features)
        for line, (model, scaler) in (cards_models or {}).items()
    }
    goals_markets = _build_market_lines(
        poisson, home_team, away_team, GOALS_LINES, goals_dedicated_probs
    )
    ht_goals_markets = _build_market_lines(
        ht_goals_poisson, home_team, away_team, HT_GOALS_LINES, ht_goals_dedicated_probs
    )
    corners_markets = _build_market_lines(
        corners_poisson, home_team, away_team, CORNERS_LINES, corners_dedicated_probs
    )
    cards_markets = _build_market_lines(
        cards_poisson, home_team, away_team, CARDS_LINES, cards_dedicated_probs
    )

    ensemble_input = EnsembleInput(
        elo_probs=elo_probs,
        poisson_probs=poisson_probs,
        xgboost_probs=xgboost_probs,
        expected_goals_home=expected_home,
        expected_goals_away=expected_away,
        top_scorelines=top_scorelines,
        prob_btts_yes=prob_btts_yes,
        feature_completeness=completeness,
    )
    output = combine(ensemble_input)
    output.goals_markets = goals_markets
    output.ht_goals_markets = ht_goals_markets
    output.corners_markets = corners_markets
    output.cards_markets = cards_markets

    if xgboost_probs is not None:
        predicted_class_index = int(np.argmax(xgboost_probs))
        scaled = _scale_features(xgb_scaler_params, features)
        output.explanation = explain_prediction(xgb_model, scaled, predicted_class_index)

    return output
