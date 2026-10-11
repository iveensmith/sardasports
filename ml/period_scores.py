"""Per-period scores: basketball quarters and tennis sets.

The markets beyond "who wins" and "total points" (a quarter's total, a half, a team's
points, set betting, a game handicap) can only be priced from, and graded against, what
each period actually produced. A match row holds only the final tally, so the period
detail is kept in one JSON column, `matches.period_scores`:

* basketball: ``{"home": [q1, q2, q3, q4], "away": [q1, q2, q3, q4], "ot": [home, away] | None}``
  where ``ot`` is the points scored in all overtime periods together (None when the game
  finished in regulation). The four quarters are regulation only, so a half or a quarter
  market is never polluted by overtime.
* tennis: ``{"sets": [[home_games, away_games], ...]}`` one entry per set played, in the
  order played, from the *home slot's* point of view (the slot is an arbitrary ordering,
  see `scripts/fetch_tennis.py`).

A period is stored only if the source gave every figure for it. A partial record is
dropped, not guessed.
"""

from __future__ import annotations

QUARTERS = 4


def _whole(value) -> int | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number < 0 or number != int(number):  # NaN, negative, fractional
        return None
    return int(number)


def basketball_periods(scores: dict | None) -> dict | None:
    """The quarters from an API-Basketball ``scores`` block, or None if any is missing."""
    if not scores:
        return None
    home, away = scores.get("home") or {}, scores.get("away") or {}
    quarters_home = [_whole(home.get(f"quarter_{i}")) for i in range(1, QUARTERS + 1)]
    quarters_away = [_whole(away.get(f"quarter_{i}")) for i in range(1, QUARTERS + 1)]
    if None in quarters_home or None in quarters_away:
        return None
    overtime_home, overtime_away = _whole(home.get("over_time")), _whole(away.get("over_time"))
    overtime = None
    if overtime_home is not None or overtime_away is not None:
        overtime = [overtime_home or 0, overtime_away or 0]
    return {"home": quarters_home, "away": quarters_away, "ot": overtime}


def tennis_sets(set_games: list[tuple[int, int]] | None) -> dict | None:
    """``{"sets": [[a, b], ...]}`` from a list of (games, games) per set, or None."""
    if not set_games:
        return None
    sets = []
    for pair in set_games:
        a, b = _whole(pair[0]), _whole(pair[1])
        if a is None or b is None:
            return None
        sets.append([a, b])
    return {"sets": sets}


def flip_tennis(periods: dict | None) -> dict | None:
    """The same sets from the other slot's point of view."""
    if not periods:
        return None
    return {"sets": [[b, a] for a, b in periods["sets"]]}


def tennis_from_row(row, winner_cols=("W1", "W2", "W3", "W4", "W5"), loser_cols=None):
    """Winner-first (games, games) pairs from a tennis-data row, for the sets that were played."""
    loser_cols = loser_cols or tuple(c.replace("W", "L") for c in winner_cols)
    pairs = []
    for w_col, l_col in zip(winner_cols, loser_cols, strict=True):
        won, lost = _whole(row.get(w_col)), _whole(row.get(l_col))
        if won is None or lost is None:
            continue
        pairs.append((won, lost))
    return pairs
