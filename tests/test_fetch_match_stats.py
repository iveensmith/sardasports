"""Per-fixture statistics and goal events for matches this engine already
graded a score for.

`fetch_results.py` fills in only the final score; these tests cover the
follow-up that fills in what actually happened during the match — shots,
corners, cards, possession, offsides, fouls, and the goals themselves —
without ever inventing a value the source didn't report or re-asking a
fixture whose competition genuinely has none of this.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.models import Match, MatchEvent, Team
from scripts.fetch_match_stats import (
    RateLimited,
    _parse_stat_value,
    apply_statistics,
    backfill_match_stats,
    events_for_match,
)


def _match(session, external_id, days_ago=1, **extra):
    home = Team(name=f"Home-{external_id}", league="Test", sport="football")
    away = Team(name=f"Away-{external_id}", league="Test", sport="football")
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
        status="completed",
        **extra,
    )
    session.add(match)
    session.commit()
    return match


def _stat_block(team_name, **stats):
    return {
        "team": {"name": team_name},
        "statistics": [{"type": k, "value": v} for k, v in stats.items()],
    }


def _goal_event(team_name, minute, player, assist=None, detail="Normal Goal", extra=None):
    return {
        "type": "Goal",
        "detail": detail,
        "time": {"elapsed": minute, "extra": extra},
        "team": {"name": team_name},
        "player": {"name": player},
        "assist": {"name": assist} if assist else {},
    }


# --- _parse_stat_value -------------------------------------------------------


def test_a_percentage_string_is_parsed_to_a_plain_int():
    assert _parse_stat_value("55%") == 55


def test_a_bare_number_is_parsed():
    assert _parse_stat_value(12) == 12


def test_none_and_blank_are_both_none():
    assert _parse_stat_value(None) is None
    assert _parse_stat_value("") is None
    assert _parse_stat_value("  ") is None


def test_unparseable_text_is_none_rather_than_a_crash():
    assert _parse_stat_value("N/A") is None


# --- apply_statistics ---------------------------------------------------------


def test_statistics_are_assigned_to_the_matching_side(db_session):
    match = _match(db_session, "apif-1")
    blocks = [
        _stat_block(match.home_team.name, **{"Total Shots": 14, "Ball Possession": "60%"}),
        _stat_block(match.away_team.name, **{"Total Shots": 9, "Ball Possession": "40%"}),
    ]
    changed = apply_statistics(match, blocks)
    assert changed is True
    assert match.home_shots == 14 and match.away_shots == 9
    assert match.home_possession == 60 and match.away_possession == 40


def test_an_unrecognised_stat_type_is_ignored(db_session):
    match = _match(db_session, "apif-2")
    blocks = [_stat_block(match.home_team.name, **{"Expected Goals": "1.8"})]
    assert apply_statistics(match, blocks) is False
    assert match.home_shots is None


def test_a_team_name_that_matches_neither_side_is_ignored(db_session):
    """A malformed or unmatched response should not silently attribute stats
    to the wrong team."""
    match = _match(db_session, "apif-3")
    blocks = [_stat_block("Some Other Club", **{"Total Shots": 20})]
    assert apply_statistics(match, blocks) is False
    assert match.home_shots is None and match.away_shots is None


def test_team_name_matching_is_accent_and_case_insensitive(db_session):
    home = Team(name="Castellón", league="Test", sport="football")
    away = Team(name="Rivals", league="Test", sport="football")
    db_session.add_all([home, away])
    db_session.flush()
    match = Match(
        external_id="apif-4",
        sport="football",
        match_date=datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1),
        competition="Test League",
        season="2026",
        home_team_id=home.id,
        away_team_id=away.id,
        status="completed",
    )
    db_session.add(match)
    db_session.commit()

    blocks = [_stat_block("castellon", **{"Total Shots": 11})]
    assert apply_statistics(match, blocks) is True
    assert match.home_shots == 11


# --- events_for_match ---------------------------------------------------------


def test_goals_are_returned_in_order_with_a_running_score(db_session):
    match = _match(db_session, "apif-10", home_score=2, away_score=1)
    items = [
        _goal_event(match.home_team.name, 12, "A. Striker"),
        _goal_event(match.away_team.name, 40, "B. Winger", assist="C. Playmaker"),
        _goal_event(match.home_team.name, 77, "A. Striker"),
    ]
    events = events_for_match(match, items)
    assert [e.minute for e in events] == [12, 40, 77]
    assert (events[0].home_score_after, events[0].away_score_after) == (1, 0)
    assert (events[1].home_score_after, events[1].away_score_after) == (1, 1)
    assert (events[2].home_score_after, events[2].away_score_after) == (2, 1)
    assert events[1].assist == "C. Playmaker"


def test_a_missed_penalty_is_not_a_goal(db_session):
    match = _match(db_session, "apif-11")
    items = [_goal_event(match.home_team.name, 55, "A. Striker", detail="Missed Penalty")]
    assert events_for_match(match, items) == []


def test_non_goal_events_are_excluded(db_session):
    match = _match(db_session, "apif-12")
    items = [
        {"type": "Card", "detail": "Yellow Card", "time": {"elapsed": 30}, "team": {}},
        {"type": "subst", "detail": "Substitution 1", "time": {"elapsed": 60}, "team": {}},
    ]
    assert events_for_match(match, items) == []


def test_a_goal_with_no_player_name_is_skipped(db_session):
    match = _match(db_session, "apif-13")
    item = _goal_event(match.home_team.name, 20, "")
    item["player"] = {"name": None}
    assert events_for_match(match, [item]) == []


def test_stoppage_time_is_carried_separately_from_the_minute(db_session):
    match = _match(db_session, "apif-14")
    items = [_goal_event(match.away_team.name, 45, "D. Sub", extra=2)]
    events = events_for_match(match, items)
    assert events[0].minute == 45
    assert events[0].added_time == 2


# --- backfill_match_stats -----------------------------------------------------


class _FakeSettings:
    api_football_key = "test-key"
    api_football_base_url = "https://example.test"


def test_backfill_only_targets_fixtures_never_fetched(db_session, monkeypatch):
    never_fetched = _match(db_session, "apif-100")
    already_fetched = _match(
        db_session, "apif-101", stats_fetched_at=datetime.now(UTC).replace(tzinfo=None)
    )
    csv_row = _match(db_session, "English-Premier-League_2024-01-01_A_vs_B")

    seen_ids = []

    def fake_fetch_statistics(fixture_id, api_key, base_url):
        seen_ids.append(fixture_id)
        return []

    monkeypatch.setattr("scripts.fetch_match_stats.fetch_statistics", fake_fetch_statistics)
    monkeypatch.setattr("scripts.fetch_match_stats.fetch_events", lambda *a, **k: [])

    backfill_match_stats(db_session, settings=_FakeSettings(), max_fixtures=10)
    db_session.commit()

    assert seen_ids == ["100"]
    db_session.refresh(never_fetched)
    db_session.refresh(already_fetched)
    db_session.refresh(csv_row)
    assert never_fetched.stats_fetched_at is not None
    assert csv_row.stats_fetched_at is None


def test_a_competition_with_no_statistics_is_still_marked_fetched(db_session, monkeypatch):
    """Some competitions genuinely report nothing — this has to stop being a
    candidate anyway, or every scheduled run re-asks it forever."""
    match = _match(db_session, "apif-200")
    monkeypatch.setattr("scripts.fetch_match_stats.fetch_statistics", lambda *a, **k: [])
    monkeypatch.setattr("scripts.fetch_match_stats.fetch_events", lambda *a, **k: [])

    updated = backfill_match_stats(db_session, settings=_FakeSettings(), max_fixtures=10)
    db_session.commit()
    db_session.refresh(match)

    assert updated == 0
    assert match.stats_fetched_at is not None
    assert match.home_shots is None


def test_events_are_stored_against_the_match(db_session, monkeypatch):
    match = _match(db_session, "apif-300", home_score=1, away_score=0)
    monkeypatch.setattr("scripts.fetch_match_stats.fetch_statistics", lambda *a, **k: [])
    monkeypatch.setattr(
        "scripts.fetch_match_stats.fetch_events",
        lambda *a, **k: [_goal_event(match.home_team.name, 33, "A. Striker")],
    )

    updated = backfill_match_stats(db_session, settings=_FakeSettings(), max_fixtures=10)
    db_session.commit()

    assert updated == 1
    stored = db_session.query(MatchEvent).filter_by(match_id=match.id).all()
    assert len(stored) == 1
    assert stored[0].player == "A. Striker"


def test_a_rate_limit_stops_the_run_instead_of_crashing_it(db_session, monkeypatch):
    # `backfill_match_stats` orders candidates most-recent-first, so `days_ago`
    # pins which one is processed first regardless of insertion order.
    first = _match(db_session, "apif-400", days_ago=1)
    stays_unmarked = _match(db_session, "apif-401", days_ago=2)

    calls = []

    def fake_fetch_statistics(fixture_id, api_key, base_url):
        calls.append(fixture_id)
        if len(calls) == 1:
            return []
        raise RateLimited("rate limited")

    monkeypatch.setattr("scripts.fetch_match_stats.fetch_statistics", fake_fetch_statistics)
    monkeypatch.setattr("scripts.fetch_match_stats.fetch_events", lambda *a, **k: [])

    backfill_match_stats(db_session, settings=_FakeSettings(), max_fixtures=10)
    db_session.commit()
    db_session.refresh(first)
    db_session.refresh(stays_unmarked)

    assert len(calls) == 2
    assert first.stats_fetched_at is not None
    assert stays_unmarked.stats_fetched_at is None


def test_backfill_caps_at_max_fixtures(db_session, monkeypatch):
    for i in range(5):
        _match(db_session, f"apif-{500 + i}")

    monkeypatch.setattr("scripts.fetch_match_stats.fetch_statistics", lambda *a, **k: [])
    monkeypatch.setattr("scripts.fetch_match_stats.fetch_events", lambda *a, **k: [])

    calls = []
    monkeypatch.setattr(
        "scripts.fetch_match_stats.fetch_statistics",
        lambda fixture_id, *a, **k: calls.append(fixture_id) or [],
    )

    backfill_match_stats(db_session, settings=_FakeSettings(), max_fixtures=2)
    assert len(calls) == 2
