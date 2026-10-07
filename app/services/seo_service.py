"""What belongs in the sitemap.

A sitemap tells a search engine which URLs exist and when each last changed. Two
rules decide what goes in. Only pages that carry real content are listed: a team
that last played years ago, or a fixture from months back, is a thin page a
crawler should not be steered towards. And every date is a real one, taken from
the matches themselves, never "today" stamped on everything, because a lastmod
that always says "just now" teaches a crawler to ignore it.

Match pages are the churn: they are listed from a fortnight back (the graded
results people search for) to a week ahead (the predictions they search for).
League and team pages are the stable core.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.match import Match
from app.models.team import Team
from app.services.board_service import match_slug
from app.services.league_service import slug_for
from app.services.team_page_service import team_slug
from ml.competition_catalogue import meta_for

# A team with no match inside this window is not worth sending a crawler to.
TEAM_ACTIVE_DAYS = 365
MATCH_DAYS_BACK = 14
MATCH_DAYS_AHEAD = 7


def _iso(value: datetime | None) -> str | None:
    return value.date().isoformat() if value else None


def _leagues(session: Session) -> list[dict]:
    rows = (
        session.query(Match.competition, func.max(Match.match_date))
        .filter(Match.sport == "football", Match.status == "completed")
        .group_by(Match.competition)
        .all()
    )
    return sorted(
        (
            {"slug": slug_for(competition), "lastmod": _iso(latest)}
            for competition, latest in rows
            if meta_for(competition) is not None
        ),
        key=lambda entry: entry["slug"],
    )


def _teams(session: Session, now: datetime) -> list[dict]:
    since = now - timedelta(days=TEAM_ACTIVE_DAYS)
    latest: dict[int, datetime] = {}
    for column in (Match.home_team_id, Match.away_team_id):
        for team_id, when in (
            session.query(column, func.max(Match.match_date))
            .filter(Match.sport == "football", Match.match_date >= since)
            .group_by(column)
            .all()
        ):
            if team_id not in latest or when > latest[team_id]:
                latest[team_id] = when

    names = {
        team.id: team.name
        for team in session.query(Team).filter(Team.id.in_(list(latest) or [0])).all()
    }
    by_slug: dict[str, dict] = {}
    for team_id, when in latest.items():
        name = names.get(team_id)
        if not name:
            continue
        slug = team_slug(name)
        # Two clubs can fold to one slug; the page resolves to one of them, so
        # list the slug once, dated by whichever played most recently.
        if slug not in by_slug or when > datetime.fromisoformat(by_slug[slug]["lastmod"]):
            by_slug[slug] = {"slug": slug, "lastmod": _iso(when)}
    return sorted(by_slug.values(), key=lambda entry: entry["slug"])


def _matches(session: Session, now: datetime) -> list[dict]:
    start = now - timedelta(days=MATCH_DAYS_BACK)
    end = now + timedelta(days=MATCH_DAYS_AHEAD)
    matches = (
        session.query(Match)
        .filter(Match.sport == "football", Match.match_date >= start, Match.match_date <= end)
        .order_by(Match.match_date.desc())
        .all()
    )
    names = {
        team.id: team.name
        for team in session.query(Team)
        .filter(Team.id.in_({m.home_team_id for m in matches} | {m.away_team_id for m in matches}))
        .all()
    }
    return [
        {
            "slug": match_slug(
                names.get(match.home_team_id, ""), names.get(match.away_team_id, ""), match.id
            ),
            "lastmod": _iso(match.match_date),
        }
        for match in matches
        if names.get(match.home_team_id) and names.get(match.away_team_id)
    ]


def sitemap_entries(session: Session) -> dict:
    now = datetime.now(UTC).replace(tzinfo=None)
    return {
        "leagues": _leagues(session),
        "teams": _teams(session, now),
        "matches": _matches(session, now),
    }
