"""Rating football results incrementally gives exactly what a full replay would.

A full replay (`rebuild_elo_history`) deletes and re-inserts the whole history in one
transaction, which locks the database for minutes. Results now continue from each team's last
rating instead, which is only allowed when it cannot change the answer: these tests pin that it
does not, and that the cases where it could (a result older than a rating already written) are
replayed in full.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.models import EloHistory, Match, Team
from app.services.elo_sync import sync_elo
from app.utils.config import get_settings
from scripts.load_to_db import rebuild_elo_history

# A competition with its own K, so the test fails if the incremental path forgets it.
COMPETITION = "FIFA World Cup"
START = datetime(2026, 1, 1, 15, 0)


@pytest.fixture
def teams(db_session):
    made = [Team(name=f"Club {n}", league="L", sport="football") for n in "ABCD"]
    db_session.add_all(made)
    db_session.flush()
    return {t.name[-1]: t for t in made}


def _played(db, teams, home, away, when, score, competition=COMPETITION):
    match = Match(
        sport="football",
        match_date=when,
        competition=competition,
        season="2026",
        home_team_id=teams[home].id,
        away_team_id=teams[away].id,
        home_score=score[0],
        away_score=score[1],
        status="completed",
    )
    db.add(match)
    db.flush()
    return match


def _ratings(db, teams):
    return {name: team.elo_rating for name, team in teams.items()}


def _refresh(db, teams):
    for team in teams.values():
        db.refresh(team)


def _seed(db, teams):
    _played(db, teams, "A", "B", START, (2, 0))
    _played(db, teams, "C", "D", START + timedelta(days=1), (1, 1))
    _played(db, teams, "A", "C", START + timedelta(days=7), (0, 3))
    db.commit()
    rebuild_elo_history(db, get_settings())
    db.commit()


def test_incremental_ratings_equal_a_full_replay(db_session, teams):
    _seed(db_session, teams)
    _played(db_session, teams, "B", "D", START + timedelta(days=14), (4, 1))
    _played(db_session, teams, "A", "D", START + timedelta(days=15), (1, 2))
    db_session.commit()

    result = sync_elo(db_session, "football")
    _refresh(db_session, teams)
    incremental = _ratings(db_session, teams)

    assert result == {"added": 2, "rebuilt": False}

    rebuild_elo_history(db_session, get_settings())
    db_session.commit()
    _refresh(db_session, teams)
    full = _ratings(db_session, teams)

    for name in "ABCD":
        assert incremental[name] == pytest.approx(full[name])


def test_a_late_result_for_teams_with_nothing_newer_is_still_incremental(db_session, teams):
    """C and D played last on day 7; a result for A and B from day 3 is older than the newest
    rating in the table but newer than anything either of them has been rated for. A global
    "newer than everything" check replayed the lot for this."""
    _seed(db_session, teams)
    _played(db_session, teams, "B", "D", START + timedelta(days=10), (0, 0))
    db_session.commit()
    sync_elo(db_session, "football")  # B and D now rated to day 10

    _played(db_session, teams, "A", "C", START + timedelta(days=20), (2, 2))
    db_session.commit()
    result = sync_elo(db_session, "football")

    assert result["rebuilt"] is False


def test_a_result_older_than_a_teams_last_rating_is_replayed_in_full(db_session, teams):
    _seed(db_session, teams)
    _played(db_session, teams, "A", "B", START + timedelta(days=3), (1, 0))  # before A's day 7
    db_session.commit()

    result = sync_elo(db_session, "football")

    assert result == {"added": 1, "rebuilt": True}


def test_nothing_new_changes_nothing(db_session, teams):
    _seed(db_session, teams)
    before = db_session.query(EloHistory).count()

    assert sync_elo(db_session, "football") == {"added": 0, "rebuilt": False}
    assert db_session.query(EloHistory).count() == before
