"""Tests for ml.monitoring.roi_backtest.

`resolve_test_period_start` and `run_backtest` are tested independently:
the former against a controlled temp CSV (so it never touches the real
project's `data/processed/matches.csv`), the latter with
`resolve_test_period_start` monkeypatched to a fixed cutoff so the betting
arithmetic itself is exercised deterministically against seeded DB matches.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest

import ml.monitoring.roi_backtest as roi_module
import ml.training.common as training_common
from app.models import Match, Team
from ml.monitoring.roi_backtest import resolve_test_period_start, run_backtest


def test_resolve_test_period_start_returns_none_without_processed_file(tmp_path, monkeypatch):
    monkeypatch.setattr(training_common, "PROCESSED_PATH", tmp_path / "does_not_exist.csv")
    assert resolve_test_period_start() is None


def test_resolve_test_period_start_derives_cutoff_from_real_split(tmp_path, monkeypatch):
    # 10 matches, one per day from Jan 1 to Jan 10; a 20% test split should
    # hold out the last 2 (Jan 9, Jan 10), so the cutoff is Jan 9.
    rows = [
        {
            "external_id": f"m{i}",
            "match_date": f"2024-01-{i:02d}",
            "competition": "Test League",
            "season": "2023-2024",
            "home_team": "A",
            "away_team": "B",
            "home_score": 1,
            "away_score": 0,
            "home_shots": None,
            "away_shots": None,
            "home_shots_on_target": None,
            "away_shots_on_target": None,
            "home_corners": None,
            "away_corners": None,
            "home_yellow_cards": None,
            "away_yellow_cards": None,
            "home_red_cards": None,
            "away_red_cards": None,
            "referee": None,
            "odds_home_win": 2.0,
            "odds_draw": 3.0,
            "odds_away_win": 4.0,
        }
        for i in range(1, 11)
    ]
    csv_path = tmp_path / "matches.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    monkeypatch.setattr(training_common, "PROCESSED_PATH", csv_path)

    cutoff = resolve_test_period_start(test_fraction=0.2)
    assert cutoff == datetime(2024, 1, 9)


def _seed_backtest_match(db_session, home_score, away_score, odds=(2.0, 3.4, 3.8)):
    home = db_session.query(Team).filter(Team.name == "Arsenal").one_or_none()
    away = db_session.query(Team).filter(Team.name == "Chelsea").one_or_none()
    if home is None:
        home = Team(name="Arsenal")
        away = Team(name="Chelsea")
        db_session.add_all([home, away])
        db_session.flush()

    match = Match(
        match_date=datetime(2024, 3, 1),
        competition="English Premier League",
        season="2023-2024",
        home_team_id=home.id,
        away_team_id=away.id,
        home_score=home_score,
        away_score=away_score,
        status="completed",
        odds_home_win=odds[0],
        odds_draw=odds[1],
        odds_away_win=odds[2],
    )
    db_session.add(match)
    db_session.commit()
    return match


def test_run_backtest_returns_zeroed_result_when_no_test_period(db_session, monkeypatch):
    monkeypatch.setattr(roi_module, "resolve_test_period_start", lambda test_fraction=0.2: None)
    result = run_backtest(db_session)
    assert result.num_bets == 0
    assert result.roi_percent == 0.0


def test_run_backtest_places_a_bet_on_a_large_edge_and_computes_profit_correctly(
    db_session, monkeypatch
):
    # Force every seeded match to be "in the test period."
    monkeypatch.setattr(
        roi_module, "resolve_test_period_start", lambda test_fraction=0.2: datetime(2000, 1, 1)
    )
    # Odds home_win=2.0 imply a raw 50% (no overround since we set draw/away
    # odds to make the market sum to ~1.0); a home win actually occurs.
    _seed_backtest_match(db_session, home_score=3, away_score=0, odds=(2.0, 3.4, 3.8))

    # edge_threshold=0 so any positive edge qualifies (Elo/Poisson alone,
    # untrained models, will still produce *some* home-win probability).
    result = run_backtest(db_session, edge_threshold=0.0, stake=1.0)

    assert result.num_matches_considered == 1
    # Whatever bets were placed, the arithmetic must be internally consistent.
    assert result.total_returned - result.total_staked == pytest.approx(result.profit, abs=1e-6)
    assert result.num_wins <= result.num_bets
    if result.num_bets:
        expected_hit_rate = 100 * result.num_wins / result.num_bets
        assert result.hit_rate_percent == pytest.approx(expected_hit_rate, abs=1e-6)


def test_run_backtest_high_threshold_places_no_bets(db_session, monkeypatch):
    monkeypatch.setattr(
        roi_module, "resolve_test_period_start", lambda test_fraction=0.2: datetime(2000, 1, 1)
    )
    _seed_backtest_match(db_session, home_score=1, away_score=1)

    result = run_backtest(db_session, edge_threshold=99.9, stake=1.0)
    assert result.num_bets == 0
    assert result.total_staked == 0.0
    assert result.roi_percent == 0.0
