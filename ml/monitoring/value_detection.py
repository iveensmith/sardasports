"""Value detection — compare the model's implied probability against the market's.

Pure math, no database access: given decimal odds and model probabilities,
compute the bookmaker's overround-adjusted implied probability and the
percentage-point edge. This never predicts profit — it only reports a
mathematical difference between two probability estimates, per the spec's
explicit requirement to never guarantee returns.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ValueEdge:
    outcome: str  # "home_win" | "draw" | "away_win"
    model_probability: float  # 0-100
    market_implied_probability: float  # 0-100, overround-adjusted
    edge: float  # model_probability - market_implied_probability, in percentage points


def decimal_odds_to_implied_probabilities(
    odds_home: float, odds_draw: float, odds_away: float
) -> tuple[float, float, float]:
    """Convert decimal odds to overround-adjusted ("fair") implied probabilities.

    Raw `1/odds` probabilities always sum to slightly over 1.0 (the
    bookmaker's margin/overround) — dividing each by that sum removes the
    margin so the three probabilities sum to exactly 1.0, which is the
    correct baseline to compare a model against.
    """
    raw_home, raw_draw, raw_away = 1 / odds_home, 1 / odds_draw, 1 / odds_away
    overround = raw_home + raw_draw + raw_away
    return raw_home / overround, raw_draw / overround, raw_away / overround


def compute_value_edges(
    model_home: float,
    model_draw: float,
    model_away: float,
    odds_home: float,
    odds_draw: float,
    odds_away: float,
) -> list[ValueEdge]:
    """Compare model probabilities (0-100 each) against market-implied ones.

    Returns one `ValueEdge` per outcome, sorted by absolute edge descending,
    so the largest divergence (in either direction) comes first.
    """
    implied_home, implied_draw, implied_away = decimal_odds_to_implied_probabilities(
        odds_home, odds_draw, odds_away
    )

    edges = [
        ValueEdge("home_win", model_home, implied_home * 100, model_home - implied_home * 100),
        ValueEdge("draw", model_draw, implied_draw * 100, model_draw - implied_draw * 100),
        ValueEdge("away_win", model_away, implied_away * 100, model_away - implied_away * 100),
    ]
    return sorted(edges, key=lambda e: abs(e.edge), reverse=True)
