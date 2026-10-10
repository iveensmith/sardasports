"""The public track record: what the engine called, and how it went.

Every claim on this page is a count, not an assertion. The engine's calls are
regenerated from the stored probabilities and graded against the final score
by `app.services.settlement`, so a number here can always be traced to
specific fixtures.

The distinction this module exists to preserve
----------------------------------------------
There are two very different things a prediction record can be, and running
them together is the single most common dishonesty in this industry:

    live       the prediction was stored *before* kick-off. Nobody could
               have known the result. This is a forecast that was published
               and then judged.
    backtest   the prediction was generated *after* the match, from history
               truncated at kick-off. The model saw nothing it should not
               have — the feature pipeline is leakage-safe — but it is still
               a reconstruction, and it was never exposed to the risk of
               being wrong in public.

A backtest is evidence. It is weaker evidence than a live record, and a page
that blurs the two is claiming credit it has not earned. They are counted
separately here and the API returns both, so the interface cannot
accidentally present one as the other.

At the time of writing every stored prediction is a backtest, because the
board only began running forward recently. The live record will fill in on
its own as fixtures are predicted and then played; nothing needs to be
backfilled for that to start counting.
"""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session, joinedload

from app.models.match import Match
from app.models.prediction import Prediction
from app.services.base_rates import competition_base_rates
from app.services.settlement import Outcome, Record, result_from_match, settle_key
from app.services.stored_predictions import payload_from_stored
from app.utils.coalesce import CoalescingCache
from ml.markets import (
    STRONG_TIP_MIN_PROBABILITY,
    best_per_market,
    candidate_calls,
    headline_call,
    is_strong_tip,
    rank_calls,
)

# How many days of daily results the "recent form" chart covers.
RECENT_DAYS = 30


@dataclass
class _Graded:
    """One settled prediction, reduced to what every breakdown needs."""

    match_date: datetime
    competition: str
    home_team: str
    away_team: str
    # The headline call as a reader saw it, e.g. "Over 2.5 goals".
    call_label: str
    confidence: float | None
    headline: Outcome
    per_market: dict[str, Outcome]
    # True when the prediction was stored before kick-off.
    live: bool
    # The headline call's stated probability, in percent.
    probability: float = 0.0


# Grading every stored prediction takes about four seconds, and the track record, every league
# page and every market page each used to do it afresh. A crawler visiting forty league pages
# therefore spent three minutes grading the same rows forty times. The graded list is read-only
# and changes only when a match finishes or a prediction is stored, so it is kept for two
# minutes and shared (simultaneous callers wait for one grading rather than each doing it).
_GRADED = CoalescingCache(300, max_entries=1, max_concurrent=1, copy_results=False)


def _grade_all(session: Session) -> list[_Graded]:
    return _GRADED.get_or_compute("all", lambda: _grade_all_uncached(session))


def _grade_all_uncached(session: Session) -> list[_Graded]:
    """Regenerate and settle every stored prediction on a played fixture."""
    rows = (
        session.query(Prediction, Match)
        .join(Match, Match.id == Prediction.match_id)
        .options(joinedload(Match.home_team), joinedload(Match.away_team))
        .filter(Match.status == "completed", Match.home_score.is_not(None))
        .all()
    )

    graded: list[_Graded] = []
    for prediction, match in rows:
        result = result_from_match(match)
        if result is None:
            continue
        ranked = rank_calls(
            candidate_calls(payload_from_stored(prediction)),
            competition_base_rates(session, match.competition),
        )
        best = headline_call(ranked)
        if best is None:
            continue
        graded.append(
            _Graded(
                match_date=match.match_date,
                competition=match.competition,
                home_team=match.home_team.name,
                away_team=match.away_team.name,
                call_label=best.call.label,
                confidence=prediction.confidence,
                headline=settle_key(best.call.key, result),
                # The *best call in each market*, not every candidate. Grading
                # all of them would settle both sides of every line and report
                # a mechanical 50% that means nothing.
                per_market={
                    entry.call.market: settle_key(entry.call.key, result)
                    for entry in best_per_market(ranked)
                },
                live=prediction.created_at is not None and prediction.created_at < match.match_date,
                probability=best.call.probability,
            )
        )
    return graded


def _record(outcomes) -> dict:
    record = Record()
    for outcome in outcomes:
        record = record.plus(outcome)
    return record.as_dict()


def _span(entries: list[_Graded]) -> dict | None:
    if not entries:
        return None
    dates = [entry.match_date for entry in entries]
    return {"first": min(dates).date().isoformat(), "last": max(dates).date().isoformat()}


def build_progress(session: Session) -> dict:
    """Everything the track-record page shows, all of it counted."""
    graded = _grade_all(session)

    live = [entry for entry in graded if entry.live]
    backtest = [entry for entry in graded if not entry.live]

    by_month: dict[str, list[Outcome]] = defaultdict(list)
    # How many of each month's calls were stored before kick-off, so a month
    # table can show how much of any rate is a published record at all.
    live_by_month: dict[str, list[Outcome]] = defaultdict(list)
    by_market: dict[str, list[Outcome]] = defaultdict(list)
    by_competition: dict[str, list[Outcome]] = defaultdict(list)
    by_confidence: dict[int, list[Outcome]] = defaultdict(list)
    for entry in graded:
        by_month[entry.match_date.strftime("%Y-%m")].append(entry.headline)
        if entry.live:
            live_by_month[entry.match_date.strftime("%Y-%m")].append(entry.headline)
        by_competition[entry.competition].append(entry.headline)
        for market, outcome in entry.per_market.items():
            by_market[market].append(outcome)
        if entry.confidence is not None:
            by_confidence[int(entry.confidence // 10)].append(entry.headline)

    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=RECENT_DAYS)
    recent: dict[str, list[Outcome]] = defaultdict(list)
    for entry in graded:
        if entry.match_date >= cutoff:
            recent[entry.match_date.date().isoformat()].append(entry.headline)

    strong = [entry for entry in graded if is_strong_tip(entry.probability)]
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        # The headline number, over everything settled.
        "overall": _record(entry.headline for entry in graded),
        "span": _span(graded),
        # The tips the engine rated at or above `min_probability` before kick-off, counted from
        # the same settled predictions as everything else: a subset, never a replacement.
        "strong": {
            "min_probability": STRONG_TIP_MIN_PROBABILITY,
            "record": _record(e.headline for e in strong),
            "live": _record(e.headline for e in strong if e.live),
            "backtest": _record(e.headline for e in strong if not e.live),
        },
        # Split so the interface cannot present a backtest as a live record.
        "live": {"record": _record(e.headline for e in live), "span": _span(live)},
        "backtest": {
            "record": _record(e.headline for e in backtest),
            "span": _span(backtest),
        },
        "by_month": [
            {
                "month": month,
                **_record(by_month[month]),
                "live_settled": _record(live_by_month[month])["settled"],
            }
            for month in sorted(by_month)
        ],
        "recent_days": [{"date": day, **_record(recent[day])} for day in sorted(recent)],
        "by_market": [
            {"market": market, **_record(by_market[market])}
            for market in sorted(by_market, key=lambda m: -len(by_market[m]))
        ],
        "by_competition": [
            {"competition": name, **_record(by_competition[name])}
            for name in sorted(by_competition, key=lambda n: -len(by_competition[n]))
        ],
        "by_confidence": [
            {
                "bucket": f"{bucket * 10}-{bucket * 10 + 10}",
                "from": bucket * 10,
                **_record(by_confidence[bucket]),
            }
            for bucket in sorted(by_confidence)
        ],
    }


def competition_record(session: Session, competition: str) -> dict:
    """One competition's settled record, live and backtested kept apart.

    The same grading as the track-record page, filtered. A league page that
    quoted a win rate without saying how much of it was backtested would be
    making the claim the track-record page is careful not to.
    """
    graded = [entry for entry in _grade_all(session) if entry.competition == competition]
    live = [entry for entry in graded if entry.live]
    backtest = [entry for entry in graded if not entry.live]
    return {
        "overall": _record(entry.headline for entry in graded),
        "live": _record(entry.headline for entry in live),
        "backtest": _record(entry.headline for entry in backtest),
    }


# --- Downloads -------------------------------------------------------------
#
# The same graded rows the page is built from, as plain CSV, so that every
# figure on the track-record page can be recounted by a reader. Both files are
# regraded from `_grade_all` rather than kept separately, which is what makes
# "the page, the daily file and the match file are three views of one set of
# rows" a fact about the code and not only a sentence.


def _csv(header: list[str], rows) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return buffer.getvalue()


def daily_record_csv(session: Session) -> str:
    """One row per day: how many calls settled, and how they went."""
    by_day: dict[str, list[_Graded]] = defaultdict(list)
    for entry in _grade_all(session):
        by_day[entry.match_date.date().isoformat()].append(entry)

    rows = []
    for day in sorted(by_day):
        record = _record(e.headline for e in by_day[day])
        live_settled = _record(e.headline for e in by_day[day] if e.live)["settled"]
        rows.append(
            [
                day,
                record["won"],
                record["lost"],
                record["void"],
                record["settled"],
                "" if record["win_rate"] is None else record["win_rate"],
                live_settled,
            ]
        )
    return _csv(["date", "won", "lost", "void", "settled", "win_rate", "live_settled"], rows)


def matches_csv(session: Session) -> str:
    """One row per graded prediction: the call made, and how the match ended."""
    entries = sorted(_grade_all(session), key=lambda e: e.match_date)
    rows = [
        [
            entry.match_date.date().isoformat(),
            entry.competition,
            entry.home_team,
            entry.away_team,
            entry.call_label,
            entry.headline.value,
            "live" if entry.live else "backtest",
        ]
        for entry in entries
    ]
    header = ["date", "competition", "home_team", "away_team", "call", "outcome", "record"]
    return _csv(header, rows)
