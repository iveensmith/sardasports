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
from app.services.live_scores import (
    FRESH_FOR,
    apply_live,
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
