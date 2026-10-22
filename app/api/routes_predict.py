"""GET /predict/{match_id} — full ensemble prediction for one fixture."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.api.deps_auth import get_viewer
from app.api.routes_board import agreement_for
from app.database.session import get_db
from app.models.match import Match
from app.models.match_event import MatchEvent
from app.models.team import Team
from app.schemas.prediction import (
    BasketballPredictionOut,
    PredictionOut,
    TennisPredictionOut,
)
from app.services import access
from app.services.base_rates import competition_base_rates
from app.services.live_scores import live_payload
from app.services.pick_service import best_pick
from app.services.prediction_service import MatchNotFoundError, predict_for_match
from ml.markets import best_per_market, candidate_calls, headline_call, rank_calls
from ml.team_badges import badge_dict

router = APIRouter(tags=["predictions"])


def _match_state(match: Match) -> dict:
    """Status, score and 1X2 price, read straight off the row — the same
    "what's actually true right now" a board row shows, added here because
    the fixture page never carried it at all before."""
    return {
        "match_status": match.status,
        "live": live_payload(match),
        "match_score": (
            {"home": match.home_score, "away": match.away_score}
            if match.home_score is not None and match.away_score is not None
            else None
        ),
        "odds_1x2": (
            {"home": match.odds_home_win, "draw": match.odds_draw, "away": match.odds_away_win}
            if match.odds_home_win is not None
            or match.odds_draw is not None
            or match.odds_away_win is not None
            else None
        ),
    }


def _withdraw_unrecorded_markets(payload: dict, rates: dict[str, float]) -> None:
    """Blank the corner, card and half-time lines for a competition that records none of them.

    A dedicated model will still return a number for a league whose history has no corners
    or cards at all (it is reading features that are all zero), and the page would then show
    "Over 8.5 corners 48.7%" as though the engine had something to go on. The rate table leaves
    these markets out for such a competition (`competition_base_rates`), so a line with no rate
    is shown as unavailable, exactly as for a competition the models were never fitted on.
    """
    if not rates:
        return
    for field, prefix in (
        ("corners_markets", "corners"),
        ("cards_markets", "cards"),
        ("ht_goals_markets", "ht_goals"),
    ):
        for entry in payload.get(field) or []:
            if f"{prefix}:over_{entry.get('line')}" not in rates:
                entry["prob_over"] = None
                entry["prob_under"] = None
                entry["model_used"] = False


def _actual_stats(match: Match) -> dict | None:
    """What actually happened, once `fetch_match_stats.py` has tried this
    fixture — None beforehand, not zero-filled. A field the source didn't
    report stays None even once the fixture itself has an answer."""
    if match.stats_fetched_at is None:
        return None

    def pair(home_attr: str, away_attr: str) -> dict:
        return {"home": getattr(match, home_attr), "away": getattr(match, away_attr)}

    return {
        "shots": pair("home_shots", "away_shots"),
        "shots_on_target": pair("home_shots_on_target", "away_shots_on_target"),
        "corners": pair("home_corners", "away_corners"),
        "yellow_cards": pair("home_yellow_cards", "away_yellow_cards"),
        "red_cards": pair("home_red_cards", "away_red_cards"),
        "possession": pair("home_possession", "away_possession"),
        "offsides": pair("home_offsides", "away_offsides"),
        "fouls": pair("home_fouls", "away_fouls"),
    }


def _events(db: Session, match_id: int) -> list[dict]:
    rows = (
        db.query(MatchEvent)
        .filter(MatchEvent.match_id == match_id)
        .order_by(MatchEvent.minute.asc(), MatchEvent.id.asc())
        .all()
    )
    return [
        {
            "minute": r.minute,
            "added_time": r.added_time,
            "side": r.side,
            "player": r.player,
            "assist": r.assist,
            "detail": r.detail,
            "home_score_after": r.home_score_after,
            "away_score_after": r.away_score_after,
        }
        for r in rows
    ]


def _completed_matches(db: Session, team_id: int | None) -> int | None:
    """How much history a competitor has, for the thin-evidence guard.

    A rating built from ten matches sits near the 1500 default, so an "edge"
    measured against it is model error rather than value.
    """
    if team_id is None:
        return None
    return (
        db.query(func.count(Match.id))
        .filter(
            Match.status == "completed",
            or_(Match.home_team_id == team_id, Match.away_team_id == team_id),
        )
        .scalar()
    )


@router.get(
    "/predict/{match_id}",
    response_model=PredictionOut | BasketballPredictionOut | TennisPredictionOut,
)
def predict(
    match_id: int,
    db: Session = Depends(get_db),
    viewer: access.Viewer = Depends(get_viewer),
) -> PredictionOut | BasketballPredictionOut | TennisPredictionOut:
    """The prediction for one match, in that sport's own shape.

    The response model is a union rather than one schema with optional
    fields: a basketball game has no draw probability and no goal markets,
    and modelling that as `draw: float | None` would make a real football
    value and a not-applicable-in-this-sport value indistinguishable to any
    client. `sport` discriminates the two.
    """
    # A match still to be played, for a viewer who may not see its prediction: say who is playing
    # and when, and stop. Checked before the prediction is computed, so none is worked out.
    gate = db.get(Match, match_id)
    if gate is not None and access.match_is_locked(db, gate, viewer):
        home, away = db.get(Team, gate.home_team_id), db.get(Team, gate.away_team_id)
        home_name, away_name = (home.name if home else ""), (away.name if away else "")
        return JSONResponse(
            access.locked_match_payload(
                gate,
                home_name,
                away_name,
                {
                    "home_badge": badge_dict(home_name, getattr(home, "api_football_id", None)),
                    "away_badge": badge_dict(away_name, getattr(away, "api_football_id", None)),
                },
            )
        )

    try:
        payload = predict_for_match(db, match_id)
    except MatchNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    match = db.get(Match, match_id)
    if match is not None:
        payload.update(_match_state(match))

    sport = payload.get("sport")
    if sport == "basketball":
        return BasketballPredictionOut(**payload)
    if sport == "tennis":
        return TennisPredictionOut(**payload)

    # A flag for a national side, initials for a club — same rule the board
    # uses, so a fixture's crest never differs between the row that links to
    # this page and the page itself.
    home_id = getattr(getattr(match, "home_team", None), "api_football_id", None)
    away_id = getattr(getattr(match, "away_team", None), "api_football_id", None)
    payload["home_badge"] = badge_dict(payload.get("home_team"), home_id)
    payload["away_badge"] = badge_dict(payload.get("away_team"), away_id)

    # Football is the fall-through, and the football payload does not carry a
    # `sport` key at all — `PredictionOut.sport` defaults it. So this must be
    # keyed off "not one of the others" exactly as the branches above are,
    # never off `sport == "football"`, which is never true here.
    #
    # Every market this fixture supports, not just the match result. Computed
    # in the route rather than the service because it needs the base-rate
    # table, which is a property of the whole database rather than of one
    # prediction.
    rates = competition_base_rates(db, payload.get("competition"))
    _withdraw_unrecorded_markets(payload, rates)
    ranked = rank_calls(candidate_calls(payload), rates)
    best = headline_call(ranked)
    payload["calls"] = {
        "headline": best.as_dict() if best else None,
        "by_market": [entry.as_dict() for entry in best_per_market(ranked)],
    }

    # The market comparison. It used to live only on the board row, where it
    # competed with the prediction for attention; a page someone has opened to
    # read the analysis is where it belongs.
    if match is not None:
        payload["value"] = best_pick(
            payload,
            match.odds_markets,
            agreement_for(payload),
            home_matches=_completed_matches(db, match.home_team_id),
            away_matches=_completed_matches(db, match.away_team_id),
        )
        payload["ht_score"] = (
            {"home": match.home_ht_goals, "away": match.away_ht_goals}
            if match.home_ht_goals is not None and match.away_ht_goals is not None
            else None
        )
        payload["actual_stats"] = _actual_stats(match)
        payload["events"] = _events(db, match_id)
    return PredictionOut(**payload)
