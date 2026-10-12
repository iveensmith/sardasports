"""Live scores: in-play fixtures shown with their minute and score, never mistaken for a result.

The rule everything here protects: a live score lives in its own columns. `home_score` and
`away_score` mean "the final result" (grading, Elo, history), so a half-played game must leave
them untouched and the match "scheduled" until it is really settled.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.models import Match, Team
from app.services.board_service import build_row
from app.services import live_scores
from app.services.live_scores import (
    FRESH_FOR,
    apply_live,
    ended_candidates,
    live_payload,
    needs_live_poll,
    parse_live,
)

NOW = datetime(2026, 10, 10, 15, 0, 0)


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _item(fixture_id, status="2H", elapsed=63, home=1, away=0):
    return {
        "fixture": {"id": fixture_id, "status": {"short": status, "elapsed": elapsed}},
        "goals": {"home": home, "away": away},
    }


@pytest.fixture
def teams(db_session):
    pair = [
        Team(name="Alpha", league="L", sport="football"),
        Team(name="Beta", league="L", sport="football"),
    ]
    db_session.add_all(pair)
    db_session.flush()
    return pair


def _match(db_session, teams, external_id, kickoff, status="scheduled", **extra):
    match = Match(
        external_id=external_id,
        sport="football",
        match_date=kickoff,
        competition="Test League",
        season="2026",
        home_team_id=teams[0].id,
        away_team_id=teams[1].id,
        status=status,
        **extra,
    )
    db_session.add(match)
    db_session.commit()
    return match


# --- reading the feed -----------------------------------------------------------------------


def test_only_in_play_fixtures_with_a_full_score_are_kept():
    live = parse_live(
        [
            _item(1),  # in play
            _item(2, status="NS", elapsed=None),  # not started
            _item(3, status="FT", elapsed=90),  # finished
            _item(4, status="HT", elapsed=45),  # half-time counts as live
            _item(5, home=None),  # score not known
        ]
    )

    assert set(live) == {"apif-1", "apif-4"}
    assert live["apif-1"] == {"status": "2H", "minute": 63, "home": 1, "away": 0}


def test_a_goalless_game_is_zero_not_missing():
    live = parse_live([_item(1, elapsed=10, home=0, away=0)])
    assert live["apif-1"]["home"] == 0 and live["apif-1"]["away"] == 0


# --- storing it -----------------------------------------------------------------------------


def test_a_live_score_never_touches_the_final_result_columns(db_session, teams):
    match = _match(db_session, teams, "apif-10", NOW - timedelta(hours=1))

    apply_live(db_session, parse_live([_item(10, home=2, away=1)]), now=NOW)
    db_session.commit()
    db_session.refresh(match)

    assert (match.live_home, match.live_away, match.live_minute) == (2, 1, 63)
    assert match.home_score is None and match.away_score is None
    assert match.status == "scheduled"


def test_only_fixtures_we_already_have_are_decorated(db_session, teams):
    updated = apply_live(db_session, parse_live([_item(999)]), now=NOW)

    assert updated == 0
    assert db_session.query(Match).count() == 0


def test_a_fixture_that_drops_out_of_the_feed_stops_being_live(db_session, teams):
    match = _match(db_session, teams, "apif-11", NOW - timedelta(hours=1))
    apply_live(db_session, parse_live([_item(11)]), now=NOW)
    db_session.commit()

    apply_live(db_session, parse_live([]), now=NOW + timedelta(minutes=30))
    db_session.commit()
    db_session.refresh(match)

    assert match.live_updated_at is None and match.live_home is None


def test_a_settled_match_is_not_decorated(db_session, teams):
    match = _match(
        db_session, teams, "apif-12", NOW - timedelta(hours=3), status="completed",
        home_score=1, away_score=1,
    )  # fmt: skip

    apply_live(db_session, parse_live([_item(12)]), now=NOW)
    db_session.refresh(match)

    assert match.live_home is None


# --- showing it -----------------------------------------------------------------------------


def test_the_payload_has_a_label_and_goes_away_when_stale(db_session, teams):
    match = _match(db_session, teams, "apif-13", NOW - timedelta(hours=1))
    apply_live(db_session, parse_live([_item(13, elapsed=63)]), now=NOW)
    db_session.commit()
    db_session.refresh(match)

    assert live_payload(match, now=NOW) == {
        "status": "2H", "minute": 63, "label": "63'", "home": 1, "away": 0,
    }  # fmt: skip
    assert live_payload(match, now=NOW + FRESH_FOR + timedelta(minutes=1)) is None


def test_half_time_reads_ht_not_a_minute(db_session, teams):
    match = _match(db_session, teams, "apif-14", NOW - timedelta(hours=1))
    apply_live(db_session, parse_live([_item(14, status="HT", elapsed=45)]), now=NOW)
    db_session.commit()
    db_session.refresh(match)

    assert live_payload(match, now=NOW)["label"] == "HT"


def test_a_board_row_carries_live_but_keeps_score_empty(db_session, teams):
    match = _match(db_session, teams, "apif-15", _utc_now() - timedelta(minutes=50))
    apply_live(db_session, parse_live([_item(15, elapsed=48, home=0, away=2)]), now=_utc_now())
    db_session.commit()
    db_session.refresh(match)

    row = build_row(match, None, {}, "Alpha", "Beta")

    assert row["score"] is None
    assert row["status"] == "scheduled"
    assert row["live"]["home"] == 0 and row["live"]["away"] == 2


# --- when to poll ---------------------------------------------------------------------------


def test_polling_only_when_a_fixture_could_be_in_play(db_session, teams):
    assert needs_live_poll(db_session, now=NOW) is False  # nothing at all

    _match(db_session, teams, "apif-20", NOW + timedelta(hours=6))  # tonight, not yet
    assert needs_live_poll(db_session, now=NOW) is False

    _match(db_session, teams, "apif-21", NOW - timedelta(minutes=40))  # kicked off, no result
    assert needs_live_poll(db_session, now=NOW) is True


def test_a_fixture_kicked_off_long_ago_does_not_keep_polling_alive(db_session, teams):
    _match(db_session, teams, "apif-22", NOW - timedelta(hours=9))
    assert needs_live_poll(db_session, now=NOW) is False


# --- the request budget -----------------------------------------------------------------------


def _scheduler_state(monkeypatch, used, limit):
    import app.scheduler as scheduler
    import app.services.live_scores as live_scores

    calls = []
    monkeypatch.setattr(
        scheduler,
        "get_settings",
        lambda: type("S", (), {"api_football_key": "k", "api_football_base_url": "https://x"})(),
    )
    monkeypatch.setattr(
        scheduler, "api_status", lambda _s: {"used": used, "limit": limit, "plan": "t"}
    )
    monkeypatch.setattr(
        live_scores, "refresh_live_scores", lambda *a, **k: calls.append(1) or {"settled": 0}
    )
    return scheduler, calls


def test_the_free_plan_keeps_a_reserve_so_live_polling_cannot_starve_other_jobs(
    db_session, teams, monkeypatch
):
    _match(db_session, teams, "apif-30", _utc_now() - timedelta(minutes=40))
    scheduler, calls = _scheduler_state(monkeypatch, used=70, limit=100)  # 30 left, reserve is 40

    scheduler.fetch_live_job()

    assert calls == []


def test_the_free_plan_polls_while_there_is_spare_quota(db_session, teams, monkeypatch):
    _match(db_session, teams, "apif-31", _utc_now() - timedelta(minutes=40))
    scheduler, calls = _scheduler_state(monkeypatch, used=10, limit=100)

    scheduler.fetch_live_job()

    assert calls == [1]


def test_nothing_is_requested_when_no_fixture_could_be_in_play(db_session, teams, monkeypatch):
    scheduler, calls = _scheduler_state(monkeypatch, used=0, limit=7500)

    scheduler.fetch_live_job()

    assert calls == []


# --- a match that has ended is settled within a poll, not at the next results run -----------


def _finished_item(fixture_id, home=2, away=1, status="FT"):
    return {
        "fixture": {"id": fixture_id, "status": {"short": status, "elapsed": 90}},
        "goals": {"home": home, "away": away},
        "score": {"fulltime": {"home": home, "away": away}, "halftime": {"home": 1, "away": 0}},
    }


def test_a_fixture_that_left_the_live_feed_is_a_candidate_to_be_looked_up(db_session, teams):
    now = _utc_now()
    vanished = _match(
        db_session, teams, "apif-1", now - timedelta(minutes=70),
        live_status="2H", live_home=1, live_away=0, live_updated_at=now - timedelta(minutes=2),
    )  # fmt: skip
    over = _match(db_session, teams, "apif-2", now - timedelta(minutes=130))
    too_soon = _match(db_session, teams, "apif-3", now - timedelta(minutes=40))
    still_live = _match(db_session, teams, "apif-4", now - timedelta(minutes=60))
    long_gone = _match(db_session, teams, "apif-5", now - timedelta(hours=9))
    db_session.flush()

    found = ended_candidates(db_session, {"apif-4": {}}, now=now)

    assert sorted(found) == ["1", "2"]
    assert {vanished.id, over.id} and too_soon.id and still_live.id and long_gone.id


def test_a_finished_match_is_settled_in_the_same_poll_it_leaves_the_feed(
    db_session, teams, monkeypatch
):
    now = _utc_now()
    match = _match(
        db_session, teams, "apif-9", now - timedelta(minutes=115),
        live_status="2H", live_home=2, live_away=1, live_updated_at=now - timedelta(minutes=2),
    )  # fmt: skip
    db_session.commit()
    requests_made = []
    monkeypatch.setattr(live_scores, "fetch_live_items", lambda *a, **k: [])
    monkeypatch.setattr(
        live_scores,
        "fetch_fixtures_by_id",
        lambda key, url, ids, **k: requests_made.append(ids) or [_finished_item(9)],
    )

    result = live_scores.refresh_live_scores(db_session, "k", "u", lookup_ended=True)

    db_session.refresh(match)
    assert result["settled"] == 1 and result["looked_up"] == 1
    assert (match.status, match.home_score, match.away_score) == ("completed", 2, 1)
    assert match.live_home is None  # the live view is gone once it is a result
    assert requests_made == [["9"]]


def test_a_free_plan_never_looks_fixtures_up_by_id(db_session, teams, monkeypatch):
    now = _utc_now()
    _match(db_session, teams, "apif-9", now - timedelta(minutes=130))
    db_session.commit()
    monkeypatch.setattr(live_scores, "fetch_live_items", lambda *a, **k: [])

    def boom(*args, **kwargs):  # pragma: no cover - must not be called
        raise AssertionError("a by-id lookup was attempted on the free plan")

    monkeypatch.setattr(live_scores, "fetch_fixtures_by_id", boom)

    result = live_scores.refresh_live_scores(db_session, "k", "u", lookup_ended=False)

    assert result["looked_up"] == 0 and result["settled"] == 0


def test_the_live_route_lists_only_matches_in_play_with_their_score(client, db_session, teams):
    now = _utc_now()
    _match(
        db_session, teams, "apif-31", now - timedelta(minutes=55),
        live_status="2H", live_minute=57, live_home=1, live_away=0,
        live_updated_at=now - timedelta(minutes=1),
    )  # fmt: skip
    _match(db_session, teams, "apif-32", now - timedelta(minutes=55))  # no live view
    _match(
        db_session, teams, "apif-33", now - timedelta(minutes=300),
        live_status="2H", live_minute=88, live_home=3, live_away=3,
        live_updated_at=now - timedelta(minutes=45),
    )  # fmt: skip

    from app.api import routes_board_table

    routes_board_table._live_cache.clear()
    body = client.get("/board/live").json()

    assert body["count"] == 1
    row = body["rows"][0]
    assert row["live"]["home"] == 1 and row["live"]["away"] == 0 and row["live"]["label"] == "57'"
    assert row["score"] is None  # a live score is never the result
