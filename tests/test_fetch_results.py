"""Closing the loop: filling in results for fixtures already predicted.

Before this, a fixture ingested by `fetch_upcoming_fixtures.py` stayed
`status="scheduled"` forever — nothing ever went back and recorded what
happened. That meant the board could never grade a fixture it had just
predicted, and the live track record could never start. These tests cover
the two ways that would go wrong quietly: matching a result to the wrong
row, and storing a fabricated score for a fixture that isn't really over.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.models import Match, Team
from scripts.fetch_results import apply_results, results_from_fixtures


def _fixture(
    fixture_id,
    status="NS",
    home_goals=None,
    away_goals=None,
    ht_home=None,
    ht_away=None,
):
    return {
        "fixture": {"id": fixture_id, "status": {"short": status}},
        "score": {
            "halftime": {"home": ht_home, "away": ht_away},
            "fulltime": {"home": home_goals, "away": away_goals},
        },
        "goals": {"home": home_goals, "away": away_goals},
    }


# --- parsing ---------------------------------------------------------------


def test_only_finished_fixtures_are_kept():
    """Live and not-yet-started fixtures have no final score to record."""
    items = [
        _fixture(1, status="NS"),
        _fixture(2, status="1H", home_goals=1, away_goals=0),
        _fixture(3, status="FT", home_goals=2, away_goals=1),
    ]
    results = results_from_fixtures(items)
    assert list(results) == ["apif-3"]


def test_extra_time_and_penalties_use_the_90_minute_score():
    """Matches the convention the historical data already uses: a cup final
    that finished 1-1 after 90 is stored as 1-1, not as the AET/penalty
    scoreline — the same result shape as every other match in the database."""
    items = [_fixture(1, status="AET", home_goals=2, away_goals=1)]
    # `score.fulltime` is the 90-minute score; `goals` on an AET fixture
    # reflects the final (post-extra-time) score, so the two can legitimately
    # differ — this asserts fulltime wins.
    items[0]["score"]["fulltime"] = {"home": 1, "away": 1}
    items[0]["goals"] = {"home": 2, "away": 1}
    results = results_from_fixtures(items)
    assert results["apif-1"]["home_score"] == 1
    assert results["apif-1"]["away_score"] == 1


def test_half_time_score_is_captured_alongside_full_time():
    items = [_fixture(1, status="FT", home_goals=2, away_goals=1, ht_home=1, ht_away=0)]
    result = results_from_fixtures(items)["apif-1"]
    assert result["home_score"] == 2 and result["away_score"] == 1
    assert result["home_ht_goals"] == 1 and result["away_ht_goals"] == 0


def test_missing_half_time_score_is_none_not_zero():
    """Not every competition/source carries a half-time score — recording it
    as 0-0 would fabricate a scoreline nobody reported."""
    items = [_fixture(1, status="FT", home_goals=2, away_goals=1)]
    result = results_from_fixtures(items)["apif-1"]
    assert result["home_ht_goals"] is None
    assert result["away_ht_goals"] is None


def test_a_finished_fixture_with_no_score_at_all_is_skipped():
    """A genuinely unscored "finished" fixture is a data problem, not a
    scoreline — storing 0-0 for it would be a fabricated result."""
    item = _fixture(1, status="FT")
    item["score"]["fulltime"] = {"home": None, "away": None}
    item["goals"] = {"home": None, "away": None}
    assert results_from_fixtures([item]) == {}


def test_falls_back_to_the_top_level_goals_block():
    """Older API-Football responses populated `goals` without a
    `score.fulltime` block; this keeps those fixtures gradeable too."""
    item = _fixture(1, status="FT", home_goals=3, away_goals=0)
    item["score"]["fulltime"] = {"home": None, "away": None}
    result = results_from_fixtures([item])["apif-1"]
    assert result["home_score"] == 3 and result["away_score"] == 0


def test_a_fixture_with_no_id_is_skipped_rather_than_crashing():
    item = _fixture(1, status="FT", home_goals=1, away_goals=0)
    item["fixture"]["id"] = None
    assert results_from_fixtures([item]) == {}


# --- applying to the database ----------------------------------------------


def _match(session, external_id, status="scheduled", days_ago=1, **extra):
    home = Team(name=f"H-{external_id}", league="Test", sport="football")
    away = Team(name=f"A-{external_id}", league="Test", sport="football")
    session.add_all([home, away])
    session.flush()
    match = Match(
        external_id=external_id,
        sport="football",
        match_date=datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days_ago),
        competition="Test League",
        season="2026",
        home_team_id=home.id,
        away_team_id=away.id,
        status=status,
        **extra,
    )
    session.add(match)
    session.commit()
    return match


def test_a_matching_scheduled_fixture_is_completed(db_session):
    match = _match(db_session, "apif-100")
    updated = apply_results(
        db_session,
        {"apif-100": {"home_score": 2, "away_score": 1, "home_ht_goals": 1, "away_ht_goals": 0}},
    )
    db_session.commit()
    db_session.refresh(match)

    assert updated == 1
    assert match.status == "completed"
    assert match.home_score == 2 and match.away_score == 1
    assert match.home_ht_goals == 1 and match.away_ht_goals == 0


def test_a_result_with_no_matching_row_is_silently_ignored(db_session):
    """A finished fixture we never ingested (a different competition, a
    fixture id we don't recognise) is not an error — most of what
    API-Football lists on any given date is outside what this engine models."""
    updated = apply_results(db_session, {"apif-999999": {"home_score": 1, "away_score": 0}})
    assert updated == 0


def test_an_already_completed_match_is_not_overwritten(db_session):
    """A row completed from a different source (the historical CSV pipeline,
    say) keeps whatever it already has rather than being silently replaced."""
    match = _match(db_session, "apif-200", status="completed", home_score=9, away_score=9)
    updated = apply_results(
        db_session,
        {
            "apif-200": {
                "home_score": 0,
                "away_score": 0,
                "home_ht_goals": None,
                "away_ht_goals": None,
            }
        },
    )
    db_session.commit()
    db_session.refresh(match)

    assert updated == 0
    assert match.home_score == 9 and match.away_score == 9


def test_an_empty_result_set_touches_nothing(db_session):
    _match(db_session, "apif-300")
    assert apply_results(db_session, {}) == 0


def test_only_the_matching_external_id_is_touched(db_session):
    """Two scheduled fixtures on the same day; only the one with a result
    is completed, the other stays scheduled and untouched."""
    played = _match(db_session, "apif-1")
    pending = _match(db_session, "apif-2")
    apply_results(
        db_session,
        {
            "apif-1": {
                "home_score": 1,
                "away_score": 0,
                "home_ht_goals": None,
                "away_ht_goals": None,
            }
        },
    )
    db_session.commit()
    db_session.refresh(played)
    db_session.refresh(pending)

    assert played.status == "completed"
    assert pending.status == "scheduled"
    assert pending.home_score is None


# --- fixtures the by-date fetch missed ---------------------------------------


def test_stale_ids_are_old_scheduled_api_fixtures_only(db_session):
    from scripts.fetch_results import stale_scheduled_ids

    _match(db_session, "apif-300", days_ago=10)  # missed: scheduled, long past
    _match(db_session, "apif-301", days_ago=1)  # still inside the by-date window
    _match(db_session, "apif-302", days_ago=10, status="completed", home_score=1, away_score=0)
    _match(db_session, "csv-303", days_ago=10)  # not an API fixture: no id to look up
    _match(db_session, "apif-304", days_ago=200)  # too old to chase

    assert stale_scheduled_ids(db_session, older_than_days=3) == ["300"]


def _response(payload):
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return payload

    return Response()


def test_stale_fixtures_are_settled_by_id(db_session, monkeypatch):
    import scripts.fetch_results as module

    match = _match(db_session, "apif-400", days_ago=10)
    asked = []

    def fake_get(url, headers, params, timeout):
        asked.append(params["ids"])
        return _response(
            {"errors": [], "response": [_fixture(400, status="FT", home_goals=3, away_goals=1)]}
        )

    monkeypatch.setattr(module.requests, "get", fake_get)
    monkeypatch.setattr(module.time, "sleep", lambda _s: None)
    monkeypatch.setattr(module, "get_settings", lambda: _Settings())
    monkeypatch.setattr("scripts.load_to_db.rebuild_elo_history", lambda *_a, **_k: None)

    assert module.resolve_stale_fixtures() == 1
    assert asked == ["400"]
    db_session.refresh(match)
    assert match.status == "completed" and match.home_score == 3


def test_a_free_plan_refusing_ids_settles_nothing_and_does_not_raise(db_session, monkeypatch):
    import scripts.fetch_results as module

    match = _match(db_session, "apif-500", days_ago=10)
    calls = []

    def fake_get(url, headers, params, timeout):
        calls.append(params)
        return _response(
            {"errors": {"plan": "Free plans do not have access to the Ids parameter."}}
        )

    monkeypatch.setattr(module.requests, "get", fake_get)
    monkeypatch.setattr(module.time, "sleep", lambda _s: None)
    monkeypatch.setattr(module, "get_settings", lambda: _Settings())

    assert module.resolve_stale_fixtures() == 0
    assert len(calls) == 1  # asked once, was refused, stopped
    db_session.refresh(match)
    assert match.status == "scheduled"


class _Settings:
    api_football_key = "key"
    api_football_base_url = "https://example.invalid"
