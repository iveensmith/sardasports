"""Basketball markets beyond the winner and the game total: teams, halves, quarters, spreads.

Everything here is priced from the engine's existing two estimates for a game, never from a new
black box:

* **Expected points for each side** (what it scores blended with what the other concedes, from
  prior games only: `predict_basketball`), and
* **the winner probability** (Elo blended with the trained model).

A game's points are then split across periods using the *league's own* historical shape, and a
period's spread is measured from that league's real quarter scores. A league with too few games
to have a shape of its own uses the pooled profile for its format. Both live in
`ml/basketball_period_profiles.json`, written by `scripts/fit_basketball_period_profiles.py`
(which also reports the out-of-sample accuracy of the whole thing).

Format matters and is read from the data, not assumed: American college basketball is played in
two halves and the source records them in two of the four quarter slots, so a game like that is
priced for its halves only and never offered a "quarter 1".

Every market is `source: "statistical"`: a normal distribution around an expectation, with the
league's measured spread. It is not a trained model per line, and it says so.
"""

from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

PROFILE_PATH = Path(__file__).with_name("basketball_period_profiles.json")
# A league needs this many games, in a format, before its own profile is trusted.
MIN_LEAGUE_GAMES = 150

QUARTERS = ("q1", "q2", "q3", "q4")
HALVES = ("h1", "h2")


# ---------------------------------------------------------------- maths


def normal_cdf(x: float) -> float:
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def _clip(p: float) -> float:
    return min(max(p, 0.01), 0.99)


def line_ladder(mean: float, sd: float, count: int = 3) -> list[float]:
    """Lines (all ending in .5, so a push is impossible) spread either side of the expectation.

    The step is about half a standard deviation in whole points (so every line still ends in
    .5) and at least one, so the three lines span the range a bettor would actually look at.
    """
    step = float(max(1, round(0.45 * sd)))
    centre = math.floor(mean) + 0.5
    half = count // 2
    return [round(centre + (i - half) * step, 1) for i in range(count)]


def over_under(mean: float, sd: float, lines: list[float] | None = None) -> list[dict]:
    lines = lines or line_ladder(mean, sd)
    out = []
    for line in lines:
        over = _clip(1.0 - normal_cdf((line - mean) / sd))
        out.append(
            {
                "line": line,
                "prob_over": round(over * 100, 1),
                "prob_under": round((1.0 - over) * 100, 1),
            }
        )
    return out


def inverse_normal(p: float) -> float:
    """Standard normal quantile (Acklam's rational approximation, accurate to ~1e-9)."""
    p = min(max(p, 1e-9), 1 - 1e-9)
    a = (-3.969683028665376e01, 2.209460984245205e02, -2.759285104469687e02,
         1.383577518672690e02, -3.066479806614716e01, 2.506628277459239e00)  # fmt: skip
    b = (-5.447609879822406e01, 1.615858368580409e02, -1.556989798598866e02,
         6.680131188771972e01, -1.328068155288572e01)  # fmt: skip
    c = (-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e00,
         -2.549732539343734e00, 4.374664141464968e00, 2.938163982698783e00)  # fmt: skip
    d = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00,
         3.754408661907416e00)  # fmt: skip
    low, high = 0.02425, 1 - 0.02425
    if p < low:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1
        )
    if p > high:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1
        )
    q = p - 0.5
    r = q * q
    return (
        (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5])
        * q
        / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)
    )


# ---------------------------------------------------------------- profiles


@lru_cache(maxsize=1)
def load_profiles() -> dict:
    try:
        return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def reset_profiles() -> None:
    load_profiles.cache_clear()


def pick_profile(competition: str | None, fmt: str) -> dict | None:
    """The league's own profile for this format if it has enough games, else the pooled one."""
    profiles = load_profiles()
    league = (profiles.get("leagues") or {}).get(competition or "", {}).get(fmt)
    if league and league.get("n", 0) >= MIN_LEAGUE_GAMES:
        return league
    return (profiles.get("default") or {}).get(fmt)


def game_format(competition: str | None) -> str:
    """ "halves" for a competition recorded in two halves, otherwise "quarters"."""
    leagues = load_profiles().get("leagues") or {}
    entry = leagues.get(competition or "") or {}
    if "halves" in entry and "quarters" not in entry:
        return "halves"
    if entry.get("halves", {}).get("n", 0) > entry.get("quarters", {}).get("n", 0):
        return "halves"
    return "quarters"


# ---------------------------------------------------------------- pricing


def _three_way(mean_margin: float, sd: float, slope: float = 1.0) -> dict:
    """Home / tie / away for an integer margin (a tie is a real outcome in a period).

    `slope` shrinks the home-versus-away split towards even (fitted on held-out games: a stated
    77% period win happened 71% of the time before it). The tie probability is left alone.
    """
    home = 1.0 - normal_cdf((0.5 - mean_margin) / sd)
    away = normal_cdf((-0.5 - mean_margin) / sd)
    tie = max(0.0, 1.0 - home - away)
    if slope != 1.0 and home > 0 and away > 0:
        conditional = home / (home + away)
        logit = math.log(conditional / (1.0 - conditional))
        shrunk = 1.0 / (1.0 + math.exp(-slope * logit))
        home, away = shrunk * (1.0 - tie), (1.0 - shrunk) * (1.0 - tie)
    return {
        "home": round(home * 100, 1),
        "tie": round(tie * 100, 1),
        "away": round(away * 100, 1),
    }


def price_game(
    exp_home: float,
    exp_away: float,
    home_win: float,
    competition: str | None,
) -> list[dict]:
    """Every extra market for one game, or [] when no profile exists to price it from.

    `exp_home`/`exp_away` are expected points for each side; `home_win` is the winner
    probability in 0..1 (the same number the moneyline shows, so the spread and the period
    winners cannot disagree with it).
    """
    fmt = game_format(competition)
    slope = float(load_profiles().get("winner_slope", 1.0))
    profile = pick_profile(competition, fmt)
    if not profile or exp_home <= 0 or exp_away <= 0:
        return []
    bias = profile["bias"]
    shares = profile["shares"]
    cv = profile["cv"]
    margin_sd_ratio = profile["margin_sd_ratio"]

    expected_total = (exp_home + exp_away) * bias["total"]
    markets: list[dict] = []

    def add(group, name, market_id, kind, **body):
        markets.append(
            {"id": market_id, "group": group, "name": name, "type": kind, "source": "statistical"}
            | body
        )

    # Team totals.
    for side, label, exp in (("home", "Home team", exp_home), ("away", "Away team", exp_away)):
        mean = exp * bias[side]
        sd = max(1.0, cv[side] * mean)
        add(
            "Teams",
            f"{label} total points",
            f"team_total_{side}",
            "over_under",
            side=side,
            expected=round(mean, 1),
            lines=over_under(mean, sd),
        )

    # Margin. Full game (overtime included) is what the moneyline answers, so the margin's
    # centre is placed where P(margin > 0) equals the stated home win probability.
    sd_margin = max(3.0, margin_sd_ratio["full"] * expected_total)
    mu = sd_margin * inverse_normal(_clip(home_win))
    # Handicap lines for the home side, h: it covers when margin + h > 0, so the fair line is
    # about -mu. Centred on the half point at or just beyond that, one step either side.
    step = float(max(1, round(0.45 * sd_margin)))
    centre = -(math.floor(mu) + 0.5)
    spread_lines = []
    for k in (-1, 0, 1):
        h = round(centre + k * step, 1)
        p_cover = _clip(normal_cdf((mu + h) / sd_margin))
        spread_lines.append(
            {
                "line": h,
                "prob_home": round(p_cover * 100, 1),
                "prob_away": round((1 - p_cover) * 100, 1),
            }
        )
    add(
        "Full game",
        "Point spread (overtime included)",
        "spread",
        "handicap",
        expected_margin=round(mu, 1),
        lines=spread_lines,
    )

    periods = QUARTERS if fmt == "quarters" else HALVES
    names = {
        "q1": "1st quarter",
        "q2": "2nd quarter",
        "q3": "3rd quarter",
        "q4": "4th quarter",
        "h1": "1st half",
        "h2": "2nd half",
    }
    period_totals: dict[str, float] = {}
    for p in periods:
        mean = expected_total * shares[p]
        period_totals[p] = mean
        sd = max(1.0, cv[p] * mean)
        add(
            "Quarters" if fmt == "quarters" else "Halves",
            f"{names[p]} total points",
            f"{p}_total",
            "over_under",
            period=p,
            expected=round(mean, 1),
            lines=over_under(mean, sd),
        )
        e_sd = margin_sd_ratio.get(p)
        if e_sd is not None:
            sd_p = max(1.0, e_sd * expected_total)
            add(
                "Quarters" if fmt == "quarters" else "Halves",
                f"{names[p]} winner",
                f"{p}_winner",
                "three_way",
                period=p,
                **_three_way(shares[p] * mu, sd_p, slope),
            )

    # Halves from quarters.
    if fmt == "quarters":
        for p, parts, label in (("h1", ("q1", "q2"), "1st half"), ("h2", ("q3", "q4"), "2nd half")):
            mean = sum(period_totals[x] for x in parts)
            sd = max(1.0, cv[p] * mean)
            add(
                "Halves",
                f"{label} total points",
                f"{p}_total",
                "over_under",
                period=p,
                expected=round(mean, 1),
                lines=over_under(mean, sd),
            )
            e_sd = margin_sd_ratio.get(p)
            if e_sd is not None:
                share = sum(shares[x] for x in parts)
                add(
                    "Halves",
                    f"{label} winner",
                    f"{p}_winner",
                    "three_way",
                    period=p,
                    **_three_way(share * mu, max(1.0, e_sd * expected_total), slope),
                )
    return markets


# ---------------------------------------------------------------- grading


def period_totals_from(periods: dict | None) -> dict | None:
    """Home/away points for every period a stored `period_scores` supports, or None."""
    if not periods or not periods.get("home") or not periods.get("away"):
        return None
    home, away = periods["home"], periods["away"]
    ot = periods.get("ot") or [0, 0]
    result: dict = {
        "q": {i + 1: (home[i], away[i]) for i in range(4)},
        "h": {
            1: (home[0] + home[1], away[0] + away[1]),
            2: (home[2] + home[3], away[2] + away[3]),
        },
        "reg": (sum(home), sum(away)),
        "final": (sum(home) + ot[0], sum(away) + ot[1]),
    }
    return result


def halves_only(periods: dict | None) -> bool:
    """True for a game recorded in two halves (the first and third slots empty)."""
    if not periods:
        return False
    return (
        periods["home"][0] == 0
        and periods["away"][0] == 0
        and (periods["home"][2] == 0 and periods["away"][2] == 0)
    )


def actual_for(market_id: str, periods: dict | None, final: tuple[int, int] | None):
    """What the market's quantity actually was, or None when it cannot be graded."""
    if market_id in ("spread",):
        return None if final is None else final[0] - final[1]
    if market_id.startswith("team_total_"):
        if final is None:
            return None
        # A team total includes overtime, as the bookmaker's does.
        return final[0] if market_id.endswith("home") else final[1]
    if not periods:
        return None
    if halves_only(periods):
        slots = {
            "h1": (periods["home"][1], periods["away"][1]),
            "h2": (periods["home"][3], periods["away"][3]),
        }
    else:
        totals = period_totals_from(periods)
        slots = {f"q{i}": totals["q"][i] for i in range(1, 5)} | {
            "h1": totals["h"][1],
            "h2": totals["h"][2],
        }
    key = market_id.split("_")[0]
    pair = slots.get(key)
    if pair is None:
        return None
    if market_id.endswith("_total"):
        return pair[0] + pair[1]
    if market_id.endswith("_winner"):
        return pair[0] - pair[1]
    return None


def grade_market(market: dict, periods: dict | None, final: tuple[int, int] | None) -> dict | None:
    """Settle one priced market. Returns what happened and which side of each line won."""
    actual = actual_for(market["id"], periods, final)
    if actual is None:
        return None
    kind = market["type"]
    if kind == "over_under":
        return {
            "actual": actual,
            "lines": ["over" if actual > ln["line"] else "under" for ln in market.get("lines", [])],
        }
    if kind == "handicap":
        return {
            "actual": actual,
            "lines": [
                "home" if actual + ln["line"] > 0 else "away" for ln in market.get("lines", [])
            ],
        }
    if kind == "three_way":
        return {
            "actual": actual,
            "result": "home" if actual > 0 else "away" if actual < 0 else "tie",
        }
    return None
