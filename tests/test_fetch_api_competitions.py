"""Tests for ingesting API-Football competitions.

`tests/data/api_football_sample.json` holds real fixtures from the 2024-25
Copa del Rey and Segunda Liga Portugal, trimmed. The Copa del Rey final is in
it, and it is the case this module exists for: Barcelona beat Real Madrid 3-2
after extra time, so the API's `goals` says 3-2 while the 90-minute score —
the one the engine predicts — is 2-2.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from app.models import Match, Team
from ml.api_competitions import BY_ID, BY_NAME, enabled_families, family_of
from scripts.fetch_api_competitions import (
    TeamResolver,
    apply_team_mapping,
    ingest_competition_season,
    parse_fixture,
    season_label,
)

SAMPLE = json.loads(
    (Path(__file__).parent / "data" / "api_football_sample.json").read_text(encoding="utf-8")
)
COPA = BY_ID[143]


def _cup(round_name=None, status=None):
    items = [i for i in SAMPLE["cup"] if round_name is None or i["league"]["round"] == round_name]
    if status:
        items = [i for i in items if i["fixture"]["status"]["short"] == status]
    return items[0]


# --- the 90-minute score ----------------------------------------------------


def test_a_tie_settled_in_extra_time_is_recorded_at_its_90_minute_score():
    final = _cup("Final")
    assert (final["goals"]["home"], final["goals"]["away"]) == (3, 2)  # what the API headlines

    row = parse_fixture(final, COPA)

    assert (row["home_score"], row["away_score"]) == (2, 2)  # what the engine predicts
    assert row["beyond_90"] is True


def test_a_tie_settled_on_penalties_is_recorded_level():
    row = parse_fixture(_cup(status="PEN"), COPA)
    assert row["home_score"] == row["away_score"]
    assert row["beyond_90"] is True


def test_an_ordinary_result_is_unchanged():
    row = parse_fixture(_cup("Round of 16", "FT"), COPA)
    assert row["beyond_90"] is False
    assert row["external_id"].startswith("apif-")


def test_a_postponed_match_is_not_a_result():
    postponed = next(i for i in SAMPLE["cup"] if i["fixture"]["status"]["short"] == "PST")
    assert parse_fixture(postponed, COPA) is None


def test_an_awarded_match_is_not_a_result():
    """Nobody scored in a technical loss; it says nothing about how teams play."""
    awarded = next(i for i in SAMPLE["cup"] if i["fixture"]["status"]["short"] == "AWD")
    assert parse_fixture(awarded, COPA) is None


# --- neutral ground ---------------------------------------------------------


def test_a_cup_final_is_at_a_neutral_venue_and_other_rounds_are_not():
    assert parse_fixture(_cup("Final"), COPA)["neutral_venue"] is True
    assert (
        parse_fixture(_cup("Semi-finals"), COPA)["neutral_venue"] is False
    )  # two legs, home and away
    assert parse_fixture(_cup("Round of 16", "FT"), COPA)["neutral_venue"] is False


def test_the_fa_cup_semi_finals_are_neutral_because_they_are_at_wembley():
    fa_cup = BY_ID[45]
    assert fa_cup.is_neutral("Semi-finals") and fa_cup.is_neutral("Final")
    assert not fa_cup.is_neutral("Quarter-finals")
    assert not fa_cup.is_neutral(None)


# --- season labels ----------------------------------------------------------


def test_a_split_year_competition_is_labelled_across_both_years():
    assert season_label(2024, True) == "2024-2025"


def test_a_calendar_year_competition_is_labelled_with_the_one_year():
    assert season_label(2025, False) == "2025"


def test_a_partial_batch_gets_the_same_label_as_the_full_season():
    """Only April's cup final is in hand, yet it belongs to 2024-2025. The label
    comes from the competition, not from which matches happened to arrive."""
    ingested = _ingest_labels([_cup("Final")])
    assert ingested == {"2024-2025"}


def test_every_registered_competition_states_its_calendar():
    from ml.api_competitions import API_COMPETITIONS

    assert all(isinstance(c.split_year, bool) for c in API_COMPETITIONS)
    assert BY_ID[143].split_year is True


# --- club identity ----------------------------------------------------------


def test_a_club_is_found_by_its_api_id_before_its_name(db_session):
    known = Team(name="Ath Bilbao", league="Spanish La Liga", sport="football", api_football_id=531)
    db_session.add(known)
    db_session.flush()

    resolver = TeamResolver(db_session)

    assert resolver.resolve("Athletic Club", 531, "Spanish Copa del Rey").id == known.id
    assert resolver.created == []


def test_an_unknown_club_is_created_not_fuzzy_matched_to_a_lookalike(db_session):
    """On name alone, "Atletico Madrid" is closest to Brazil's "Atletico-MG". It
    must become its own row, to be paired properly by roster, not merged."""
    brazil = Team(name="Atletico-MG", league="Brazilian Serie A", sport="football")
    db_session.add(brazil)
    db_session.flush()

    resolver = TeamResolver(db_session)
    team = resolver.resolve("Atletico Madrid", 530, "Spanish Copa del Rey")

    assert team.id != brazil.id
    assert team.api_football_id == 530
    assert [name for name, _, _ in resolver.created] == ["Atletico Madrid"]


def test_a_shared_name_with_a_different_api_id_is_a_different_club(db_session):
    db_session.add(
        Team(name="Racing", league="Spanish La Liga", sport="football", api_football_id=1)
    )
    db_session.flush()

    resolver = TeamResolver(db_session)
    other = resolver.resolve("Racing", 2, "Portuguese Segunda Liga")

    assert other.api_football_id == 2
    assert other.name == "Racing (Portuguese Segunda Liga)"


def test_a_name_match_teaches_the_club_its_api_id(db_session):
    plain = Team(name="Barcelona", league="Spanish La Liga", sport="football")
    db_session.add(plain)
    db_session.flush()

    TeamResolver(db_session).resolve("Barcelona", 529, "Spanish Copa del Rey")

    assert plain.api_football_id == 529


def test_roster_mapping_pairs_clubs_one_to_one_and_writes_their_ids(db_session):
    names = {"Ath Bilbao": 531, "Ath Madrid": 530, "Celta": 538, "Espanol": 540}
    teams = [Team(name=n, league="Spanish La Liga", sport="football") for n in names]
    db_session.add_all(teams)
    db_session.flush()
    # A season of matches so each club is on the 2024-2025 La Liga roster.
    for a, b in zip(teams, teams[1:] + teams[:1], strict=True):
        db_session.add(
            Match(
                match_date=datetime(2024, 9, 1),
                competition="Spanish La Liga",
                season="2024-2025",
                home_team_id=a.id,
                away_team_id=b.id,
                status="completed",
                home_score=1,
                away_score=0,
            )
        )
    db_session.flush()

    api = [(531, "Athletic Club"), (530, "Atletico Madrid"), (538, "Celta Vigo"), (540, "Espanyol")]
    result = apply_team_mapping(db_session, "Spanish La Liga", "2024-2025", api)

    assert result["written"] == 4 and result["review"] == []
    assert {t.name: t.api_football_id for t in teams} == names


# --- ingestion --------------------------------------------------------------


def _ingest(db_session, items=None):
    items = SAMPLE["cup"] if items is None else items
    return ingest_competition_season(db_session, COPA, 2024, items, TeamResolver(db_session))


def test_ingestion_stores_finished_matches_with_the_right_shape(db_session):
    counts = _ingest(db_session)

    # Seven fixtures in the sample; the postponed and the awarded are not results.
    assert counts == {"fetched": 7, "finished": 5, "inserted": 5, "existing": 0}
    final = (
        db_session.query(Match)
        .filter(Match.competition == "Spanish Copa del Rey", Match.neutral_venue.is_(True))
        .one()
    )
    assert (final.home_score, final.away_score) == (2, 2)
    assert final.season == "2024-2025"
    assert final.status == "completed"
    assert final.external_id.startswith("apif-")


def test_ingesting_the_same_season_twice_adds_nothing(db_session):
    _ingest(db_session)
    again = _ingest(db_session)

    assert again["inserted"] == 0 and again["existing"] == 5
    assert db_session.query(Match).filter_by(competition="Spanish Copa del Rey").count() == 5


def test_a_fixture_already_held_under_another_id_is_not_duplicated(db_session):
    """The same match can arrive from a CSV with a different id."""
    final = _cup("Final")
    home = Team(name="Barcelona", league="Spanish La Liga", sport="football", api_football_id=529)
    away = Team(name="Real Madrid", league="Spanish La Liga", sport="football", api_football_id=541)
    db_session.add_all([home, away])
    db_session.flush()
    db_session.add(
        Match(
            external_id="csv-hash-123",
            match_date=datetime(2025, 4, 26, 21, 0),
            competition="Spanish Copa del Rey",
            season="2024-2025",
            home_team_id=home.id,
            away_team_id=away.id,
            status="completed",
            home_score=2,
            away_score=2,
        )
    )
    db_session.flush()

    counts = _ingest(db_session, [final])

    assert counts["inserted"] == 0 and counts["existing"] == 1


# --- the registry -----------------------------------------------------------


def test_nothing_is_enabled_so_the_feature_schema_is_unchanged():
    """Enabling a competition widens the feature vector, which needs a retrain
    and a restart. It must only ever happen in the same change that carries the
    data and the retrained models."""
    assert enabled_families() == []


def test_a_regional_group_shares_its_tiers_family():
    groups = [c for c in BY_NAME.values() if c.family == "Spanish Tercera RFEF"]
    assert len(groups) == 18
    assert len({c.name for c in groups}) == 18  # each group still has its own table
    assert family_of("Spanish Tercera RFEF - Group 7") == "Spanish Tercera RFEF"


def test_every_registry_entry_is_well_formed():
    ids = [c.api_id for c in BY_ID.values()]
    assert len(ids) == len(set(ids))
    for comp in BY_ID.values():
        assert comp.first_season <= comp.last_season
        assert comp.kind in {"league", "cup"}
        assert (comp.tier is None) == (comp.kind == "cup")
        assert comp.country_code
    cups = [c for c in BY_ID.values() if c.kind == "cup"]
    assert all(c.neutral_rounds for c in cups), "every cup final is at a neutral venue"


@pytest.mark.parametrize(
    "api_id,name",
    [
        (143, "Spanish Copa del Rey"),
        (81, "German DFB Pokal"),
        (137, "Italian Coppa Italia"),
        (66, "French Coupe de France"),
        (90, "Dutch KNVB Beker"),
        (96, "Portuguese Taca de Portugal"),
        (45, "English FA Cup"),
        (48, "English League Cup"),
    ],
)
def test_the_main_domestic_cups_are_registered_as_core(api_id, name):
    comp = BY_ID[api_id]
    assert comp.name == name and comp.kind == "cup" and comp.scope == "core"


def _ingest_labels(items):
    """Season labels that ingesting `items` writes, via a throwaway session."""
    from app.database.session import SessionLocal

    session = SessionLocal()
    try:
        ingest_competition_season(session, COPA, 2024, items, TeamResolver(session))
        labels = {s for (s,) in session.query(Match.season).filter(Match.competition == COPA.name)}
        session.rollback()
        return labels
    finally:
        session.close()
