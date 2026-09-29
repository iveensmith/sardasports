"""How often each market actually lands — the yardstick a call is judged against.

A probability on its own does not say whether the engine has found anything.
"Over 1.5 goals, 76%" sounds like a prediction until you know that over 1.5
lands in 74.8% of all matches, at which point it is a restatement of how
football works. What makes a call a claim is the distance between the model's
number and that base rate.

These are measured from completed matches rather than written down, for two
reasons. Hardcoded rates drift silently as data is ingested — a figure copied
from a blog post about the Premier League is simply wrong for a board that
also carries AFCON qualifiers. And the lines the engine prices can change; a
measured table follows them.

One pass over the matches table computes every rate at once and the result is
cached for the process, so this costs a single scan at first use rather than
anything per fixture. Rates move slowly — a season shifts them by a fraction
of a point — so a process-lifetime cache is the right granularity, and a
restart picks up new data.

Markets where the stat is not recorded (corners and cards are absent for
several competitions, half-time scores for some seasons) are counted only
over the matches that do record them. Treating a missing corner count as zero
corners would drag every corners base rate towards nothing.
"""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from ml.markets import BTTS, CARDS, CORNERS, DOUBLE_CHANCE, GOALS, HT_GOALS, MATCH_RESULT
from ml.prediction.predict import CARDS_LINES, CORNERS_LINES, GOALS_LINES, HT_GOALS_LINES

logger = logging.getLogger(__name__)

# Below this many completed matches a rate is noise, so the call is reported
# without a comparison rather than against a made-up yardstick.
MIN_SAMPLE = 200


def _line_sql(expression: str, line: float) -> str:
    return (
        f"AVG(CASE WHEN {expression} IS NULL THEN NULL "
        f"WHEN {expression} > {line} THEN 1.0 ELSE 0.0 END)"
    )


def _counted_sql(expression: str) -> str:
    return f"SUM(CASE WHEN {expression} IS NULL THEN 0 ELSE 1 END)"


TOTAL_GOALS = "(home_score + away_score)"
TOTAL_HT_GOALS = "(home_ht_goals + away_ht_goals)"
TOTAL_CORNERS = "(home_corners + away_corners)"
TOTAL_CARDS = "(home_yellow_cards + away_yellow_cards + home_red_cards + away_red_cards)"


# Process-lifetime cache, keyed by sport. Rates move by a fraction of a point
# over a season, so anything finer-grained would be false precision.
_CACHE: dict[str, dict[str, float]] = {}


def market_base_rates(session: Session, sport: str = "football") -> dict[str, float]:
    """`{"goals:over_2.5": 50.6, ...}` — percentages, cached per process."""
    cached = _CACHE.get(sport)
    if cached is not None:
        return cached

    selects = [
        "COUNT(*) AS n",
        "AVG(CASE WHEN home_score > away_score THEN 1.0 ELSE 0.0 END) AS mr_home",
        "AVG(CASE WHEN home_score = away_score THEN 1.0 ELSE 0.0 END) AS mr_draw",
        "AVG(CASE WHEN home_score < away_score THEN 1.0 ELSE 0.0 END) AS mr_away",
        f"{_counted_sql(TOTAL_HT_GOALS)} AS n_ht",
        f"{_counted_sql(TOTAL_CORNERS)} AS n_corners",
        f"{_counted_sql(TOTAL_CARDS)} AS n_cards",
    ]
    for line in GOALS_LINES:
        selects.append(f"{_line_sql(TOTAL_GOALS, line)} AS goals_{str(line).replace('.', '_')}")
    for line in HT_GOALS_LINES:
        selects.append(f"{_line_sql(TOTAL_HT_GOALS, line)} AS ht_{str(line).replace('.', '_')}")
    for line in CORNERS_LINES:
        selects.append(f"{_line_sql(TOTAL_CORNERS, line)} AS corners_{str(line).replace('.', '_')}")
    for line in CARDS_LINES:
        selects.append(f"{_line_sql(TOTAL_CARDS, line)} AS cards_{str(line).replace('.', '_')}")
    selects.append(
        "AVG(CASE WHEN home_score > 0 AND away_score > 0 THEN 1.0 ELSE 0.0 END) AS btts_yes"
    )

    row = (
        session.execute(
            text(
                f"SELECT {', '.join(selects)} FROM matches "
                "WHERE sport = :sport AND status = 'completed' "
                "AND home_score IS NOT NULL AND away_score IS NOT NULL"
            ),
            {"sport": sport},
        )
        .mappings()
        .one()
    )

    total = row["n"] or 0
    if total < MIN_SAMPLE:
        logger.info("Only %d completed %s matches; base rates not computed.", total, sport)
        _CACHE[sport] = {}
        return {}

    rates: dict[str, float] = {}

    def put(key: str, value, sample: int = total) -> None:
        """Record a rate, skipping markets with too little history to judge."""
        if value is None or sample < MIN_SAMPLE:
            return
        rates[key] = round(float(value) * 100.0, 1)

    home, draw, away = row["mr_home"], row["mr_draw"], row["mr_away"]
    put(f"{MATCH_RESULT}:home", home)
    put(f"{MATCH_RESULT}:draw", draw)
    put(f"{MATCH_RESULT}:away", away)
    # Derived exactly as the calls are, so a double chance is compared against
    # the sum of the same two outcomes rather than a separately-counted figure.
    if None not in (home, draw, away):
        put(f"{DOUBLE_CHANCE}:home_draw", home + draw)
        put(f"{DOUBLE_CHANCE}:away_draw", away + draw)
        put(f"{DOUBLE_CHANCE}:home_away", home + away)

    put(f"{BTTS}:yes", row["btts_yes"])
    if row["btts_yes"] is not None:
        put(f"{BTTS}:no", 1.0 - row["btts_yes"])

    for market, lines, prefix, sample in (
        (GOALS, GOALS_LINES, "goals", total),
        (HT_GOALS, HT_GOALS_LINES, "ht", row["n_ht"] or 0),
        (CORNERS, CORNERS_LINES, "corners", row["n_corners"] or 0),
        (CARDS, CARDS_LINES, "cards", row["n_cards"] or 0),
    ):
        for line in lines:
            over = row[f"{prefix}_{str(line).replace('.', '_')}"]
            if over is None:
                continue
            put(f"{market}:over_{line}", over, sample)
            put(f"{market}:under_{line}", 1.0 - over, sample)

    logger.info("Measured %d %s market base rates from %d matches", len(rates), sport, total)
    _CACHE[sport] = rates
    return rates


def reset_cache() -> None:
    """Drop the cached rates. Used by tests and after a bulk ingest."""
    _CACHE.clear()
