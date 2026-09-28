"""Tests for GET /standings/{competition} and GET /model/roi-backtest."""

from __future__ import annotations

from datetime import datetime

from app.models import Match, Team


def test_standings_endpoint_returns_a_real_table(client, db_session):
    a = Team(name="Arsenal")
    b = Team(name="Chelsea")
    db_session.add_all([a, b])
    db_session.flush()
    db_session.add(
        Match(
            match_date=datetime(2024, 1, 1),
            competition="English Premier League",
            season="2023-2024",
            home_team_id=a.id,
            away_team_id=b.id,
            home_score=2,
            away_score=1,
            status="completed",
        )
    )
    db_session.commit()

    response = client.get("/standings/English Premier League")
    assert response.status_code == 200
    body = response.json()
    assert body["season"] == "2023-2024"
    assert {row["team"] for row in body["table"]} == {"Arsenal", "Chelsea"}
    top = next(r for r in body["table"] if r["team"] == "Arsenal")
    assert top["points"] == 3


def test_standings_endpoint_404_for_unknown_competition(client):
    response = client.get("/standings/Nonexistent League")
    assert response.status_code == 404


def test_roi_backtest_endpoint_returns_a_real_shaped_response(client, db_session):
    response = client.get("/model/roi-backtest")
    assert response.status_code == 200
    body = response.json()
    assert "roi_percent" in body
    assert "disclaimer" in body
    assert body["num_bets"] >= 0


def test_roi_backtest_endpoint_accepts_query_params(client):
    response = client.get("/model/roi-backtest", params={"edge_threshold": 10, "stake": 2.5})
    assert response.status_code == 200
    body = response.json()
    assert body["edge_threshold"] == 10.0
    assert body["stake_per_bet"] == 2.5


class _FakeCache:
    """A minimal in-memory stand-in for app.utils.cache.Cache, since Redis is
    disabled in the test environment (REDIS_URL="") and its real Cache would
    silently no-op — this test needs an actually-working cache to verify
    against."""

    def __init__(self):
        self.store = {}

    def get_json(self, key):
        return self.store.get(key)

    def set_json(self, key, value, ttl_seconds=300):
        self.store[key] = value


def test_roi_backtest_endpoint_caches_the_expensive_computation(client, db_session, monkeypatch):
    """Regression test: the real backtest takes ~2 minutes uncached (see
    routes_roi.py docstring) — a second identical request must be served
    from cache, not recomputed, or the endpoint is effectively unusable."""
    import app.api.routes_roi as roi_route
    from ml.monitoring.roi_backtest import BacktestResult

    call_count = {"n": 0}

    def fake_run_backtest(session, edge_threshold=5.0, stake=1.0, test_fraction=0.2):
        call_count["n"] += 1
        return BacktestResult(
            edge_threshold=edge_threshold,
            stake_per_bet=stake,
            num_matches_considered=0,
            num_bets=0,
            num_wins=0,
            total_staked=0.0,
            total_returned=0.0,
            profit=0.0,
            roi_percent=0.0,
            hit_rate_percent=0.0,
            bets=[],
        )

    fake_cache = _FakeCache()  # one shared instance — get_cache() must return the SAME
    # cache both requests, or "caching" would just create a fresh empty one each time.
    monkeypatch.setattr(roi_route, "run_backtest", fake_run_backtest)
    monkeypatch.setattr(roi_route, "get_cache", lambda: fake_cache)

    first = client.get("/model/roi-backtest")
    second = client.get("/model/roi-backtest")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert call_count["n"] == 1  # the second call was served from cache, not recomputed
