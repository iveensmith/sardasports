"""Predicting a whole board's worth of fixtures in one request.

`predict_for_matches` shares one SQLAlchemy session and one query cache
across every fixture on the card, for speed. That sharing has a failure mode
the per-match `try/except` alone doesn't cover: a transient DB error (a
concurrent writer holding SQLite's single write lock, say) leaves the shared
session unable to run another statement until it is rolled back — so without
an explicit rollback, one unlucky fixture silently takes every fixture after
it down with it, and a board that should read "28 predicted, 1 gap" instead
reads "0 predicted, 29 gaps". These tests cover that recovery, not the
prediction logic itself (already covered elsewhere).
"""

from __future__ import annotations

from datetime import datetime, timedelta

import app.services.prediction_service as prediction_service
from app.models import Match, Team
from app.services.prediction_service import predict_for_matches


def _match(session, external_id, days_ahead=0, competition="Test League"):
    home = Team(name=f"H-{external_id}", league="Test", sport="football")
    away = Team(name=f"A-{external_id}", league="Test", sport="football")
    session.add_all([home, away])
    session.flush()
    match = Match(
        external_id=external_id,
        sport="football",
        match_date=datetime.now() + timedelta(days=days_ahead),
        competition=competition,
        season="2026",
        home_team_id=home.id,
        away_team_id=away.id,
        status="scheduled",
    )
    session.add(match)
    session.commit()
    return match


def test_a_failed_fixture_does_not_cascade_into_the_rest_of_its_group(db_session, monkeypatch):
    """Both fixtures share a match_date, so they land in the same batch
    group. Without a rollback after the first one's failure, the shared
    session is left unusable and the second would fail too, purely as a side
    effect of sharing a session — not because it was unpriceable itself."""
    failing = _match(db_session, "m-1")
    healthy = _match(db_session, "m-2")

    monkeypatch.setattr(prediction_service, "_all_completed_history", lambda *a, **k: [])
    monkeypatch.setattr(prediction_service, "build_shared_fits", lambda *a, **k: {})

    rollbacks = []
    original_rollback = db_session.rollback
    monkeypatch.setattr(db_session, "rollback", lambda: (rollbacks.append(1), original_rollback()))

    calls = []

    def fake_predict_for_match(session, match_id, history, shared):
        calls.append(match_id)
        if match_id == failing.id:
            raise RuntimeError("database is locked")
        return {"match_id": match_id, "ok": True}

    monkeypatch.setattr(prediction_service, "predict_for_match", fake_predict_for_match)

    results = predict_for_matches(db_session, [failing, healthy])

    assert calls == [failing.id, healthy.id]
    assert rollbacks == [1]
    assert results[0] is None
    assert results[1] == {"match_id": healthy.id, "ok": True}


def test_a_failed_group_setup_only_takes_out_its_own_group(db_session, monkeypatch):
    """A history-load failure happens before any fixture in that (sport,
    date) group is even attempted — it should mark that whole group as
    unpriceable, not the request, and must not touch a different day's
    group sharing the same request."""
    today = _match(db_session, "m-10", days_ahead=0)
    tomorrow = _match(db_session, "m-11", days_ahead=1)

    def fake_history(session, before_date, sport):
        if before_date.date() == today.match_date.date():
            raise RuntimeError("database is locked")
        return []

    monkeypatch.setattr(prediction_service, "_all_completed_history", fake_history)
    monkeypatch.setattr(prediction_service, "build_shared_fits", lambda *a, **k: {})
    monkeypatch.setattr(
        prediction_service,
        "predict_for_match",
        lambda session, match_id, history, shared: {"match_id": match_id, "ok": True},
    )

    rollbacks = []
    original_rollback = db_session.rollback
    monkeypatch.setattr(db_session, "rollback", lambda: (rollbacks.append(1), original_rollback()))

    results = predict_for_matches(db_session, [today, tomorrow])

    assert rollbacks == [1]
    assert results[0] is None
    assert results[1] == {"match_id": tomorrow.id, "ok": True}
