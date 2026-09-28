"""Choosing the one selection to lead with, and saying why.

The board shows a single pick per fixture with its price and a one-line
rationale. That pick is chosen by expected value against the best available
market price, not by which outcome the model likes most — those are
different questions. A 78%-likely favourite at 1.10 is a worse bet than a
40% shot at 3.50, and only the second is worth putting on a board.

Nothing here invents a probability. Every candidate is a market the engine
already priced; this only pairs each one with a bookmaker price and ranks
them.

Definitions, so the numbers on the page mean exactly one thing:

    fair price      1 / model probability — what the model thinks the
                    selection is worth.
    offered price   the best decimal price any bookmaker quotes for it.
    expected value  model probability x offered price - 1. Negative means
                    the market is asking more than the model thinks it is
                    worth, which is the normal case against efficient odds
                    and is reported rather than hidden.
"""

from __future__ import annotations

from dataclasses import dataclass

# Selections worth leading with. A market the engine cannot price is not
# here, so a price with no model behind it is never shown as a pick.
MATCH_WINNER_LABELS = {"home": "Home", "draw": "Draw", "away": "Away"}
BTTS_LABELS = {"yes": "Both teams score", "no": "Both teams score - No"}


@dataclass
class Candidate:
    market: str
    selection: str
    label: str
    model_probability: float  # 0-1
    offered_price: float

    @property
    def fair_price(self) -> float:
        return 1.0 / self.model_probability

    @property
    def expected_value(self) -> float:
        """Fractional EV: 0.05 is +5%."""
        return self.model_probability * self.offered_price - 1.0

    @property
    def market_implied(self) -> float:
        return 1.0 / self.offered_price


def _goals_probability(prediction: dict, line: float, side: str) -> float | None:
    for entry in prediction.get("goals_markets") or []:
        if abs(float(entry.get("line", -1)) - line) < 1e-9:
            value = entry.get("prob_over") if side == "over" else entry.get("prob_under")
            return None if value is None else float(value) / 100.0
    return None


def candidates_for(prediction: dict, odds_markets: dict | None) -> list[Candidate]:
    """Every selection that has both a model probability and a price."""
    if not prediction or not odds_markets:
        return []

    found: list[Candidate] = []

    winner = odds_markets.get("match_winner") or {}
    for selection, key in (("home", "home_win"), ("draw", "draw"), ("away", "away_win")):
        price = winner.get(selection)
        probability = prediction.get(key)
        if price and isinstance(probability, int | float) and probability > 0:
            found.append(
                Candidate(
                    market="Match result",
                    selection=selection,
                    label=MATCH_WINNER_LABELS[selection],
                    model_probability=probability / 100.0,
                    offered_price=float(price),
                )
            )

    btts = odds_markets.get("btts") or {}
    for selection, key in (("yes", "btts_yes"), ("no", "btts_no")):
        price = btts.get(selection)
        probability = prediction.get(key)
        if price and isinstance(probability, int | float) and probability > 0:
            found.append(
                Candidate(
                    market="Both teams to score",
                    selection=selection,
                    label=BTTS_LABELS[selection],
                    model_probability=probability / 100.0,
                    offered_price=float(price),
                )
            )

    goals = odds_markets.get("goals") or {}
    for selection, price in goals.items():
        try:
            side, raw_line = selection.split("_", 1)
            line = float(raw_line)
        except (ValueError, AttributeError):
            continue
        probability = _goals_probability(prediction, line, side)
        if price and probability and probability > 0:
            found.append(
                Candidate(
                    market="Goals",
                    selection=selection,
                    label=f"{side.capitalize()} {line}",
                    model_probability=probability,
                    offered_price=float(price),
                )
            )

    return found


def rationale_for(best: Candidate, agreement: dict | None, thin_evidence: bool = False) -> str:
    """One sentence explaining the pick, in the interface's own voice.

    Deliberately states the unflattering case plainly: most selections
    against efficient odds price *worse* than the model thinks they are
    worth, and a board that only ever narrated wins would be lying by
    omission.
    """
    expected_value = best.expected_value * 100
    lead = (
        f"Fair price {best.fair_price:.2f} against an offered price of "
        f"{best.offered_price:.2f} ({expected_value:+.1f}% expected value)."
    )

    if thin_evidence:
        # The edge is arithmetically real and evidentially worthless. Saying
        # so is the whole point: an unqualified "+276% expected value" would
        # be the most misleading thing on the page.
        return (
            f"{lead} One or both sides have too few matches for their rating to mean "
            "much, so this gap reflects what the model does not know rather than value."
        )

    if agreement is None:
        return f"{lead} No multi-estimator ensemble for this sport, so agreement is not measured."

    model_percent = best.model_probability * 100
    market_percent = best.market_implied * 100
    if agreement.get("unanimous"):
        detail = (
            f"All {agreement['total']} estimators back the same outcome; "
            f"model {model_percent:.0f}% against market {market_percent:.0f}%."
        )
    elif agreement.get("agreeing", 0) * 2 < agreement.get("total", 3):
        detail = (
            f"Only {agreement['agreeing']} of {agreement['total']} estimators back this, "
            "so treat the rating as weak."
        )
    else:
        detail = (
            f"{agreement['agreeing']} of {agreement['total']} estimators agree; "
            f"model {model_percent:.0f}% against market {market_percent:.0f}%."
        )
    return f"{lead} {detail}"


# Below this many completed matches, a competitor's rating has not moved
# meaningfully off the 1500 default, so the model is guessing from a near-
# neutral prior while the market is not. Any edge computed against such a
# rating is model error rather than value.
#
# This matters most for national teams: only three seasons of international
# football are ingested (the API plan caps it), so Central African Republic
# carries 10 matches and an Elo of 1520 — the model reads a coin flip where
# the market prices 10%, and the arithmetic then reports a "+276% edge".
THIN_EVIDENCE_MATCHES = 30


def best_pick(
    prediction: dict,
    odds_markets: dict | None,
    agreement: dict | None,
    home_matches: int | None = None,
    away_matches: int | None = None,
) -> dict | None:
    """The single highest-expected-value selection, with its reasoning.

    Returns None when the fixture has no price, or no priced market the
    engine can put a probability against — reported as an absence rather
    than filled with the model's favourite outcome at no price.

    A large positive edge is treated as a warning sign, not a headline. The
    engine's own ROI backtest returned -6.74% against bookmaker odds, so a
    board where every pick shows free money is reporting model error. Where
    either side has thin evidence the pick is flagged, and the flag is
    surfaced rather than the number quietly suppressed.
    """
    found = candidates_for(prediction, odds_markets)
    if not found:
        return None

    best = max(found, key=lambda c: c.expected_value)
    thin = [
        count
        for count in (home_matches, away_matches)
        if count is not None and count < THIN_EVIDENCE_MATCHES
    ]
    return {
        "thin_evidence": bool(thin),
        "min_competitor_matches": (
            min(c for c in (home_matches, away_matches) if c is not None)
            if any(c is not None for c in (home_matches, away_matches))
            else None
        ),
        "market": best.market,
        "selection": best.selection,
        "label": best.label,
        "model_probability": round(best.model_probability * 100, 1),
        "market_implied_probability": round(best.market_implied * 100, 1),
        "fair_price": round(best.fair_price, 2),
        "offered_price": round(best.offered_price, 2),
        "expected_value": round(best.expected_value * 100, 1),
        "positive_value": best.expected_value > 0,
        "candidates_considered": len(found),
        "rationale": rationale_for(best, agreement, bool(thin)),
    }
