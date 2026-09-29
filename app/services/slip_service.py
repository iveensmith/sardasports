"""Building an accumulator from the day's picks.

An accumulator multiplies its legs' prices together and needs every one of
them to land. That second half is what makes the feature dangerous to build
carelessly: six legs at 80% each is a 26% chance of a return, and a builder
that reports only the combined price is showing the upside of a bet whose
downside it has calculated and withheld.

So every slip carries its combined probability beside its combined odds, and
the two are given equal weight. A reader who sees "5.20" and "26%" together
is being told the truth; one who sees only "5.20" is being sold something.

The search
----------
Choosing legs to hit a target price is a subset-sum problem, and an exact
one is both unnecessary and slow. What a reader wants is a slip near their
target made of the engine's better calls, so this does a greedy pass over
candidates sorted by confidence, taking a leg whenever it moves the running
product towards the target without overshooting it, then stops. Deterministic
for the same inputs, which matters more here than optimality: a builder that
returns a different slip on every refresh is not a tool, it is a slot machine.

Legs are drawn from distinct fixtures. Two selections from one match are
correlated — "over 2.5" and "both teams to score" tend to land together — and
multiplying their prices as if they were independent overstates the combined
price of the slip.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import prod

from app.services.board_service import odds_for
from ml.markets import RankedCall

# Guard rails on a single leg. Below the floor a leg adds almost nothing to
# the price while still adding a way to lose; above the ceiling one leg
# dominates the slip and the other picks are decoration.
DEFAULT_MIN_ODD = 1.15
DEFAULT_MAX_ODD = 2.50

# A slip needs at least two legs to be an accumulator at all, and past a
# dozen the probability of a return is negligible whatever the price says.
MIN_LEGS = 2
MAX_LEGS = 12


@dataclass(frozen=True)
class Leg:
    """One selection in a slip, tied to the fixture it came from."""

    match_id: int
    slug: str
    home_team: str
    away_team: str
    competition: str
    match_date: str
    market: str
    selection: str
    label: str
    short_label: str
    probability: float  # percent
    odds: float
    confidence: float | None  # out of ten

    def as_dict(self) -> dict:
        return {
            "match_id": self.match_id,
            "slug": self.slug,
            "home_team": self.home_team,
            "away_team": self.away_team,
            "competition": self.competition,
            "match_date": self.match_date,
            "market": self.market,
            "selection": self.selection,
            "label": self.label,
            "short_label": self.short_label,
            "probability": round(self.probability, 1),
            "odds": round(self.odds, 2),
            "confidence": self.confidence,
        }


def candidate_legs(
    rows: list[dict],
    ranked_by_match: dict[int, list[RankedCall]],
    odds_by_match: dict[int, dict | None],
    *,
    markets: set[str] | None = None,
    min_odd: float = DEFAULT_MIN_ODD,
    max_odd: float = DEFAULT_MAX_ODD,
) -> list[Leg]:
    """Every priced selection eligible to be a leg, best per fixture.

    One leg per fixture, because two selections from the same match are
    correlated and multiplying their prices as independent overstates the
    slip. The fixture contributes its highest-probability eligible call.
    """
    legs: list[Leg] = []
    for row in rows:
        match_id = row["match_id"]
        entries = ranked_by_match.get(match_id) or []
        odds_markets = odds_by_match.get(match_id)

        best: Leg | None = None
        for entry in entries:
            call = entry.call
            if markets is not None and call.market not in markets:
                continue
            price = odds_for(call.market, call.selection, odds_markets)
            if price is None or not (min_odd <= price <= max_odd):
                continue
            leg = Leg(
                match_id=match_id,
                slug=row["slug"],
                home_team=row["home_team"],
                away_team=row["away_team"],
                competition=row["competition"]["name"],
                match_date=row["match_date"],
                market=call.market,
                selection=call.selection,
                label=call.label,
                short_label=call.short_label,
                probability=call.probability,
                odds=price,
                confidence=row.get("confidence"),
            )
            if best is None or leg.probability > best.probability:
                best = leg
        if best is not None:
            legs.append(best)
    return legs


def build_slip(
    legs: list[Leg],
    *,
    target_odds: float,
    min_legs: int = 3,
    max_legs: int = 6,
) -> dict:
    """Assemble a slip as near the target price as the day's card allows.

    Greedy over confidence, then probability: the engine's surest calls go in
    first, and a leg is taken only while the running price stays under the
    target. Deterministic for identical inputs.
    """
    min_legs = max(MIN_LEGS, min_legs)
    max_legs = min(MAX_LEGS, max(max_legs, min_legs))

    ordered = sorted(
        legs,
        key=lambda leg: (-(leg.confidence or 0.0), -leg.probability, leg.match_id),
    )

    chosen: list[Leg] = []
    running = 1.0
    for leg in ordered:
        if len(chosen) >= max_legs:
            break
        # Stop adding once the target is met and the minimum is satisfied,
        # rather than padding the slip out to max_legs — every extra leg is
        # another way for the whole thing to fail.
        if running >= target_odds and len(chosen) >= min_legs:
            break
        chosen.append(leg)
        running *= leg.odds

    combined_odds = prod(leg.odds for leg in chosen) if chosen else 0.0
    # The number a builder that only showed the price would be hiding.
    combined_probability = prod(leg.probability / 100 for leg in chosen) * 100 if chosen else 0.0

    return {
        "legs": [leg.as_dict() for leg in chosen],
        "leg_count": len(chosen),
        "combined_odds": round(combined_odds, 2),
        "combined_probability": round(combined_probability, 1),
        "target_odds": target_odds,
        "reached_target": combined_odds >= target_odds,
        # True when the day's card simply could not supply enough eligible
        # legs — reported so the interface can say so rather than quietly
        # returning a shorter slip as though it were what was asked for.
        "short_of_minimum": len(chosen) < min_legs,
        "candidates_considered": len(legs),
    }
