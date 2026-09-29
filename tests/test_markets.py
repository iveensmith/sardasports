"""Calling every market, and the reason raw probability cannot rank them.

The board answered one question — who wins — and dropped everything else the
engine computes. Opening it up is mostly arithmetic, but the ranking is not
obvious, and getting it wrong produces a board that looks informative and
says nothing.

Measured over 64,365 completed matches, "either team to win" lands 73.8% of
the time and "over 1.5 goals" 74.8%. Rank on raw probability and 26 of 29
fixtures on a real card lead with a double chance, most of them with "either
team to win" — which only means "not a draw". The engine has contributed
nothing to that sentence.

So a call is ranked on its lift above its own base rate. These tests pin that
choice, the arithmetic behind the derived markets, and the handling of
markets the engine cannot price — which must stay distinguishable from
markets it prices at zero.
"""

from __future__ import annotations

import pytest

from ml.markets import (
    DOUBLE_CHANCE,
    GOALS,
    HEADLINE_EXCLUDED,
    MATCH_RESULT,
    MIN_HEADLINE_LIFT,
    NOTABLE_LIFT,
    Call,
    best_per_market,
    candidate_calls,
    headline_call,
    rank_calls,
)

# The real measured table, so tests reason about the same yardstick the
# product does.
BASE_RATES = {
    "match_result:home": 44.4,
    "match_result:draw": 26.2,
    "match_result:away": 29.5,
    "double_chance:home_draw": 70.5,
    "double_chance:away_draw": 55.6,
    "double_chance:home_away": 73.8,
    "goals:over_1.5": 74.8,
    "goals:under_1.5": 25.2,
    "goals:over_2.5": 50.6,
    "goals:under_2.5": 49.4,
    "btts:yes": 52.4,
    "btts:no": 47.6,
    "ht_goals:over_0.5": 69.3,
    "ht_goals:under_0.5": 30.7,
}

SPAIN_CROATIA = {
    "home_win": 65.3,
    "draw": 20.6,
    "away_win": 14.2,
    "btts_yes": 51.7,
    "btts_no": 48.3,
    "goals_markets": [
        {"line": 1.5, "prob_over": 82.6, "prob_under": 17.4, "model_used": True},
        {"line": 2.5, "prob_over": 61.0, "prob_under": 39.0, "model_used": True},
    ],
    "ht_goals_markets": [{"line": 0.5, "prob_over": 78.3, "prob_under": 21.7, "model_used": True}],
    # The engine prices no corners or cards for this competition. Nulls, not
    # zeroes — the distinction this module has to preserve.
    "corners_markets": [{"line": 7.5, "prob_over": None, "prob_under": None, "model_used": False}],
    "cards_markets": [{"line": 2.5, "prob_over": None, "prob_under": None, "model_used": False}],
}


def _ranked(prediction=SPAIN_CROATIA, rates=BASE_RATES):
    return rank_calls(candidate_calls(prediction), rates)


# --- what gets called ----------------------------------------------------


def test_every_market_the_engine_prices_becomes_a_call():
    markets = {call.market for call in candidate_calls(SPAIN_CROATIA)}
    assert markets == {"match_result", "double_chance", "goals", "btts", "ht_goals"}


def test_a_market_the_engine_could_not_price_produces_no_call():
    """Null is "no reading", and inventing 0% for it would be a lie the UI
    would then render as a confident under bet."""
    labels = {c.label for c in candidate_calls(SPAIN_CROATIA)}
    assert not any("corners" in label for label in labels)
    assert not any("cards" in label for label in labels)


def test_double_chance_is_exactly_the_sum_of_two_outcomes():
    """Derived, not modelled — so it can never disagree with the match result."""
    calls = {c.selection: c for c in candidate_calls(SPAIN_CROATIA)}
    assert calls["home_draw"].probability == pytest.approx(65.3 + 20.6)
    assert calls["away_draw"].probability == pytest.approx(14.2 + 20.6)
    assert calls["home_away"].probability == pytest.approx(65.3 + 14.2)


def test_calls_are_named_in_the_markets_own_terms_not_the_competitors():
    """The fixture is printed on the line above, so a name repeated here is
    width spent saying nothing twice."""
    labels = {c.label for c in candidate_calls(SPAIN_CROATIA)}
    assert {"Home", "Draw", "Away", "Home or draw", "Away or draw", "Home or away"} <= labels
    assert not any("Spain" in label or "Croatia" in label for label in labels)


def test_no_prediction_means_no_calls():
    assert candidate_calls(None) == []
    assert candidate_calls({}) == []


# --- the ranking, which is the part that is easy to get wrong ------------


def test_lift_is_the_distance_above_the_selections_own_base_rate():
    by_key = {r.call.key: r for r in _ranked()}
    spain = by_key["match_result:home"]
    assert spain.base_rate == 44.4
    assert spain.lift == pytest.approx(65.3 - 44.4)


def test_rank_calls_orders_by_lift_for_the_per_market_listing():
    """`rank_calls` is not the headline rule — it decides which call
    represents each market in the detail page's table, where the most
    informative one is the right representative."""
    top = _ranked()[0]
    assert top.call.market == MATCH_RESULT
    assert top.call.label == "Home"

    by_key = {r.call.key: r for r in _ranked()}
    double_chance = by_key["double_chance:home_draw"]
    assert double_chance.call.probability > top.call.probability  # likelier...
    assert double_chance.lift < top.lift  # ...but says less


def test_a_common_markets_high_probability_is_mostly_its_base_rate():
    """The reason every call carries a base rate.

    "Either team to win" reads 79.5% here, which looks like a strong call
    until you see that it lands 73.8% of the time anyway — almost all of that
    number is football, not this fixture. It may still be shown, and it may
    even be the prediction if it is the likeliest thing; the base rate beside
    it is what stops it reading as a discovery.
    """
    by_key = {r.call.key: r for r in _ranked()}
    either = by_key["double_chance:home_away"]
    assert either.call.probability == pytest.approx(79.5)
    assert either.base_rate == 73.8
    assert either.lift == pytest.approx(5.7, abs=0.05)
    # Far less informative than the match-result call, despite reading higher.
    assert either.lift < by_key["match_result:home"].lift


def test_a_market_with_no_base_rate_sorts_below_one_that_has_lift():
    """Without a yardstick there is no evidence a call is notable, and
    inventing a base rate would fake the only comparison that matters."""
    calls = [
        Call(GOALS, "over_2.5", "Over 2.5 goals", 61.0),  # +10.4
        Call("corners", "over_9.5", "Over 9.5 corners", 95.0),  # no base rate
    ]
    ranked = rank_calls(calls, {"goals:over_2.5": 50.6})
    assert ranked[0].call.selection == "over_2.5"
    assert ranked[1].lift is None
    assert ranked[1].notable is False


def test_notable_marks_a_lift_worth_a_readers_attention():
    ranked = {r.call.key: r for r in _ranked()}
    assert ranked["match_result:home"].notable  # +20.9
    assert not ranked["btts:no"].notable  # +0.7, football being football


# --- the headline --------------------------------------------------------


def test_the_headline_is_the_likeliest_call_that_clears_the_lift_bar():
    """The product rule: likeliest, among calls that actually say something.

    For Spain v Croatia that is "Home or draw" at 85.9% — likelier than the
    65.3% match-result favourite, and its +15.4 lift clears the bar.
    """
    head = headline_call(_ranked())
    assert head.call.label == "Home or draw"
    assert head.call.probability == pytest.approx(85.9)
    assert head.lift >= MIN_HEADLINE_LIFT


def test_lift_never_displaces_a_likelier_eligible_call():
    """Among eligible calls, probability alone decides.

    "Home" has the bigger lift (+20.9 against +15.4) and is still not the
    prediction, because it is less likely to happen.
    """
    ranked = _ranked()
    head = headline_call(ranked)
    by_key = {r.call.key: r for r in ranked}
    assert by_key["match_result:home"].lift > head.lift
    assert head.call.probability > by_key["match_result:home"].call.probability


def test_home_or_away_never_leads_however_likely_it_is():
    """It is the sum of both wins, so it says only "not a draw" — true of
    73.8% of matches by construction. Arithmetically among the likeliest
    things on almost every fixture, and among the least informative."""
    calls = [
        Call(DOUBLE_CHANCE, "home_away", "Home or away", 88.0),
        Call(GOALS, "over_1.5", "Over 1.5 goals", 84.0),
    ]
    head = headline_call(rank_calls(calls, {**BASE_RATES, "goals:over_1.5": 74.8}))
    assert head.call.selection == "over_1.5"
    assert f"{DOUBLE_CHANCE}:home_away" in HEADLINE_EXCLUDED


def test_home_or_away_is_still_a_candidate_for_the_per_market_table():
    """Barred from the headline, not deleted — the double-chance row of the
    fixture page may still be best represented by it."""
    assert any(c.selection == "home_away" for c in candidate_calls(SPAIN_CROATIA))


def test_an_empty_call_loses_to_a_less_likely_one_that_means_something():
    """The bug this bar exists to fix. "Over 1.5 goals" at 76% against a
    74.8% base rate is a restatement of football; "Under 2.5 goals" at 62%
    against 49.4% is a reading of this fixture."""
    calls = [
        Call(GOALS, "over_1.5", "Over 1.5 goals", 76.0),  # +1.2
        Call(GOALS, "under_2.5", "Under 2.5 goals", 62.0),  # +12.6
    ]
    head = headline_call(rank_calls(calls, BASE_RATES))
    assert head.call.selection == "under_2.5"


def test_when_nothing_clears_the_bar_the_likeliest_call_is_shown_anyway():
    """A blank row helps nobody. The honest form of "no strong read here" is
    a modest number shown modestly, and `lift` survives so the interface can
    do exactly that."""
    calls = [
        Call(GOALS, "over_1.5", "Over 1.5 goals", 76.0),  # +1.2
        Call(MATCH_RESULT, "home", "Home", 46.0),  # +1.6
    ]
    head = headline_call(rank_calls(calls, BASE_RATES))
    assert head is not None
    assert head.call.selection == "over_1.5"
    assert head.lift < MIN_HEADLINE_LIFT
    assert head.notable is False


def test_a_call_with_no_base_rate_cannot_lead_while_a_measured_one_can():
    """Without a yardstick there is no evidence a call says anything, so it
    cannot clear a bar defined in terms of one. It is not deleted — it simply
    loses to any call that has been measured and qualifies."""
    calls = [
        Call(GOALS, "under_2.5", "Under 2.5 goals", 62.0),  # +12.6, measured
        Call("corners", "over_7.5", "Over 7.5 corners", 91.0),  # no base rate
    ]
    head = headline_call(rank_calls(calls, BASE_RATES))
    assert head.call.selection == "under_2.5"


def test_an_unmeasurable_call_still_leads_when_it_is_all_there_is():
    calls = [Call("corners", "over_7.5", "Over 7.5 corners", 91.0)]
    head = headline_call(rank_calls(calls, {}))
    assert head.call.selection == "over_7.5"
    assert head.lift is None


def test_no_calls_means_no_headline():
    assert headline_call([]) is None


# --- one call per market -------------------------------------------------


def test_best_per_market_uses_the_same_rule_as_the_headline():
    """Likeliest among calls that clear the lift bar — not highest lift.

    Over 1.5 (82.6%, +7.8) is chosen over Over 2.5 (61.0%, +10.4): both say
    something, and the first is likelier. Ranking these columns by lift is a
    bug that shipped once — it put the 1X2 cell on a 33% away win ahead of a
    45% home win, and that column graded 24.7% over 807 fixtures against
    33.3% for guessing.
    """
    per_market = {r.call.market: r for r in best_per_market(_ranked())}
    assert per_market[MATCH_RESULT].call.label == "Home"
    assert per_market[DOUBLE_CHANCE].call.label == "Home or draw"
    assert per_market[GOALS].call.label == "Over 1.5 goals"


def test_a_market_column_agrees_with_the_best_tip_when_they_are_the_same_market():
    """A cell labelled "1X2 tip" has to mean what the best-tip column means,
    or the row contradicts itself."""
    ranked = _ranked()
    head = headline_call(ranked)
    per_market = {r.call.market: r for r in best_per_market(ranked)}
    assert per_market[head.call.market].call.key == head.call.key


def test_best_per_market_never_repeats_a_market():
    """Three goals lines in a row would crowd out every other question."""
    markets = [r.call.market for r in best_per_market(_ranked())]
    assert len(markets) == len(set(markets))


def test_best_per_market_is_in_reading_order_not_score_order():
    markets = [r.call.market for r in best_per_market(_ranked())]
    assert markets == ["match_result", "double_chance", "goals", "btts", "ht_goals"]


def test_over_and_under_are_both_candidates_so_a_low_line_can_win():
    """Madagascar v Tanzania's real call was Under 2.5 at 68.6%."""
    low_scoring = {
        "home_win": 30.0,
        "draw": 33.0,
        "away_win": 37.0,
        "goals_markets": [{"line": 2.5, "prob_over": 31.4, "prob_under": 68.6, "model_used": True}],
    }
    ranked = rank_calls(candidate_calls(low_scoring), BASE_RATES)
    goals = next(r for r in ranked if r.call.market == GOALS)
    assert goals.call.label == "Under 2.5 goals"
    assert goals.lift == pytest.approx(68.6 - 49.4)
    assert goals.lift > NOTABLE_LIFT


def test_the_exclusion_holds_even_when_nothing_else_qualifies():
    """The fallback must not readmit a barred selection.

    Letting "Home or away" back in when nothing clears the bar would put it
    on exactly the fixtures the engine reads least well — the worst possible
    moment to print "not a draw" as though it were a prediction.
    """
    calls = [
        Call(DOUBLE_CHANCE, "home_away", "Home or away", 74.7),  # +0.9, barred
        Call(GOALS, "over_1.5", "Over 1.5 goals", 71.0),  # -3.8, eligible but weak
    ]
    head = headline_call(rank_calls(calls, BASE_RATES))
    assert head.call.selection == "over_1.5"
    assert head.lift < MIN_HEADLINE_LIFT  # shown quietly, but it is a real market
