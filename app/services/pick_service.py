"""What the engine thinks will happen, and separately where the price is wrong.

These are two different questions and the board asks both. Conflating them
was a real bug: a fixture row led with "Away" — the highest-expected-value
selection at 14.50 — while the fixture's own detail page had the home side
at 65%. Two pages of the same product disagreeing about the same match, with
nothing on either saying they were answering different questions.

So both now have a name and neither is called "the prediction":

    forecast   the outcome the model considers most likely. This is what a
               reader means by "the prediction", it is what the row leads
               with, and it is the same number the detail page shows.
    value      the selection whose price looks most wrong, by expected value
               against the best available market price. Often *not* the
               likely outcome — a 78%-likely favourite at 1.10 is a worse
               bet than a 40% shot at 3.50 — which is exactly why it cannot
               be the headline.

A long price on an unlikely outcome is a legitimate thing to surface. It is
not a prediction that the outcome will happen, and the interface must never
let it read as one.

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


def most_likely_outcome(prediction: dict | None, home_team: str, away_team: str) -> dict | None:
    """The outcome the model considers most likely — the fixture's forecast.

    Named by what a reader sees rather than by the market: "Spain to win",
    not "Home". A draw has no team to name, so it is called a draw.

    This reads the same blended probabilities the detail page renders, so the
    two cannot drift apart. Returns None only when there is no prediction at
    all; unlike `best_pick` it needs no odds, because what the model expects
    does not depend on anyone offering a price for it.
    """
    if not prediction:
        return None

    options = (
        ("home", prediction.get("home_win"), f"{home_team} to win"),
        ("draw", prediction.get("draw"), "Draw"),
        ("away", prediction.get("away_win"), f"{away_team} to win"),
    )
    priced = [
        (selection, float(probability), label)
        for selection, probability, label in options
        if isinstance(probability, int | float)
    ]
    if not priced:
        return None

    selection, probability, label = max(priced, key=lambda option: option[1])
    return {
        "selection": selection,
        "label": label,
        "probability": round(probability, 1),
        # The short form, for places too narrow for the team name.
        "short_label": MATCH_WINNER_LABELS[selection],
    }


def rationale_for(best: Candidate, agreement: dict | None, thin_evidence: bool = False) -> str:
    """One sentence explaining the value selection, in the interface's own voice.

    Deliberately states the unflattering case plainly: most selections
    against efficient odds price *worse* than the model thinks they are
    worth, and a board that only ever narrated wins would be lying by
    omission.

    The estimator agreement needs care, because it is a vote on the *match
    result* and this selection may be neither the winning side nor a match
    result at all. Attaching it unqualified read as an endorsement it was
    never giving: Spain v Croatia said "All 3 estimators back the same
    outcome; model 14% against market 7%" about a Croatia selection the
    estimators unanimously made the *loser*. So the agreement clause now
    names which outcome it is about, and says plainly when that is not this
    one.
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
    prices = f"Model {model_percent:.0f}% against market {market_percent:.0f}%."

    # The estimators vote on the match result only. For a goals or BTTS
    # selection they have said nothing about it, and claiming otherwise
    # would be inventing support.
    if best.market != "Match result":
        return (
            f"{lead} {prices} Estimator agreement is measured on the match result, not this market."
        )

    backed = agreement.get("pick") == best.selection
    if not backed:
        # The case that made the board look self-contradictory: a long price
        # on the outcome the model itself considers least likely.
        backed_label = MATCH_WINNER_LABELS.get(agreement.get("pick"), "another outcome")
        return (
            f"{lead} {prices} This is the price, not the forecast — "
            f"{agreement['agreeing']} of {agreement['total']} estimators make {backed_label} "
            "the likelier result."
        )

    if agreement.get("unanimous"):
        detail = f"All {agreement['total']} estimators back this outcome; {prices.lower()}"
    elif agreement.get("agreeing", 0) * 2 < agreement.get("total", 3):
        detail = (
            f"Only {agreement['agreeing']} of {agreement['total']} estimators back this, "
            "so treat the rating as weak."
        )
    else:
        detail = (
            f"{agreement['agreeing']} of {agreement['total']} estimators agree; {prices.lower()}"
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
