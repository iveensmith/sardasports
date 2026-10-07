"""The slip builder's selection rules.

Two of them are about honesty rather than arithmetic. A fixture that has been
played cannot be in a slip, because nobody can place it. And the combined
probability is returned with the combined price, never instead of it: six legs
that each look safe multiply into a bet that usually loses, and a builder that
showed only the price would be advertising a number it knew the other half of.
"""

from __future__ import annotations

import pytest

from app.services.slip_service import Leg, build_slip, candidate_legs
from ml.markets import candidate_calls, rank_calls

PREDICTION = {
    "home_win": 70.0,
    "draw": 20.0,
    "away_win": 10.0,
    "btts_yes": 40.0,
    "btts_no": 60.0,
    "goals_markets": [{"line": 2.5, "prob_over": 45.0, "prob_under": 55.0}],
}
ODDS = {
    "match_winner": {"home": 1.50, "draw": 4.0, "away": 7.0},
    "btts": {"yes": 2.0, "no": 1.75},
    "goals": {"over_2.5": 2.1, "under_2.5": 1.75},
}
BASE_RATES = {
    "match_result:home": 44.0,
    "match_result:draw": 26.0,
    "match_result:away": 30.0,
    "btts:yes": 52.0,
    "btts:no": 48.0,
    "goals:over_2.5": 50.0,
    "goals:under_2.5": 50.0,
}


def _row(match_id: int, *, score=None) -> dict:
    return {
        "match_id": match_id,
        "slug": f"a-vs-b-prediction-{match_id}",
        "home_team": "A",
        "away_team": "B",
        "competition": {"name": "English Premier League"},
        "match_date": "2026-10-08T15:00:00",
        "score": score,
        "confidence": 8.0,
    }


def _legs(rows, **kwargs) -> list[Leg]:
    ranked = {row["match_id"]: rank_calls(candidate_calls(PREDICTION), BASE_RATES) for row in rows}
    odds = {row["match_id"]: ODDS for row in rows}
    return candidate_legs(rows, ranked, odds, **kwargs)


def _leg(match_id: int, odds: float, probability: float, confidence: float = 8.0) -> Leg:
    return Leg(
        match_id=match_id,
        slug=f"s-{match_id}",
        home_team="A",
        away_team="B",
        competition="English Premier League",
        match_date="2026-10-08T15:00:00",
        market="match_result",
        selection="home",
        label="Home win",
        short_label="1",
        probability=probability,
        odds=odds,
        confidence=confidence,
    )


def test_a_played_fixture_is_never_a_leg():
    legs = _legs([_row(1), _row(2, score={"home": 2, "away": 0})])

    assert [leg.match_id for leg in legs] == [1]


def test_a_card_that_is_over_has_no_candidate_legs():
    assert _legs([_row(1, score={"home": 1, "away": 1})]) == []


def test_each_fixture_contributes_at_most_one_leg_its_likeliest_priced_call():
    legs = _legs([_row(1)])

    assert len(legs) == 1
    # Home-or-away is 90% and is priced from the quoted 1X2 legs, so it is the
    # likeliest priced call — likelier than the 70% home win on its own.
    assert legs[0].selection == "home_away"
    assert legs[0].odds == pytest.approx(round(1 / (1 / 1.50 + 1 / 7.0), 2))


def test_a_selection_outside_the_price_window_is_not_a_leg():
    # The home win at 1.50 is under a 1.60 floor, so the next best priced call leads instead.
    legs = _legs([_row(1)], min_odd=1.60)

    assert legs and legs[0].odds >= 1.60


def test_a_fixture_with_no_quoted_price_yields_no_leg():
    ranked = {1: rank_calls(candidate_calls(PREDICTION), BASE_RATES)}
    assert candidate_legs([_row(1)], ranked, {1: None}) == []


def test_the_combined_price_is_the_product_and_comes_with_its_probability():
    slip = build_slip(
        [_leg(1, 1.5, 70.0), _leg(2, 2.0, 60.0), _leg(3, 1.8, 65.0)],
        target_odds=100.0,
        min_legs=3,
        max_legs=3,
    )

    assert slip["combined_odds"] == pytest.approx(1.5 * 2.0 * 1.8)
    assert slip["combined_probability"] == pytest.approx(70 * 0.6 * 0.65, abs=0.1)
    assert slip["leg_count"] == 3


def test_the_slip_stops_once_the_target_is_met_instead_of_padding():
    legs = [_leg(i, 2.0, 60.0, confidence=9.0 - i * 0.1) for i in range(1, 7)]

    slip = build_slip(legs, target_odds=4.0, min_legs=2, max_legs=6)

    assert slip["leg_count"] == 2  # 2.0 x 2.0 reaches the target
    assert slip["reached_target"] is True


def test_a_card_too_thin_for_the_minimum_says_so():
    slip = build_slip([_leg(1, 1.5, 70.0)], target_odds=10.0, min_legs=3, max_legs=6)

    assert slip["short_of_minimum"] is True
    assert slip["leg_count"] == 1


def test_the_same_inputs_always_give_the_same_slip():
    legs = [_leg(i, 1.6 + i * 0.1, 60.0 + i) for i in range(1, 6)]

    first = build_slip(legs, target_odds=6.0, min_legs=3, max_legs=5)
    second = build_slip(list(reversed(legs)), target_odds=6.0, min_legs=3, max_legs=5)

    assert first == second
