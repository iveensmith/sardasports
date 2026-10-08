"""Tool implementations for the AI analyst agent.

Every tool is a thin wrapper over an existing, already-tested service
(`app.services.*`, `ml.prediction.predict`) — the agent never gets a code
path that could return fabricated data. `get_injuries` reads whatever
`scripts/sync_injuries.py` has synced from API-Football; if nothing has been
synced for a team yet, it says so explicitly rather than guessing.
`get_standings` is computed live from our own ingested match results, which
needs no external source at all.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models import Team
from app.services.injury_service import get_team_injuries
from app.services.prediction_service import MatchNotFoundError, predict_for_match
from app.services.standings_service import compute_standings
from app.services.team_service import get_team_detail, get_team_matches_as_dicts
from app.utils.team_names import normalize_team_name
from ml.feature_engineering.features import compute_head_to_head


class ToolError(Exception):
    """Raised when a tool can't fulfil a request — surfaced to the model as an error,
    never silently replaced with made-up data."""


def _get_team_or_raise(session: Session, name: str) -> Team:
    team = session.query(Team).filter(Team.name == normalize_team_name(name)).one_or_none()
    if team is None:
        raise ToolError(f"No team found matching '{name}'")
    return team


def get_team_form(session: Session, team: str) -> dict:
    """Recent form (last 5 / last 10 matches) and current Elo rating for a team."""
    team_obj = _get_team_or_raise(session, team)
    detail = get_team_detail(session, team_obj)
    return {
        "team": team_obj.name,
        "elo_rating": round(team_obj.elo_rating, 1),
        "form_last5": detail["form_last5"],
        "form_last10": detail["form_last10"],
    }


def get_recent_matches(session: Session, team: str, limit: int = 5) -> dict:
    """The team's most recent completed results."""
    team_obj = _get_team_or_raise(session, team)
    matches = get_team_matches_as_dicts(session, team_obj)
    recent = sorted(matches, key=lambda m: m["match_date"], reverse=True)[:limit]
    return {"team": team_obj.name, "recent_matches": recent}


def get_head_to_head(session: Session, home_team: str, away_team: str, limit: int = 5) -> dict:
    """Historical head-to-head record between two teams."""
    home = _get_team_or_raise(session, home_team)
    away = _get_team_or_raise(session, away_team)
    history = get_team_matches_as_dicts(session, home)
    h2h = compute_head_to_head(
        home.name, away.name, history, before_date=datetime.now(UTC).replace(tzinfo=None), n=limit
    )
    return {"home_team": home.name, "away_team": away.name, **h2h}


def get_model_prediction(session: Session, match_id: int) -> dict:
    """The ensemble engine's current prediction for a match — the same data /predict returns."""
    try:
        return predict_for_match(session, match_id)
    except MatchNotFoundError as exc:
        raise ToolError(str(exc)) from exc


def get_elo_rating(session: Session, team: str) -> dict:
    """A team's current Elo rating."""
    team_obj = _get_team_or_raise(session, team)
    return {"team": team_obj.name, "elo_rating": round(team_obj.elo_rating, 1)}


def get_injuries(session: Session, team: str) -> dict:
    """Current injuries/suspensions for a team, as last synced from API-Football."""
    team_obj = _get_team_or_raise(session, team)
    if team_obj.injuries_synced_at is None:
        return {
            "team": team_obj.name,
            "available": False,
            "message": (
                f"No injury data has been synced for {team_obj.name} yet. Run "
                f'`uv run python scripts/sync_injuries.py --team "{team_obj.name}"` '
                "(requires API_FOOTBALL_KEY)."
            ),
        }

    injuries = get_team_injuries(session, team_obj)
    return {
        "team": team_obj.name,
        "available": True,
        "synced_at": team_obj.injuries_synced_at.isoformat(),
        "injuries": [
            {"player": i.player_name, "type": i.injury_type, "reason": i.reason} for i in injuries
        ],
    }


def get_standings(session: Session, competition: str, season: str | None = None) -> dict:
    """Current league table, computed live from ingested match results."""
    resolved_season, table = compute_standings(session, competition, season)
    if not table:
        return {
            "competition": competition,
            "available": False,
            "message": f"No completed matches found for competition '{competition}'.",
        }
    return {
        "competition": competition,
        "season": resolved_season,
        "available": True,
        "table": [
            {
                "team": row.team,
                "played": row.played,
                "won": row.won,
                "drawn": row.drawn,
                "lost": row.lost,
                "goal_difference": row.goal_difference,
                "points": row.points,
            }
            for row in table
        ],
    }


def retrieve_knowledge(session: Session, query: str) -> dict:
    """Semantic search over SARDASPORTS's football-analytics knowledge base
    (methodology explanations, not live match data — use the other tools for that)."""
    from rag.retriever import query_knowledge_base

    passages = query_knowledge_base(query, n_results=3)
    if not passages:
        return {
            "query": query,
            "results": [],
            "message": "No relevant knowledge base entries found.",
        }
    return {
        "query": query,
        "results": [{"title": p.title, "text": p.text, "source": p.source} for p in passages],
    }


# Anthropic tool-use schema for every tool above. Descriptions are written for
# the model, not for humans — they state exactly what each tool can and can't
# answer so it doesn't try to use get_injuries/get_standings as if they were
# real data sources.
TOOL_DEFINITIONS = [
    {
        "name": "get_team_form",
        "description": (
            "Get a team's recent form (last 5 and last 10 match records) and current Elo rating."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"team": {"type": "string", "description": "Team name"}},
            "required": ["team"],
        },
    },
    {
        "name": "get_recent_matches",
        "description": "Get a team's most recent completed match results.",
        "input_schema": {
            "type": "object",
            "properties": {
                "team": {"type": "string"},
                "limit": {"type": "integer", "default": 5},
            },
            "required": ["team"],
        },
    },
    {
        "name": "get_head_to_head",
        "description": "Get the historical head-to-head record between two teams.",
        "input_schema": {
            "type": "object",
            "properties": {
                "home_team": {"type": "string"},
                "away_team": {"type": "string"},
                "limit": {"type": "integer", "default": 5},
            },
            "required": ["home_team", "away_team"],
        },
    },
    {
        "name": "get_model_prediction",
        "description": (
            "Get SARDASPORTS's current ensemble prediction (probabilities, expected goals, "
            "correct score, confidence) for a match by its match_id."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"match_id": {"type": "integer"}},
            "required": ["match_id"],
        },
    },
    {
        "name": "get_elo_rating",
        "description": "Get a team's current Elo rating.",
        "input_schema": {
            "type": "object",
            "properties": {"team": {"type": "string"}},
            "required": ["team"],
        },
    },
    {
        "name": "get_injuries",
        "description": (
            "Get current injuries/suspensions for a team, from the last API-Football sync. "
            "Returns available=false if no sync has run for that team yet — do not treat "
            "that as 'no injuries'; it means the data hasn't been fetched, not that it's empty."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"team": {"type": "string"}},
            "required": ["team"],
        },
    },
    {
        "name": "get_standings",
        "description": (
            "Get the current league table (played/won/drawn/lost/goal difference/points per "
            "team), computed live from ingested match results, most recent season by default."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "competition": {"type": "string"},
                "season": {
                    "type": "string",
                    "description": "e.g. '2024-2025'; omit for the most recent",
                },
            },
            "required": ["competition"],
        },
    },
    {
        "name": "retrieve_knowledge",
        "description": (
            "Semantic search over SARDASPORTS's football-analytics knowledge base (how "
            "Elo/Poisson/calibration/value-detection work, home advantage, injury-impact "
            "research). Use this for methodology/background questions, not for live match data."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
]

TOOL_DISPATCH = {
    "get_team_form": get_team_form,
    "get_recent_matches": get_recent_matches,
    "get_head_to_head": get_head_to_head,
    "get_model_prediction": get_model_prediction,
    "get_elo_rating": get_elo_rating,
    "get_injuries": get_injuries,
    "get_standings": get_standings,
    "retrieve_knowledge": retrieve_knowledge,
}
