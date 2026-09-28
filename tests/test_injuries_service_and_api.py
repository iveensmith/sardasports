"""Tests for app.services.injury_service, the agent's get_injuries tool, and
GET /injuries/{team} — all reading data already stored (no network calls)."""

from __future__ import annotations

from datetime import UTC, datetime

from app.agents.tools import get_injuries as tool_get_injuries
from app.models import Injury, Team
from app.services.injury_service import get_team_injuries


def _seed_team_with_injuries(db_session, synced: bool = True):
    team = Team(name="Arsenal")
    db_session.add(team)
    db_session.flush()

    if synced:
        team.injuries_synced_at = datetime.now(UTC).replace(tzinfo=None)
        db_session.add(
            Injury(
                team_id=team.id, player_name="Bukayo Saka", injury_type="Injury", reason="Hamstring"
            )
        )
    db_session.commit()
    return team


def test_get_team_injuries_returns_stored_rows(db_session):
    team = _seed_team_with_injuries(db_session)
    injuries = get_team_injuries(db_session, team)
    assert len(injuries) == 1
    assert injuries[0].player_name == "Bukayo Saka"


def test_get_team_injuries_empty_for_never_synced_team(db_session):
    team = _seed_team_with_injuries(db_session, synced=False)
    injuries = get_team_injuries(db_session, team)
    assert injuries == []


def test_agent_tool_get_injuries_reports_unavailable_when_never_synced(db_session):
    team = _seed_team_with_injuries(db_session, synced=False)
    result = tool_get_injuries(db_session, team.name)
    assert result["available"] is False
    assert "sync_injuries.py" in result["message"]


def test_agent_tool_get_injuries_returns_real_data_when_synced(db_session):
    _seed_team_with_injuries(db_session, synced=True)
    result = tool_get_injuries(db_session, "Arsenal")
    assert result["available"] is True
    assert result["injuries"] == [
        {"player": "Bukayo Saka", "type": "Injury", "reason": "Hamstring"}
    ]


def test_injuries_endpoint_unavailable_when_never_synced(client, db_session):
    team = _seed_team_with_injuries(db_session, synced=False)
    response = client.get(f"/injuries/{team.name}")
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert body["injuries"] == []


def test_injuries_endpoint_returns_real_data_when_synced(client, db_session):
    _seed_team_with_injuries(db_session, synced=True)
    response = client.get("/injuries/Arsenal")
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    assert len(body["injuries"]) == 1
    assert body["injuries"][0]["player_name"] == "Bukayo Saka"


def test_injuries_endpoint_404_for_unknown_team(client):
    response = client.get("/injuries/Definitely Not A Team")
    assert response.status_code == 404
