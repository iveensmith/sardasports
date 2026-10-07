"""A club or national team's own page: form, results, what is next, and its table.

Everything here is read from matches already on record. There is deliberately
no squad, no player list and no market value: none of those are ingested, and
inventing a plausible-looking figure for any of them is exactly what the
no-fabrication rule exists to stop. The page shows what the engine knows.

Teams are addressed by a readable slug (`aston-villa`) rather than by id or by
the raw name, for the same reason fixtures are (see
`app.services.board_service.match_slug`): it reads well in a link and in a
search result. Two clubs can fold to the same slug; the one with more matches
on record wins, since that is the one a reader most plausibly meant.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.match import Match
from app.models.team import Team
from app.services.board_service import match_slug, slugify
from app.services.standings_service import compute_standings
from app.services.team_service import get_team_detail
from ml.competition_catalogue import BY_COMPETITION, meta_for
from ml.competitions import is_international
from ml.team_badges import badge_dict

UPCOMING_LIMIT = 5
RECENT_LIMIT = 10
FORM_LETTERS = 6


# "Active" for the top-rated list: a club that has not played inside this window
# is not someone a visitor is likely looking for, whatever its old rating.
ACTIVE_WITHIN_DAYS = 90


def team_slug(name: str) -> str:
    return slugify(name)


def top_rated_teams(session: Session, limit: int = 8) -> list[dict]:
    """The highest-rated clubs that have played recently in a domestic league.

    Ranked by the engine's own Elo rating, which is the one team-level number it
    actually computes, and labelled as such — "popular" would need a traffic
    figure this site does not have. National sides are left out: their ratings
    are built from far fewer matches and sit on a different footing.
    """
    since = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=ACTIVE_WITHIN_DAYS)
    tiered = [m.competition for m in BY_COMPETITION.values() if m.tier is not None]
    active_ids: set[int] = set()
    for column in (Match.home_team_id, Match.away_team_id):
        active_ids.update(
            row[0]
            for row in session.query(column)
            .filter(Match.competition.in_(tiered), Match.match_date >= since)
            .distinct()
            .all()
        )
    if not active_ids:
        return []
    teams = (
        session.query(Team)
        .filter(Team.sport == "football", Team.id.in_(active_ids))
        .order_by(Team.elo_rating.desc(), Team.name.asc())
        .limit(limit)
        .all()
    )
    return [
        {"name": t.name, "slug": team_slug(t.name), "elo_rating": round(t.elo_rating, 0)}
        for t in teams
    ]


def resolve_team(session: Session, slug: str) -> Team | None:
    """The team a slug refers to, or None."""
    candidates = [
        team
        for team in session.query(Team).filter(Team.sport == "football").all()
        if team_slug(team.name) == slug
    ]
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    counts = dict(
        session.query(Match.home_team_id, func.count(Match.id))
        .filter(Match.home_team_id.in_([t.id for t in candidates]))
        .group_by(Match.home_team_id)
        .all()
    )
    return max(candidates, key=lambda t: counts.get(t.id, 0))


def _letter(match: dict, team: str) -> str | None:
    """W / D / L from this team's side, or None for an unplayed match."""
    home, away = match["home_score"], match["away_score"]
    if home is None or away is None:
        return None
    ours, theirs = (home, away) if match["home_team"] == team else (away, home)
    return "W" if ours > theirs else "L" if ours < theirs else "D"


def _home_league(session: Session, team: Team) -> tuple[str, str] | None:
    """The domestic league the team most recently played in, with its season.

    Cups and internationals carry no tier, and a table built from them would
    be meaningless, so only a tiered competition qualifies.
    """
    recent = (
        session.query(Match.competition, Match.season)
        .filter(
            Match.status == "completed",
            or_(Match.home_team_id == team.id, Match.away_team_id == team.id),
        )
        .order_by(Match.match_date.desc())
        .limit(40)
        .all()
    )
    for competition, season in recent:
        meta = meta_for(competition)
        if meta is not None and meta.tier is not None and not meta.is_international:
            return competition, season
    return None


def _standing(session: Session, team: Team) -> dict | None:
    league = _home_league(session, team)
    if league is None:
        return None
    competition, season = league
    resolved_season, table = compute_standings(session, competition, season)
    for position, row in enumerate(table, start=1):
        if row.team == team.name:
            meta = meta_for(competition)
            return {
                "competition": competition,
                "short_name": meta.short_name if meta else competition,
                "slug": slugify(competition),
                "season": resolved_season,
                "position": position,
                "of": len(table),
                "row": vars(row),
            }
    return None


def _upcoming(session: Session, team: Team) -> list[dict]:
    now = datetime.now(UTC).replace(tzinfo=None)
    matches = (
        session.query(Match)
        .filter(
            Match.status != "completed",
            Match.match_date >= now,
            or_(Match.home_team_id == team.id, Match.away_team_id == team.id),
        )
        .order_by(Match.match_date.asc())
        .limit(UPCOMING_LIMIT)
        .all()
    )
    names = {
        t.id: t.name
        for t in session.query(Team)
        .filter(Team.id.in_({m.home_team_id for m in matches} | {m.away_team_id for m in matches}))
        .all()
    }
    out = []
    for match in matches:
        home, away = names.get(match.home_team_id, ""), names.get(match.away_team_id, "")
        meta = meta_for(match.competition)
        out.append(
            {
                "match_id": match.id,
                "slug": match_slug(home, away, match.id),
                "match_date": match.match_date.isoformat(),
                "competition": match.competition,
                "short_name": meta.short_name if meta else match.competition,
                "home_team": home,
                "away_team": away,
                "is_home": match.home_team_id == team.id,
            }
        )
    return out


def build_team_page(session: Session, team: Team) -> dict:
    detail = get_team_detail(session, team)
    recent = []
    for match in detail["recent_matches"]:
        home, away = match["home_team"], match["away_team"]
        recent.append(
            {
                "match_id": match["match_id"],
                "slug": match_slug(home, away, match["match_id"]),
                "match_date": match["match_date"].isoformat(),
                "competition": match["competition"],
                "home_team": home,
                "away_team": away,
                "home_score": match["home_score"],
                "away_score": match["away_score"],
                "is_home": home == team.name,
                "result": _letter(match, team.name),
            }
        )

    # Most recent first, which is how a reader reads form: the newest result
    # sits at the left of the strip.
    form = [m["result"] for m in recent if m["result"] is not None][:FORM_LETTERS]
    meta = meta_for(recent[0]["competition"]) if recent else None
    # Days since the newest result, so the page can say how current "recent
    # form" is instead of implying it is live.
    age_days = (
        (
            datetime.now(UTC).replace(tzinfo=None) - datetime.fromisoformat(recent[0]["match_date"])
        ).days
        if recent
        else None
    )
    return {
        "team": {
            "id": team.id,
            "name": team.name,
            "slug": team_slug(team.name),
            "elo_rating": round(team.elo_rating, 0),
            "badge": badge_dict(team.name),
            "country": meta.country if meta else None,
            # True when its latest matches are national-team fixtures, where the
            # catalogue's "country" is only the competition's ("World").
            "is_national": bool(recent) and is_international(recent[0]["competition"]),
        },
        "last_match_age_days": age_days,
        "form_letters": form,
        "form_last5": detail["form_last5"],
        "form_last10": detail["form_last10"],
        "season_stats": detail["season_stats"],
        "recent_matches": recent,
        "upcoming": _upcoming(session, team),
        "standing": _standing(session, team),
    }
