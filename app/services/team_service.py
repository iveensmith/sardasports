"""Team lookup service: current form and recent results."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import Match, Team
from ml.feature_engineering.features import (
    GoalRateForm,
    TeamForm,
    compute_goal_rate_form,
    compute_team_form,
)


def get_team_matches_as_dicts(
    session: Session, team: Team, before_date: datetime | None = None
) -> list[dict]:
    query = session.query(Match).filter(
        Match.status == "completed",
        or_(Match.home_team_id == team.id, Match.away_team_id == team.id),
    )
    if before_date is not None:
        query = query.filter(Match.match_date < before_date)

    matches = query.order_by(Match.match_date.asc()).all()
    team_ids = {m.home_team_id for m in matches} | {m.away_team_id for m in matches}
    # Resolve team names for the small set of teams involved.
    id_to_name = {t.id: t.name for t in session.query(Team).filter(Team.id.in_(team_ids)).all()}

    return [
        {
            "match_id": m.id,
            "match_date": m.match_date,
            "competition": m.competition,
            "home_team": id_to_name[m.home_team_id],
            "away_team": id_to_name[m.away_team_id],
            "home_score": m.home_score,
            "away_score": m.away_score,
        }
        for m in matches
    ]


def _form_to_summary(form: TeamForm, goal_rates: GoalRateForm) -> dict:
    return {
        "matches_played": form.matches_played,
        "wins": form.wins,
        "draws": form.draws,
        "losses": form.losses,
        "goals_scored": form.goals_scored,
        "goals_conceded": form.goals_conceded,
        "clean_sheets": form.clean_sheets,
        "points_per_game": round(form.points_per_game, 2),
        "over_1_5": goal_rates.over_1_5,
        "over_2_5": goal_rates.over_2_5,
        "over_3_5": goal_rates.over_3_5,
        "btts": goal_rates.btts,
    }


def get_team_detail(session: Session, team: Team) -> dict:
    now = datetime.now(UTC).replace(tzinfo=None)
    history = get_team_matches_as_dicts(session, team, before_date=None)

    form5 = compute_team_form(team.name, history, before_date=now, n=5)
    form10 = compute_team_form(team.name, history, before_date=now, n=10)
    rates5 = compute_goal_rate_form(team.name, history, before_date=now, n=5)
    rates10 = compute_goal_rate_form(team.name, history, before_date=now, n=10)

    recent = sorted(history, key=lambda m: m["match_date"], reverse=True)[:10]

    return {
        "team": team,
        "form_last5": _form_to_summary(form5, rates5),
        "form_last10": _form_to_summary(form10, rates10),
        "recent_matches": recent,
    }
