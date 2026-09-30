"""Assembling and grading a board row.

The row is where a prediction becomes something a reader can check: a pick in
each column, a price beside it, and — once the match is played — a verdict.
These tests cover the two ways that goes wrong quietly. A price attached to
the wrong selection makes every expected value on the page nonsense, and an
ungraded row rendering as a loss makes the engine look worse than it is on
exactly the fixtures it has not been judged on yet.
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest

from app.services.board_service import (
    BOARD_COLUMNS,
    build_row,
    confidence_out_of_ten,
    is_won,
    match_id_from_slug,
    match_slug,
    odds_for,
    slugify,
)

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
}

PREDICTION = {
    "home_win": 62.0,
    "draw": 22.0,
    "away_win": 16.0,
    "btts_yes": 40.0,
    "btts_no": 60.0,
    "goals_markets": [
        {"line": 1.5, "prob_over": 70.0, "prob_under": 30.0, "model_used": True},
        {"line": 2.5, "prob_over": 45.0, "prob_under": 55.0, "model_used": True},
    ],
    "confidence": 84.0,
    "confidence_label": "High",
}

ODDS = {
    "match_winner": {"home": 1.55, "draw": 4.00, "away": 6.50},
    "goals": {"over_2.5": 2.05, "under_2.5": 1.80},
    "btts": {"yes": 2.10, "no": 1.72},
}


def _match(**overrides):
    defaults = {
        "id": 4242,
        "match_date": datetime(2026, 5, 21, 19, 45),
        "competition": "Spanish La Liga",
        "sport": "football",
        "status": "scheduled",
        "home_team_id": 1,
        "away_team_id": 2,
        "home_score": None,
        "away_score": None,
        "home_ht_goals": None,
        "away_ht_goals": None,
        "home_corners": None,
        "away_corners": None,
        "home_yellow_cards": None,
        "away_yellow_cards": None,
        "home_red_cards": None,
        "away_red_cards": None,
        "odds_markets": ODDS,
    }
    return SimpleNamespace(**{**defaults, **overrides})


def _row(**overrides):
    return build_row(_match(**overrides), PREDICTION, BASE_RATES, "Real Madrid", "Getafe")


# --- readable URLs --------------------------------------------------------


def test_slugify_folds_accents_rather_than_dropping_them():
    """Stripping instead of folding turns "Türkiye" into "trkiye"."""
    assert slugify("Türkiye") == "turkiye"
    assert slugify("Bayern München") == "bayern-munchen"
    assert slugify("Atlético Madrid") == "atletico-madrid"


def test_slugify_collapses_punctuation_to_single_hyphens():
    assert slugify("Bosnia & Herzegovina") == "bosnia-herzegovina"
    assert slugify("  Real  Madrid  ") == "real-madrid"


def test_a_slug_carries_the_id_for_exact_resolution():
    slug = match_slug("Spain", "Croatia", 144414)
    assert slug == "spain-vs-croatia-prediction-144414"
    assert match_id_from_slug(slug) == 144414


def test_the_name_part_of_a_slug_is_decoration():
    """A team renamed since the URL was shared still resolves, and a
    hand-edited slug cannot land on the wrong fixture."""
    assert match_id_from_slug("whatever-someone-typed-144414") == 144414


def test_a_slug_with_no_id_resolves_to_nothing_rather_than_guessing():
    assert match_id_from_slug("spain-vs-croatia") is None
    assert match_id_from_slug("") is None


# --- prices ---------------------------------------------------------------


def test_odds_are_looked_up_per_selection():
    assert odds_for("match_result", "home", ODDS) == 1.55
    assert odds_for("match_result", "away", ODDS) == 6.50
    assert odds_for("goals", "under_2.5", ODDS) == 1.80
    assert odds_for("btts", "no", ODDS) == 1.72


def test_an_unpriced_market_returns_no_price_rather_than_a_default():
    """Corners odds are never ingested at all, so there is nothing to derive
    them from — a fabricated price would make every expected value computed
    from it nonsense."""
    assert odds_for("corners", "over_9.5", ODDS) is None
    assert odds_for("match_result", "home", None) is None


def test_double_chance_price_is_derived_from_the_1x2_prices():
    """No bookmaker double-chance line is ingested, but "1X" is exactly "not
    2" — its fair price is computable from the same 1X2 prices already on
    the row: implied probabilities of the two legs, summed, inverted."""
    assert odds_for("double_chance", "home_draw", ODDS) == pytest.approx(1.12)
    assert odds_for("double_chance", "away_draw", ODDS) == pytest.approx(2.48)
    assert odds_for("double_chance", "home_away", ODDS) == pytest.approx(1.25)


def test_double_chance_price_needs_both_legs_quoted():
    assert odds_for("double_chance", "home_draw", {"match_winner": {"home": 1.55}}) is None
    assert odds_for("double_chance", "home_draw", None) is None
    assert odds_for("double_chance", "unknown_selection", ODDS) is None


def test_an_impossible_price_is_rejected():
    """A price of 1.00 or below pays nothing and is bad data, not a bargain."""
    assert odds_for("match_result", "home", {"match_winner": {"home": 1.0}}) is None
    assert odds_for("match_result", "home", {"match_winner": {"home": "n/a"}}) is None


# --- confidence -----------------------------------------------------------


def test_confidence_is_rescaled_to_ten_for_the_board():
    assert confidence_out_of_ten(84.0) == 8.4
    assert confidence_out_of_ten(95.5) == 9.6
    assert confidence_out_of_ten(None) is None


# --- the row --------------------------------------------------------------


def test_a_row_carries_a_pick_in_every_board_column():
    row = _row()
    assert set(row["tips"]) == set(BOARD_COLUMNS)
    assert row["best_tip"] is not None
    assert row["confidence"] == 8.4


def test_the_best_tip_gets_a_real_derived_price_when_one_is_available():
    """This fixture's headline is the double-chance call (84% beats 62% for
    a plain home win) — a market with no bookmaker line of its own, but a
    real price derivable from the 1X2 prices already ingested. It should
    use that, not the fair-price fallback."""
    row = _row()
    assert row["best_tip"]["market"] == "double_chance"
    assert row["best_tip"]["odds"] is not None
    assert row["best_tip"]["odds_is_estimated"] is False


def test_the_best_tip_always_has_a_price_even_when_nothing_was_quoted():
    """A fixture no bookmaker priced at all still has to lead with
    something — the pick's own fair price, computed from its probability
    and clearly flagged as an estimate rather than a market price."""
    row = _row(odds_markets=None)
    best = row["best_tip"]
    assert best["odds"] is not None
    assert best["odds_is_estimated"] is True
    assert best["odds"] == pytest.approx(round(100.0 / best["probability"], 2))

    # The regular board columns make no such promise — they show the real
    # gap in market coverage rather than papering over it.
    assert all(tip["odds"] is None for tip in row["tips"].values())
    assert all(tip["odds_is_estimated"] is False for tip in row["tips"].values())


def test_competition_metadata_is_resolved_for_the_country_sidebar():
    row = _row()
    assert row["competition"]["country"] == "Spain"
    assert row["competition"]["short_name"] == "La Liga"
    assert row["competition"]["tier"] == 1


def test_an_uncatalogued_competition_is_ungrouped_rather_than_guessed():
    """A wrong flag beside a match is worse than no flag."""
    row = build_row(_match(competition="Some Invitational Cup"), PREDICTION, BASE_RATES, "A", "B")
    assert row["competition"]["country"] is None
    assert row["competition"]["short_name"] == "Some Invitational Cup"


def test_an_unplayed_fixture_has_no_score_and_no_verdict():
    """None, not 0-0 — which is a real scoreline — and no outcome, so an
    ungraded row can never render as a loss."""
    row = _row()
    assert row["score"] is None
    assert row["best_tip"]["outcome"] is None
    assert all(tip["outcome"] is None for tip in row["tips"].values())
    assert is_won(row) is False


def test_a_played_fixture_grades_every_column():
    # 3-0: home win, over 2.5, both teams did not score.
    row = _row(status="completed", home_score=3, away_score=0)
    assert row["score"] == {"home": 3, "away": 0}
    assert row["tips"]["match_result"]["outcome"] == "won"  # picked home
    assert row["tips"]["goals"]["outcome"] == "lost"  # picked under 2.5
    assert row["tips"]["btts"]["outcome"] == "won"  # picked no


def test_the_best_tip_is_graded_and_drives_the_rows_verdict():
    row = _row(status="completed", home_score=3, away_score=0)
    assert row["best_tip"]["outcome"] == "won"
    assert is_won(row) is True

    lost = _row(status="completed", home_score=0, away_score=2)
    assert lost["best_tip"]["outcome"] == "lost"
    assert is_won(lost) is False


def test_a_market_with_no_recorded_stat_grades_void_not_lost():
    """This fixture records no corners, so a corners call was never
    settleable. The row must not be scored for it either way."""
    from app.services.settlement import Outcome, result_from_match, settle_key

    match = _match(status="completed", home_score=1, away_score=0)
    result = result_from_match(match)
    assert settle_key("corners:over_9.5", result) is Outcome.VOID


def test_a_fixture_with_no_prediction_still_produces_a_row():
    """A competition with no trained model appears on the board unpredicted
    rather than being dropped from the day's card."""
    row = build_row(_match(), None, BASE_RATES, "A", "B")
    assert row["tips"] == {}
    assert row["best_tip"] is None
    assert row["confidence"] is None
    assert row["home_team"] == "A"


def test_prices_reach_the_cells_they_belong_to():
    row = _row()
    match_result = row["tips"]["match_result"]
    assert match_result["selection"] == "home"
    assert match_result["odds"] == pytest.approx(1.55)
    goals = row["tips"]["goals"]
    assert goals["odds"] == odds_for("goals", goals["selection"], ODDS)
