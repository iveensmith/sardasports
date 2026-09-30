"""Pricing fixtures the bulk /odds pass misses.

`/odds?date=` paginates every fixture API-Football knows about that day, and
a free plan caps that pagination at 3 pages — confirmed directly against the
API. On a busy day our own modelled fixtures don't all land in the first 3
pages, and once a match kicks off there is no going back to price it from
that endpoint. `backfill_missing_odds` closes that gap with a per-fixture
lookup, scoped tightly enough that it can't quietly re-fetch or over-spend
quota on fixtures that were never candidates for it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.models import Match, Team
from scripts.fetch_odds import apply_prices, backfill_missing_odds, best_prices


def _bookmaker_entry(match_winner=None, goals=None, btts=None):
    values = []
    if match_winner:
        values.append(
            {
                "id": 1,
                "name": "Match Winner",
                "values": [
                    {"value": k.capitalize(), "odd": str(v)} for k, v in match_winner.items()
                ],
            }
        )
    if goals:
        values.append(
            {
                "id": 2,
                "name": "Goals Over/Under",
                "values": [{"value": k, "odd": str(v)} for k, v in goals.items()],
            }
        )
    if btts:
        values.append(
            {
                "id": 3,
                "name": "Both Teams Score",
                "values": [{"value": k.capitalize(), "odd": str(v)} for k, v in btts.items()],
            }
        )
    return {"bookmakers": [{"id": 1, "name": "Test Book", "bets": values}]}


# --- parsing -----------------------------------------------------------


def test_best_prices_picks_the_highest_across_bookmakers():
    item = {
        "bookmakers": [
            {"bets": [{"name": "Match Winner", "values": [{"value": "Home", "odd": "1.80"}]}]},
            {"bets": [{"name": "Match Winner", "values": [{"value": "Home", "odd": "1.95"}]}]},
        ]
    }
    prices = best_prices(item)
    assert prices["match_winner"]["home"] == 1.95


def test_unpriceable_markets_are_dropped():
    """Asian handicaps, exact-goals props etc. have no model to compare
    against, so keeping them would print a price with nothing beside it."""
    item = {
        "bookmakers": [
            {
                "bets": [
                    {"name": "Asian Handicap", "values": [{"value": "Home -1.5", "odd": "1.90"}]}
                ]
            }
        ]
    }
    assert best_prices(item) == {}


def test_quarter_goal_lines_are_dropped():
    """The engine only prices whole '.5' lines."""
    item = _bookmaker_entry(goals={"Over 2.25": 1.90})
    assert best_prices(item) == {}


# --- applying to a match -------------------------------------------------


def _match(session, external_id, days_ago=0, **extra):
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
        status="scheduled",
        **extra,
    )
    session.add(match)
    session.commit()
    return match


def test_apply_prices_mirrors_match_winner_into_legacy_columns(db_session):
    match = _match(db_session, "apif-1")
    apply_prices(db_session, match, {"match_winner": {"home": 1.8, "draw": 3.4, "away": 4.2}})
    db_session.commit()
    db_session.refresh(match)

    assert match.odds_home_win == 1.8
    assert match.odds_draw == 3.4
    assert match.odds_away_win == 4.2
    assert match.odds_markets == {"match_winner": {"home": 1.8, "draw": 3.4, "away": 4.2}}
    assert match.odds_updated_at is not None


# --- the per-fixture backfill --------------------------------------------


class _FakeSettings:
    api_football_key = "test-key"
    api_football_base_url = "https://example.test"


def test_backfill_only_targets_api_football_fixtures_missing_a_price(db_session, monkeypatch):
    """CSV-sourced historical rows use a different external_id scheme
    entirely and were never candidates for a live lookup; a match the bulk
    pass already priced should not be re-fetched either."""
    live_unpriced = _match(db_session, "apif-200")
    live_priced = _match(db_session, "apif-201", odds_markets={"match_winner": {"home": 1.5}})
    csv_row = _match(db_session, "English-Premier-League_2024-01-01_A_vs_B")

    seen_ids = []

    def fake_fetch_fixture(fixture_id, api_key, base_url):
        seen_ids.append(fixture_id)
        return _bookmaker_entry(match_winner={"home": 2.1, "draw": 3.3, "away": 3.0})

    monkeypatch.setattr("scripts.fetch_odds.fetch_fixture", fake_fetch_fixture)

    since = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1)
    until = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=1)
    updated = backfill_missing_odds(
        db_session, settings=_FakeSettings(), since=since, until=until, max_fixtures=10
    )
    db_session.commit()

    assert seen_ids == ["200"]
    assert updated == 1
    db_session.refresh(live_unpriced)
    db_session.refresh(live_priced)
    db_session.refresh(csv_row)
    assert live_unpriced.odds_home_win == 2.1
    assert live_priced.odds_markets == {"match_winner": {"home": 1.5}}
    assert csv_row.odds_markets is None


def test_backfill_respects_the_date_window(db_session, monkeypatch):
    _match(db_session, "apif-300", days_ago=30)  # well outside any window

    monkeypatch.setattr(
        "scripts.fetch_odds.fetch_fixture",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not be called")),
    )

    since = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=3)
    until = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=3)
    updated = backfill_missing_odds(
        db_session, settings=_FakeSettings(), since=since, until=until, max_fixtures=10
    )
    assert updated == 0


def test_backfill_caps_at_max_fixtures(db_session, monkeypatch):
    for i in range(5):
        _match(db_session, f"apif-{400 + i}")

    monkeypatch.setattr(
        "scripts.fetch_odds.fetch_fixture",
        lambda *a, **k: _bookmaker_entry(match_winner={"home": 2.0, "draw": 3.0, "away": 3.5}),
    )

    since = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1)
    until = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=1)
    updated = backfill_missing_odds(
        db_session, settings=_FakeSettings(), since=since, until=until, max_fixtures=2
    )
    assert updated == 2


def test_a_fixture_with_no_odds_available_is_left_unpriced(db_session, monkeypatch):
    match = _match(db_session, "apif-500")
    monkeypatch.setattr("scripts.fetch_odds.fetch_fixture", lambda *a, **k: None)

    since = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1)
    until = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=1)
    updated = backfill_missing_odds(
        db_session, settings=_FakeSettings(), since=since, until=until, max_fixtures=10
    )

    assert updated == 0
    db_session.refresh(match)
    assert match.odds_markets is None


def test_a_rate_limit_stops_the_run_instead_of_crashing_it(db_session, monkeypatch):
    """A 429 is the per-minute cap, not "no odds" — every fixture after this
    one would fail the same way this run, so the loop should stop cleanly
    (leaving them for the next scheduled run) rather than raise."""
    from scripts.fetch_odds import RateLimited

    priced_first = _match(db_session, "apif-600")
    stays_unpriced = _match(db_session, "apif-601")

    calls = []

    def fake_fetch_fixture(fixture_id, api_key, base_url):
        calls.append(fixture_id)
        if len(calls) == 1:
            return _bookmaker_entry(match_winner={"home": 2.0, "draw": 3.0, "away": 3.5})
        raise RateLimited("rate limited")

    monkeypatch.setattr("scripts.fetch_odds.fetch_fixture", fake_fetch_fixture)

    since = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1)
    until = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=1)
    updated = backfill_missing_odds(
        db_session, settings=_FakeSettings(), since=since, until=until, max_fixtures=10
    )
    db_session.commit()

    assert updated == 1
    assert len(calls) == 2
    db_session.refresh(priced_first)
    db_session.refresh(stays_unpriced)
    assert priced_first.odds_markets is not None
    assert stays_unpriced.odds_markets is None
