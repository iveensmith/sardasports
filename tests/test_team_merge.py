"""Folding a duplicate club into the club it duplicates, and the mapping fixes.

The duplicates were real: the first scheduled run of the live feed created nine
clubs, every one a club we already held under another spelling — "Flamengo"
beside "Flamengo RJ", "HJK Helsinki" beside "HJK". Each starts at the default
rating, so each fixture would have been a coin-flip prediction.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.models import EloHistory, Injury, Match, Team
from app.services.team_identity import merge_team
from app.utils.seasons import season_start_year
from scripts import fetch_upcoming_fixtures as live
from scripts.fetch_api_competitions import _stored_labels


def _club(db_session, name, api_id=None, sport="football"):
    team = Team(name=name, league="Brazilian Serie A", sport=sport, api_football_id=api_id)
    db_session.add(team)
    db_session.flush()
    return team


def _match(
    db_session, home, away, status="scheduled", season="2626", competition="Brazilian Serie A"
):
    match = Match(
        match_date=datetime(2026, 10, 7, 22, 30),
        competition=competition,
        season=season,
        home_team_id=home.id,
        away_team_id=away.id,
        status=status,
        home_score=1 if status == "completed" else None,
        away_score=0 if status == "completed" else None,
    )
    db_session.add(match)
    db_session.flush()
    return match


# --- merging -------------------------------------------------------------------


def test_a_duplicate_is_folded_into_the_club_it_duplicates(db_session):
    keeper = _club(db_session, "Flamengo RJ")
    duplicate = _club(db_session, "Flamengo", api_id=127)
    rival = _club(db_session, "Santos", api_id=128)
    fixture = _match(db_session, rival, duplicate)  # the duplicate is the away side
    other = _match(db_session, duplicate, rival)  # and the home side

    result = merge_team(db_session, duplicate, keeper)

    assert (fixture.home_team_id, fixture.away_team_id) == (rival.id, keeper.id)
    assert (other.home_team_id, other.away_team_id) == (keeper.id, rival.id)
    assert keeper.api_football_id == 127  # the keeper learns the duplicate's id
    assert db_session.query(Team).filter_by(name="Flamengo").count() == 0
    assert result["needs_elo_rebuild"] is False  # nothing had been rated yet


def test_rating_history_and_injuries_follow_the_merge(db_session):
    keeper = _club(db_session, "HJK")
    duplicate = _club(db_session, "HJK Helsinki", api_id=649)
    rival = _club(db_session, "VPS")
    match = _match(db_session, duplicate, rival, status="completed")
    db_session.add(
        EloHistory(
            team_id=duplicate.id,
            match_id=match.id,
            match_date=match.match_date,
            rating_before=1500.0,
            rating_after=1510.0,
            opponent_team_id=rival.id,
            was_home=True,
        )
    )
    db_session.add(
        EloHistory(
            team_id=rival.id,
            match_id=match.id,
            match_date=match.match_date,
            rating_before=1500.0,
            rating_after=1490.0,
            opponent_team_id=duplicate.id,
            was_home=False,
        )
    )
    db_session.flush()

    result = merge_team(db_session, duplicate, keeper)

    histories = db_session.query(EloHistory).all()
    assert {(h.team_id, h.opponent_team_id) for h in histories} == {
        (keeper.id, rival.id),
        (rival.id, keeper.id),
    }
    # Those ratings were computed for a club that does not exist.
    assert result["needs_elo_rebuild"] is True
    assert db_session.query(Injury).count() == 0


def test_two_clubs_with_different_api_ids_are_different_clubs_and_are_not_merged(db_session):
    a = _club(db_session, "Racing", api_id=1)
    b = _club(db_session, "Racing Club", api_id=2)
    with pytest.raises(ValueError, match="different clubs"):
        merge_team(db_session, a, b)
    assert db_session.query(Team).count() == 2


def test_a_team_cannot_be_merged_into_itself_or_across_sports(db_session):
    club = _club(db_session, "Santos")
    player = _club(db_session, "A Player", sport="tennis")
    with pytest.raises(ValueError):
        merge_team(db_session, club, club)
    with pytest.raises(ValueError, match="different sports"):
        merge_team(db_session, player, club)


def test_the_keepers_own_api_id_is_never_overwritten(db_session):
    keeper = _club(db_session, "Vasco", api_id=133)
    duplicate = _club(db_session, "Vasco DA Gama", api_id=133)
    merge_team(db_session, duplicate, keeper)
    assert keeper.api_football_id == 133


# --- season labels in the mapping tool ---------------------------------------------


@pytest.mark.parametrize(
    "label,year",
    [
        ("2024-2025", 2024),
        ("2025-2025", 2025),  # the old calendar-year spelling
        ("2525", 2025),  # a doubled two-digit year
        ("2424", 2024),
        ("2022", 2022),  # a bare year
        ("garbage", None),
        ("", None),
    ],
)
def test_a_stored_season_label_is_read_back_to_its_year(label, year):
    assert season_start_year(label) == year


def test_a_calendar_year_leagues_season_is_found_by_its_year(db_session):
    """`startswith("2024")` never matches "2424", so the mapping tool skipped every
    calendar-year league — Brazil, Finland, Ireland — the very ones in play."""
    home, away = _club(db_session, "A"), _club(db_session, "B")
    _match(db_session, home, away, season="2424")
    _match(db_session, home, away, season="2525")

    assert _stored_labels(db_session, "Brazilian Serie A", 2024) == {"2424"}
    assert _stored_labels(db_session, "Brazilian Serie A", 2025) == {"2525"}
    assert _stored_labels(db_session, "Brazilian Serie A", 2023) == set()  # no request needed


# --- the live loader says when it invents a club ----------------------------------------


def test_the_live_loader_warns_by_name_when_it_creates_a_club(db_session, caplog):
    row = {
        "external_id": "apif-1",
        "match_date": datetime(2026, 10, 8, 20, 0),
        "competition": "Brazilian Serie A",
        "season": None,
        "season_year": 2026,
        "neutral_venue": False,
        "home_team": "Flamengo",
        "away_team": "Santos",
        "home_api_id": 127,
        "away_api_id": 128,
    }
    with caplog.at_level("WARNING", logger=live.logger.name):
        live.load_rows(db_session, [row])

    message = " ".join(r.getMessage() for r in caplog.records)
    assert "Created 2 club(s)" in message
    assert "Flamengo (api 127)" in message and "Santos (api 128)" in message
    assert "--map-teams" in message


def test_the_live_loader_is_quiet_when_every_club_is_already_known(db_session, caplog):
    _club(db_session, "Flamengo RJ", api_id=127)
    _club(db_session, "Santos", api_id=128)
    row = {
        "external_id": "apif-2",
        "match_date": datetime(2026, 10, 8, 20, 0),
        "competition": "Brazilian Serie A",
        "season": None,
        "season_year": 2026,
        "neutral_venue": False,
        "home_team": "Flamengo",
        "away_team": "Santos",
        "home_api_id": 127,
        "away_api_id": 128,
    }
    with caplog.at_level("WARNING", logger=live.logger.name):
        live.load_rows(db_session, [row])

    assert not [r for r in caplog.records if "Created" in r.getMessage()]
    assert db_session.query(Team).count() == 2  # resolved by API id, nothing invented
