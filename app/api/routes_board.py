"""GET /predictions/today — the prediction board.

An additive endpoint composing `/fixtures/today` and `/predict/{id}`,
changing neither. It exists for two reasons.

**Speed.** Calling them separately is quadratic in practice: `/predict/{id}`
loads the sport's entire completed history to fit its baselines, so a
40-fixture board re-read ~64,000 rows forty times.
`predict_for_matches` loads that history once per (sport, date).

**Agreement.** The engine runs three genuinely independent result estimators
— Elo, Poisson and a trained model — and then blends them. The blend is the
answer, but it averages away the most interesting thing on the board: where
the three *disagree*. A 2-vs-1 split can blend into a tidy-looking
near-even prediction that conceals a real argument. This endpoint reports
the split alongside the blend so a caller can sort by it.

Note that agreement here is about the *picked outcome*, which is not what
`confidence` measures — that is a distributional score (how close the three
probability vectors are), so two estimators can sit close together overall
while still picking different winners. Both are reported; neither is
derived from the other.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps_auth import get_viewer
from app.database.session import get_db
from app.models import Match, Team
from app.services import access
from app.services.base_rates import competition_base_rates
from app.services.pick_service import best_pick, most_likely_outcome
from app.services.stored_predictions import predict_with_stored_fallback
from ml.markets import best_per_market, candidate_calls, headline_call, rank_calls

router = APIRouter(tags=["predictions"])

OUTCOMES = ("home", "draw", "away")


def _pick_from(probs: list[float] | None) -> str | None:
    """The outcome an estimator favours, or None if it has no opinion."""
    if not probs:
        return None
    return OUTCOMES[max(range(len(probs)), key=lambda i: probs[i])]


def agreement_for(prediction: dict) -> dict | None:
    """How many independent estimators back the blended pick.

    Returns None for sports with no multi-estimator ensemble — basketball
    and tennis blend a single trained model with an Elo baseline, so
    "2 of 3 agree" would be a category error rather than a weaker signal.
    """
    estimators = prediction.get("estimator_probs") or {}
    if len(estimators) < 2:
        return None

    blended = [
        prediction.get("home_win", 0.0),
        prediction.get("draw", 0.0),
        prediction.get("away_win", 0.0),
    ]
    consensus_pick = _pick_from(blended)
    picks = {name: _pick_from(probs) for name, probs in estimators.items()}
    agreeing = sum(1 for pick in picks.values() if pick == consensus_pick)

    return {
        "pick": consensus_pick,
        "agreeing": agreeing,
        "total": len(picks),
        "unanimous": agreeing == len(picks),
        "by_estimator": picks,
    }


def _passed(prediction: dict | None, agreement: dict | None) -> bool:
    """Whether the engine has no coherent view of this fixture.

    Two ways that happens, and the second is not redundant:

    * Its own confidence label is "Low" — the scale's own way of saying so.
    * A minority of estimators back the blended pick. When only one of three
      favours the outcome, the "consensus" is an artifact of how the three
      were weighted rather than anything they agree on.

    The second case is needed because `confidence` does not measure outcome
    agreement at all — it scores how close the three probability *vectors*
    are, so a fixture where one estimator backs the pick and two dissent can
    still be labelled "High". One such fixture is on the current card. Both
    numbers are reported; neither is derived from the other.
    """
    if prediction is None:
        return True
    if prediction.get("confidence_label") == "Low":
        return True
    if agreement and agreement["total"] >= 3:
        return agreement["agreeing"] * 2 < agreement["total"]
    return False


@router.get("/predictions/today")
def predictions_today(
    on_date: date | None = Query(default=None, description="Defaults to today (UTC)"),
    sport: str | None = Query(default=None),
    competition: str | None = Query(default=None),
    view: str = Query(
        default="all",
        pattern="^(all|consensus|disagreement|passed)$",
        description=(
            "all · consensus (every estimator backs the pick) · "
            "disagreement (they split) · passed (engine is not confident)"
        ),
    ),
    min_confidence: float | None = Query(default=None, ge=0, le=100),
    limit: int = Query(default=60, ge=1, le=200),
    db: Session = Depends(get_db),
    viewer: access.Viewer = Depends(get_viewer),
) -> dict:
    """Fixtures for a date, each with its prediction and estimator split.

    `prediction` is null for a fixture the engine could not price. That is
    reported per fixture rather than dropped, so the board can say what it
    could not do instead of quietly showing a shorter list.
    """
    target = on_date or datetime.now(UTC).date()
    start = datetime.combine(target, datetime.min.time())
    end = start + timedelta(days=1)

    query = db.query(Match).filter(Match.match_date >= start, Match.match_date < end)
    if sport:
        query = query.filter(Match.sport == sport)
    if competition:
        query = query.filter(Match.competition == competition)
    matches = query.order_by(Match.match_date.asc()).limit(limit).all()

    predictions = predict_with_stored_fallback(db, matches)

    team_ids = {m.home_team_id for m in matches} | {m.away_team_id for m in matches}
    names = {t.id: t.name for t in db.query(Team).filter(Team.id.in_(team_ids)).all()}

    # How much history each competitor actually has. A rating built from ten
    # matches sits near the 1500 default, and an "edge" measured against it
    # is model error — see pick_service.THIN_EVIDENCE_MATCHES. Counted in
    # one grouped pass rather than per fixture.
    played: dict[int, int] = dict.fromkeys(team_ids, 0)
    if team_ids:
        for column in (Match.home_team_id, Match.away_team_id):
            rows = (
                db.query(column, func.count(Match.id))
                .filter(Match.status == "completed", column.in_(team_ids))
                .group_by(column)
                .all()
            )
            for team_id, total in rows:
                played[team_id] = played.get(team_id, 0) + total

    entries = []
    for match, prediction in zip(matches, predictions, strict=True):
        agreement = agreement_for(prediction) if prediction else None
        home_name = names.get(match.home_team_id, "")
        away_name = names.get(match.away_team_id, "")

        # Every market the engine can call for this fixture, ranked by how
        # far each sits above its own base rate. Ranking by raw probability
        # instead puts a double chance on top of almost every row — see
        # ml.markets for the measurements.
        calls = None
        if prediction and match.sport == "football":
            ranked = rank_calls(
                candidate_calls(prediction),
                competition_base_rates(db, match.competition),
            )
            best = headline_call(ranked)
            calls = {
                "headline": best.as_dict() if best else None,
                "by_market": [entry.as_dict() for entry in best_per_market(ranked)],
            }
        entries.append(
            {
                "match_id": match.id,
                "match_date": match.match_date.isoformat(),
                "sport": match.sport,
                "competition": match.competition,
                "home_team": home_name,
                "away_team": away_name,
                "status": match.status,
                "prediction": prediction,
                "agreement": agreement,
                # What the engine actually expects to happen. This is what
                # the row leads with, and it is read off the same blended
                # probabilities the detail page renders — the row and the
                # detail page previously disagreed, because the row led with
                # `pick` below, which answers a different question.
                "forecast": most_likely_outcome(prediction, home_name, away_name),
                # Calls across every market, headline first. The forecast
                # above stays the match-result answer specifically, because
                # "who wins?" is the question a reader always has.
                "calls": calls,
                # Where the *price* looks wrong, by expected value against
                # the best available price. Frequently not the likely
                # outcome, so it is shown as value and never as the
                # forecast. None when the fixture has no odds.
                "pick": best_pick(
                    prediction,
                    match.odds_markets,
                    agreement,
                    home_matches=played.get(match.home_team_id),
                    away_matches=played.get(match.away_team_id),
                ),
                "odds_updated_at": (
                    match.odds_updated_at.isoformat() if match.odds_updated_at else None
                ),
                "passed": _passed(prediction, agreement),
            }
        )

    # Counts are computed over the whole card before filtering, so the tabs
    # can show how many fixtures each view holds without three round trips.
    counts = {
        "all": len(entries),
        "consensus": sum(1 for e in entries if e["agreement"] and e["agreement"]["unanimous"]),
        # Split, but the engine still has a majority view. A fixture where
        # most estimators dissent belongs under "not called" instead, and is
        # excluded here so the tabs do not double-count it.
        "disagreement": sum(
            1
            for e in entries
            if e["agreement"] and not e["agreement"]["unanimous"] and not e["passed"]
        ),
        "passed": sum(1 for e in entries if e["passed"]),
    }

    visible = entries
    if view == "consensus":
        visible = [e for e in entries if e["agreement"] and e["agreement"]["unanimous"]]
        # Strongest agreement first means most confident among the unanimous.
        visible.sort(key=lambda e: -(e["prediction"] or {}).get("confidence", 0))
    elif view == "disagreement":
        visible = [
            e
            for e in entries
            if e["agreement"] and not e["agreement"]["unanimous"] and not e["passed"]
        ]
        # Most split first: fewest estimators backing the blended pick.
        visible.sort(key=lambda e: (e["agreement"]["agreeing"], e["match_date"]))
    elif view == "passed":
        visible = [e for e in entries if e["passed"]]

    if min_confidence is not None:
        visible = [
            e
            for e in visible
            if e["prediction"] and e["prediction"].get("confidence", 0) >= min_confidence
        ]

    return {
        "date": target.isoformat(),
        "view": view,
        "counts": counts,
        "count": len(visible),
        "predicted": sum(1 for e in visible if e["prediction"] is not None),
        "fixtures": access.hide_entries(db, visible, viewer),
    }
