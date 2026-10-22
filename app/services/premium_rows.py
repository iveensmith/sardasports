"""Full board rows for chosen matches, for a premium member's browser.

The public pages are built from hidden rows (see `app.services.access`) and are the same for
everyone, so they can be cached. A premium member's browser then asks for the rows it is missing,
by match id, through a route that checks the member first, and fills them in. One function serves
every page that shows a board: the day board, the league pages, the bankers.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.match import Match
from app.models.team import Team
from app.services.base_rates import competition_base_rates
from app.services.board_service import build_row
from app.services.stored_predictions import predict_with_stored_fallback

# A day's card is a few hundred fixtures at most; a request for more than this is not a page.
MAX_IDS = 400


def parse_ids(raw: str | None) -> list[int]:
    """Match ids from "1,2,3". Anything that is not a whole number is skipped; at most MAX_IDS."""
    ids: list[int] = []
    for part in (raw or "").split(","):
        part = part.strip()
        if part.isdigit():
            ids.append(int(part))
    return list(dict.fromkeys(ids))[:MAX_IDS]


def rows_for_matches(db: Session, ids: list[int]) -> list[dict]:
    """Full (unhidden) rows for the football matches among `ids`, in the order asked."""
    if not ids:
        return []
    matches = {
        m.id: m for m in db.query(Match).filter(Match.id.in_(ids), Match.sport == "football").all()
    }
    ordered = [matches[i] for i in ids if i in matches]
    if not ordered:
        return []
    team_ids = {m.home_team_id for m in ordered} | {m.away_team_id for m in ordered}
    names = {t.id: t.name for t in db.query(Team).filter(Team.id.in_(team_ids)).all()}
    predictions = predict_with_stored_fallback(db, ordered, allow_stored=True)
    return [
        {
            **build_row(
                match,
                prediction,
                competition_base_rates(db, match.competition),
                names.get(match.home_team_id, ""),
                names.get(match.away_team_id, ""),
            ),
            "locked": False,
        }
        for match, prediction in zip(ordered, predictions, strict=True)
    ]
