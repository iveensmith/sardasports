"""Tests for pairing API-Football clubs with our team rows.

The cases are real: the names are what Football-Data.co.uk and API-Football
actually call these clubs, taken from the 2024-25 La Liga, Serie A and
Bundesliga rosters. The point of the module is that name similarity alone is
not safe — the trap cases below are ones where the nearest string is a
different club entirely.
"""

from __future__ import annotations

from app.services.team_identity import assign_clubs, similarity, tokens


def _pairs(api, ours):
    return {m.api_name: m.our_name for m in assign_clubs(api, ours)}


def test_football_data_abbreviations_meet_the_api_full_names():
    api = [(1, "Athletic Club"), (2, "Atletico Madrid"), (3, "Celta Vigo"), (4, "Espanyol")]
    ours = ["Ath Bilbao", "Ath Madrid", "Celta", "Espanol"]
    assert _pairs(api, ours) == {
        "Athletic Club": "Ath Bilbao",
        "Atletico Madrid": "Ath Madrid",
        "Celta Vigo": "Celta",
        "Espanyol": "Espanol",
    }


def test_a_different_club_with_a_closer_string_is_not_chosen_when_context_rules_it_out():
    """On name alone "Atletico Madrid" is closer to Brazil's "Atletico-MG" than
    to "Ath Madrid". Pairing a whole league one-to-one is what gets it right:
    the Brazilian club is not on the roster, and Athletic Club has claimed
    "Ath Bilbao"."""
    api = [(1, "Atletico Madrid"), (2, "Athletic Club")]
    ours = ["Ath Madrid", "Ath Bilbao"]
    assert _pairs(api, ours) == {
        "Atletico Madrid": "Ath Madrid",
        "Athletic Club": "Ath Bilbao",
    }


def test_german_clubs_with_umlauts_and_apostrophes_pair_up():
    api = [(1, "Borussia Mönchengladbach"), (2, "Bayern München"), (3, "FSV Mainz 05")]
    ours = ["M'gladbach", "Bayern Munich", "Mainz"]
    assert _pairs(api, ours) == {
        "Borussia Mönchengladbach": "M'gladbach",
        "Bayern München": "Bayern Munich",
        "FSV Mainz 05": "Mainz",
    }


def test_a_reserve_side_is_not_its_senior_club():
    """Real Madrid Castilla and Real Madrid share almost every word."""
    assert similarity("Real Madrid", "Real Madrid") > similarity(
        "Real Madrid", "Real Madrid Castilla"
    )
    api = [(1, "Real Madrid"), (2, "Real Madrid Castilla")]
    ours = ["Real Madrid", "Real Madrid Castilla"]
    assert _pairs(api, ours) == {
        "Real Madrid": "Real Madrid",
        "Real Madrid Castilla": "Real Madrid Castilla",
    }


def test_an_api_club_with_no_counterpart_is_reported_new_not_forced_into_a_pair():
    api = [(1, "Barcelona"), (2, "SV Elversberg")]
    result = assign_clubs(api, ["Barcelona"])
    by_name = {m.api_name: m for m in result}
    assert by_name["Barcelona"].our_name == "Barcelona"
    assert not by_name["Barcelona"].needs_review
    assert by_name["SV Elversberg"].our_name is None
    assert by_name["SV Elversberg"].needs_review


def test_a_weak_pair_is_flagged_for_a_person_not_trusted():
    api = [(1, "Chiclana")]
    result = assign_clubs(api, ["China"])
    assert result[0].needs_review


def test_with_nothing_to_pair_against_every_club_is_new():
    result = assign_clubs([(1, "Leganes"), (2, "Castellon")], [])
    assert all(m.our_name is None and m.needs_review for m in result)
    assert assign_clubs([], ["Leganes"]) == []


def test_generic_words_do_not_make_two_clubs_look_alike():
    # "FC" and "CF" say nothing about which club it is.
    assert tokens("FC Cartagena") == tokens("Cartagena") == ["cartagena"]
    assert similarity("FC Cartagena", "Cartagena") == 1.0
