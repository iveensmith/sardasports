"""The yardstick every market call is judged against.

These rates are what stop the board saying "over 1.5 goals, 76%" as though it
were a finding. They are measured rather than written down, so the risks are
arithmetic ones: counting a market over matches that never recorded it,
double-counting a derived market, or caching a table across a database that
has since changed.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.models import Match, Team
from app.services.base_rates import MIN_SAMPLE, market_base_rates, reset_cache


@pytest.fixture(autouse=True)
def _drop_cache():
    """The table is cached for the process, so a test must start clean."""
    reset_cache()
    yield
    reset_cache()


_seed_calls = 0


def _seed(session, results, sport="football", **extra):
    """`results` is a list of (home_score, away_score) tuples.

    Teams and external ids are tagged per call so a test can seed twice
    without tripping `UNIQUE(sport, name)` on teams.
    """
    global _seed_calls
    _seed_calls += 1
    tag = _seed_calls
    home = Team(name=f"H-{sport}-{tag}", league="Test", sport=sport)
    away = Team(name=f"A-{sport}-{tag}", league="Test", sport=sport)
    session.add_all([home, away])
    session.flush()
    start = datetime(2024, 1, 1)
    for index, (home_score, away_score) in enumerate(results):
        session.add(
            Match(
                external_id=f"{sport}-{tag}-{index}",
                match_date=start + timedelta(days=index),
                competition="Test League",
                season="2024",
                home_team_id=home.id,
                away_team_id=away.id,
                home_score=home_score,
                away_score=away_score,
                status="completed",
                sport=sport,
                **extra,
            )
        )
    session.commit()


def test_match_result_rates_are_the_observed_frequencies(db_session):
    # 200 matches: 100 home wins, 60 draws, 40 away wins.
    _seed(db_session, [(2, 0)] * 100 + [(1, 1)] * 60 + [(0, 1)] * 40)
    rates = market_base_rates(db_session)
    assert rates["match_result:home"] == pytest.approx(50.0)
    assert rates["match_result:draw"] == pytest.approx(30.0)
    assert rates["match_result:away"] == pytest.approx(20.0)


def test_double_chance_is_derived_from_the_same_counts(db_session):
    """Derived the way the calls are, so a call and its yardstick can never
    be computed two different ways and disagree."""
    _seed(db_session, [(2, 0)] * 100 + [(1, 1)] * 60 + [(0, 1)] * 40)
    rates = market_base_rates(db_session)
    assert rates["double_chance:home_draw"] == pytest.approx(80.0)
    assert rates["double_chance:away_draw"] == pytest.approx(50.0)
    assert rates["double_chance:home_away"] == pytest.approx(70.0)


def test_over_and_under_sum_to_a_hundred(db_session):
    _seed(db_session, [(2, 1)] * 120 + [(0, 0)] * 80)
    rates = market_base_rates(db_session)
    for line in ("1.5", "2.5"):
        assert rates[f"goals:over_{line}"] + rates[f"goals:under_{line}"] == pytest.approx(
            100.0, abs=0.2
        )


def test_a_market_with_no_recorded_data_gets_no_rate(db_session):
    """Corners are absent for several competitions. Counting those matches as
    zero corners would drag every corners rate towards nothing."""
    _seed(db_session, [(1, 0)] * 250)  # no corners recorded
    rates = market_base_rates(db_session)
    assert not any(key.startswith("corners:") for key in rates)
    assert not any(key.startswith("cards:") for key in rates)


def test_a_recorded_market_is_counted_only_over_matches_that_record_it(db_session):
    """Half the matches carry corners; the rate must be over those, not all."""
    home = Team(name="H", league="Test", sport="football")
    away = Team(name="A", league="Test", sport="football")
    db_session.add_all([home, away])
    db_session.flush()
    start = datetime(2024, 1, 1)
    for index in range(400):
        recorded = index < 250
        db_session.add(
            Match(
                external_id=f"m-{index}",
                match_date=start + timedelta(days=index),
                competition="Test League",
                season="2024",
                home_team_id=home.id,
                away_team_id=away.id,
                home_score=1,
                away_score=0,
                status="completed",
                sport="football",
                # Every recorded match has 10 corners, so over 7.5 is 100%.
                home_corners=5 if recorded else None,
                away_corners=5 if recorded else None,
            )
        )
    db_session.commit()

    rates = market_base_rates(db_session)
    assert rates["corners:over_7.5"] == pytest.approx(100.0)
    assert rates["corners:under_7.5"] == pytest.approx(0.0)


def test_too_little_history_produces_no_table_rather_than_a_fake_one(db_session):
    _seed(db_session, [(1, 0)] * (MIN_SAMPLE - 1))
    assert market_base_rates(db_session) == {}


def test_rates_are_scoped_to_one_sport(db_session):
    """Basketball has no draws. Averaging it into football's table would
    quietly move every football rate."""
    _seed(db_session, [(2, 0)] * 200, sport="football")
    _seed(db_session, [(110, 100)] * 200, sport="basketball")
    football = market_base_rates(db_session, "football")
    assert football["match_result:home"] == pytest.approx(100.0)


def test_an_unfinished_match_is_not_counted(db_session):
    _seed(db_session, [(2, 0)] * 200)
    db_session.add(
        Match(
            external_id="scheduled-1",
            match_date=datetime(2030, 1, 1),
            competition="Test League",
            season="2030",
            home_team_id=db_session.query(Team).order_by(Team.id).all()[0].id,
            away_team_id=db_session.query(Team).order_by(Team.id).all()[1].id,
            home_score=None,
            away_score=None,
            status="scheduled",
            sport="football",
        )
    )
    db_session.commit()
    assert market_base_rates(db_session)["match_result:home"] == pytest.approx(100.0)


def test_the_table_is_cached_so_a_board_costs_one_scan(db_session):
    _seed(db_session, [(2, 0)] * 200)
    first = market_base_rates(db_session)
    _seed(db_session, [(0, 2)] * 200)  # would halve the home rate if re-read
    assert market_base_rates(db_session) is first


def test_resetting_the_cache_picks_up_new_matches(db_session):
    _seed(db_session, [(2, 0)] * 200)
    assert market_base_rates(db_session)["match_result:home"] == pytest.approx(100.0)
    _seed(db_session, [(0, 2)] * 200, sport="football2")
    reset_cache()
    # Same sport, so still 100% — but the read really did happen again.
    assert market_base_rates(db_session)["match_result:home"] == pytest.approx(100.0)
