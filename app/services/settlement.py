"""Grading a call against what actually happened.

A prediction board is only worth reading if its predictions are settled. The
difference between a tipster and a model is not the confidence of the claim,
it is whether anybody went back and counted — so every call the engine makes
has to be gradeable against the final result by the same rule, automatically,
with no room to quietly drop the ones that lost.

Three outcomes, and the third matters as much as the first two:

    WON    the selection happened.
    LOST   it did not.
    VOID   the match does not record the stat this call was about, so there
           is no fact to grade against.

VOID is not a polite word for LOST. Several competitions record no corners
or cards, and some seasons no half-time score; a corners call on one of those
fixtures was never settleable. Counting it as a loss would understate the
engine, counting it as a win would flatter it, and counting it at all would
make the sample size a lie. It is excluded from the rate and reported
separately.

Keys match `ml.markets.Call.key` exactly, so a call settles without any
translation between the two modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ml.markets import BTTS, CARDS, CORNERS, DOUBLE_CHANCE, GOALS, HT_GOALS, MATCH_RESULT


class Outcome(StrEnum):
    """Serialises as its own value, so `outcome.value` and `str(outcome)`
    agree and a JSON payload carries "won" rather than "Outcome.WON"."""

    WON = "won"
    LOST = "lost"
    VOID = "void"


@dataclass(frozen=True)
class MatchResult:
    """The facts a call can be graded against.

    Every field beyond the full-time score is optional because the data
    genuinely is: `home_corners` is None for a competition that records no
    corners, which is different from a goalless first half.
    """

    home_score: int
    away_score: int
    home_ht_goals: int | None = None
    away_ht_goals: int | None = None
    home_corners: int | None = None
    away_corners: int | None = None
    home_cards: int | None = None
    away_cards: int | None = None

    @property
    def total_goals(self) -> int:
        return self.home_score + self.away_score

    @property
    def total_ht_goals(self) -> int | None:
        return _total(self.home_ht_goals, self.away_ht_goals)

    @property
    def total_corners(self) -> int | None:
        return _total(self.home_corners, self.away_corners)

    @property
    def total_cards(self) -> int | None:
        return _total(self.home_cards, self.away_cards)

    @property
    def winner(self) -> str:
        if self.home_score > self.away_score:
            return "home"
        if self.home_score < self.away_score:
            return "away"
        return "draw"

    @property
    def both_scored(self) -> bool:
        return self.home_score > 0 and self.away_score > 0


def _total(home, away) -> int | None:
    """Sum, or None if either side is unrecorded.

    Not `(home or 0) + (away or 0)`: that turns a missing corner count into
    zero corners, which grades every "under" call on an unrecorded fixture as
    a win.
    """
    if home is None or away is None:
        return None
    return home + away


def _over_under(selection: str, actual: int | None) -> Outcome:
    """Grade an `over_2.5` / `under_2.5` selection.

    Lines are half-numbers throughout, so a push is impossible and every
    settleable line resolves one way or the other.
    """
    if actual is None:
        return Outcome.VOID
    try:
        side, raw_line = selection.split("_", 1)
        line = float(raw_line)
    except (ValueError, AttributeError):
        return Outcome.VOID
    if side == "over":
        return Outcome.WON if actual > line else Outcome.LOST
    if side == "under":
        return Outcome.WON if actual < line else Outcome.LOST
    return Outcome.VOID


def settle(market: str, selection: str, result: MatchResult) -> Outcome:
    """Grade one selection against the final result.

    An unrecognised market or selection is VOID rather than LOST. If this
    module has not been taught how to settle something, that is our ignorance
    and not the model's failure, and recording it as a loss would be scoring
    the engine for our own omission.
    """
    if market == MATCH_RESULT:
        if selection not in ("home", "draw", "away"):
            return Outcome.VOID
        return Outcome.WON if result.winner == selection else Outcome.LOST

    if market == DOUBLE_CHANCE:
        covered = {
            "home_draw": {"home", "draw"},
            "away_draw": {"away", "draw"},
            "home_away": {"home", "away"},
        }.get(selection)
        if covered is None:
            return Outcome.VOID
        return Outcome.WON if result.winner in covered else Outcome.LOST

    if market == BTTS:
        if selection == "yes":
            return Outcome.WON if result.both_scored else Outcome.LOST
        if selection == "no":
            return Outcome.WON if not result.both_scored else Outcome.LOST
        return Outcome.VOID

    if market == GOALS:
        return _over_under(selection, result.total_goals)
    if market == HT_GOALS:
        return _over_under(selection, result.total_ht_goals)
    if market == CORNERS:
        return _over_under(selection, result.total_corners)
    if market == CARDS:
        return _over_under(selection, result.total_cards)

    return Outcome.VOID


def settle_key(key: str, result: MatchResult) -> Outcome:
    """Grade a `ml.markets.Call.key` — `"goals:over_2.5"` — directly."""
    market, _, selection = key.partition(":")
    if not selection:
        return Outcome.VOID
    return settle(market, selection, result)


def result_from_match(match) -> MatchResult | None:
    """Build a `MatchResult` from a `Match` row, or None if unplayed.

    Cards are the sum of both colours, matching how the engine prices them.
    """
    if match.home_score is None or match.away_score is None:
        return None
    return MatchResult(
        home_score=match.home_score,
        away_score=match.away_score,
        home_ht_goals=match.home_ht_goals,
        away_ht_goals=match.away_ht_goals,
        home_corners=match.home_corners,
        away_corners=match.away_corners,
        home_cards=_total(match.home_yellow_cards, match.home_red_cards),
        away_cards=_total(match.away_yellow_cards, match.away_red_cards),
    )


@dataclass(frozen=True)
class Record:
    """A settled tally, with voids held apart from the win rate."""

    won: int = 0
    lost: int = 0
    void: int = 0

    @property
    def settled(self) -> int:
        """Calls that could actually be graded — the sample the rate is over."""
        return self.won + self.lost

    @property
    def win_rate(self) -> float | None:
        """Percent, or None when nothing was settleable.

        None rather than 0.0: "no gradeable calls" and "graded and lost every
        one" are opposite facts and must not render as the same number.
        """
        if not self.settled:
            return None
        return round(self.won / self.settled * 100, 1)

    def plus(self, outcome: Outcome) -> Record:
        if outcome is Outcome.WON:
            return Record(self.won + 1, self.lost, self.void)
        if outcome is Outcome.LOST:
            return Record(self.won, self.lost + 1, self.void)
        return Record(self.won, self.lost, self.void + 1)

    def as_dict(self) -> dict:
        return {
            "won": self.won,
            "lost": self.lost,
            "void": self.void,
            "settled": self.settled,
            "win_rate": self.win_rate,
        }


def tally(outcomes) -> Record:
    record = Record()
    for outcome in outcomes:
        record = record.plus(outcome)
    return record
