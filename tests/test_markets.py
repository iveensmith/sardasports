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
    MATCH_RESULT,
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


def _ranked(prediction=SPAIN_CROATIA, home="Spain", away="Croatia", rates=BASE_RATES):
    return rank_calls(candidate_calls(prediction, home, away), rates)


# --- what gets called ----------------------------------------------------


def test_every_market_the_engine_prices_becomes_a_call():
    markets = {call.market for call in candidate_calls(SPAIN_CROATIA, "Spain", "Croatia")}
    assert markets == {"match_result", "double_chance", "goals", "btts", "ht_goals"}


def test_a_market_the_engine_could_not_price_produces_no_call():
    """Null is "no reading", and inventing 0% for it would be a lie the UI
    would then render as a confident under bet."""
    labels = {c.label for c in candidate_calls(SPAIN_CROATIA, "Spain", "Croatia")}
    assert not any("corners" in label for label in labels)
    assert not any("cards" in label for label in labels)


def test_double_chance_is_exactly_the_sum_of_two_outcomes():
    """Derived, not modelled — so it can never disagree with the match result."""
    calls = {c.selection: c for c in candidate_calls(SPAIN_CROATIA, "Spain", "Croatia")}
    assert calls["home_draw"].probability == pytest.approx(65.3 + 20.6)
    assert calls["away_draw"].probability == pytest.approx(14.2 + 20.6)
    assert calls["home_away"].probability == pytest.approx(65.3 + 14.2)


def test_calls_name_the_teams_rather_than_the_market_side():
    labels = {c.label for c in candidate_calls(SPAIN_CROATIA, "Spain", "Croatia")}
    assert "Spain to win" in labels
    assert "Spain or draw" in labels
    assert "1X" not in labels  # what a bookmaker calls it, not what a reader reads


def test_no_prediction_means_no_calls():
    assert candidate_calls(None, "A", "B") == []
    assert candidate_calls({}, "A", "B") == []


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
    assert top.call.label == "Spain to win"

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


def test_the_headline_is_the_likeliest_call_across_every_market():
    """The product rule, stated literally: one prediction, highest chance.

    For Spain v Croatia that is "Spain or draw" at 85.9%, not the 65.3%
    match-result favourite and not the highest-lift call.
    """
    head = headline_call(_ranked())
    assert head.call.label == "Spain or draw"
    assert head.call.probability == pytest.approx(85.9)


def test_lift_never_displaces_a_likelier_call():
    """A more *surprising* call must not outrank a more *likely* one.

    "Spain to win" has the bigger lift (+20.9 against +15.4) and is still not
    the prediction, because it is less likely to happen.
    """
    ranked = _ranked()
    head = headline_call(ranked)
    by_key = {r.call.key: r for r in ranked}
    assert by_key["match_result:home"].lift > head.lift
    assert head.call.probability > by_key["match_result:home"].call.probability


def test_the_headline_can_be_a_call_more_likely_to_fail_than_land():
    """If nothing on a fixture clears 50%, the likeliest thing is still the
    prediction rather than the board going blank."""
    flat = {"home_win": 34.0, "draw": 33.0, "away_win": 33.0}
    calls = [c for c in candidate_calls(flat, "A", "B") if c.market == MATCH_RESULT]
    head = headline_call(rank_calls(calls, BASE_RATES))
    assert head is not None
    assert head.call.probability == pytest.approx(34.0)


def test_a_call_with_no_base_rate_can_still_be_the_headline():
    """Probability decides. An unmeasurable market is not disqualified from
    being the likeliest thing to happen — it just cannot be marked notable."""
    calls = [
        Call(GOALS, "over_2.5", "Over 2.5 goals", 61.0),
        Call("corners", "over_7.5", "Over 7.5 corners", 91.0),
    ]
    head = headline_call(rank_calls(calls, {"goals:over_2.5": 50.6}))
    assert head.call.selection == "over_7.5"
    assert head.lift is None
    assert head.notable is False


def test_no_calls_means_no_headline():
    assert headline_call([]) is None


# --- one call per market -------------------------------------------------


def test_best_per_market_returns_the_strongest_call_in_each():
    per_market = {r.call.market: r for r in best_per_market(_ranked())}
    assert per_market[MATCH_RESULT].call.label == "Spain to win"
    assert per_market[DOUBLE_CHANCE].call.label == "Spain or draw"
    assert per_market[GOALS].call.label == "Over 2.5 goals"  # +10.4 beats over 1.5's +7.8


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
    ranked = rank_calls(candidate_calls(low_scoring, "Madagascar", "Tanzania"), BASE_RATES)
    goals = next(r for r in ranked if r.call.market == GOALS)
    assert goals.call.label == "Under 2.5 goals"
    assert goals.lift == pytest.approx(68.6 - 49.4)
    assert goals.lift > NOTABLE_LIFT
