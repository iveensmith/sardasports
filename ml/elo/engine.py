"""Elo rating engine.

An independent, DB-agnostic implementation of the Elo rating system adapted
for football (three-outcome results, draws count as a half-win for each
side). It knows nothing about SQLAlchemy — callers pass in plain data and get
plain data back, which keeps it trivially unit-testable and reusable from
scripts, training code, and the API layer alike.

Reference: standard Elo update with a home-advantage offset, as used by
football rating sites (e.g. clubelo.com / eloratings.net conventions).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass
class MatchResult:
    """One completed match, as needed to update Elo ratings."""

    home_team: str
    away_team: str
    home_score: int
    away_score: int
    match_date: object  # any sortable/orderable date-like value (datetime, date, str-ISO)
    # Tournament football (World Cup, Euros, Copa America) is played on
    # neutral ground, where the "home" side is only a fixture-list label.
    # Crediting it the home-advantage offset would systematically under-rate
    # whichever side the schedule happened to list second.
    neutral_venue: bool = False
    # Used only to look up a per-competition K (see EloEngine.competition_k).
    # None means "use the engine's default K", which is what every caller
    # that predates competition weighting gets.
    competition: str | None = None


@dataclass
class EloUpdate:
    """The result of applying one match to the Elo state."""

    home_team: str
    away_team: str
    match_date: object
    home_rating_before: float
    away_rating_before: float
    home_rating_after: float
    away_rating_after: float


@dataclass
class EloEngine:
    """Tracks and updates Elo ratings for a set of teams.

    Parameters
    ----------
    k_factor:
        Controls how much a single match moves a team's rating. Higher = more
        volatile ratings.
    home_advantage:
        Rating points added to the home team's effective rating before
        computing the expected-score, modeling home-field advantage.
    initial_rating:
        Rating assigned to a team the first time it is seen.
    competition_k:
        Optional per-competition override of `k_factor`, keyed by the
        competition name on each `MatchResult`. Competitions absent from the
        mapping — and matches carrying no competition at all — use
        `k_factor`, so leaving this as None reproduces the flat-K behaviour
        exactly.

        This exists because a flat K assumes every pool gets enough matches
        to converge, and one of ours does not. National teams play ~10
        matches a year: measured on our own completed internationals, a flat
        K=20 leaves the pool with a standard deviation of 43.8 rating points
        against 112.9 for clubs, and the favourite in a 50-60% fixture
        actually wins 67.4% of the time — 14 points of under-confidence that
        clubs (within 2 points across the mass of the distribution) do not
        show. Weighting a World Cup match above a friendly is also right on
        the merits: friendlies are played with rotated squads and nothing at
        stake. See ml/elo/football.py for the values and scripts/elo_calibration.py
        for the harness that measures this.
    """

    k_factor: float = 20.0
    home_advantage: float = 60.0
    initial_rating: float = 1500.0
    competition_k: Mapping[str, float] | None = None
    _ratings: dict[str, float] = field(default_factory=dict)

    def _k_for(self, competition: str | None) -> float:
        """The K to apply to one match."""
        if self.competition_k is None or competition is None:
            return self.k_factor
        return self.competition_k.get(competition, self.k_factor)

    def _home_offset(self, neutral_venue: bool) -> float:
        """The home-advantage offset to actually apply: zero on neutral ground."""
        return 0.0 if neutral_venue else self.home_advantage

    def get_rating(self, team: str) -> float:
        """Current rating for `team`, defaulting to `initial_rating` if unseen."""
        return self._ratings.get(team, self.initial_rating)

    def set_rating(self, team: str, rating: float) -> None:
        self._ratings[team] = rating

    @staticmethod
    def expected_score(rating_a: float, rating_b: float) -> float:
        """Probability that the side rated `rating_a` beats the side rated `rating_b`.

        Standard Elo logistic expectation, symmetric around a 400-point gap
        giving a ~10x expectation ratio.
        """
        return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400.0))

    def result_probabilities(
        self, home_team: str, away_team: str, neutral_venue: bool = False
    ) -> tuple[float, float, float]:
        """Elo-implied (home_win, draw, away_win) probabilities for a hypothetical match.

        Elo natively only models a binary win-probability, so we derive a
        three-way split: `expected_score` gives the home win-or-draw-credit
        rate; we convert it to a draw-aware distribution using an empirically
        reasonable draw band around 50/50, which shrinks as the rating gap
        (and hence result certainty) grows.
        """
        home_rating = self.get_rating(home_team) + self._home_offset(neutral_venue)
        away_rating = self.get_rating(away_team)
        home_expected = self.expected_score(home_rating, away_rating)

        # Draw probability peaks when the match is a toss-up and shrinks as
        # one side becomes heavily favored — modeled as a simple triangular
        # function of how far `home_expected` is from 0.5.
        draw_prob = max(0.05, 0.28 - 0.35 * abs(home_expected - 0.5))
        home_win_prob = home_expected * (1 - draw_prob)
        away_win_prob = (1 - home_expected) * (1 - draw_prob)

        total = home_win_prob + draw_prob + away_win_prob
        return home_win_prob / total, draw_prob / total, away_win_prob / total

    def apply_result(self, match: MatchResult) -> EloUpdate:
        """Update both teams' ratings from a completed match and return the delta."""
        home_before = self.get_rating(match.home_team)
        away_before = self.get_rating(match.away_team)

        if match.home_score > match.away_score:
            actual_home, actual_away = 1.0, 0.0
        elif match.home_score < match.away_score:
            actual_home, actual_away = 0.0, 1.0
        else:
            actual_home, actual_away = 0.5, 0.5

        expected_home = self.expected_score(
            home_before + self._home_offset(match.neutral_venue), away_before
        )
        expected_away = 1.0 - expected_home

        # Goal-difference multiplier (common Elo-for-football extension): a
        # 3-0 result moves ratings more than a 1-0 result.
        goal_diff = abs(match.home_score - match.away_score)
        margin_multiplier = 1.0 if goal_diff <= 1 else (1.5 if goal_diff == 2 else 1.75)

        k_factor = self._k_for(match.competition)
        home_after = home_before + k_factor * margin_multiplier * (actual_home - expected_home)
        away_after = away_before + k_factor * margin_multiplier * (actual_away - expected_away)

        self._ratings[match.home_team] = home_after
        self._ratings[match.away_team] = away_after

        return EloUpdate(
            home_team=match.home_team,
            away_team=match.away_team,
            match_date=match.match_date,
            home_rating_before=home_before,
            away_rating_before=away_before,
            home_rating_after=home_after,
            away_rating_after=away_after,
        )

    def replay(self, matches: list[MatchResult]) -> list[EloUpdate]:
        """Apply a chronologically-sorted list of matches, returning every update.

        Callers are responsible for sorting `matches` by date first — this
        method applies them in the given order without re-sorting, so the
        caller controls (and can verify) chronology explicitly.
        """
        return [self.apply_result(m) for m in matches]
