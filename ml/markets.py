"""Every selection the engine can call, across every market it prices.

The board used to call one market: the match result. That threw away most of
what the engine already computes. A fixture it prices produces probabilities
for goals lines, half-time goals, both-teams-to-score, corners and cards, and
the match-result probabilities themselves imply the three double chances — so
"Spain or draw" needs no new model, only the arithmetic nobody was doing.

Ranking these by raw probability does not work, and the reason is worth
stating because it is not obvious. Measured over 64,365 completed matches:

    Either team to win (12)     73.8%      <- true of three matches in four
    Over 1.5 goals              74.8%
    Home or draw (1X)           70.5%
    Over 2.5 corners            78.1%

A market that lands three-quarters of the time is not a prediction when the
engine says 76%; it is a restatement of how football works. Ranked on raw
probability, 26 of 29 fixtures on a real card led with a double chance and
most of those with "Either team to win", which only means "not a draw".

So a call carries both numbers: the probability, and how far it sits above
that selection's own base rate. The second is what makes it a claim. An 86%
"Spain or draw" against a 70.5% base rate is +15 points of genuine signal; a
76% "Either team to win" against 73.8% is +2 and belongs nowhere near a
headline.

This module is pure — it turns a prediction payload into candidate calls and
knows nothing about databases or base rates. `app.services.base_rates`
measures the yardstick and `app.services.pick_service` does the ranking.
"""

from __future__ import annotations

from dataclasses import dataclass

# Market identifiers, used as the first half of a base-rate key. Stable
# strings rather than an enum, because they are serialised to the API.
MATCH_RESULT = "match_result"
DOUBLE_CHANCE = "double_chance"
GOALS = "goals"
BTTS = "btts"
HT_GOALS = "ht_goals"
CORNERS = "corners"
CARDS = "cards"

# Display names, in the order a reader most likely wants them.
MARKET_NAMES = {
    MATCH_RESULT: "Match result",
    DOUBLE_CHANCE: "Double chance",
    GOALS: "Goals",
    BTTS: "Both teams to score",
    HT_GOALS: "Half-time goals",
    CORNERS: "Corners",
    CARDS: "Cards",
}
MARKET_ORDER = [MATCH_RESULT, DOUBLE_CHANCE, GOALS, BTTS, HT_GOALS, CORNERS, CARDS]


@dataclass(frozen=True)
class Call:
    """One selection the engine can make, with how likely it thinks it is."""

    market: str
    selection: str
    label: str
    probability: float  # percent, 0-100

    @property
    def key(self) -> str:
        """Stable identifier, matching the base-rate table's keys."""
        return f"{self.market}:{self.selection}"


def _number(value) -> float | None:
    """A probability, or None for a market the engine could not price.

    Absence is meaningful here — a competition with no corner data returns
    None rather than zero — so it is preserved rather than coerced.
    """
    return float(value) if isinstance(value, int | float) else None


def _over_under(market: str, entries, label_for) -> list[Call]:
    """Both sides of every line the engine actually priced."""
    calls: list[Call] = []
    for entry in entries or []:
        line = entry.get("line")
        over, under = _number(entry.get("prob_over")), _number(entry.get("prob_under"))
        if line is None or over is None or under is None:
            continue
        calls.append(Call(market, f"over_{line}", label_for("Over", line), over))
        calls.append(Call(market, f"under_{line}", label_for("Under", line), under))
    return calls


def candidate_calls(prediction: dict | None, home_team: str, away_team: str) -> list[Call]:
    """Every selection this fixture supports, unranked.

    Labels name the teams rather than the market's side, because "Spain or
    draw" is what a reader understands and "1X" is not.
    """
    if not prediction:
        return []

    calls: list[Call] = []

    home = _number(prediction.get("home_win"))
    draw = _number(prediction.get("draw"))
    away = _number(prediction.get("away_win"))
    if None not in (home, draw, away):
        calls += [
            Call(MATCH_RESULT, "home", f"{home_team} to win", home),
            Call(MATCH_RESULT, "draw", "Draw", draw),
            Call(MATCH_RESULT, "away", f"{away_team} to win", away),
            # Derived, not modelled. A double chance is exactly the sum of two
            # mutually exclusive outcomes, so this introduces no new estimate
            # and cannot disagree with the match-result call.
            Call(DOUBLE_CHANCE, "home_draw", f"{home_team} or draw", home + draw),
            Call(DOUBLE_CHANCE, "away_draw", f"{away_team} or draw", away + draw),
            Call(DOUBLE_CHANCE, "home_away", "Either team to win", home + away),
        ]

    btts_yes, btts_no = _number(prediction.get("btts_yes")), _number(prediction.get("btts_no"))
    if btts_yes is not None and btts_no is not None:
        calls += [
            Call(BTTS, "yes", "Both teams to score", btts_yes),
            Call(BTTS, "no", "Both teams not to score", btts_no),
        ]

    calls += _over_under(
        GOALS, prediction.get("goals_markets"), lambda side, line: f"{side} {line} goals"
    )
    calls += _over_under(
        HT_GOALS,
        prediction.get("ht_goals_markets"),
        lambda side, line: f"{side} {line} goals at half-time",
    )
    calls += _over_under(
        CORNERS, prediction.get("corners_markets"), lambda side, line: f"{side} {line} corners"
    )
    calls += _over_under(
        CARDS, prediction.get("cards_markets"), lambda side, line: f"{side} {line} cards"
    )

    return calls


# A headline call should at minimum be more likely to happen than not.
# Without this floor the ranking will happily lead with "Draw 46%" whenever a
# fixture looks unusually even — the most *surprising* thing the model has
# said, but a poor thing to print as a prediction.
HEADLINE_MIN_PROBABILITY = 50.0

# Below this, the model has found nothing the base rate did not already say.
# Reported, but never dressed up as a standout.
NOTABLE_LIFT = 5.0


@dataclass(frozen=True)
class RankedCall:
    """A call with the context that turns its probability into a claim."""

    call: Call
    base_rate: float | None
    # Percentage points above the base rate. None when the market has too
    # little history to have a yardstick, which is not the same as zero.
    lift: float | None

    @property
    def notable(self) -> bool:
        return self.lift is not None and self.lift >= NOTABLE_LIFT

    def as_dict(self) -> dict:
        return {
            "market": self.call.market,
            "market_name": MARKET_NAMES.get(self.call.market, self.call.market),
            "selection": self.call.selection,
            "label": self.call.label,
            "probability": round(self.call.probability, 1),
            "base_rate": self.base_rate,
            "lift": None if self.lift is None else round(self.lift, 1),
            "notable": self.notable,
        }


def rank_calls(calls: list[Call], base_rates: dict[str, float]) -> list[RankedCall]:
    """Attach each call's base rate and lift, most notable first.

    Sorted by lift rather than probability, because probability alone ranks
    markets by how common they are rather than by what the model has found.
    Calls with no base rate sort last among equals: without a yardstick there
    is no evidence they are notable, and guessing one would invent the
    comparison this whole module exists to make honest.
    """
    ranked = [
        RankedCall(
            call=call,
            base_rate=base_rates.get(call.key),
            lift=(
                None
                if base_rates.get(call.key) is None
                else call.probability - base_rates[call.key]
            ),
        )
        for call in calls
    ]
    return sorted(
        ranked,
        key=lambda r: (r.lift if r.lift is not None else float("-inf"), r.call.probability),
        reverse=True,
    )


def best_per_market(ranked: list[RankedCall]) -> list[RankedCall]:
    """The strongest call in each market, in reading order.

    One per market rather than a global top-N, so the board shows a spread of
    genuinely different questions instead of three near-identical goals lines.
    Within a market the winner is the highest-lift call, which is already the
    order `rank_calls` produced.
    """
    seen: dict[str, RankedCall] = {}
    for entry in ranked:
        seen.setdefault(entry.call.market, entry)
    return [seen[market] for market in MARKET_ORDER if market in seen]


def headline_call(ranked: list[RankedCall]) -> RankedCall | None:
    """The one call worth leading with.

    Highest lift among calls likely enough to print as a prediction. If
    nothing clears the floor — an genuinely unreadable fixture — falls back to
    the likeliest call, so the board still says something rather than nothing.
    """
    if not ranked:
        return None
    eligible = [r for r in ranked if r.call.probability >= HEADLINE_MIN_PROBABILITY]
    if eligible:
        return eligible[0]
    return max(ranked, key=lambda r: r.call.probability)
