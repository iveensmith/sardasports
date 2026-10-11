"""Tennis markets beyond the winner and total games: sets, handicaps, first set, tiebreaks.

Every market is derived from the one number the engine already states for a match, the
probability that the home slot's player wins, and what has been fitted from 80,000 real
set-by-set results about how matches break down around that number
(`scripts/fit_tennis_markets.py` writes `ml/tennis_market_params.json`, and reports the
out-of-sample calibration). Because the set-score distribution is built *conditional on who
wins*, it always agrees with the moneyline: the home player's set scores sum to exactly the
match win probability.

The home and away slots are an arbitrary ordering (see `scripts/fetch_tennis.py`), so
everything is worked out from the favourite's point of view and mapped back.

Total games (over/under) stays with its trained model in `predict_tennis`; this module does
not duplicate it.
"""

from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

PARAMS_PATH = Path(__file__).with_name("tennis_market_params.json")
_OVERRIDE: dict | None = None

SURFACES = ("Hard", "Clay", "Grass")


def set_params(params: dict | None) -> None:
    """Use `params` instead of the file (evaluation), or None to go back to the file."""
    global _OVERRIDE
    _OVERRIDE = params
    load_params.cache_clear()


@lru_cache(maxsize=1)
def load_params() -> dict:
    if _OVERRIDE is not None:
        return _OVERRIDE
    try:
        return json.loads(PARAMS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _logit(p: float) -> float:
    p = min(max(p, 1e-4), 1 - 1e-4)
    return math.log(p / (1 - p))


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _normal_cdf(x: float) -> float:
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def _clip(p: float) -> float:
    return min(max(p, 0.01), 0.99)


def _linear(model: dict, row: list[float]) -> float:
    return model["intercept"] + sum(c * x for c, x in zip(model["coef"], row, strict=True))


def _softmax(logits: list[float]) -> list[float]:
    top = max(logits)
    exps = [math.exp(v - top) for v in logits]
    total = sum(exps)
    return [v / total for v in exps]


def _pct(p: float) -> float:
    return round(p * 100.0, 1)


def _features(z: float, surface: str | None, tour: str | None, best_of: int) -> list[float]:
    return [
        z,
        1.0 if surface == "Hard" else 0.0,
        1.0 if surface == "Clay" else 0.0,
        1.0 if surface == "Grass" else 0.0,
        1.0 if tour == "ATP" else 0.0,
        1.0 if best_of == 5 else 0.0,
    ]


def _split(model: dict, z: float) -> dict[int, float]:
    """P(loser takes k sets | this player wins), best of five."""
    logits = [i + c[0] * z for i, c in zip(model["intercept"], model["coef"], strict=True)]
    probs = _softmax(logits)
    return {int(k): p for k, p in zip(model["classes"], probs, strict=True)}


# ---------------------------------------------------------------- pricing


def set_score_distribution(p_home: float, best_of: int, params: dict | None = None) -> dict:
    """{(home_sets, away_sets): probability}, summing to 1, with the home total equal to p_home."""
    params = params or load_params()
    p_fav = max(p_home, 1.0 - p_home)
    home_is_fav = p_home >= 0.5
    z = _logit(p_fav)
    needed = best_of // 2 + 1
    fav_wins: dict[int, float]
    dog_wins: dict[int, float]
    if best_of == 3:
        a = _sigmoid(_linear(params["bo3_fav_straight"], [z]))
        b = _sigmoid(_linear(params["bo3_dog_straight"], [z]))
        fav_wins = {0: a, 1: 1.0 - a}
        dog_wins = {0: b, 1: 1.0 - b}
    else:
        fav_wins = _split(params["bo5_fav_split"], z)
        dog_wins = _split(params["bo5_dog_split"], z)
    out: dict[tuple[int, int], float] = {}
    for lost, share in fav_wins.items():
        key = (needed, lost) if home_is_fav else (lost, needed)
        out[key] = out.get(key, 0.0) + p_fav * share
    for lost, share in dog_wins.items():
        key = (lost, needed) if home_is_fav else (needed, lost)
        out[key] = out.get(key, 0.0) + (1.0 - p_fav) * share
    return out


def price_match(
    p_home: float, best_of: int | None, surface: str | None, tour: str | None
) -> list[dict]:
    """Every extra market for one match, or [] when the format is unknown or nothing is fitted."""
    params = load_params()
    if best_of not in (3, 5) or not params or "set1_fav" not in params:
        return []
    p_home = _clip(p_home)
    home_is_fav = p_home >= 0.5
    p_fav = max(p_home, 1.0 - p_home)
    z = _logit(p_fav)
    markets: list[dict] = []

    def add(group, name, market_id, kind, **body):
        markets.append(
            {"id": market_id, "group": group, "name": name, "type": kind, "source": "statistical"}
            | body
        )

    # --- set betting and what follows from it
    dist = set_score_distribution(p_home, best_of, params)
    needed = best_of // 2 + 1
    home_wins = sorted([k for k in dist if k[0] == needed], key=lambda k: k[1])
    away_wins = sorted([k for k in dist if k[1] == needed], key=lambda k: k[0])
    order = home_wins + away_wins
    add(
        "Sets",
        "Correct score (sets)",
        "set_score",
        "correct_score",
        scores=[
            {
                "score": f"{h}-{a}",
                "home_sets": h,
                "away_sets": a,
                "prob": _pct(dist[(h, a)]),
            }
            for h, a in order
        ],
    )

    played_prob: dict[int, float] = {}
    for (h, a), prob in dist.items():
        played_prob[h + a] = played_prob.get(h + a, 0.0) + prob
    total_lines = [2.5] if best_of == 3 else [3.5, 4.5]
    add(
        "Sets",
        "Total sets",
        "total_sets",
        "over_under",
        lines=[
            {
                "line": line,
                "prob_over": _pct(sum(p for n, p in played_prob.items() if n > line)),
                "prob_under": _pct(sum(p for n, p in played_prob.items() if n < line)),
            }
            for line in total_lines
        ],
    )

    def home_margin_covers(handicap: float) -> float:
        """P(home sets - away sets + handicap > 0)."""
        return sum(p for (h, a), p in dist.items() if h - a + handicap > 0)

    set_lines = [-1.5, 1.5] if best_of == 3 else [-2.5, -1.5, 1.5, 2.5]
    add(
        "Sets",
        "Set handicap",
        "set_handicap",
        "handicap",
        lines=[
            {
                "line": line,
                "prob_home": _pct(home_margin_covers(line)),
                "prob_away": _pct(1.0 - home_margin_covers(line)),
            }
            for line in set_lines
        ],
    )

    home_takes_a_set = 1.0 - sum(p for (h, a), p in dist.items() if h == 0)
    away_takes_a_set = 1.0 - sum(p for (h, a), p in dist.items() if a == 0)
    add(
        "Sets",
        "Home player to win at least one set",
        "home_to_win_a_set",
        "yes_no",
        yes=_pct(home_takes_a_set),
        no=_pct(1.0 - home_takes_a_set),
    )
    add(
        "Sets",
        "Away player to win at least one set",
        "away_to_win_a_set",
        "yes_no",
        yes=_pct(away_takes_a_set),
        no=_pct(1.0 - away_takes_a_set),
    )

    # --- first set
    p_set1_fav = _clip(_sigmoid(_linear(params["set1_fav"], [z])))
    p_set1_home = p_set1_fav if home_is_fav else 1.0 - p_set1_fav
    add(
        "First set",
        "First set winner",
        "first_set_winner",
        "two_way",
        home=_pct(p_set1_home),
        away=_pct(1.0 - p_set1_home),
    )
    row = _features(z, surface, tour, best_of)
    over_9 = _clip(_sigmoid(_linear(params["set1_over_9_5"], row)))
    over_10 = _clip(_sigmoid(_linear(params["set1_over_10_5"], row)))
    add(
        "First set",
        "First set total games",
        "first_set_total_games",
        "over_under",
        lines=[
            {"line": 9.5, "prob_over": _pct(over_9), "prob_under": _pct(1.0 - over_9)},
            {"line": 10.5, "prob_over": _pct(over_10), "prob_under": _pct(1.0 - over_10)},
        ],
    )

    # --- games
    margin_params = params["margin"][f"bo{best_of}"]
    mu = margin_params["slope"] * _logit(p_home)
    sd = max(2.0, margin_params["sd"])
    step = float(max(1, round(0.45 * sd)))
    centre = -(math.floor(mu) + 0.5)
    lines = []
    for k in (-1, 0, 1):
        h = round(centre + k * step, 1)
        covers = _clip(_normal_cdf((mu + h) / sd))
        lines.append({"line": h, "prob_home": _pct(covers), "prob_away": _pct(1.0 - covers)})
    add(
        "Games",
        "Game handicap",
        "game_handicap",
        "handicap",
        expected_margin=round(mu, 1),
        lines=lines,
    )

    tiebreak = _clip(_sigmoid(_linear(params["tiebreak"], row)))
    add(
        "Match",
        "Tiebreak in the match",
        "tiebreak",
        "yes_no",
        yes=_pct(tiebreak),
        no=_pct(1.0 - tiebreak),
    )
    return markets


# ---------------------------------------------------------------- grading


def _is_tiebreak(pair) -> bool:
    return set(pair) == {6, 7}


def grade_market(
    market: dict, sets: list[list[int]] | None, home_sets: int | None, away_sets: int | None
) -> dict | None:
    """What happened for one priced market, or None when the match has no detail to grade by."""
    market_id = market["id"]
    if home_sets is None or away_sets is None:
        return None
    if market_id in ("first_set_winner", "first_set_total_games", "tiebreak", "game_handicap"):
        if not sets:
            return None
    if market_id == "set_score":
        return {
            "actual": f"{home_sets}-{away_sets}",
            "scores": [
                1 if (e["home_sets"], e["away_sets"]) == (home_sets, away_sets) else 0
                for e in market["scores"]
            ],
        }
    if market_id == "total_sets":
        total = home_sets + away_sets
        return {
            "actual": total,
            "lines": ["over" if total > ln["line"] else "under" for ln in market["lines"]],
        }
    if market_id == "set_handicap":
        margin = home_sets - away_sets
        return {
            "actual": margin,
            "lines": ["home" if margin + ln["line"] > 0 else "away" for ln in market["lines"]],
        }
    if market_id == "home_to_win_a_set":
        return {"result": "yes" if home_sets > 0 else "no"}
    if market_id == "away_to_win_a_set":
        return {"result": "yes" if away_sets > 0 else "no"}
    if market_id == "first_set_winner":
        first = sets[0]
        return {"result": "home" if first[0] > first[1] else "away"}
    if market_id == "first_set_total_games":
        total = sets[0][0] + sets[0][1]
        return {
            "actual": total,
            "lines": ["over" if total > ln["line"] else "under" for ln in market["lines"]],
        }
    if market_id == "game_handicap":
        margin = sum(s[0] for s in sets) - sum(s[1] for s in sets)
        return {
            "actual": margin,
            "lines": ["home" if margin + ln["line"] > 0 else "away" for ln in market["lines"]],
        }
    if market_id == "tiebreak":
        return {"result": "yes" if any(_is_tiebreak(s) for s in sets) else "no"}
    return None
