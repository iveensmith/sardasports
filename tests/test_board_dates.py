"""`/board/dates` and which day counts as "last settled".

The home page's results strip is built on the last settled day. The newest day
with *any* result is routinely a day with a single match on it, and a strip
built on that has nothing to show and disappears — which is how it vanished
after a data refresh made one Argentine match the newest result on record.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.models import Match, Team


def _teams(db_session, count: int):
    teams = [Team(name=f"Club {i}", league="Test League", sport="football") for i in range(count)]
    db_session.add_all(teams)
    db_session.flush()
    return teams


def _finished(db_session, teams, day: datetime, n: int, sport: str = "football") -> None:
    for i in range(n):
        db_session.add(
            Match(
                match_date=day.replace(hour=12, minute=i),
                competition="English Premier League",
                season="2026-2027",
                home_team_id=teams[i % len(teams)].id,
                away_team_id=teams[(i + 1) % len(teams)].id,
                status="completed",
                home_score=1,
                away_score=0,
                sport=sport,
            )
        )


def _seed(db_session):
    """Ten finished matches five days ago; one yesterday."""
    teams = _teams(db_session, 6)
    today = datetime.now(UTC).replace(tzinfo=None, hour=0, minute=0, second=0, microsecond=0)
    busy, thin = today - timedelta(days=5), today - timedelta(days=1)
    _finished(db_session, teams, busy, 10)
    _finished(db_session, teams, thin, 1)
    db_session.commit()
    return busy.date().isoformat(), thin.date().isoformat()


def test_by_default_last_settled_is_the_newest_day_with_any_result(client, db_session):
    _, thin = _seed(db_session)
    assert client.get("/board/dates").json()["last_settled"] == thin


def test_a_day_with_too_few_results_is_skipped_for_the_one_that_can_fill_a_strip(
    client, db_session
):
    busy, _ = _seed(db_session)
    body = client.get("/board/dates", params={"min_settled": 8}).json()
    assert body["last_settled"] == busy


def test_a_threshold_nothing_meets_gives_no_day_rather_than_a_thin_one(client, db_session):
    _seed(db_session)
    assert client.get("/board/dates", params={"min_settled": 11}).json()["last_settled"] is None


def test_the_threshold_is_inclusive(client, db_session):
    busy, _ = _seed(db_session)
    assert client.get("/board/dates", params={"min_settled": 10}).json()["last_settled"] == busy


def test_matches_that_get_no_pick_do_not_count_towards_the_threshold(client, db_session):
    """Only football is predicted, so a day of tennis cannot fill a picks strip."""
    teams = _teams(db_session, 6)
    today = datetime.now(UTC).replace(tzinfo=None, hour=0, minute=0, second=0, microsecond=0)
    _finished(db_session, teams, today - timedelta(days=2), 12, sport="tennis")
    db_session.commit()

    assert client.get("/board/dates", params={"min_settled": 8}).json()["last_settled"] is None


def test_unfinished_matches_never_count(client, db_session):
    teams = _teams(db_session, 4)
    today = datetime.now(UTC).replace(tzinfo=None, hour=12, minute=0, second=0, microsecond=0)
    for i in range(10):
        db_session.add(
            Match(
                match_date=today - timedelta(days=1, minutes=i),
                competition="English Premier League",
                season="2026-2027",
                home_team_id=teams[i % 4].id,
                away_team_id=teams[(i + 1) % 4].id,
                status="scheduled",
            )
        )
    db_session.commit()

    assert client.get("/board/dates").json()["last_settled"] is None
