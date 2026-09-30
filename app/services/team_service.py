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
            "season": m.season,
            "home_team": id_to_name[m.home_team_id],
            "away_team": id_to_name[m.away_team_id],
            "home_score": m.home_score,
            "away_score": m.away_score,
            # Season-average stats (see `compute_season_stat_averages`) —
            # None where the source never recorded it, which is skipped
            # from the average rather than counted as zero.
            "home_shots": m.home_shots,
            "away_shots": m.away_shots,
            "home_shots_on_target": m.home_shots_on_target,
            "away_shots_on_target": m.away_shots_on_target,
            "home_corners": m.home_corners,
            "away_corners": m.away_corners,
            "home_cards": _sum_or_none(m.home_yellow_cards, m.home_red_cards),
            "away_cards": _sum_or_none(m.away_yellow_cards, m.away_red_cards),
            "home_possession": m.home_possession,
            "away_possession": m.away_possession,
            "home_offsides": m.home_offsides,
            "away_offsides": m.away_offsides,
            "home_fouls": m.home_fouls,
            "away_fouls": m.away_fouls,
        }
        for m in matches
    ]


def _sum_or_none(a: int | None, b: int | None) -> int | None:
    """Yellow + red cards, `None` only when *both* are unrecorded — a
    competition that records yellows but had no reds in a match still has a
    genuine cards total, not a missing one."""
    if a is None and b is None:
        return None
    return (a or 0) + (b or 0)


STAT_FIELD_PAIRS: dict[str, tuple[str, str]] = {
    "shots": ("home_shots", "away_shots"),
    "shots_on_target": ("home_shots_on_target", "away_shots_on_target"),
    "corners": ("home_corners", "away_corners"),
    "cards": ("home_cards", "away_cards"),
    "possession": ("home_possession", "away_possession"),
    "offsides": ("home_offsides", "away_offsides"),
    "fouls": ("home_fouls", "away_fouls"),
}


def compute_season_stat_averages(matches: list[dict], team: str) -> dict | None:
    """Average per match, current-season only, for every stat that has one
    beyond goals (already covered by `compute_team_form`'s goals_scored/
    goals_conceded). `None` if the team has no completed match history at
    all; a stat with nothing recorded this season reports `None` for that
    stat specifically rather than a fabricated 0.0 — several of these
    (possession, offsides, fouls) only exist going forward from
    `scripts/fetch_match_stats.py`, so a team early in that rollout may have
    a real sample size of zero for them even with a full season of goals.

    "Current season" is whichever season the team's most recent match falls
    in — `matches` must already be sorted ascending by date, the shape
    `get_team_matches_as_dicts` returns.
    """
    if not matches:
        return None
    season = matches[-1]["season"]
    season_matches = [m for m in matches if m["season"] == season]

    stats: dict[str, dict] = {}
    for stat, (home_attr, away_attr) in STAT_FIELD_PAIRS.items():
        values = [
            m[home_attr] if m["home_team"] == team else m[away_attr]
            for m in season_matches
        ]
        values = [v for v in values if v is not None]
        stats[stat] = {
            "value": round(sum(values) / len(values), 2) if values else None,
            "sample_size": len(values),
        }

    return {"season": season, "matches_played": len(season_matches), **stats}


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
        "season_stats": compute_season_stat_averages(history, team.name),
    }
