"""Every selection the engine can call, and the one it leads with.

The board used to call one market: the match result. That threw away most of
what the engine already computes. A fixture it prices produces probabilities
for goals lines, half-time goals, both-teams-to-score, corners and cards, and
the match-result probabilities themselves imply the three double chances — so
"Spain or draw" needs no new model, only the arithmetic nobody was doing.

**One prediction per fixture: the likeliest selection that actually says
something.** Probability picks the winner; a call only enters the contest if
it beats its own base rate by `MIN_HEADLINE_LIFT`.

The second half of that rule is not fussiness, it is the difference between
a board and a decoration. Measured over 64,365 completed matches:

    Home or away (not a draw)   73.8%      <- true by construction
    Over 1.5 goals              74.8%
    Over 2.5 cards              78.1%
    Home or draw                70.5%

Ranked on raw probability alone, 26 of 29 fixtures on a real card led with a
double chance and 14 of 29 leading calls added under five points over what
that selection manages unaided. Half the board was true and empty.

Banning the common markets is the obvious fix and it is worse: doing that
left 21 of 29 rows on "Over 1.5 goals" at about the rate it lands anyway —
more variety, less meaning. Filtering on lift keeps the likeliest call in
each case and drops only the ones with nothing behind them, which took the
same card to five markets and no empty calls at all.
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
# Markets that depend on a statistic only some competitions record. Where a competition has none
# of it, there is nothing to price the market from, so it is not called there at all.
STAT_MARKETS = frozenset({HT_GOALS, CORNERS, CARDS})

MARKET_ORDER = [MATCH_RESULT, DOUBLE_CHANCE, GOALS, BTTS, HT_GOALS, CORNERS, CARDS]


# Bookmaker shorthand, for the board's fixed-width market columns.
#
# A table cell has room for "1X" and not for "Home or draw", and anyone
# reading a football board already knows what 1X means. The long labels stay
# on `Call.label` for the fixture page and anywhere a full sentence fits.
SHORT_CODES: dict[str, str] = {
    f"{MATCH_RESULT}:home": "1",
    f"{MATCH_RESULT}:draw": "X",
    f"{MATCH_RESULT}:away": "2",
    f"{DOUBLE_CHANCE}:home_draw": "1X",
    f"{DOUBLE_CHANCE}:away_draw": "X2",
    f"{DOUBLE_CHANCE}:home_away": "12",
    f"{BTTS}:yes": "Yes",
    f"{BTTS}:no": "No",
}

# Prefixes for the over/under markets, whose selections carry their own line.
_OVER_UNDER_PREFIX = {GOALS: "", HT_GOALS: "HT ", CORNERS: "Crn ", CARDS: "Crd "}


def short_code(market: str, selection: str) -> str:
    """ "1X", "O2.5", "HT O0.5" — the shorthand a board column has room for."""
    fixed = SHORT_CODES.get(f"{market}:{selection}")
    if fixed is not None:
        return fixed
    prefix = _OVER_UNDER_PREFIX.get(market)
    if prefix is not None and "_" in selection:
        side, _, line = selection.partition("_")
        if side in ("over", "under"):
            return f"{prefix}{side[0].upper()}{line}"
    return selection


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

    @property
    def short_label(self) -> str:
        """Bookmaker shorthand for a narrow column."""
        return short_code(self.market, self.selection)


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


def candidate_calls(prediction: dict | None) -> list[Call]:
    """Every selection this fixture supports, unranked.

    Labels are the market's own terms — "Home or draw", "Over 2.5 goals" —
    not the competitors' names. They sit in a fixed-width slot on the board
    directly beneath the fixture, which already names both sides, so
    repeating a name there costs the width that makes long ties readable and
    tells the reader nothing twice.
    """
    if not prediction:
        return []

    calls: list[Call] = []

    home = _number(prediction.get("home_win"))
    draw = _number(prediction.get("draw"))
    away = _number(prediction.get("away_win"))
    if None not in (home, draw, away):
        calls += [
            Call(MATCH_RESULT, "home", "Home", home),
            Call(MATCH_RESULT, "draw", "Draw", draw),
            Call(MATCH_RESULT, "away", "Away", away),
            # Derived, not modelled. A double chance is exactly the sum of two
            # mutually exclusive outcomes, so this introduces no new estimate
            # and cannot disagree with the match-result call.
            Call(DOUBLE_CHANCE, "home_draw", "Home or draw", home + draw),
            Call(DOUBLE_CHANCE, "away_draw", "Away or draw", away + draw),
            Call(DOUBLE_CHANCE, "home_away", "Home or away", home + away),
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
# say. Marks a call as a standout in the per-market table.
NOTABLE_LIFT = 5.0

# A call must beat its own base rate by this much to lead a row.
#
# Probability still picks the winner — this only decides who is allowed to
# enter. Without it, half the board was true-but-empty: measured on a real
# 29-fixture card, 14 of 29 leading calls added under five points over what
# that selection achieves on its own, which is a confident-looking number
# that tells a reader nothing about the fixture in front of them.
MIN_HEADLINE_LIFT = 5.0

# The same bar, but held higher for double chance specifically.
#
# A double chance is a sum of two match-result outcomes, so its probability
# starts inflated before the model contributes anything — that is exactly
# why "Home or away" is barred outright below. Home-or-draw and away-or-draw
# are not that extreme (they do say something about this fixture, not just
# "not a draw"), but they inherit enough of the same structural edge that a
# flat MIN_HEADLINE_LIFT lets them win the headline on it alone: measured on
# 150 real completed fixtures, double chance led 75% of rows at the ordinary
# bar, most of them adding little over what the market already implies.
#
# This is not the banning `headline_call` already tried and rejected — that
# made "Over 1.5 goals" the new near-universal headline instead, which is
# just the crowding-out problem wearing a different market. Asking double
# chance to clear a higher bar keeps the same rule ("does this beat its own
# baseline by enough to be worth leading with") and answers it against a
# baseline the market itself has already inflated. At this threshold the
# same 150 fixtures split close to evenly across goals, match result and
# double chance instead of double chance crowding out the other two.
DOUBLE_CHANCE_MIN_HEADLINE_LIFT = 20.0

# The same bar, held higher for corners and cards, where the model has measurably overstated
# what it knows.
#
# Measured on every graded stored prediction, judged against each competition's own rates: a
# match-result, double-chance or goals call that claimed a lift of five to ten points realised
# about that much (over 400 to 1,000 calls in each), while corners claimed 7.0 and realised
# 2.4 (1,475 calls), and cards claimed 6.8 and realised 4.8 (1,140). The corner probabilities
# run about five points too high at every level, so a corner line "beating its base rate by 5"
# has usually not beaten it at all, and because the lines are ladders (over 7.5, 8.5, 9.5
# corners; over 2.5, 3.5, 4.5 cards) there are always several easy ones with a high
# probability to win the headline. Asking these two markets for a larger claimed lift is the
# same rule as for double chance: it keeps the likeliest call that has really earned its
# place, and lets a market that has earned more of the claim it makes lead instead.
#
# Corner probabilities are now recalibrated when read (`app/services/count_calibration.py`),
# which removed most of the overstatement, so this bar no longer has to carry the whole
# correction. It stays for two measured reasons (`scripts/measure_headline_mix.py`, 2,119
# graded predictions): lowering the corner bar to 5 to 7.5 adds headlines that came in only
# about 30% to 50% of the time (the share that hit falls from 68% to 61%), and card headlines
# win about 73% of the time at any bar, so their bar of 8 is not about accuracy: it keeps
# cards at roughly one headline in seven instead of one in four, so that other markets can
# lead too.
MARKET_MIN_HEADLINE_LIFT = {CORNERS: 10.0, CARDS: 8.0}

# A best tip the engine rates at least this likely is a "strong tip".
#
# Measured on 2,117 graded best tips, the engine's stated probabilities are honest: tips it put
# in the 70s won 75.9% of the time, the 80s 85.8%, the 90s 95.6%. So how often a tip wins is
# mostly decided by how likely the engine says it is, and the way to a high win rate is to put
# forward the tips it is surest of, not to retune the engine. Seventy is the point where about
# half the fixtures still qualify and the record reaches 83.6%. Every fixture keeps its best
# tip; this only marks which ones are strong, from the probability stored before kick-off.
STRONG_TIP_MIN_PROBABILITY = 70.0


def is_strong_tip(probability: float | None) -> bool:
    return probability is not None and probability >= STRONG_TIP_MIN_PROBABILITY


# Selections that never lead a row whatever their probability.
#
# "Home or away" is the sum of both wins, so it says only "not a draw" —
# true of 73.8% of matches by construction. That makes it simultaneously one
# of the likeliest selections on almost every fixture and one of the least
# informative, so a pure probability rule handed it a third of the board
# while the engine contributed nothing. It stays a candidate, so it can still
# represent the double-chance row in the per-market table; it just cannot be
# the headline.
# Under 1.5 and Under 2.5 goals are also kept off the headline and the board's goals column.
# Measured on 2,184 graded best tips, an Under 2.5 headline won 56.7% of the time (180 of them,
# against 68.7% for all best tips) and Under 1.5 almost never leads, while Under 3.5 won 85.3%.
# Their probabilities are honest (the model is calibrated on them), so they stay candidates: the
# match page's full table still lists them. They just do not lead. Taking them out left the record
# where it was (68.3% against 68.7%, strong tips 83.5% either way).
HEADLINE_EXCLUDED = frozenset(
    {f"{DOUBLE_CHANCE}:home_away", f"{GOALS}:under_1.5", f"{GOALS}:under_2.5"}
)


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
            "short_label": self.call.short_label,
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
    # Hold back a corners, cards or half-time call that has no base rate when rates exist at
    # all: the table is built per competition (see `competition_base_rates`) and leaves these
    # out where the competition records none of that statistic. A call with no yardstick for its
    # own league is a number the engine has no history to stand behind.
    if base_rates:
        calls = [c for c in calls if c.market not in STAT_MARKETS or c.key in base_rates]
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


def _pick(
    entries: list[RankedCall],
    *,
    double_chance_min_lift: float | None = None,
    market_min_lift: dict[str, float] | None = None,
) -> RankedCall | None:
    """The likeliest call that clears the lift bar, else the likeliest.

    The one selection rule, used for the headline and for each market column
    alike. Sharing it is not tidiness — the two diverging is a bug that
    already shipped once. Ranking the columns by lift instead put the 1X2
    cell on the *highest-lift* result rather than the likeliest, so it
    preferred a 33% away win over a 45% home win because away beats its base
    rate by more. Graded over 807 fixtures that column won 24.7% of the time,
    against 33.3% for picking at random, while the headline beside it — which
    had always used probability — won 77.7%.

    `double_chance_min_lift` raises the bar for double-chance calls alone,
    without touching how any market picks its own representative — only
    `headline_call` passes it. A market column choosing among its own
    selections (`best_per_market`) has no crowding-out problem to solve;
    giving it the stricter bar too would just make the double-chance row on
    the fixture page go blank on fixtures where it is still the best reading
    of that one market, for no benefit to the headline it doesn't drive.
    """
    if not entries:
        return None
    allowed = [e for e in entries if e.call.key not in HEADLINE_EXCLUDED]

    def _bar(entry: RankedCall) -> float:
        if double_chance_min_lift is not None and entry.call.market == DOUBLE_CHANCE:
            return double_chance_min_lift
        if market_min_lift is not None and entry.call.market in market_min_lift:
            return market_min_lift[entry.call.market]
        return MIN_HEADLINE_LIFT

    eligible = [e for e in allowed if e.lift is not None and e.lift >= _bar(e)]
    return max(eligible or allowed or entries, key=lambda e: e.call.probability)


def best_per_market(ranked: list[RankedCall]) -> list[RankedCall]:
    """The call to show in each market's column, in reading order.

    One per market rather than a global top-N, so the board shows a spread of
    genuinely different questions instead of three near-identical goals lines.
    Within a market the winner is chosen by `_pick`, exactly as the headline
    is — a column labelled "1X2 tip" has to mean the same thing the best-tip
    column means, or the row contradicts itself.
    """
    grouped: dict[str, list[RankedCall]] = {}
    for entry in ranked:
        grouped.setdefault(entry.call.market, []).append(entry)
    chosen = {market: _pick(entries) for market, entries in grouped.items()}
    return [chosen[market] for market in MARKET_ORDER if chosen.get(market) is not None]


def headline_call(ranked: list[RankedCall]) -> RankedCall | None:
    """The one call the fixture leads with.

    The likeliest thing to happen — but only among selections that beat their
    own base rate by `MIN_HEADLINE_LIFT` (`DOUBLE_CHANCE_MIN_HEADLINE_LIFT`
    for a double chance) and are not in `HEADLINE_EXCLUDED`. Probability
    decides the winner; those rules decide who is eligible.

    They exist because "likeliest" and "worth saying" pull in opposite
    directions, and a pure probability rule collapses onto whichever market
    is most common rather than whichever reading is strongest. A double
    chance is the sum of two outcomes and over 1.5 goals a low line, so they
    win a raw contest almost every time regardless of what the model thinks.

    Banning double chance outright is the obvious fix and it is wrong: on the
    same card it left 21 of 29 rows showing "Over 1.5 goals" at roughly the
    74.8% that line lands anyway. That is more variety and less meaning.
    Filtering on lift instead keeps the likeliest call in each case and
    removes only the empty ones — but a double chance's lift is measured
    against a base rate the market has already inflated by construction, so
    the ordinary bar alone still let it dominate (75% of headlines on a real
    150-fixture sample). Raising its bar specifically is the same fix taken
    one step further, not a different one: `DOUBLE_CHANCE_MIN_HEADLINE_LIFT`.

    When nothing qualifies the likeliest call is returned anyway, with its
    lift intact so the interface can show it quietly. A blank row helps
    nobody, and the honest version of "we have no strong read here" is a
    modest number shown modestly, not an absence.
    """
    if not ranked:
        return None
    # Not quite the rule each market column uses — double chance answers to
    # a higher bar here, see `_pick` — so the best tip and the column it came
    # from can still disagree on a double-chance headline specifically. They
    # cannot disagree on which selection represents a market once both have
    # decided that market gets to speak, which is the invariant that matters:
    # see `test_a_market_column_agrees_with_the_best_tip_when_they_are_the_same_market`.
    return _pick(
        ranked,
        double_chance_min_lift=DOUBLE_CHANCE_MIN_HEADLINE_LIFT,
        market_min_lift=MARKET_MIN_HEADLINE_LIFT,
    )
