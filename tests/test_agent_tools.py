"""Tests for app.agents.tools — the AI analyst's tool implementations.

No LLM calls here; these exercise the tool functions directly against the
test database, which is exactly what the agent loop calls internally.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.agents.tools import (
    ToolError,
    get_elo_rating,
    get_head_to_head,
    get_injuries,
    get_model_prediction,
    get_recent_matches,
    get_standings,
    get_team_form,
)
from app.models import Match, Team


def _seed(db_session):
    arsenal = Team(name="Arsenal", elo_rating=1620.0)
    chelsea = Team(name="Chelsea", elo_rating=1580.0)
    db_session.add_all([arsenal, chelsea])
    db_session.flush()

    db_session.add(
        Match(
            match_date=datetime(2024, 1, 1),
            competition="English Premier League",
            season="2023-2024",
            home_team_id=arsenal.id,
            away_team_id=chelsea.id,
            home_score=2,
            away_score=1,
            status="completed",
        )
    )
    fixture = Match(
        match_date=datetime(2024, 2, 1),
        competition="English Premier League",
        season="2023-2024",
        home_team_id=arsenal.id,
        away_team_id=chelsea.id,
        status="scheduled",
    )
    db_session.add(fixture)
    db_session.commit()
    return arsenal, chelsea, fixture


def test_get_team_form_returns_real_data(db_session):
    _seed(db_session)
    result = get_team_form(db_session, "Arsenal")
    assert result["team"] == "Arsenal"
    assert result["elo_rating"] == 1620.0
    assert result["form_last5"]["matches_played"] == 1


def test_get_team_form_unknown_team_raises_tool_error(db_session):
    with pytest.raises(ToolError):
        get_team_form(db_session, "Definitely Not A Team")


def test_get_recent_matches(db_session):
    _seed(db_session)
    result = get_recent_matches(db_session, "Chelsea", limit=5)
    assert result["team"] == "Chelsea"
    assert len(result["recent_matches"]) == 1


def test_get_head_to_head(db_session):
    _seed(db_session)
    result = get_head_to_head(db_session, "Arsenal", "Chelsea")
    assert result["h2h_matches_played"] == 1
    assert result["h2h_home_team_wins"] == 1


def test_get_elo_rating(db_session):
    _seed(db_session)
    result = get_elo_rating(db_session, "Chelsea")
    assert result["elo_rating"] == 1580.0


def test_get_model_prediction_returns_real_ensemble_output(db_session):
    _, _, fixture = _seed(db_session)
    result = get_model_prediction(db_session, fixture.id)
    assert result["home_team"] == "Arsenal"
    assert "home_win" in result


def test_get_model_prediction_unknown_match_raises_tool_error(db_session):
    with pytest.raises(ToolError):
        get_model_prediction(db_session, 999999)


def test_get_injuries_is_honest_about_unavailability_when_never_synced(db_session):
    _seed(db_session)  # Arsenal exists, but no injuries sync has ever run for it
    result = get_injuries(db_session, "Arsenal")
    assert result["available"] is False
    assert "sync_injuries.py" in result["message"]


def test_get_injuries_unknown_team_raises_tool_error(db_session):
    with pytest.raises(ToolError):
        get_injuries(db_session, "Definitely Not A Team")


def test_get_standings_is_honest_about_unavailability(db_session):
    result = get_standings(db_session, "English Premier League")
    assert result["available"] is False
