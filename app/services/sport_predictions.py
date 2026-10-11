"""Basketball and tennis predictions: stored in advance, served per day, graded.

Three jobs, one module, because they share the one fact that makes the record honest:
a prediction counts as a live pick only if it was stored before the match began.

* `store_upcoming` writes a prediction for every fixture in the next day and a half, and
  refreshes it while the match is still far enough away for new information to matter,
  then leaves it alone. After that it is what the engine said in advance.
* `build_board` serves one day's matches grouped by competition, from the stored
  prediction where there is one and from a fresh (unstored) calculation where not, so a
  day that was never stored still shows what the engine would say, labelled as such.
* `sport_record` grades the stored predictions that have finished: winner picks and
  total picks, counted separately for live and reconstructed rows, per sport.

A reconstructed row (stored after the match began) is shown and counted separately and is
never blended into the live figure, the same rule as the football record.
"""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime, timedelta
from time import monotonic

from sqlalchemy.orm import Session

from app.models import Match, SportPrediction, Team
from app.services.prediction_service import predict_for_matches
from app.services.sport_markets import attach_results, markets_record
from ml.basketball_catalogue import by_display_name

logger = logging.getLogger(__name__)

SPORTS = ("basketball", "tennis")
# How far ahead predictions are stored, and when they stop being refreshed.
STORE_AHEAD_HOURS = 36
REFRESH_UNTIL_HOURS = 3
REFRESH_AFTER_HOURS = 6
# A board is capped so one big tournament day cannot make a request that never returns.
BOARD_LIMIT = 160
# How long after the start a match can still be being played (tennis runs longest).
OVERDUE_AFTER = timedelta(hours=6)
BOARD_TTL_SECONDS = 300
_board_cache: dict[tuple, tuple[float, dict]] = {}
# Two scheduled jobs store predictions (basketball's and tennis's); one at a time keeps
# them from both inserting the same match, which the unique `match_id` would reject.
_STORE_LOCK = threading.Lock()


def clear_cache() -> None:
    _board_cache.clear()


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def main_total(payload: dict | None) -> dict | None:
    """The total offered at the line closest to a coin flip, or None if none was priced."""
    if not payload:
        return None
    markets = payload.get("total_points_markets") or payload.get("total_games_markets") or []
    priced = [m for m in markets if m.get("prob_over") is not None]
    if not priced:
        return None
    best = min(priced, key=lambda m: abs(m["prob_over"] - 50.0))
    return {
        "line": best["line"],
        "prob_over": best["prob_over"],
        "model_used": best.get("model_used"),
    }


def _expected_total(payload: dict) -> float | None:
    return payload.get("expected_total_points") or payload.get("expected_total_games")


def _apply(row: SportPrediction, payload: dict) -> None:
    total = main_total(payload)
    row.home_win_pct = float(payload["home_win"])
    row.away_win_pct = float(payload["away_win"])
    row.confidence = payload.get("confidence")
    row.total_line = None if total is None else float(total["line"])
    row.prob_over_pct = None if total is None else float(total["prob_over"])
    row.expected_total = _expected_total(payload)
    row.model_version = payload.get("model_version")
    row.payload = payload
    row.updated_at = _now()


def store_upcoming(
    session: Session, hours_ahead: int = STORE_AHEAD_HOURS, sports: tuple[str, ...] = SPORTS
) -> dict:
    """Store (or refresh, while the match is far off) predictions for the next day and a half."""
    with _STORE_LOCK:
        return _store_upcoming(session, hours_ahead, sports)


def _store_upcoming(session: Session, hours_ahead: int, sports: tuple[str, ...]) -> dict:
    now = _now()
    counts = {"stored": 0, "refreshed": 0, "frozen": 0, "unpriced": 0}
    for sport in sports:
        matches = (
            session.query(Match)
            .filter(
                Match.sport == sport,
                Match.status == "scheduled",
                Match.match_date > now,
                Match.match_date < now + timedelta(hours=hours_ahead),
            )
            .order_by(Match.match_date.asc())
            .limit(BOARD_LIMIT * 2)
            .all()
        )
        if not matches:
            continue
        existing = {
            p.match_id: p
            for p in session.query(SportPrediction)
            .filter(SportPrediction.match_id.in_([m.id for m in matches]))
            .all()
        }
        todo = []
        for match in matches:
            row = existing.get(match.id)
            if row is None:
                todo.append(match)
            elif match.match_date - now <= timedelta(hours=REFRESH_UNTIL_HOURS):
                counts["frozen"] += 1
            elif now - row.updated_at >= timedelta(hours=REFRESH_AFTER_HOURS):
                todo.append(match)
        if not todo:
            continue
        payloads = predict_for_matches(session, todo)
        for match, payload in zip(todo, payloads, strict=True):
            if not payload or payload.get("home_win") is None or payload.get("thin_history"):
                # A side with too little history has no basis for a pick; storing one
                # would put a made-up number on the record.
                counts["unpriced"] += 1
                continue
            row = existing.get(match.id)
            if row is None:
                row = SportPrediction(
                    match_id=match.id, sport=sport, created_at=now, updated_at=now
                )
                session.add(row)
                counts["stored"] += 1
            else:
                counts["refreshed"] += 1
            _apply(row, payload)
        session.commit()
    return counts


def _grade(match: Match, home_win: float, away_win: float, line: float | None, over: float | None):
    """(winner pick correct, total pick correct), each None if not gradable."""
    if match.status != "completed" or match.home_score is None or match.away_score is None:
        return None, None
    winner_correct = (home_win >= away_win) == (match.home_score > match.away_score)
    total_correct = None
    if line is not None and over is not None:
        if match.sport == "tennis":
            actual = (
                None
                if match.home_games is None or match.away_games is None
                else match.home_games + match.away_games
            )
        else:
            actual = match.home_score + match.away_score
        if actual is not None:
            total_correct = (actual > line) == (over >= 50.0)
    return winner_correct, total_correct


def _match_entry(match: Match, names: dict[int, str], row, fresh: dict | None) -> dict:
    if row is not None:
        home_win, away_win = row.home_win_pct, row.away_win_pct
        total = (
            None
            if row.total_line is None
            else {"line": row.total_line, "prob_over": row.prob_over_pct}
        )
        expected = row.expected_total
        confidence = row.confidence
        age = (
            (row.payload or {}).get("ratings_age_days")
            if (row.payload or {}).get("stale_ratings")
            else None
        )
        source = "stored" if row.created_at < match.match_date else "reconstructed"
        markets = (row.payload or {}).get("markets")
    elif fresh and fresh.get("home_win") is not None and not fresh.get("thin_history"):
        home_win, away_win = fresh["home_win"], fresh["away_win"]
        total = main_total(fresh)
        expected = _expected_total(fresh)
        confidence = fresh.get("confidence")
        age = fresh.get("ratings_age_days") if fresh.get("stale_ratings") else None
        source = "calculated"
        markets = fresh.get("markets")
    else:
        home_win = away_win = total = expected = confidence = age = None
        source = "unpriced"
        markets = None

    home, away = names.get(match.home_team_id, ""), names.get(match.away_team_id, "")
    entry = {
        "match_id": match.id,
        "kickoff": match.match_date.isoformat(),
        "status": match.status,
        # Started but not finished, as far as the feed has told us; and if no result has
        # come six hours after the start (a postponement or an abandoned game the feed never
        # reported), say so rather than showing it as in play for ever.
        "in_play": match.status != "completed"
        and timedelta(0) <= _now() - match.match_date < OVERDUE_AFTER,
        "overdue": match.status != "completed" and _now() - match.match_date >= OVERDUE_AFTER,
        "home": home,
        "away": away,
        "home_score": match.home_score,
        "away_score": match.away_score,
        "home_games": match.home_games,
        "away_games": match.away_games,
        "surface": match.surface,
        "home_win": home_win,
        "away_win": away_win,
        "pick": None,
        "total": (
            None if total is None else {"line": total["line"], "prob_over": total["prob_over"]}
        ),
        "expected_total": expected,
        "confidence": confidence,
        "ratings_age_days": age,
        "source": source,
        "winner_correct": None,
        "total_correct": None,
        # Teams, halves, quarters, spread (basketball); sets, handicaps, first set (tennis).
        # Each carries its result once the match is over and it can be graded.
        "markets": attach_results(match.sport, match, markets),
    }
    if home_win is not None:
        side = "home" if home_win >= away_win else "away"
        entry["pick"] = {
            "side": side,
            "name": home if side == "home" else away,
            "probability": max(home_win, away_win),
        }
        line = None if total is None else total["line"]
        over = None if total is None else total["prob_over"]
        entry["winner_correct"], entry["total_correct"] = _grade(
            match, home_win, away_win, line, over
        )
    return entry


def build_board(session: Session, sport: str, day: datetime) -> dict:
    """One day's matches in a sport, grouped by competition, with predictions."""
    if sport not in SPORTS:
        raise KeyError(sport)
    key = (sport, day.date().isoformat())
    cached = _board_cache.get(key)
    if cached is not None and monotonic() - cached[0] < BOARD_TTL_SECONDS:
        return cached[1]

    start = datetime.combine(day.date(), datetime.min.time())
    matches = (
        session.query(Match)
        .filter(
            Match.sport == sport,
            Match.match_date >= start,
            Match.match_date < start + timedelta(days=1),
        )
        .order_by(Match.match_date.asc(), Match.id.asc())
        .limit(BOARD_LIMIT)
        .all()
    )
    ids = {m.home_team_id for m in matches} | {m.away_team_id for m in matches}
    names = (
        {t.id: t.name for t in session.query(Team).filter(Team.id.in_(ids)).all()} if ids else {}
    )
    stored = {
        p.match_id: p
        for p in session.query(SportPrediction)
        .filter(SportPrediction.match_id.in_([m.id for m in matches]))
        .all()
    }
    missing = [m for m in matches if m.id not in stored]
    fresh: dict[int, dict | None] = {}
    if missing:
        try:
            fresh = {
                m.id: p for m, p in zip(missing, predict_for_matches(session, missing), strict=True)
            }
        except Exception:  # noqa: BLE001 - a board with no predictions beats no board
            logger.exception("board predictions failed for %s on %s", sport, day.date())
            try:
                session.rollback()
            except Exception:  # noqa: BLE001
                pass

    leagues = by_display_name() if sport == "basketball" else {}
    grouped: dict[str, list[dict]] = {}
    for match in matches:
        entry = _match_entry(match, names, stored.get(match.id), fresh.get(match.id))
        if entry["pick"] is None:
            # A side with too little history has no prediction, and a match with no
            # prediction is not listed: the site shows what the engine can stand behind.
            continue
        # Tennis is grouped by tournament (under its tour); basketball by league.
        group = match.tournament or match.competition if sport == "tennis" else match.competition
        grouped.setdefault((match.competition, group), []).append(entry)

    competitions = []
    for (tour, name), entries in grouped.items():
        info = leagues.get(name)
        competitions.append(
            {
                "name": name,
                "tour": tour if sport == "tennis" else None,
                "country": None if info is None else info.country,
                "country_code": None if info is None else info.country_code,
                "women": False if info is None else info.women,
                "matches": entries,
            }
        )
    competitions.sort(key=lambda c: (-len(c["matches"]), c["name"]))

    flat = [e for c in competitions for e in c["matches"]]
    result = {
        "sport": sport,
        "date": day.date().isoformat(),
        "counts": {
            "fixtures": len(flat),
            "finished": sum(1 for e in flat if e["status"] == "completed"),
            "priced": sum(1 for e in flat if e["pick"]),
            "stored_in_advance": sum(1 for e in flat if e["source"] == "stored"),
            "competitions": len(competitions),
        },
        "competitions": competitions,
    }
    _board_cache[key] = (monotonic(), result)
    return result


def _record(rows: list[tuple[bool | None, bool | None]]) -> dict:
    won = sum(1 for w, _ in rows if w)
    settled = sum(1 for w, _ in rows if w is not None)
    t_won = sum(1 for _, t in rows if t)
    t_settled = sum(1 for _, t in rows if t is not None)
    return {
        "winner": {"settled": settled, "won": won},
        "total": {"settled": t_settled, "won": t_won},
    }


def sport_record(session: Session, sport: str) -> dict:
    """Graded stored predictions for a sport, live (stored in advance) apart from reconstructed."""
    if sport not in SPORTS:
        raise KeyError(sport)
    pairs = (
        session.query(SportPrediction, Match)
        .join(Match, Match.id == SportPrediction.match_id)
        .filter(SportPrediction.sport == sport, Match.status == "completed")
        .all()
    )
    live: list = []
    reconstructed: list = []
    first = None
    market_rows: list = []
    for row, match in pairs:
        market_rows.append(
            (row.created_at < match.match_date, sport, match, (row.payload or {}).get("markets"))
        )
        graded = _grade(
            match, row.home_win_pct, row.away_win_pct, row.total_line, row.prob_over_pct
        )
        if row.created_at < match.match_date:
            live.append(graded)
            first = row.created_at if first is None or row.created_at < first else first
        else:
            reconstructed.append(graded)
    return {
        "sport": sport,
        "live": _record(live),
        "reconstructed": _record(reconstructed),
        "markets": markets_record(market_rows),
        "live_since": None if first is None else first.isoformat(),
        "stored_total": session.query(SportPrediction)
        .filter(SportPrediction.sport == sport)
        .count(),
    }
