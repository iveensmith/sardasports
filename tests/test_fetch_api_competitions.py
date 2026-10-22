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
from ml.api_competitions import (
    API_COMPETITIONS,
    BY_ID,
    BY_NAME,
    COUNTRY_CODES,
    enabled_families,
    family_of,
)
from scripts.fetch_api_competitions import (
    TeamResolver,
    _already_ingested,
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
    assert counts == {"fetched": 7, "finished": 5, "inserted": 5, "existing": 0, "corrected": 0}
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
        assert comp.kind in {"league", "cup", "national"}
        assert (comp.tier is None) == (comp.kind != "league")
        # Every nation has a flag; a confederation ("Europe", "Asia", "World") is a
        # grouping and deliberately has none.
        assert (comp.country_code is None) == (comp.country not in COUNTRY_CODES)
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


# --- the UEFA club competitions ---------------------------------------------

UCL = BY_ID[2]


def _ucl(round_name, status=None):
    items = [i for i in SAMPLE["ucl"] if i["league"]["round"] == round_name]
    if status:
        items = [i for i in items if i["fixture"]["status"]["short"] == status]
    return items[0]


def test_the_three_uefa_club_competitions_are_registered_under_europe():
    names = {
        2: "UEFA Champions League",
        3: "UEFA Europa League",
        848: "UEFA Conference League",
    }
    for api_id, name in names.items():
        comp = BY_ID[api_id]
        assert comp.name == name and comp.country == "Europe" and comp.kind == "cup"
        assert comp.country_code is None and comp.tier is None
        assert comp.split_year is True  # the season starts in July
        assert comp.scope == "core"


def test_uefa_club_competitions_are_not_in_the_national_team_pool():
    """They sit under "Europe" beside the Euros, but they are made of clubs. The
    national-team Poisson pool must not swallow them."""
    from ml.competitions import INTERNATIONAL_COMPETITIONS, fit_pool

    for name in ("UEFA Champions League", "UEFA Europa League", "UEFA Conference League"):
        assert name not in INTERNATIONAL_COMPETITIONS
        assert fit_pool(name) == name


def test_the_champions_league_final_is_neutral_and_recorded_at_90_minutes():
    row = parse_fixture(_ucl("Final"), UCL)
    assert row["neutral_venue"] is True
    assert (row["home_score"], row["away_score"]) == (5, 0)  # PSG 5-0 Inter


def test_a_league_stage_match_is_an_ordinary_home_and_away_fixture():
    row = parse_fixture(_ucl("League Stage - 4"), UCL)
    assert row["neutral_venue"] is False
    assert (row["home_score"], row["away_score"]) == (4, 0)


def test_a_qualifying_round_match_is_ingested_like_any_other():
    """Qualifiers bring in clubs from across Europe; they are results all the same."""
    row = parse_fixture(_ucl("1st Qualifying Round", "FT"), UCL)
    assert row is not None and row["round"] == "1st Qualifying Round"


def test_a_second_leg_settled_on_penalties_keeps_its_own_90_minute_score():
    """In a two-legged tie extra time is triggered by the aggregate, so the
    second leg's 90-minute score is not level. Ballkani v UE Santa Coloma:
    the API's headline `goals` is 1-2 (extra time included), the match's own
    90-minute score is 0-1 — and it is the latter that is recorded."""
    item = _ucl("1st Qualifying Round", "PEN")
    assert (item["goals"]["home"], item["goals"]["away"]) == (1, 2)

    row = parse_fixture(item, UCL)

    assert (row["home_score"], row["away_score"]) == (0, 1)
    assert row["home_score"] != row["away_score"]  # not level, unlike a single-leg cup
    assert row["beyond_90"] is True


def test_the_champions_league_semi_final_is_not_neutral():
    """Two legs, home and away; only the final is at a neutral venue."""
    assert parse_fixture(_ucl("Semi-finals"), UCL)["neutral_venue"] is False


def test_champions_league_season_is_labelled_across_both_years(db_session):
    counts = ingest_competition_season(
        db_session, UCL, 2024, SAMPLE["ucl"], TeamResolver(db_session)
    )
    assert counts["inserted"] == 5
    assert {m.season for m in db_session.query(Match).filter(Match.competition == UCL.name)} == {
        "2024-2025"
    }


def _stored(db_session, comp, season, kickoff, external_id):
    home = Team(name=f"H-{external_id}", league="x", sport="football")
    away = Team(name=f"A-{external_id}", league="x", sport="football")
    db_session.add_all([home, away])
    db_session.flush()
    db_session.add(
        Match(
            external_id=external_id,
            match_date=kickoff,
            competition=comp.name,
            season=season,
            home_team_id=home.id,
            away_team_id=away.id,
            status="completed",
            home_score=1,
            away_score=0,
        )
    )
    db_session.flush()


def test_a_final_played_in_june_does_not_make_the_next_season_look_already_loaded(db_session):
    """The Champions League final is played in June. The check used a date window that
    reached into the following season, so 2016-17's final (3 June 2017) made 2017-18 read as
    loaded and it was never fetched: Champions League 2017, 2019 and 2023, Europa League 2020
    and Conference League 2023 were skipped on the first real ingest."""
    _stored(db_session, UCL, "2016-2017", datetime(2017, 6, 3, 18, 45), "apif-final-2017")

    assert _already_ingested(db_session, UCL, 2016) is True
    assert _already_ingested(db_session, UCL, 2017) is False


def test_a_season_with_no_matches_stored_is_not_already_loaded(db_session):
    assert _already_ingested(db_session, UCL, 2018) is False


# --- national-team competitions ---------------------------------------------

WORLD_CUP = BY_ID[1]


def _wc(round_name=None, status=None):
    items = SAMPLE["wc"]
    if round_name:
        items = [i for i in items if i["league"]["round"] == round_name]
    if status:
        items = [i for i in items if i["fixture"]["status"]["short"] == status]
    return items[0]


def test_the_national_registry_uses_only_the_four_calibrated_elo_weights():
    """90 / 80 / 70 / 45 are the tiers the first seven were calibrated on. A new
    competition is assigned to one of them; it does not get a number of its own."""
    nationals = [c for c in API_COMPETITIONS if c.kind == "national"]
    assert len(nationals) >= 40
    assert {c.elo_k for c in nationals} <= {90.0, 80.0, 70.0, 45.0}
    assert all(c.national_teams and c.elo_k is not None for c in nationals)


def test_the_seven_existing_internationals_are_registered_but_never_re_added():
    """They can be refetched for deeper history, but they already have a feature
    column and an Elo weight; enabling them must not give them a second."""
    existing = {c.name for c in API_COMPETITIONS if c.already_modelled}
    assert existing == {
        "FIFA World Cup",
        "UEFA European Championship",
        "UEFA Nations League",
        "Copa America",
        "Africa Cup of Nations",
        "Africa Cup of Nations Qualifiers",
        "International Friendlies",
    }
    from ml.api_competitions import enabled

    assert not any(c.already_modelled for c in enabled())


def test_national_competitions_use_tournament_years_not_split_seasons():
    assert all(not c.split_year for c in API_COMPETITIONS if c.kind == "national")


def test_every_qualifying_group_of_the_world_cup_shares_one_family():
    names = [c.name for c in API_COMPETITIONS if c.name.startswith("FIFA World Cup Qualification")]
    assert len(names) == 6
    assert {family_of(n) for n in names} == {"FIFA World Cup Qualification"}


def test_a_single_host_tournament_is_neutral_throughout_and_qualifiers_are_not():
    assert BY_ID[4].is_neutral("Group Stage - 1")  # Euros
    assert BY_ID[7].is_neutral("Quarter-finals")  # Asian Cup
    assert not BY_ID[32].is_neutral("Group A - 1")  # World Cup qualification: home and away
    assert not BY_ID[5].is_neutral("League A - 1")  # Nations League: home and away


def test_a_world_cup_final_is_stored_at_its_90_minute_score_not_its_penalty_score():
    final = _wc("Final")
    assert (final["goals"]["home"], final["goals"]["away"]) == (3, 3)  # extra time included

    row = parse_fixture(final, WORLD_CUP)

    assert (row["home_score"], row["away_score"]) == (2, 2)  # Argentina 2-2 France at 90
    assert row["neutral_venue"] is True


def test_a_stored_extra_time_score_is_corrected_to_the_90_minute_score(db_session):
    """The first loader for national teams read the API's headline score, so the
    2022 final sits in the database as 3-3 when it was 2-2 at 90 minutes."""
    home = Team(name="Argentina", league="FIFA World Cup", sport="football")
    away = Team(name="France", league="FIFA World Cup", sport="football")
    db_session.add_all([home, away])
    db_session.flush()
    held = Match(
        external_id="hash-from-the-csv-loader",
        match_date=datetime(2022, 12, 18),
        competition="FIFA World Cup",
        season="2022",
        home_team_id=home.id,
        away_team_id=away.id,
        status="completed",
        home_score=3,
        away_score=3,
    )
    db_session.add(held)
    db_session.flush()

    counts = ingest_competition_season(
        db_session, WORLD_CUP, 2022, [_wc("Final")], TeamResolver(db_session)
    )

    assert counts["existing"] == 1 and counts["inserted"] == 0 and counts["corrected"] == 1
    assert (held.home_score, held.away_score) == (2, 2)
    assert db_session.query(Match).filter_by(competition="FIFA World Cup").count() == 1


def test_a_match_decided_in_90_minutes_is_never_rewritten(db_session):
    group = _wc("Group Stage - 1")
    home = Team(name=group["teams"]["home"]["name"], league="FIFA World Cup", sport="football")
    away = Team(name=group["teams"]["away"]["name"], league="FIFA World Cup", sport="football")
    db_session.add_all([home, away])
    db_session.flush()
    kickoff = datetime.fromisoformat(group["fixture"]["date"]).replace(tzinfo=None)
    held = Match(
        external_id="hash",
        match_date=kickoff,
        competition="FIFA World Cup",
        season="2022",
        home_team_id=home.id,
        away_team_id=away.id,
        status="completed",
        home_score=9,
        away_score=9,
    )
    db_session.add(held)
    db_session.flush()

    counts = ingest_competition_season(
        db_session, WORLD_CUP, 2022, [group], TeamResolver(db_session)
    )

    # Only a match that went beyond 90 minutes is ever corrected; a discrepancy
    # on an ordinary result is somebody else's problem, not ours to overwrite.
    assert counts["corrected"] == 0
    assert (held.home_score, held.away_score) == (9, 9)


def test_an_under_age_side_is_dropped_from_a_friendlies_feed():
    friendlies = BY_ID[10]
    assert friendlies.exclude_youth
    senior = parse_fixture(_cup("Round of 16", "FT"), friendlies)
    assert senior is not None

    youth = json.loads(json.dumps(_cup("Round of 16", "FT")))
    youth["teams"]["home"]["name"] = "England U21"
    assert parse_fixture(youth, friendlies) is None


def test_a_registered_leagues_reserve_side_is_not_dropped():
    youth_named = json.loads(json.dumps(_cup("Round of 16", "FT")))
    youth_named["teams"]["home"]["name"] = "Bayern Munich II"
    assert parse_fixture(youth_named, BY_ID[80]) is not None  # the 3. Liga


def test_the_catalogue_knows_every_confederation():
    from ml.competition_catalogue import INTERNATIONAL_GROUPS

    confederations = {c.country for c in API_COMPETITIONS if c.kind == "national"}
    assert confederations <= INTERNATIONAL_GROUPS


def test_a_neutral_throughout_tournament_stays_neutral_when_the_feed_names_no_round():
    """The World Cup is single-host. A fixture with no round name must not lose that."""
    assert BY_ID[1].is_neutral(None) and BY_ID[1].is_neutral("Group Stage - 1")
    assert BY_ID[4].is_neutral(None)
    # A competition that is neutral only in some rounds still needs the round.
    assert not BY_ID[143].is_neutral(None)
    assert BY_ID[143].is_neutral("Final")
