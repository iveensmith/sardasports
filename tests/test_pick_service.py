"""Choosing the selection to lead with.

The dangerous failure here is not a crash — it is a confident, wrong number.
A fixture where a competitor has ten matches of history produces an
arithmetically correct "+276% expected value" that is pure model error, and
the engine's own backtest (-6.74% against bookmaker odds) says such edges do
not exist at that scale. These tests pin the guards.
"""

from __future__ import annotations

import pytest

from app.services.pick_service import (
    THIN_EVIDENCE_MATCHES,
    best_pick,
    candidates_for,
    most_likely_outcome,
)

ODDS = {
    "match_winner": {"home": 2.80, "draw": 3.20, "away": 2.80},
    "btts": {"yes": 1.83, "no": 2.00},
    "goals": {"over_1.5": 1.40, "over_2.5": 2.21, "under_2.5": 1.73},
}

PREDICTION = {
    "home_win": 48.7,
    "draw": 26.0,
    "away_win": 25.3,
    "btts_yes": 55.0,
    "btts_no": 45.0,
    "goals_markets": [
        {"line": 1.5, "prob_over": 72.0, "prob_under": 28.0, "model_used": True},
        {"line": 2.5, "prob_over": 45.7, "prob_under": 54.3, "model_used": True},
    ],
}

UNANIMOUS = {"agreeing": 3, "total": 3, "unanimous": True, "pick": "home"}


def test_candidates_pair_every_priced_market_with_a_model_probability():
    found = candidates_for(PREDICTION, ODDS)
    labels = {c.label for c in found}
    assert "Home" in labels and "Draw" in labels and "Away" in labels
    assert "Both teams score" in labels
    assert "Over 1.5" in labels and "Over 2.5" in labels and "Under 2.5" in labels


def test_a_price_with_no_model_behind_it_is_never_a_candidate():
    """The engine prices no 3.5 goals line, so a price for one is ignored."""
    odds = {"goals": {"over_3.5": 4.20}}
    assert candidates_for(PREDICTION, odds) == []


def test_quarter_lines_are_ignored():
    """Asian-style splits have no equivalent in this engine."""
    odds = {"goals": {"over_2.25": 1.35, "over_1.75": 1.15}}
    assert candidates_for(PREDICTION, odds) == []


def test_expected_value_and_fair_price_are_defined_as_documented():
    found = [c for c in candidates_for(PREDICTION, ODDS) if c.label == "Home"][0]
    # model 48.7% at 2.80 -> fair 1/0.487, EV 0.487*2.80 - 1
    assert found.fair_price == pytest.approx(1 / 0.487, rel=1e-6)
    assert found.expected_value == pytest.approx(0.487 * 2.80 - 1, rel=1e-6)
    assert found.market_implied == pytest.approx(1 / 2.80, rel=1e-6)


def test_the_pick_is_the_highest_expected_value_not_the_likeliest_outcome():
    """A short-priced favourite is not automatically the pick.

    Over 1.5 is the likeliest selection here at 72%, but priced at 1.40 it
    is worth less than the 48.7% home side at 2.80.
    """
    pick = best_pick(PREDICTION, ODDS, UNANIMOUS, home_matches=500, away_matches=500)
    assert pick["label"] == "Home"
    assert pick["model_probability"] == pytest.approx(48.7)


def test_no_odds_means_no_pick_rather_than_the_models_favourite():
    assert best_pick(PREDICTION, None, UNANIMOUS) is None
    assert best_pick(PREDICTION, {}, UNANIMOUS) is None


def test_no_prediction_means_no_pick():
    assert best_pick(None, ODDS, UNANIMOUS) is None


# --- the guard that matters ----------------------------------------------


def test_thin_evidence_is_flagged_when_either_side_lacks_history():
    """One side short of the threshold is enough to taint the comparison."""
    pick = best_pick(PREDICTION, ODDS, UNANIMOUS, home_matches=10, away_matches=500)
    assert pick["thin_evidence"] is True
    assert pick["min_competitor_matches"] == 10


def test_thin_evidence_rationale_says_the_gap_is_ignorance_not_value():
    """The number stays; the claim about what it means changes.

    Suppressing it would hide a real model output; presenting it unqualified
    would assert free money the backtest says is not there.
    """
    pick = best_pick(PREDICTION, ODDS, UNANIMOUS, home_matches=10, away_matches=500)
    assert "too few matches" in pick["rationale"]
    assert "expected value" in pick["rationale"]  # the figure is still reported


def test_well_evidenced_fixtures_are_not_flagged():
    pick = best_pick(PREDICTION, ODDS, UNANIMOUS, home_matches=500, away_matches=400)
    assert pick["thin_evidence"] is False
    assert "too few matches" not in pick["rationale"]


def test_the_threshold_boundary_is_inclusive_of_the_threshold():
    at_threshold = best_pick(
        PREDICTION,
        ODDS,
        UNANIMOUS,
        home_matches=THIN_EVIDENCE_MATCHES,
        away_matches=THIN_EVIDENCE_MATCHES,
    )
    below = best_pick(
        PREDICTION,
        ODDS,
        UNANIMOUS,
        home_matches=THIN_EVIDENCE_MATCHES - 1,
        away_matches=THIN_EVIDENCE_MATCHES,
    )
    assert at_threshold["thin_evidence"] is False
    assert below["thin_evidence"] is True


def test_unknown_match_counts_do_not_falsely_flag():
    """Absent counts mean unknown, not thin."""
    pick = best_pick(PREDICTION, ODDS, UNANIMOUS)
    assert pick["thin_evidence"] is False
    assert pick["min_competitor_matches"] is None


def test_negative_expected_value_is_reported_plainly():
    """The normal case against efficient odds, and it must not be hidden."""
    # Every selection priced below its fair value, as efficient odds are:
    #   home 0.60*1.50-1 = -10%, draw 0.25*3.00-1 = -25%, away 0.15*5.00-1 = -25%
    # so the best available is still a losing proposition, and that is what
    # gets reported.
    odds = {"match_winner": {"home": 1.50, "draw": 3.0, "away": 5.0}}
    prediction = {"home_win": 60.0, "draw": 25.0, "away_win": 15.0, "goals_markets": []}
    pick = best_pick(prediction, odds, UNANIMOUS, home_matches=500, away_matches=500)
    assert pick["label"] == "Home"
    assert pick["expected_value"] == pytest.approx(-10.0, abs=0.1)
    assert pick["positive_value"] is False
    assert "-10.0% expected value" in pick["rationale"]


# --- forecast vs value: they answer different questions -------------------
#
# The bug these pin: the board row led with the highest-expected-value
# selection while the fixture's own detail page led with the most likely
# outcome. For Spain v Croatia that meant the row said "Away" (14.50) and the
# detail page said Spain 65%. Both were right; nothing said they were
# different questions, so the product looked broken and a 14% shot read as a
# prediction.


def test_the_forecast_is_the_most_likely_outcome_not_the_best_price():
    """The exact shape that surfaced the bug."""
    prediction = {"home_win": 65.3, "draw": 20.6, "away_win": 14.2, "goals_markets": []}
    odds = {"match_winner": {"home": 1.22, "draw": 7.83, "away": 14.5}}

    forecast = most_likely_outcome(prediction, "Spain", "Croatia")
    assert forecast["selection"] == "home"
    assert forecast["label"] == "Spain to win"
    assert forecast["probability"] == pytest.approx(65.3)

    # And the value pick still, correctly, disagrees — 14.2% at 14.50 is a
    # positive-EV selection. That is why it cannot be the headline.
    pick = best_pick(prediction, odds, UNANIMOUS, home_matches=500, away_matches=500)
    assert pick["selection"] == "away"
    assert pick["expected_value"] > 0
    assert forecast["selection"] != pick["selection"]


def test_the_forecast_names_the_team_a_reader_sees():
    prediction = {"home_win": 10.0, "draw": 25.0, "away_win": 65.0}
    assert most_likely_outcome(prediction, "Lesotho", "Morocco")["label"] == "Morocco to win"


def test_a_draw_can_be_the_forecast_and_names_no_team():
    prediction = {"home_win": 28.0, "draw": 40.0, "away_win": 32.0}
    forecast = most_likely_outcome(prediction, "Spain", "Croatia")
    assert forecast["selection"] == "draw"
    assert forecast["label"] == "Draw"


def test_the_forecast_needs_no_odds():
    """What the model expects does not depend on anyone pricing it — unlike
    `best_pick`, which returns None without odds."""
    prediction = {"home_win": 55.0, "draw": 25.0, "away_win": 20.0, "goals_markets": []}
    assert most_likely_outcome(prediction, "A", "B")["selection"] == "home"
    assert best_pick(prediction, None, UNANIMOUS) is None


def test_no_prediction_means_no_forecast():
    assert most_likely_outcome(None, "A", "B") is None
    assert most_likely_outcome({}, "A", "B") is None


def test_a_prediction_with_no_match_winner_probabilities_has_no_forecast():
    """Rather than reporting a zero as if it were a real reading."""
    assert most_likely_outcome({"home_win": None, "draw": None, "away_win": None}, "A", "B") is None


def test_the_forecast_matches_the_probability_the_detail_page_renders():
    """The two pages read the same field, so they cannot drift apart."""
    prediction = {"home_win": 48.7, "draw": 26.0, "away_win": 25.3}
    forecast = most_likely_outcome(prediction, "Home Team", "Away Team")
    assert forecast["probability"] == pytest.approx(
        max(prediction["home_win"], prediction["draw"], prediction["away_win"])
    )


# --- the rationale must not borrow support the estimators never gave -----


def test_value_on_the_losing_side_says_so_rather_than_claiming_agreement():
    """The sentence that made the board look self-contradictory.

    It read "All 3 estimators back the same outcome; model 14% against
    market 7%" about a Croatia selection those same estimators unanimously
    made the loser. "The same outcome" as what was never stated, so it
    parsed as an endorsement of the selection it was attached to.
    """
    prediction = {"home_win": 65.3, "draw": 20.6, "away_win": 14.2, "goals_markets": []}
    odds = {"match_winner": {"home": 1.22, "draw": 7.83, "away": 14.5}}
    agreement = {"agreeing": 3, "total": 3, "unanimous": True, "pick": "home"}

    pick = best_pick(prediction, odds, agreement, home_matches=500, away_matches=500)
    assert pick["selection"] == "away"
    assert "This is the price, not the forecast" in pick["rationale"]
    assert "make Home the likelier result" in pick["rationale"]
    assert "back this outcome" not in pick["rationale"]


def test_value_on_the_forecast_keeps_the_endorsement():
    """When they *do* agree, saying so is accurate and useful."""
    prediction = {"home_win": 48.7, "draw": 26.0, "away_win": 25.3, "goals_markets": []}
    odds = {"match_winner": {"home": 2.80, "draw": 3.20, "away": 2.80}}
    agreement = {"agreeing": 3, "total": 3, "unanimous": True, "pick": "home"}

    pick = best_pick(prediction, odds, agreement, home_matches=500, away_matches=500)
    assert pick["selection"] == "home"
    assert "All 3 estimators back this outcome" in pick["rationale"]


def test_a_goals_selection_does_not_borrow_match_result_agreement():
    """The estimators vote on the match result. They have said nothing about
    whether a game goes over 2.5, so claiming their support invents it."""
    prediction = {
        "home_win": 40.0,
        "draw": 30.0,
        "away_win": 30.0,
        "goals_markets": [{"line": 2.5, "prob_over": 62.0, "prob_under": 38.0, "model_used": True}],
    }
    odds = {"goals": {"over_2.5": 2.60}}
    agreement = {"agreeing": 3, "total": 3, "unanimous": True, "pick": "home"}

    pick = best_pick(prediction, odds, agreement, home_matches=500, away_matches=500)
    assert pick["label"] == "Over 2.5"
    assert "not this market" in pick["rationale"]
    assert "estimators back" not in pick["rationale"]


def test_thin_evidence_still_overrides_every_agreement_wording():
    """The thin-data caveat is the most important thing on the row, so it
    wins regardless of which way the estimators voted."""
    prediction = {"home_win": 65.3, "draw": 20.6, "away_win": 14.2, "goals_markets": []}
    odds = {"match_winner": {"home": 1.22, "draw": 7.83, "away": 14.5}}
    agreement = {"agreeing": 3, "total": 3, "unanimous": True, "pick": "home"}

    pick = best_pick(prediction, odds, agreement, home_matches=10, away_matches=500)
    assert "too few matches" in pick["rationale"]
    assert "estimators" not in pick["rationale"]
