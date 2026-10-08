"""Browsing routes: leagues, bankers, and the slip builder.

Three ways into the same day's calls. `/leagues` is the catalogue, `/bankers`
is the engine's surest handful, and `/slip` assembles an accumulator from
them.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.match import Match
from app.models.team import Team
from app.services.base_rates import market_base_rates
from app.services.board_service import build_row
from app.services.league_service import build_league, competition_for_slug, slug_for
from app.services.settlement import Outcome, Record
from app.services.slip_service import (
    DEFAULT_MAX_ODD,
    DEFAULT_MIN_ODD,
    build_slip,
    candidate_legs,
)
from app.services.stored_predictions import predict_with_stored_fallback
from app.utils.coalesce import CoalescingCache
from ml.competition_catalogue import BY_COMPETITION, competitions_in, countries
from ml.markets import candidate_calls, rank_calls

router = APIRouter(tags=["discover"])

# What makes a pick a "banker": how likely the engine thinks it is.
#
# Not confidence, which is the obvious choice and does not work. That score
# is an estimator-agreement measure, and measured over 851 stored predictions
# it runs 78.5 to 99.4 with a median of 94.4 and a standard deviation of 3.6
# — it occupies the top fifth of its own nominal scale. Rendered out of ten,
# a threshold of 8.0 admitted 29 of 29 fixtures on a real card. A filter that
# selects everything is not a filter.
#
# Probability discriminates and also means what a reader means: a banker is a
# selection that is very likely to land. Confidence is still reported beside
# each row, it just does not choose them.
BANKER_PROBABILITY = 80.0

# `/bankers` and `/slip` both start from the same priced day, and the slip builder is
# hit repeatedly with different targets. The day is built once and shared; see
# `routes_board_table.BOARD_CACHE_SECONDS` for why the window is short.
DAY_CACHE_SECONDS = 30.0
_day_cache = CoalescingCache(DAY_CACHE_SECONDS)


@router.get("/leagues")
def leagues(db: Session = Depends(get_db)) -> dict:
    """Every competition we model, grouped by country, with how much we hold.

    The match counts are the honest part. A competition with four hundred
    completed matches behind it produces very different predictions from one
    with forty, and a catalogue that listed them identically would imply a
    uniformity that is not there.
    """
    counts = dict(
        db.query(Match.competition, func.count(Match.id))
        .filter(Match.sport == "football", Match.status == "completed")
        .group_by(Match.competition)
        .all()
    )
    upcoming = dict(
        db.query(Match.competition, func.count(Match.id))
        .filter(
            Match.sport == "football",
            Match.status == "scheduled",
            Match.match_date >= datetime.now(UTC).replace(tzinfo=None),
        )
        .group_by(Match.competition)
        .all()
    )

    grouped = []
    for country in countries():
        entries = []
        for meta in competitions_in(country):
            entries.append(
                {
                    "competition": meta.competition,
                    "slug": slug_for(meta.competition),
                    "short_name": meta.short_name,
                    "tier": meta.tier,
                    "completed": counts.get(meta.competition, 0),
                    "upcoming": upcoming.get(meta.competition, 0),
                }
            )
        if entries:
            grouped.append(
                {
                    "country": country,
                    "country_code": next(
                        (m.country_code for m in competitions_in(country) if m.country_code),
                        None,
                    ),
                    "competitions": entries,
                    "completed": sum(e["completed"] for e in entries),
                    "upcoming": sum(e["upcoming"] for e in entries),
                }
            )

    return {
        "countries": grouped,
        "competition_count": len(BY_COMPETITION),
        "country_count": len(grouped),
    }


@router.get("/leagues/{slug}")
def league(slug: str, db: Session = Depends(get_db)) -> dict:
    """One competition: its rates, table, record, fixtures and latest results."""
    meta = competition_for_slug(slug)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"No competition matches '{slug}'")
    return build_league(db, meta)


def _day_rows(db: Session, target: date):
    """Board rows for a day, plus the ranked calls behind each."""
    return _day_cache.get_or_compute(target, lambda: _build_day_rows(db, target))


def _build_day_rows(db: Session, target: date):
    start = datetime.combine(target, datetime.min.time())
    matches = (
        db.query(Match)
        .filter(
            Match.sport == "football",
            Match.match_date >= start,
            Match.match_date < start + timedelta(days=1),
        )
        .order_by(Match.match_date.asc())
        .all()
    )
    team_ids = {m.home_team_id for m in matches} | {m.away_team_id for m in matches}
    names = {t.id: t.name for t in db.query(Team).filter(Team.id.in_(team_ids)).all()}
    base_rates = market_base_rates(db, "football")
    # Only markets and confidence are read here, so a current stored prediction will do.
    predictions = predict_with_stored_fallback(db, matches, allow_stored=True)

    rows, ranked_by_match, odds_by_match = [], {}, {}
    for match, prediction in zip(matches, predictions, strict=True):
        row = build_row(
            match,
            prediction,
            base_rates,
            names.get(match.home_team_id, ""),
            names.get(match.away_team_id, ""),
        )
        rows.append(row)
        ranked_by_match[match.id] = (
            rank_calls(candidate_calls(prediction), base_rates) if prediction else []
        )
        odds_by_match[match.id] = match.odds_markets
    return rows, ranked_by_match, odds_by_match


@router.get("/bankers")
def bankers(
    on_date: date | None = Query(None),
    min_probability: float = Query(BANKER_PROBABILITY, ge=50.0, le=99.0),
    db: Session = Depends(get_db),
) -> dict:
    """The day's likeliest picks, and how the settled ones went.

    Selected on the best tip's probability rather than the confidence score,
    which does not discriminate — see `BANKER_PROBABILITY`.

    The record travels with the list. A page that shows a handful of
    near-certainties and never mentions how the last batch went is asking to
    be believed on the strength of its own adjectives.
    """
    target = on_date or datetime.now(UTC).date()
    rows, _, _ = _day_rows(db, target)

    selected = [
        row
        for row in rows
        if row["best_tip"] is not None and row["best_tip"]["probability"] >= min_probability
    ]
    selected.sort(key=lambda r: (-r["best_tip"]["probability"], r["match_date"]))

    record = Record()
    for row in selected:
        outcome = row["best_tip"]["outcome"]
        if outcome is not None:
            record = record.plus(Outcome(outcome))

    return {
        "date": target.isoformat(),
        "min_probability": min_probability,
        "count": len(selected),
        "considered": len(rows),
        # Fixtures on the card still to be played, so a page can tell a card
        # worth building a slip from a day that is already over.
        "upcoming": sum(1 for row in rows if row["score"] is None),
        "record": record.as_dict(),
        "rows": selected,
    }


@router.get("/slip")
def slip(
    on_date: date | None = Query(None),
    target_odds: float = Query(5.0, ge=1.1, le=1000.0),
    min_legs: int = Query(3, ge=2, le=12),
    max_legs: int = Query(6, ge=2, le=12),
    min_odd: float = Query(DEFAULT_MIN_ODD, ge=1.01, le=10.0),
    max_odd: float = Query(DEFAULT_MAX_ODD, ge=1.01, le=100.0),
    markets: str | None = Query(
        None, description="Comma-separated markets to draw from. All if omitted."
    ),
    db: Session = Depends(get_db),
) -> dict:
    """Assemble an accumulator from the day's picks.

    The combined probability is returned alongside the combined price and is
    not optional. Six legs at 80% is a 26% chance of a return, and showing
    the price without it would be advertising the upside of a bet whose
    downside we had calculated and withheld.
    """
    target = on_date or datetime.now(UTC).date()
    rows, ranked_by_match, odds_by_match = _day_rows(db, target)

    wanted = {m.strip() for m in markets.split(",") if m.strip()} if markets else None
    legs = candidate_legs(
        rows,
        ranked_by_match,
        odds_by_match,
        markets=wanted,
        min_odd=min_odd,
        max_odd=max_odd,
    )
    result = build_slip(legs, target_odds=target_odds, min_legs=min_legs, max_legs=max_legs)
    result["date"] = target.isoformat()
    return result
