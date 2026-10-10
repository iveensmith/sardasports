"""Bring one sport's Elo history up to date after new results arrive.

`scripts.load_to_db.rebuild_elo_history` replays every match from the start, which is
the right tool after a bulk load but far too heavy for a job that has added a day's
results. This adds only the matches that have no rating row yet, continuing each
competitor from their last rating.

That is exact provided each new match is newer than the last one already rated for
**both of its teams** (ratings are per team, so two teams' histories do not interact). If one
turns up older than a rating already written (a backfilled season, a corrected date),
continuing from the last rating would be wrong, so the sport is replayed in full instead.
Correct and slower beats fast and quietly off.

The check is per team, not "newer than anything rated". Football results arrive a day or
so late and in any order across leagues; a global check sent nearly every result to a full
replay, which deletes and re-inserts about 236,000 rows in one transaction and locks the
database for minutes. Football also needs the per-competition K the full replay uses, or the
two would disagree.
"""

from __future__ import annotations

import logging

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import EloHistory, Match, Team
from app.utils.config import get_settings
from ml.elo.engine import EloEngine, MatchResult
from ml.elo.football import FOOTBALL_COMPETITION_K

logger = logging.getLogger(__name__)


def sync_elo(session: Session, sport: str) -> dict:
    settings = get_settings()
    rated = session.query(EloHistory.match_id).filter(EloHistory.match_id.is_not(None))
    new = (
        session.query(Match)
        .filter(
            Match.sport == sport,
            Match.status == "completed",
            Match.home_score.is_not(None),
            Match.id.not_in(rated),
        )
        .order_by(Match.match_date.asc(), Match.id.asc())
        .all()
    )
    if not new:
        return {"added": 0, "rebuilt": False}

    involved = {m.home_team_id for m in new} | {m.away_team_id for m in new}
    last_rated = dict(
        session.query(EloHistory.team_id, func.max(EloHistory.match_date))
        .filter(EloHistory.team_id.in_(involved))
        .group_by(EloHistory.team_id)
        .all()
    )
    out_of_order = False
    for match in new:  # ascending, so a team's own new matches are checked in order
        for team_id in (match.home_team_id, match.away_team_id):
            last = last_rated.get(team_id)
            if last is not None and match.match_date <= last:
                out_of_order = True
            last_rated[team_id] = match.match_date
    if out_of_order:
        from scripts.load_to_db import rebuild_elo_history

        logger.info("elo sync: %s has results older than its ratings; replaying in full", sport)
        rebuild_elo_history(session, settings, {sport})
        session.commit()
        return {"added": len(new), "rebuilt": True}

    names = {t.id: t for t in session.query(Team).filter(Team.sport == sport).all()}
    engine = EloEngine(
        k_factor=settings.elo_k_factor,
        home_advantage=settings.elo_home_advantage,
        initial_rating=settings.elo_initial_rating,
        # Must match `rebuild_elo_history`; the other sports see no listed competition.
        competition_k=FOOTBALL_COMPETITION_K if sport == "football" else None,
    )
    for team_id in involved:
        last = (
            session.query(EloHistory.rating_after)
            .filter(EloHistory.team_id == team_id)
            .order_by(EloHistory.match_date.desc(), EloHistory.id.desc())
            .first()
        )
        if last is not None:
            engine.set_rating(names[team_id].name, last[0])

    for match in new:
        home, away = names[match.home_team_id], names[match.away_team_id]
        update = engine.apply_result(
            MatchResult(
                home_team=home.name,
                away_team=away.name,
                home_score=match.home_score,
                away_score=match.away_score,
                match_date=match.match_date,
                neutral_venue=match.neutral_venue,
                competition=match.competition,
            )
        )
        session.add(
            EloHistory(
                team_id=home.id,
                match_id=match.id,
                match_date=match.match_date,
                rating_before=update.home_rating_before,
                rating_after=update.home_rating_after,
                opponent_team_id=away.id,
                was_home=True,
            )
        )
        session.add(
            EloHistory(
                team_id=away.id,
                match_id=match.id,
                match_date=match.match_date,
                rating_before=update.away_rating_before,
                rating_after=update.away_rating_after,
                opponent_team_id=home.id,
                was_home=False,
            )
        )
    for team_id in involved:
        names[team_id].elo_rating = engine.get_rating(names[team_id].name)
    session.commit()
    return {"added": len(new), "rebuilt": False}
