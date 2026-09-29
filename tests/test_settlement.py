"""Grading calls against results.

The whole accountability claim rests on this module: if settlement is wrong,
every win rate on the site is wrong, and wrong in the flattering direction is
the easy mistake to make. The tests that matter most here are the ones about
absent data, because that is where a grader silently inflates itself.
"""

from __future__ import annotations

import pytest

from app.services.settlement import (
    MatchResult,
    Outcome,
    Record,
    settle,
    settle_key,
    tally,
)

HOME_WIN = MatchResult(home_score=2, away_score=0)
DRAW = MatchResult(home_score=1, away_score=1)
AWAY_WIN = MatchResult(home_score=0, away_score=3)
GOALLESS = MatchResult(home_score=0, away_score=0)


# --- match result and double chance --------------------------------------


@pytest.mark.parametrize(
    "result,selection,expected",
    [
        (HOME_WIN, "home", Outcome.WON),
        (HOME_WIN, "draw", Outcome.LOST),
        (HOME_WIN, "away", Outcome.LOST),
        (DRAW, "draw", Outcome.WON),
        (DRAW, "home", Outcome.LOST),
        (AWAY_WIN, "away", Outcome.WON),
    ],
)
def test_match_result_settles_on_the_final_score(result, selection, expected):
    assert settle("match_result", selection, result) is expected


@pytest.mark.parametrize(
    "result,selection,expected",
    [
        (HOME_WIN, "home_draw", Outcome.WON),
        (DRAW, "home_draw", Outcome.WON),
        (AWAY_WIN, "home_draw", Outcome.LOST),
        (DRAW, "away_draw", Outcome.WON),
        (AWAY_WIN, "away_draw", Outcome.WON),
        (HOME_WIN, "away_draw", Outcome.LOST),
        (HOME_WIN, "home_away", Outcome.WON),
        (AWAY_WIN, "home_away", Outcome.WON),
        (DRAW, "home_away", Outcome.LOST),
    ],
)
def test_double_chance_covers_exactly_two_outcomes(result, selection, expected):
    assert settle("double_chance", selection, result) is expected


# --- goals lines ----------------------------------------------------------


def test_over_and_under_are_exact_opposites_on_a_half_line():
    """Lines are half-numbers throughout, so a push is impossible."""
    result = MatchResult(home_score=2, away_score=1)  # three goals
    assert settle("goals", "over_2.5", result) is Outcome.WON
    assert settle("goals", "under_2.5", result) is Outcome.LOST
    assert settle("goals", "over_3.5", result) is Outcome.LOST
    assert settle("goals", "under_3.5", result) is Outcome.WON


def test_a_goalless_draw_settles_every_under_line():
    assert settle("goals", "under_1.5", GOALLESS) is Outcome.WON
    assert settle("goals", "over_1.5", GOALLESS) is Outcome.LOST


# --- both teams to score --------------------------------------------------


def test_btts_needs_a_goal_from_each_side():
    assert settle("btts", "yes", MatchResult(1, 1)) is Outcome.WON
    assert settle("btts", "yes", MatchResult(3, 0)) is Outcome.LOST
    assert settle("btts", "no", MatchResult(3, 0)) is Outcome.WON
    assert settle("btts", "no", GOALLESS) is Outcome.WON


# --- the part that inflates a grader if you get it wrong ------------------


def test_an_unrecorded_stat_is_void_not_lost():
    """Several competitions record no corners. A corners call on one of them
    was never settleable, and calling it a loss understates the engine as
    surely as calling it a win flatters it."""
    no_corners = MatchResult(home_score=1, away_score=0)
    assert settle("corners", "over_9.5", no_corners) is Outcome.VOID
    assert settle("corners", "under_9.5", no_corners) is Outcome.VOID


def test_a_missing_side_voids_rather_than_counting_as_zero():
    """The bug this guards: `(home or 0) + (away or 0)` turns an unrecorded
    corner count into zero corners, which grades every "under" call on the
    fixture as a win."""
    half_recorded = MatchResult(home_score=1, away_score=0, home_corners=6, away_corners=None)
    assert settle("corners", "under_9.5", half_recorded) is Outcome.VOID


def test_a_recorded_zero_is_not_the_same_as_unrecorded():
    """A genuinely goalless first half settles; an unrecorded one does not."""
    played = MatchResult(home_score=1, away_score=0, home_ht_goals=0, away_ht_goals=0)
    unrecorded = MatchResult(home_score=1, away_score=0)
    assert settle("ht_goals", "under_0.5", played) is Outcome.WON
    assert settle("ht_goals", "under_0.5", unrecorded) is Outcome.VOID


def test_cards_settle_on_both_colours_combined():
    booked = MatchResult(home_score=0, away_score=0, home_cards=2, away_cards=3)
    assert settle("cards", "over_4.5", booked) is Outcome.WON
    assert settle("cards", "under_4.5", booked) is Outcome.LOST


def test_an_unknown_market_is_void_rather_than_lost():
    """If this module has not been taught to settle something, that is our
    omission. Recording it as a loss scores the engine for our ignorance."""
    assert settle("asian_handicap", "home_-1.5", HOME_WIN) is Outcome.VOID
    assert settle("match_result", "both_teams_win", HOME_WIN) is Outcome.VOID


# --- keys match ml.markets.Call.key ---------------------------------------


def test_a_call_key_settles_without_translation():
    """`settle_key` takes exactly what `Call.key` produces, so the two
    modules cannot drift apart over a naming change."""
    result = MatchResult(home_score=2, away_score=1, home_ht_goals=1, away_ht_goals=0)
    assert settle_key("match_result:home", result) is Outcome.WON
    assert settle_key("double_chance:home_draw", result) is Outcome.WON
    assert settle_key("goals:over_2.5", result) is Outcome.WON
    assert settle_key("btts:yes", result) is Outcome.WON
    assert settle_key("ht_goals:over_0.5", result) is Outcome.WON


def test_a_malformed_key_is_void():
    assert settle_key("nonsense", HOME_WIN) is Outcome.VOID


# --- the record -----------------------------------------------------------


def test_void_calls_are_excluded_from_the_win_rate():
    """Including them would make the sample size a lie."""
    record = tally([Outcome.WON, Outcome.WON, Outcome.LOST, Outcome.VOID, Outcome.VOID])
    assert record.settled == 3
    assert record.win_rate == pytest.approx(66.7)
    assert record.void == 2


def test_nothing_settleable_reports_no_rate_rather_than_zero():
    """ "No gradeable calls" and "graded and lost every one" are opposite
    facts and must not render as the same number."""
    assert tally([Outcome.VOID, Outcome.VOID]).win_rate is None
    assert tally([Outcome.LOST, Outcome.LOST]).win_rate == 0.0


def test_an_empty_record_has_no_rate():
    assert Record().win_rate is None
    assert Record().settled == 0


def test_the_record_serialises_every_field_the_ui_needs():
    body = tally([Outcome.WON, Outcome.LOST, Outcome.VOID]).as_dict()
    assert body == {"won": 1, "lost": 1, "void": 1, "settled": 2, "win_rate": 50.0}
