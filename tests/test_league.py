"""Tests for the per-competition page: GET /leagues/{slug}.

The behaviours worth pinning are the ones that stop a page claiming more than
the data supports: a rate that is a dash rather than a zero, form that is only
named while it is recent, no table for a competition where a table means
nothing, and a slug that names nothing returning 404 rather than an empty page.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.models import Match, Team
from app.services.league_service import (
    _outcome_rates,
    competition_for_slug,
    season_label,
    slug_for,
)

PREMIER_LEAGUE = "English Premier League"


def _teams(db_session, *names: str) -> list[Team]:
    teams = [Team(name=n, league=PREMIER_LEAGUE, elo_rating=1500) for n in names]
    db_session.add_all(teams)
    db_session.flush()
    return teams


def _result(
    db_session,
    competition: str,
    home: Team,
    away: Team,
    when: datetime,
    score: tuple[int, int],
    season: str = "2025-2026",
):
    db_session.add(
        Match(
            match_date=when,
            competition=competition,
            season=season,
            home_team_id=home.id,
            away_team_id=away.id,
            status="completed",
            home_score=score[0],
            away_score=score[1],
        )
    )


def _season_of_results(db_session, ended_days_ago: int) -> None:
    """Three teams, eight matches each; Alpha wins everything it plays."""
    alpha, beta, gamma = _teams(db_session, "Alpha", "Beta", "Gamma")
    newest = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=ended_days_ago)
    pairs = [(alpha, beta, (2, 0)), (beta, gamma, (1, 1)), (gamma, alpha, (0, 3))]
    day = 0
    for _ in range(4):
        for home, away, score in pairs:
            _result(db_session, PREMIER_LEAGUE, home, away, newest - timedelta(days=day), score)
            day += 1
    db_session.commit()


# --- pure helpers ----------------------------------------------------------


def test_rates_are_none_not_zero_when_there_is_nothing_to_measure():
    rates = _outcome_rates([])
    assert rates["matches"] == 0
    assert rates["home_win"] is None
    assert rates["over_2_5"] is None
    assert rates["btts"] is None


def test_rates_count_what_they_say():
    # 2-0 home, 1-1 draw, 0-3 away, 2-2 draw
    rates = _outcome_rates([(2, 0), (1, 1), (0, 3), (2, 2)])
    assert rates["home_win"] == 25.0
    assert rates["draw"] == 50.0
    assert rates["away_win"] == 25.0
    assert rates["over_2_5"] == 50.0  # 0-3 and 2-2
    assert rates["btts"] == 50.0  # 1-1 and 2-2


def test_a_calendar_year_season_is_shown_as_the_year_it_is():
    assert season_label("2525") == "2025"
    assert season_label("2025-2025") == "2025"
    assert season_label("2024-2025") == "2024-2025"
    assert season_label(None) is None


def test_a_slug_resolves_to_its_competition_and_back():
    meta = competition_for_slug("english-premier-league")
    assert meta is not None
    assert meta.competition == PREMIER_LEAGUE
    assert slug_for(PREMIER_LEAGUE) == "english-premier-league"
    assert competition_for_slug("no-such-league") is None


# --- the route --------------------------------------------------------------


def test_an_unknown_slug_is_a_404(client):
    assert client.get("/leagues/no-such-league").status_code == 404


def test_a_competition_with_no_results_reports_nothing_rather_than_zeros(client):
    body = client.get("/leagues/english-premier-league").json()
    assert body["history"]["matches"] == 0
    assert body["history"]["home_win"] is None
    assert body["last_match_age_days"] is None
    assert body["standings"] == []
    assert body["hot_team"] is None
    assert body["fixtures"] == []


def test_the_page_carries_the_table_and_rates_for_a_played_season(client, db_session):
    _season_of_results(db_session, ended_days_ago=3)
    body = client.get("/leagues/english-premier-league").json()

    assert body["history"]["matches"] == 12
    assert body["teams"] == 3
    assert body["season"] == "2025-2026"
    assert body["standings"][0]["team"] == "Alpha"
    assert body["standings"][0]["points"] == 24  # 8 wins from 8
    assert body["slug"] == "english-premier-league"
    assert len(body["results"]) == 10


def test_hot_and_cold_are_named_while_the_results_are_recent(client, db_session):
    _season_of_results(db_session, ended_days_ago=3)
    body = client.get("/leagues/english-premier-league").json()

    assert body["hot_team"]["team"] == "Alpha"
    assert body["hot_team"]["points"] == 15  # five wins
    assert body["hot_team"]["results"] == "WWWWW"
    assert body["cold_team"]["team"] != "Alpha"
    assert body["form_window"] == 5


def test_hot_and_cold_are_withheld_once_the_results_are_old(client, db_session):
    """Last season's last five are not "current form", whatever they were."""
    _season_of_results(db_session, ended_days_ago=300)
    body = client.get("/leagues/english-premier-league").json()

    assert body["last_match_age_days"] >= 300
    assert body["hot_team"] is None
    assert body["cold_team"] is None
    # The table is still returned — it is labelled by season on the page.
    assert body["standings"]


def test_an_international_competition_has_no_table_and_no_form(client, db_session):
    home, away = _teams(db_session, "Brazil", "Chile")
    _result(
        db_session,
        "International Friendlies",
        home,
        away,
        datetime.now(UTC).replace(tzinfo=None) - timedelta(days=2),
        (2, 1),
        season="2026",
    )
    db_session.commit()
    body = client.get("/leagues/international-friendlies").json()

    assert body["is_international"] is True
    assert body["history"]["matches"] == 1
    assert body["standings"] == []
    assert body["teams"] is None
    assert body["hot_team"] is None


def test_the_leagues_index_carries_a_slug_for_every_competition(client):
    countries = client.get("/leagues").json()["countries"]
    entries = [entry for country in countries for entry in country["competitions"]]
    assert entries
    assert all(entry["slug"] == slug_for(entry["competition"]) for entry in entries)
    assert len({entry["slug"] for entry in entries}) == len(entries)
