"""A team's own page: slug lookup, results from the team's side, and its table.

The properties worth pinning are the ones a reader would notice being wrong: a
slug that opens the wrong club, a win shown as a loss because the team was the
away side, and a league position invented for a team that has no league.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.models import Match, Team
from app.services.team_page_service import (
    _letter,
    build_team_page,
    resolve_team,
    team_slug,
)

LEAGUE = "English Premier League"


def _team(db_session, name: str) -> Team:
    team = Team(name=name, league=LEAGUE, elo_rating=1600)
    db_session.add(team)
    db_session.flush()
    return team


def _match(db_session, home: Team, away: Team, when: datetime, score=None, *, competition=LEAGUE):
    match = Match(
        match_date=when,
        competition=competition,
        season="2026-2027",
        home_team_id=home.id,
        away_team_id=away.id,
        status="completed" if score else "scheduled",
        home_score=None if score is None else score[0],
        away_score=None if score is None else score[1],
    )
    db_session.add(match)
    db_session.flush()
    return match


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def test_a_team_slug_folds_accents_like_the_fixture_slug():
    assert team_slug("Bayern München") == "bayern-munchen"
    assert team_slug("Aston Villa") == "aston-villa"
    assert team_slug("  Real  Madrid ") == "real-madrid"


def test_a_slug_finds_its_team_and_an_unknown_one_finds_nothing(db_session):
    villa = _team(db_session, "Aston Villa")
    db_session.commit()

    assert resolve_team(db_session, "aston-villa").id == villa.id
    assert resolve_team(db_session, "no-such-club") is None


def test_two_clubs_folding_to_one_slug_resolve_to_the_one_with_more_matches(db_session):
    big = _team(db_session, "Real Madrid")
    small = _team(db_session, "Real  Madrid")  # folds to the same slug
    other = _team(db_session, "Getafe")
    for day in range(1, 4):
        _match(db_session, big, other, datetime(2026, 9, day, 15), (1, 0))
    _match(db_session, small, other, datetime(2026, 9, 10, 15), (1, 0))
    db_session.commit()

    assert resolve_team(db_session, "real-madrid").id == big.id


@pytest.mark.parametrize(
    "team, home, away, expected",
    [
        ("A", 2, 1, "W"),  # at home, won
        ("B", 2, 1, "L"),  # away, lost
        ("B", 1, 2, "W"),  # away, won — the case a home-only reading gets wrong
        ("A", 1, 1, "D"),
    ],
)
def test_a_result_is_read_from_the_teams_own_side(team, home, away, expected):
    match = {"home_team": "A", "away_team": "B", "home_score": home, "away_score": away}
    assert _letter(match, team) == expected


def test_an_unplayed_match_has_no_result_letter():
    match = {"home_team": "A", "away_team": "B", "home_score": None, "away_score": None}
    assert _letter(match, "A") is None


def test_recent_matches_carry_the_result_for_this_team_not_for_the_home_side(db_session):
    villa = _team(db_session, "Aston Villa")
    spurs = _team(db_session, "Tottenham Hotspur")
    _match(db_session, spurs, villa, _now() - timedelta(days=3), (2, 3))  # Villa won away
    db_session.commit()

    page = build_team_page(db_session, villa)

    assert page["recent_matches"][0]["result"] == "W"
    assert page["recent_matches"][0]["is_home"] is False
    assert page["form_letters"] == ["W"]
    assert page["last_match_age_days"] == 3


def test_form_is_newest_first(db_session):
    villa = _team(db_session, "Aston Villa")
    other = _team(db_session, "Everton")
    _match(db_session, villa, other, _now() - timedelta(days=9), (0, 2))  # L, oldest
    _match(db_session, villa, other, _now() - timedelta(days=2), (3, 0))  # W, newest
    db_session.commit()

    assert build_team_page(db_session, villa)["form_letters"] == ["W", "L"]


def test_only_future_unplayed_matches_are_listed_as_next(db_session):
    villa = _team(db_session, "Aston Villa")
    other = _team(db_session, "Everton")
    _match(db_session, villa, other, _now() - timedelta(days=2), (1, 0))  # played
    upcoming = _match(db_session, other, villa, _now() + timedelta(days=2))
    db_session.commit()

    page = build_team_page(db_session, villa)

    assert [m["match_id"] for m in page["upcoming"]] == [upcoming.id]
    assert page["upcoming"][0]["is_home"] is False
    assert page["upcoming"][0]["slug"].endswith(f"-prediction-{upcoming.id}")


def test_a_team_in_a_tiered_league_gets_a_table_position(db_session):
    villa = _team(db_session, "Aston Villa")
    other = _team(db_session, "Everton")
    _match(db_session, villa, other, _now() - timedelta(days=2), (2, 0))
    db_session.commit()

    standing = build_team_page(db_session, villa)["standing"]

    assert standing["position"] == 1
    assert standing["of"] == 2
    assert build_team_page(db_session, villa)["team"]["is_national"] is False
    assert standing["row"]["points"] == 3
    assert standing["slug"] == "english-premier-league"


def test_a_national_side_has_no_league_position_rather_than_an_invented_one(db_session):
    brazil = _team(db_session, "Brazil")
    chile = _team(db_session, "Chile")
    _match(
        db_session,
        brazil,
        chile,
        _now() - timedelta(days=5),
        (1, 0),
        competition="International Friendlies",
    )
    db_session.commit()

    page = build_team_page(db_session, brazil)

    assert page["standing"] is None
    assert page["form_letters"] == ["W"]
    assert page["team"]["is_national"] is True


def test_a_team_with_no_matches_still_builds_an_empty_page(db_session):
    lonely = _team(db_session, "Lonely FC")
    db_session.commit()

    page = build_team_page(db_session, lonely)

    assert page["recent_matches"] == []
    assert page["form_letters"] == []
    assert page["last_match_age_days"] is None
    assert page["standing"] is None
    assert page["upcoming"] == []


def test_the_endpoint_serves_a_known_slug_and_404s_an_unknown_one(client, db_session):
    _team(db_session, "Aston Villa")
    db_session.commit()

    ok = client.get("/teams/aston-villa")
    assert ok.status_code == 200
    assert ok.json()["team"]["slug"] == "aston-villa"
    assert client.get("/teams/no-such-club").status_code == 404


# --- the top-rated list used for footer navigation -----------------------------------------


def test_top_rated_teams_are_ranked_by_rating_and_limited_to_recent_league_play(db_session):
    from app.services.team_page_service import top_rated_teams

    strong = _team(db_session, "Strong FC")
    strong.elo_rating = 1900
    middling = _team(db_session, "Middling FC")
    middling.elo_rating = 1700
    dormant = _team(db_session, "Dormant FC")
    dormant.elo_rating = 2000  # the highest rated, but has not played lately
    other = _team(db_session, "Opponent FC")
    other.elo_rating = 1500

    _match(db_session, strong, middling, _now() - timedelta(days=10), (1, 0))
    _match(db_session, dormant, other, _now() - timedelta(days=400), (1, 0))
    db_session.commit()

    names = [t["name"] for t in top_rated_teams(db_session, limit=10)]

    # Ranked by rating; the dormant club is excluded however high its rating.
    assert names == ["Strong FC", "Middling FC"]
    assert "Dormant FC" not in names


def test_national_sides_are_left_out_of_the_top_rated_list(db_session):
    from app.services.team_page_service import top_rated_teams

    brazil = _team(db_session, "Brazil")
    brazil.elo_rating = 2100
    chile = _team(db_session, "Chile")
    _match(
        db_session,
        brazil,
        chile,
        _now() - timedelta(days=5),
        (1, 0),
        competition="International Friendlies",
    )
    db_session.commit()

    assert top_rated_teams(db_session) == []


def test_the_top_rated_endpoint_returns_a_list(client):
    response = client.get("/teams?limit=3")
    assert response.status_code == 200
    assert response.json() == {"teams": []}
