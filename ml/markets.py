"""Every selection the engine can call, and the one it leads with.

The board used to call one market: the match result. That threw away most of
what the engine already computes. A fixture it prices produces probabilities
for goals lines, half-time goals, both-teams-to-score, corners and cards, and
the match-result probabilities themselves imply the three double chances — so
"Spain or draw" needs no new model, only the arithmetic nobody was doing.

**One prediction per fixture: the selection most likely to happen.** That is
the product decision, and `headline_call` implements it literally — the
highest probability across every market, nothing else weighed in.

Two consequences are worth knowing rather than discovering:

* Most fixtures will lead with a double chance or an over/under, because
  those are genuinely the likeliest things in football. On a real 29-fixture
  card, 26 led with a double chance.
* A likely selection is not the same as an informative one. Measured over
  64,365 completed matches, "either team to win" lands 73.8% of the time and
  "over 1.5 goals" 74.8%, so an engine reading near those numbers is telling
  you about football rather than about this fixture.

That second point is why every call still carries its base rate and the lift
above it. The lift does not choose the prediction — probability does — but it
is shown beside it, so a reader can tell a 76% that means something from a
76% that was always going to be true.
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


# Below this lift, the model has found nothing the base rate did not already
# say. This never changes which call is made — probability alone decides that
# — it only controls whether the call is shown as a standout or plainly.
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

    This ordering is *not* how the prediction is chosen — `headline_call`
    takes the highest probability regardless. It exists so `best_per_market`
    can pick the most informative call within each market for the detail
    page, where several markets are listed side by side.

    Calls with no base rate sort last among equals: without a yardstick there
    is no evidence they are notable, and guessing one would invent the
    comparison this module exists to make honest.
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
    """The one call the fixture leads with: the likeliest thing to happen.

    Highest probability across every market, with no floor, no weighting and
    no tie-break on how informative the selection is. A reader asking "what
    does it predict?" gets the answer to that question and no other.

    Lift deliberately plays no part in this choice. It is attached to the
    result so it can be shown as context — a 76% call on a market that lands
    74% of the time is worth knowing about — but a more *surprising* call
    never displaces a more *likely* one.
    """
    if not ranked:
        return None
    return max(ranked, key=lambda r: r.call.probability)
