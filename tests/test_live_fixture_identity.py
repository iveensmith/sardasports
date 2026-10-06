"""The live fixture feed must give a club one identity, and a season one label.

Both failure modes were silent. A club whose API spelling differed from
Football-Data's was created as a *new* team at the default rating, so its next
fixture got a coin-flip prediction. A fixture labelled "2026" beside a history
that says "2026-2027" sat in a season bucket of its own, so the league's table
and form were computed over the wrong matches. Neither raises an error.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.models import Match, Team
from app.utils.seasons import fallback_label, label_like
from scripts import fetch_upcoming_fixtures as live
from scripts.fetch_upcoming_fixtures import load_rows, rows_from_fixtures


def _item(home, away, league_id, round_name="Regular Season - 3", season=2026, fixture_id=1):
    return {
        "fixture": {
            "id": fixture_id,
            "date": "2026-10-10T14:00:00+00:00",
            "status": {"short": "NS"},
        },
        "league": {"id": league_id, "season": season, "round": round_name},
        "teams": {
            "home": {"id": home[0], "name": home[1]},
            "away": {"id": away[0], "name": away[1]},
        },
    }


@pytest.fixture
def with_registry_competitions(monkeypatch):
    """Pretend the 3. Liga (80) and the Copa del Rey (143) are enabled."""
    monkeypatch.setitem(live.LEAGUE_ID_TO_COMPETITION, 80, "German 3. Liga")
    monkeypatch.setitem(live.LEAGUE_ID_TO_COMPETITION, 143, "Spanish Copa del Rey")


# --- reserve sides ----------------------------------------------------------


def test_a_reserve_side_in_a_registered_league_is_a_real_member(with_registry_competitions):
    """Bayern II plays in the 3. Liga. The reserve filter is for the Friendlies feed."""
    rows, skipped = rows_from_fixtures([_item((1, "Bayern Munich II"), (2, "Ulm"), 80)])
    assert len(rows) == 1 and skipped == 0
    assert rows[0]["home_team"] == "Bayern Munich II"


def test_a_youth_side_in_the_friendlies_feed_is_still_excluded():
    rows, skipped = rows_from_fixtures([_item((1, "England U17"), (2, "Israel U17"), 10)])
    assert rows == [] and skipped == 1


# --- neutral ground ---------------------------------------------------------


def test_a_registered_cup_final_is_neutral_and_other_rounds_are_not(with_registry_competitions):
    final, _ = rows_from_fixtures([_item((1, "A"), (2, "B"), 143, "Final")])
    early, _ = rows_from_fixtures([_item((1, "A"), (2, "B"), 143, "Round of 16", fixture_id=2)])
    assert final[0]["neutral_venue"] is True
    assert early[0]["neutral_venue"] is False


# --- club identity ----------------------------------------------------------


def test_a_club_arriving_under_its_api_spelling_is_the_existing_club(db_session):
    known = Team(name="Ath Bilbao", league="Spanish La Liga", sport="football", api_football_id=531)
    other = Team(name="Barcelona", league="Spanish La Liga", sport="football", api_football_id=529)
    db_session.add_all([known, other])
    db_session.flush()
    rows = [
        {
            "external_id": "apif-1",
            "match_date": datetime(2026, 10, 10, 14, 0),
            "competition": "Spanish La Liga",
            "season": "2026-2027",
            "season_year": 2026,
            "neutral_venue": False,
            "home_team": "Athletic Club",
            "away_team": "Barcelona",
            "home_api_id": 531,
            "away_api_id": 529,
        }
    ]

    inserted, _ = load_rows(db_session, rows)

    assert inserted == 1
    match = db_session.query(Match).one()
    assert match.home_team_id == known.id  # not a fresh "Athletic Club" at 1500
    assert db_session.query(Team).count() == 2


# --- season labels ----------------------------------------------------------


def _row(competition, month=10):
    return {
        "external_id": f"apif-{competition}",
        "match_date": datetime(2026, month, 10, 14, 0),
        "competition": competition,
        "season": None,
        "season_year": 2026,
        "neutral_venue": False,
        "home_team": "Home FC",
        "away_team": "Away FC",
        "home_api_id": None,
        "away_api_id": None,
    }


def _history(db_session, competition, season):
    home = Team(name=f"{competition} H", league=competition, sport="football")
    away = Team(name=f"{competition} A", league=competition, sport="football")
    db_session.add_all([home, away])
    db_session.flush()
    db_session.add(
        Match(
            match_date=datetime(2026, 5, 1),
            competition=competition,
            season=season,
            home_team_id=home.id,
            away_team_id=away.id,
            status="completed",
            home_score=1,
            away_score=0,
        )
    )
    db_session.flush()


def test_a_live_fixture_joins_its_leagues_split_year_season(db_session):
    _history(db_session, "Dutch Eredivisie", "2025-2026")
    load_rows(db_session, [_row("Dutch Eredivisie")])
    live_match = db_session.query(Match).filter(Match.status == "scheduled").one()
    assert live_match.season == "2026-2027"


def test_a_live_fixture_joins_a_calendar_year_leagues_doubled_label(db_session):
    _history(db_session, "Major League Soccer", "2525")
    load_rows(db_session, [_row("Major League Soccer", month=3)])
    live_match = db_session.query(Match).filter(Match.status == "scheduled").one()
    assert live_match.season == "2626"


def test_a_competition_with_no_history_falls_back_on_when_its_season_starts(db_session):
    load_rows(db_session, [_row("Brand New League", month=10)])
    assert db_session.query(Match).one().season == "2026-2027"


# --- the label helper -------------------------------------------------------


@pytest.mark.parametrize(
    "sample,year,expected",
    [
        ("2025-2026", 2026, "2026-2027"),  # split-year
        ("2025-2025", 2026, "2026-2026"),  # the older calendar-year spelling
        ("2525", 2026, "2626"),  # doubled two-digit year
        ("2022", 2026, "2026"),  # a bare year
        ("garbage", 2026, None),
        ("", 2026, None),
    ],
)
def test_label_like_extends_whatever_shape_the_history_uses(sample, year, expected):
    assert label_like(sample, year) == expected


def test_the_fallback_follows_when_football_starts():
    assert fallback_label(2026, 8) == "2026-2027"
    assert fallback_label(2026, 3) == "2026"
