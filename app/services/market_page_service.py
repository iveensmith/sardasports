"""Single-market landing pages: "Over 2.5 goals today", "Correct score today".

The board answers "what does the engine say about every market on this match".
These pages answer the narrower question people actually search for — "which
matches today look like over 2.5?" — by ranking the day's fixtures on one
market only, and by putting that market's own track record beside the picks.

The record is the part that makes the page more than a sorted list. It is
counted from the engine's stored predictions on played fixtures, over a fixed
window, with live and backtested calls kept apart for the same reason the
track-record page keeps them apart (see `app.services.progress_service`): a
prediction generated after the match is evidence, but weaker evidence than
one published beforehand, and the page does not get to blur the two.

Correct score is reported at its true hit rate. Even the single likeliest
scoreline carries roughly one chance in seven, so a page that listed only the
hits would look far better than the market is. The record line below the picks
is therefore every settled call, not just the ones that landed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session, joinedload

from app.models.match import Match
from app.models.prediction import Prediction
from app.models.team import Team
from app.services.base_rates import market_base_rates
from app.services.board_service import build_row, effective_odds_markets, odds_for
from app.services.prediction_service import predict_for_matches
from app.services.settlement import MatchResult, result_from_match

# How far back the record looks, and how many hits are listed.
RECORD_WINDOW_DAYS = 30
RECENT_HITS = 8
# How many of the day's fixtures are listed as picks.
MAX_PICKS = 12

OVER_LINE = 2.5


@dataclass(frozen=True)
class MarketSpec:
    slug: str
    # What a "hit" is called on the page.
    hit_word: str


SPECS = {
    "over-2-5": MarketSpec(slug="over-2-5", hit_word="winner"),
    "correct-score": MarketSpec(slug="correct-score", hit_word="hit"),
}


def _over_probability(prediction: dict | None) -> float | None:
    """P(over 2.5), as a percentage, from either a live or a stored prediction."""
    for entry in (prediction or {}).get("goals_markets") or []:
        if abs(float(entry.get("line", -1)) - OVER_LINE) < 1e-9 and entry.get("prob_over"):
            return float(entry["prob_over"])
    return None


def _top_scoreline(prediction: dict | None) -> tuple[str, float] | None:
    """The likeliest exact score and its probability as a percentage."""
    scorelines = (prediction or {}).get("top_scorelines") or []
    if not scorelines:
        return None
    first = scorelines[0]
    if isinstance(first, dict):
        score, probability = first.get("score"), first.get("probability")
    else:  # the older stored shape was a bare "2-1" string
        score, probability = first, None
    if not score or probability is None:
        return None
    return str(score), round(float(probability) * 100.0, 1)


def _settle_over(result: MatchResult) -> str:
    return "won" if result.total_goals > OVER_LINE else "lost"


def _settle_score(score: str, result: MatchResult) -> str:
    return "won" if score == f"{result.home_score}-{result.away_score}" else "lost"


def _pick(kind: str, prediction: dict | None, odds_markets: dict | None) -> dict | None:
    """What this market says about one fixture, or None if it has no view."""
    if kind == "over-2-5":
        probability = _over_probability(prediction)
        if probability is None:
            return None
        price = odds_for("goals", f"over_{OVER_LINE}", odds_markets)
        label = "Over 2.5 goals"
    else:
        top = _top_scoreline(prediction)
        if top is None:
            return None
        label, probability = top
        # No bookmaker correct-score line is ingested, so this is always the
        # pick's own fair price, flagged as such.
        price = None
    estimated = price is None and probability > 0
    if estimated:
        price = round(100.0 / probability, 2)
    return {
        "label": label,
        "probability": round(probability, 1),
        "odds": price,
        "odds_is_estimated": estimated,
    }


def _settle(kind: str, pick: dict, result: MatchResult) -> str:
    return _settle_over(result) if kind == "over-2-5" else _settle_score(pick["label"], result)


def _stored_payload(prediction: Prediction) -> dict:
    return {
        "goals_markets": prediction.goals_markets or [],
        "top_scorelines": prediction.top_scorelines or [],
    }


def _record(session: Session, kind: str, today: datetime) -> dict:
    """The market's settled record over the window, plus its latest hits."""
    since = today - timedelta(days=RECORD_WINDOW_DAYS)
    rows = (
        session.query(Prediction, Match)
        .join(Match, Match.id == Prediction.match_id)
        .options(joinedload(Match.home_team), joinedload(Match.away_team))
        .filter(
            Match.status == "completed",
            Match.home_score.is_not(None),
            Match.match_date >= since,
            Match.match_date < today,
        )
        .order_by(Match.match_date.desc())
        .all()
    )

    live = {"settled": 0, "won": 0}
    backtest = {"settled": 0, "won": 0}
    hits: list[dict] = []
    for prediction, match in rows:
        result = result_from_match(match)
        pick = _pick(kind, _stored_payload(prediction), None)
        if result is None or pick is None:
            continue
        # Over 2.5 is only a *call* where the engine leans over; a fixture it
        # rates under is not a pick that failed to land.
        if kind == "over-2-5" and pick["probability"] < 50.0:
            continue
        outcome = _settle(kind, pick, result)
        is_live = prediction.created_at is not None and prediction.created_at < match.match_date
        bucket = live if is_live else backtest
        bucket["settled"] += 1
        if outcome == "won":
            bucket["won"] += 1
            if len(hits) < RECENT_HITS:
                hits.append(
                    {
                        "match_id": match.id,
                        "match_date": match.match_date.isoformat(),
                        "competition": match.competition,
                        "home_team": match.home_team.name,
                        "away_team": match.away_team.name,
                        "score": {"home": match.home_score, "away": match.away_score},
                        "pick": pick["label"],
                        "probability": pick["probability"],
                        "live": is_live,
                    }
                )

    def with_rate(bucket: dict) -> dict:
        settled = bucket["settled"]
        return {**bucket, "rate": round(100.0 * bucket["won"] / settled, 1) if settled else None}

    total = {
        "settled": live["settled"] + backtest["settled"],
        "won": live["won"] + backtest["won"],
    }
    return {
        "window_days": RECORD_WINDOW_DAYS,
        "overall": with_rate(total),
        "live": with_rate(live),
        "backtest": with_rate(backtest),
        "recent_hits": hits,
    }


def build_market_page(session: Session, kind: str, target_day: datetime) -> dict:
    """One market's picks for a day, ranked, with its record beside them."""
    start = datetime.combine(target_day.date(), datetime.min.time())
    matches = (
        session.query(Match)
        .filter(
            Match.sport == "football",
            Match.match_date >= start,
            Match.match_date < start + timedelta(days=1),
        )
        .order_by(Match.match_date.asc(), Match.id.asc())
        .all()
    )
    names = {
        t.id: t.name
        for t in session.query(Team)
        .filter(Team.id.in_({m.home_team_id for m in matches} | {m.away_team_id for m in matches}))
        .all()
    }
    base_rates = market_base_rates(session, "football")
    predictions = predict_for_matches(session, matches)

    picks: list[dict] = []
    considered = 0
    for match, prediction in zip(matches, predictions, strict=True):
        if prediction is None:
            continue
        markets = effective_odds_markets(match)
        pick = _pick(kind, prediction, markets)
        if pick is None:
            continue
        considered += 1
        # The same rule as the record: Over 2.5 is a call only where the
        # engine leans over, so a fixture it rates under is not listed as one.
        if kind == "over-2-5" and pick["probability"] < 50.0:
            continue
        row = build_row(
            match,
            prediction,
            base_rates,
            names.get(match.home_team_id, ""),
            names.get(match.away_team_id, ""),
        )
        result = result_from_match(match)
        picks.append(
            {
                "match_id": row["match_id"],
                "slug": row["slug"],
                "match_date": row["match_date"],
                "competition": row["competition"],
                "home_team": row["home_team"],
                "away_team": row["away_team"],
                "home_badge": row["home_badge"],
                "away_badge": row["away_badge"],
                "score": row["score"],
                "pick": {
                    **pick,
                    "outcome": _settle(kind, pick, result) if result is not None else None,
                },
            }
        )

    picks.sort(key=lambda p: (-p["pick"]["probability"], p["match_date"]))
    base_rate = base_rates.get(f"goals:over_{OVER_LINE}") if kind == "over-2-5" else None
    return {
        "kind": kind,
        "date": start.date().isoformat(),
        "fixtures": len(matches),
        "considered": considered,
        "picks": picks[:MAX_PICKS],
        # How often the market lands across every completed match on record —
        # the yardstick the day's numbers should be read against.
        "base_rate": None if base_rate is None else round(base_rate, 1),
        "record": _record(session, kind, start),
    }
