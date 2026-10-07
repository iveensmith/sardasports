"""What the sitemap is fed.

Two properties matter to a crawler: only pages with real content are listed, and
every date is a real one. A team that last played years ago or a fixture from
months back is a thin page, and a lastmod that is always "today" teaches a crawler
to ignore the field.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.models import Match, Team
from app.services.seo_service import sitemap_entries

LEAGUE = "English Premier League"


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _teams(db_session, *names: str) -> list[Team]:
    teams = [Team(name=n, league=LEAGUE, elo_rating=1500) for n in names]
    db_session.add_all(teams)
    db_session.flush()
    return teams


def _match(db_session, home, away, when, *, competition=LEAGUE, sport="football", score=(1, 0)):
    played = when < _now()
    match = Match(
        match_date=when,
        competition=competition,
        season="2026-2027",
        sport=sport,
        home_team_id=home.id,
        away_team_id=away.id,
        status="completed" if played else "scheduled",
        home_score=score[0] if played else None,
        away_score=score[1] if played else None,
    )
    db_session.add(match)
    db_session.flush()
    return match


def test_a_recent_and_an_upcoming_match_are_listed_with_their_own_dates(db_session):
    a, b = _teams(db_session, "Arsenal", "Chelsea")
    recent = _match(db_session, a, b, _now() - timedelta(days=3))
    upcoming = _match(db_session, b, a, _now() + timedelta(days=2))
    db_session.commit()

    matches = {m["slug"]: m["lastmod"] for m in sitemap_entries(db_session)["matches"]}

    assert (
        matches[f"arsenal-vs-chelsea-prediction-{recent.id}"]
        == recent.match_date.date().isoformat()
    )
    assert (
        matches[f"chelsea-vs-arsenal-prediction-{upcoming.id}"]
        == upcoming.match_date.date().isoformat()
    )


def test_old_fixtures_and_far_future_ones_are_left_out(db_session):
    a, b = _teams(db_session, "Arsenal", "Chelsea")
    _match(db_session, a, b, _now() - timedelta(days=60))
    _match(db_session, a, b, _now() + timedelta(days=40))
    db_session.commit()

    assert sitemap_entries(db_session)["matches"] == []


def test_only_football_matches_are_listed(db_session):
    a, b = _teams(db_session, "Lakers", "Celtics")
    _match(db_session, a, b, _now() - timedelta(days=1), sport="basketball")
    db_session.commit()

    assert sitemap_entries(db_session)["matches"] == []


def test_a_team_is_listed_only_if_it_has_played_within_the_year(db_session):
    a, b, c = _teams(db_session, "Arsenal", "Chelsea", "Long Gone FC")
    _match(db_session, a, b, _now() - timedelta(days=10))
    _match(db_session, c, b, _now() - timedelta(days=900))
    db_session.commit()

    slugs = [t["slug"] for t in sitemap_entries(db_session)["teams"]]

    assert "arsenal" in slugs and "chelsea" in slugs
    assert "long-gone-fc" not in slugs


def test_a_team_is_dated_by_its_most_recent_match(db_session):
    a, b = _teams(db_session, "Arsenal", "Chelsea")
    newest = _match(db_session, a, b, _now() - timedelta(days=2))
    _match(db_session, b, a, _now() - timedelta(days=30))
    db_session.commit()

    teams = {t["slug"]: t["lastmod"] for t in sitemap_entries(db_session)["teams"]}

    assert teams["arsenal"] == newest.match_date.date().isoformat()


def test_two_clubs_that_fold_to_one_slug_are_listed_once(db_session):
    a, b, dup = _teams(db_session, "Real Madrid", "Getafe", "Real  Madrid")
    _match(db_session, a, b, _now() - timedelta(days=5))
    _match(db_session, dup, b, _now() - timedelta(days=2))
    db_session.commit()

    slugs = [t["slug"] for t in sitemap_entries(db_session)["teams"]]

    assert slugs.count("real-madrid") == 1


def test_a_league_is_listed_with_its_latest_result_and_an_uncatalogued_one_is_not(db_session):
    a, b = _teams(db_session, "Arsenal", "Chelsea")
    newest = _match(db_session, a, b, _now() - timedelta(days=4))
    _match(db_session, a, b, _now() - timedelta(days=40))
    _match(db_session, a, b, _now() - timedelta(days=4), competition="Some Invitational Cup")
    db_session.commit()

    leagues = {entry["slug"]: entry["lastmod"] for entry in sitemap_entries(db_session)["leagues"]}

    assert leagues == {"english-premier-league": newest.match_date.date().isoformat()}


def test_the_endpoint_serves_all_three_lists(client, db_session):
    a, b = _teams(db_session, "Arsenal", "Chelsea")
    _match(db_session, a, b, _now() - timedelta(days=1))
    db_session.commit()

    body = client.get("/seo/urls").json()

    assert set(body) == {"leagues", "teams", "matches"}
    assert body["matches"] and body["teams"] and body["leagues"]
