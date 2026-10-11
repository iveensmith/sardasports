"""Draw no bet: a side to win, with the stake returned on a draw.

Its probability is the chance the side wins given there is a winner (home / (home + away)), so a
draw can only settle it as void. A void is held apart from the win rate (the site's existing rule
for a call that could not be graded), never counted as a win and never as a loss.
"""

from __future__ import annotations

import pytest

from app.services.settlement import MatchResult, Outcome, settle, settle_key
from ml.markets import (
    DNB,
    Call,
    best_per_market,
    candidate_calls,
    headline_call,
    rank_calls,
)

PREDICTION = {"home_win": 50.0, "draw": 25.0, "away_win": 25.0}
BASE_RATES = {"dnb:home": 60.0, "dnb:away": 40.0, "match_result:home": 44.4}


def _result(home, away):
    return MatchResult(home_score=home, away_score=away)


def test_the_probability_is_the_chance_to_win_given_there_is_a_winner():
    calls = {c.selection: c for c in candidate_calls(PREDICTION) if c.market == DNB}

    assert calls["home"].probability == pytest.approx(50.0 / 75.0 * 100.0)
    assert calls["away"].probability == pytest.approx(25.0 / 75.0 * 100.0)
    assert calls["home"].probability + calls["away"].probability == pytest.approx(100.0)


def test_it_is_named_in_the_markets_own_terms():
    calls = {c.selection: c for c in candidate_calls(PREDICTION) if c.market == DNB}
    assert calls["home"].label == "Home (draw no bet)"
    assert calls["home"].short_label == "1 DNB"
    assert calls["away"].short_label == "2 DNB"


def test_no_call_is_made_when_neither_side_can_win():
    calls = candidate_calls({"home_win": 0.0, "draw": 100.0, "away_win": 0.0})
    assert not any(c.market == DNB for c in calls)


@pytest.mark.parametrize(
    "score, selection, expected",
    [
        ((2, 0), "home", Outcome.WON),
        ((0, 1), "home", Outcome.LOST),
        ((1, 1), "home", Outcome.VOID),  # the stake is returned
        ((0, 1), "away", Outcome.WON),
        ((3, 1), "away", Outcome.LOST),
        ((0, 0), "away", Outcome.VOID),
    ],
)
def test_a_draw_returns_the_stake_so_it_is_void_not_lost(score, selection, expected):
    assert settle(DNB, selection, _result(*score)) is expected
    assert settle_key(f"dnb:{selection}", _result(*score)) is expected


def test_an_unknown_selection_is_void_rather_than_a_loss():
    assert settle(DNB, "draw", _result(1, 0)) is Outcome.VOID


def test_a_draw_no_bet_pick_can_lead_when_it_clears_the_bar():
    ranked = rank_calls(candidate_calls(PREDICTION), BASE_RATES)

    lead = headline_call(ranked)

    assert lead.call.market == DNB
    assert lead.call.selection == "home"


def test_it_does_not_lead_without_a_lean_over_its_own_base_rate():
    """Even odds between the sides is a 50% DNB, below the 60% a home side wins when there is a
    winner: not a finding, so it does not take the headline from a real one."""
    even = {"home_win": 40.0, "draw": 20.0, "away_win": 40.0}
    ranked = rank_calls(candidate_calls(even), BASE_RATES)

    dnb = [r for r in ranked if r.call.market == DNB]

    assert all(r.lift is not None and r.lift < 5.0 for r in dnb if r.call.selection == "home")


def test_it_is_a_column_on_the_match_page():
    ranked = rank_calls(candidate_calls(PREDICTION), BASE_RATES)
    assert DNB in [r.call.market for r in best_per_market(ranked)]


def test_its_base_rate_is_how_often_a_side_wins_when_there_is_a_winner():
    from app.services.base_rates import _rates_from_row

    row = {
        "n": 1000,
        "mr_home": 0.44,
        "mr_draw": 0.26,
        "mr_away": 0.30,
        "btts_yes": None,
        "n_ht": 0,
        "n_corners": 0,
        "n_cards": 0,
    }
    rates = _rates_from_row(_with_lines(row), 100)

    assert rates["dnb:home"] == pytest.approx(0.44 / 0.74 * 100.0, abs=0.1)
    assert rates["dnb:away"] == pytest.approx(0.30 / 0.74 * 100.0, abs=0.1)


def _with_lines(row):
    from app.services import base_rates

    filled = dict(row)
    for select in base_rates._select_list():
        alias = select.rsplit(" AS ", 1)[-1]
        filled.setdefault(alias, None)
    return filled


def test_a_call_with_the_dnb_key_matches_the_settlement_key():
    assert Call(DNB, "home", "x", 60.0).key == "dnb:home"
