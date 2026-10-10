"""What keeps a crawler's first visit from taking the engine down.

A search engine arriving for the first time asks for hundreds of cold pages in a few minutes.
The engine is one Python process, so anything expensive that every page repeats is paid for
hundreds of times over. These pin the pieces that stop that: the shared history window, the
shared grading, a rate limit that does not throttle the website's own server, and cache
objects that are handed out without copying when the result is large and read-only.
"""

from __future__ import annotations

from datetime import datetime

from app.models import Match, Team
from app.services import prediction_service
from app.services.prediction_service import HistoryWindow, _all_completed_history
from app.utils.coalesce import CoalescingCache
from app.utils.config import Settings


def _teams(db):
    a = Team(name="Alpha", sport="football", league="L")
    b = Team(name="Beta", sport="football", league="L")
    db.add_all([a, b])
    db.flush()
    return a, b


def _played(db, a, b, when):
    db.add(
        Match(
            sport="football", competition="L", season="2026", match_date=when,
            home_team_id=a.id, away_team_id=b.id, home_score=1, away_score=0,
            status="completed",
        )
    )  # fmt: skip


def test_every_match_on_a_day_shares_one_history_window(db_session):
    a, b = _teams(db_session)
    _played(db_session, a, b, datetime(2026, 3, 1, 15))
    _played(db_session, b, a, datetime(2026, 3, 5, 12))  # the same day as the matches below
    db_session.commit()

    morning = _all_completed_history(db_session, datetime(2026, 3, 5, 10), "football")
    evening = _all_completed_history(db_session, datetime(2026, 3, 5, 21), "football")

    assert morning is evening  # one build for the day, not one per kick-off
    assert isinstance(morning, HistoryWindow)
    # Cut at the start of the day: the 5 March result is not in it, the 1 March one is.
    assert [m["match_date"] for m in morning] == [datetime(2026, 3, 1, 15)]


def test_a_later_day_sees_the_result_without_rebuilding_the_full_history(db_session):
    a, b = _teams(db_session)
    _played(db_session, a, b, datetime(2026, 3, 1, 15))
    _played(db_session, b, a, datetime(2026, 3, 5, 12))
    db_session.commit()

    _all_completed_history(db_session, datetime(2026, 3, 5, 10), "football")
    later = _all_completed_history(db_session, datetime(2026, 3, 6, 10), "football")

    assert len(later) == 2


def test_the_football_fits_are_built_once_per_window_and_competition(db_session, monkeypatch):
    a, b = _teams(db_session)
    _played(db_session, a, b, datetime(2026, 3, 1, 15))
    db_session.commit()
    built = []
    monkeypatch.setattr(
        prediction_service, "build_shared_fit", lambda history, comp: built.append(comp) or object()
    )
    window = _all_completed_history(db_session, datetime(2026, 3, 5, 10), "football")

    first = prediction_service._shared_fit_for(window, "L")
    second = prediction_service._shared_fit_for(window, "L")

    assert first is second and built == ["L"]


def test_a_large_read_only_result_can_be_shared_without_copying():
    big = {"rows": list(range(10))}
    shared = CoalescingCache(60, copy_results=False)
    copied = CoalescingCache(60)

    assert shared.get_or_compute("k", lambda: big) is big
    assert shared.get_or_compute("k", lambda: {"rows": []}) is big  # served from the cache
    assert copied.get_or_compute("k", lambda: big) is not big


def test_the_engine_rate_limit_does_not_throttle_the_websites_own_server():
    """The engine's only client is the website's server, so every request arrives from one
    address. 60 a minute turned a crawler's first visit into hundreds of 429 responses."""
    assert Settings.model_fields["api_rate_limit_per_minute"].default >= 1000
