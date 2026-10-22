"""Poisson goal-scoring model.

A standard football analytics approach (Maher, 1982; popularized by Dixon &
Coles): each team has an attack strength and a defense strength, fit from
historical goals scored/conceded relative to the league average. Expected
goals for a fixture are:

    lambda_home = league_avg_home_goals * attack[home] * defense[away] * home_advantage
    lambda_away = league_avg_away_goals * attack[away] * defense[home]

Goals are then modeled as independent Poisson(lambda_home) / Poisson(lambda_away)
random variables, which gives a full scoreline probability matrix — from that
matrix everything else (match result, correct score, over/under, BTTS) falls
out directly as a real calculation, not an invented number.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import exp, factorial

import numpy as np


def _poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return exp(-lam) * (lam**k) / factorial(k)


@dataclass
class TeamStrength:
    attack: float = 1.0
    defense: float = 1.0


@dataclass
class PoissonModel:
    """Fits per-team attack/defense strengths and predicts scorelines."""

    home_advantage: float = 1.15
    max_goals: int = 8
    league_avg_home_goals: float = 1.5
    league_avg_away_goals: float = 1.2
    team_strength: dict[str, TeamStrength] = field(default_factory=dict)
    _is_fitted: bool = False

    def fit(self, matches: list[dict]) -> PoissonModel:
        """Fit attack/defense strengths from a list of completed matches.

        Each match dict must have: home_team, away_team, home_score, away_score.
        Uses simple iterative proportional fitting (a few passes converge well
        for this purpose — this is the standard textbook approach, not a
        heavyweight MLE solve, which keeps it fast and dependency-light).
        """
        if not matches:
            raise ValueError("Cannot fit PoissonModel on an empty match list")

        teams = sorted({m["home_team"] for m in matches} | {m["away_team"] for m in matches})
        home_goals_total = sum(m["home_score"] for m in matches)
        away_goals_total = sum(m["away_score"] for m in matches)
        n = len(matches)
        self.league_avg_home_goals = home_goals_total / n
        self.league_avg_away_goals = away_goals_total / n

        strengths = {t: TeamStrength() for t in teams}

        # Index each team's own appearances once.
        #
        # The loops below previously scanned *every* match for *every* team,
        # on each of 50 iterations — O(50 x 2 x teams x matches), where a
        # team actually appears in a tiny fraction of the rows. On a real
        # competition that made one fit take ~1.1 seconds and dominated both
        # serving (57% of a prediction board) and training.
        #
        # Each entry is (goals_for, goals_against, opponent, scored_at_home),
        # which is everything the two passes need. The arithmetic, the
        # iteration order over `teams`, and the in-place updates are all
        # unchanged, so the fitted strengths are identical — this only stops
        # reading rows that contribute nothing.
        appearances: dict[str, list[tuple[float, float, str, bool]]] = {t: [] for t in teams}
        for m in matches:
            home, away = m["home_team"], m["away_team"]
            home_score, away_score = m["home_score"], m["away_score"]
            appearances[home].append((home_score, away_score, away, True))
            appearances[away].append((away_score, home_score, home, False))

        for _ in range(50):  # fixed-point iterations, converges quickly in practice
            # --- attack strengths: goals scored vs. opponents' defense ---
            for team in teams:
                scored, expected = 0.0, 0.0
                for goals_for, _against, opponent, at_home in appearances[team]:
                    scored += goals_for
                    league_avg = (
                        self.league_avg_home_goals if at_home else self.league_avg_away_goals
                    )
                    expected += league_avg * strengths[opponent].defense
                if expected > 0:
                    strengths[team].attack = max(0.05, scored / expected)

            # --- defense strengths: goals conceded vs. opponents' attack ---
            for team in teams:
                conceded, expected = 0.0, 0.0
                for _for, goals_against, opponent, at_home in appearances[team]:
                    conceded += goals_against
                    # Note the asymmetry, preserved from the original: a
                    # team's *defensive* expectation uses the league average
                    # for the side its opponent played on.
                    league_avg = (
                        self.league_avg_away_goals if at_home else self.league_avg_home_goals
                    )
                    expected += league_avg * strengths[opponent].attack
                if expected > 0:
                    strengths[team].defense = max(0.05, conceded / expected)

        self.team_strength = strengths
        self._is_fitted = True
        return self

    def _strength(self, team: str) -> TeamStrength:
        return self.team_strength.get(team, TeamStrength())

    def expected_goals(self, home_team: str, away_team: str) -> tuple[float, float]:
        """Return (expected_home_goals, expected_away_goals) for a fixture."""
        home = self._strength(home_team)
        away = self._strength(away_team)
        lambda_home = self.league_avg_home_goals * home.attack * away.defense * self.home_advantage
        lambda_away = self.league_avg_away_goals * away.attack * home.defense
        return max(0.05, lambda_home), max(0.05, lambda_away)

    def scoreline_matrix(self, home_team: str, away_team: str) -> np.ndarray:
        """Full P(home_score=i, away_score=j) matrix, i,j in [0, max_goals]."""
        lambda_home, lambda_away = self.expected_goals(home_team, away_team)
        home_probs = np.array([_poisson_pmf(i, lambda_home) for i in range(self.max_goals + 1)])
        away_probs = np.array([_poisson_pmf(j, lambda_away) for j in range(self.max_goals + 1)])
        matrix = np.outer(home_probs, away_probs)
        return matrix / matrix.sum()  # renormalize for the truncation at max_goals

    def result_probabilities(self, home_team: str, away_team: str) -> tuple[float, float, float]:
        """(P(home win), P(draw), P(away win)) from the scoreline matrix."""
        matrix = self.scoreline_matrix(home_team, away_team)
        home_win = float(np.tril(matrix, k=-1).sum())
        draw = float(np.trace(matrix))
        away_win = float(np.triu(matrix, k=1).sum())
        return home_win, draw, away_win

    def top_scorelines(self, home_team: str, away_team: str, n: int = 5) -> list[dict]:
        """Top `n` most likely exact scorelines, e.g. [{"score": "2-1", "probability": 0.12}]."""
        matrix = self.scoreline_matrix(home_team, away_team)
        flat = [
            (i, j, matrix[i, j])
            for i in range(self.max_goals + 1)
            for j in range(self.max_goals + 1)
        ]
        flat.sort(key=lambda x: x[2], reverse=True)
        return [{"score": f"{i}-{j}", "probability": round(float(p), 4)} for i, j, p in flat[:n]]

    def prob_over_under(
        self, home_team: str, away_team: str, line: float = 2.5
    ) -> tuple[float, float]:
        """(P(total goals > line), P(total goals < line))."""
        matrix = self.scoreline_matrix(home_team, away_team)
        over = 0.0
        for i in range(self.max_goals + 1):
            for j in range(self.max_goals + 1):
                if i + j > line:
                    over += matrix[i, j]
        return float(over), float(1 - over)

    def prob_btts(self, home_team: str, away_team: str) -> tuple[float, float]:
        """(P(both teams score), P(not both teams score))."""
        matrix = self.scoreline_matrix(home_team, away_team)
        btts_yes = float(matrix[1:, 1:].sum())
        return btts_yes, 1 - btts_yes


# --- Dixon-Coles ---------------------------------------------------------------------------------


def _dc_tau(i: int, j: int, lam: float, mu: float, rho: float) -> float:
    """Dixon & Coles' (1997) correction to the independent-Poisson probability of a low score.

    Plain independent Poisson goals under-state how often a low-scoring game ends 0-0 or 1-1
    and over-state 1-0 / 0-1. The correction multiplies exactly those four cells; the form is
    chosen so the adjusted probabilities still sum to one.
    """
    if i == 0 and j == 0:
        return 1.0 - lam * mu * rho
    if i == 0 and j == 1:
        return 1.0 + lam * rho
    if i == 1 and j == 0:
        return 1.0 + mu * rho
    if i == 1 and j == 1:
        return 1.0 - rho
    return 1.0


@dataclass
class DixonColesModel(PoissonModel):
    """`PoissonModel` with Dixon & Coles' low-score correction, and three honest differences.

    1. **No second home-advantage factor.** `PoissonModel` multiplies the home side's expected
       goals by 1.15 *on top of* a league average of home goals that already contains the home
       advantage (the fit divides by separate home and away averages). Counted twice, the home
       side was given about 15% too many goals, which showed up as home wins claimed 49.3% of
       the time against 43.8% real. Here the factor defaults to 1.
    2. **`rho`**, the low-score dependence, estimated by maximum likelihood from the matches
       the model is fitted on (about -0.05 to -0.15 for football: a draw at low scores is more
       likely than independence says).
    3. **Optional recency weighting** (`decay_per_day`): a match counts `exp(-decay * age)`,
       so a team's recent form moves its strengths more than a season-old result. Matches need
       a `match_date`; ages are measured from `as_of` (the day being predicted) or, if that is
       unset, the newest match in the fit.

    Everything else (iterative strengths, the scoreline matrix, how markets are read off it)
    is the parent's, so a `DixonColesModel` is a drop-in replacement.
    """

    home_advantage: float = 1.0
    rho: float = 0.0
    decay_per_day: float = 0.0
    as_of: object = None  # datetime the ages are measured from
    fit_rho: bool = True
    # Shrinkage toward an average team, in "matches": each team's strengths are fitted as if it had
    # also played this many matches at exactly average strength. Zero is the plain fit. It exists
    # for competitions whose teams rarely meet (the UEFA club competitions), where a handful of
    # matches against unrelated opponents is enough for the plain fit to produce a defence of 0.05
    # or an attack of 5, and to state it with full confidence. A league where every team plays
    # every other many times does not need it and keeps zero.
    prior_matches: float = 0.0

    def _weights(self, matches: list[dict]) -> list[float]:
        if not self.decay_per_day:
            return [1.0] * len(matches)
        dated = [m.get("match_date") for m in matches]
        if any(d is None for d in dated):
            return [1.0] * len(matches)
        reference = self.as_of or max(dated)
        return [
            exp(-self.decay_per_day * max(0.0, (reference - d).total_seconds() / 86400.0))
            for d in dated
        ]

    def fit(self, matches: list[dict]) -> DixonColesModel:
        if not matches:
            raise ValueError("Cannot fit DixonColesModel on an empty match list")
        weights = self._weights(matches)
        teams = sorted({m["home_team"] for m in matches} | {m["away_team"] for m in matches})
        total_w = sum(weights)
        self.league_avg_home_goals = (
            sum(w * m["home_score"] for w, m in zip(weights, matches, strict=True)) / total_w
        )
        self.league_avg_away_goals = (
            sum(w * m["away_score"] for w, m in zip(weights, matches, strict=True)) / total_w
        )

        strengths = {t: TeamStrength() for t in teams}
        appearances: dict[str, list[tuple[float, float, str, bool, float]]] = {t: [] for t in teams}
        for w, m in zip(weights, matches, strict=True):
            home, away = m["home_team"], m["away_team"]
            appearances[home].append((m["home_score"], m["away_score"], away, True, w))
            appearances[away].append((m["away_score"], m["home_score"], home, False, w))

        avg_home, avg_away = self.league_avg_home_goals, self.league_avg_away_goals
        # The prior's weight in goals: `prior_matches` average-strength matches' worth.
        prior_goals = self.prior_matches * (avg_home + avg_away) / 2
        for _ in range(50):
            for team in teams:
                scored = expected = 0.0
                for goals_for, _against, opponent, at_home, w in appearances[team]:
                    scored += w * goals_for
                    league_avg = avg_home if at_home else avg_away
                    expected += w * league_avg * strengths[opponent].defense
                if expected + prior_goals > 0:
                    strengths[team].attack = max(
                        0.05, (scored + prior_goals) / (expected + prior_goals)
                    )
            for team in teams:
                conceded = expected = 0.0
                for _for, goals_against, opponent, at_home, w in appearances[team]:
                    conceded += w * goals_against
                    league_avg = avg_away if at_home else avg_home
                    expected += w * league_avg * strengths[opponent].attack
                if expected + prior_goals > 0:
                    strengths[team].defense = max(
                        0.05, (conceded + prior_goals) / (expected + prior_goals)
                    )

        self.team_strength = strengths
        self._is_fitted = True
        if self.fit_rho:
            self.rho = self._estimate_rho(matches, weights)
        return self

    def _estimate_rho(self, matches: list[dict], weights: list[float]) -> float:
        """Maximum-likelihood rho given the fitted strengths.

        Only matches that finished 0-0, 0-1, 1-0 or 1-1 depend on it, and the form of the
        correction keeps the distribution normalised, so the likelihood is just the sum of
        `log(tau)` over those matches. One bounded scalar search; rho is held where every
        tau stays positive for every match in the fit.
        """
        from scipy.optimize import minimize_scalar

        low = []
        upper, lower = 0.5, -0.5
        for w, m in zip(weights, matches, strict=True):
            i, j = int(m["home_score"]), int(m["away_score"])
            lam, mu = self.expected_goals(m["home_team"], m["away_team"])
            if i <= 1 and j <= 1:
                low.append((w, i, j, lam, mu))
            # Keep tau positive for the low cells of every match, not just the observed ones.
            upper = min(upper, 0.99 / max(lam * mu, 1e-9), 0.99)
            lower = max(lower, -0.99 / max(lam, mu, 1e-9))
        if not low or lower >= upper:
            return 0.0

        def negative_log_likelihood(rho: float) -> float:
            total = 0.0
            for w, i, j, lam, mu in low:
                tau = _dc_tau(i, j, lam, mu, rho)
                if tau <= 1e-9:
                    return 1e12
                total += w * np.log(tau)
            return -total

        result = minimize_scalar(
            negative_log_likelihood,
            bounds=(lower, upper),
            method="bounded",
            options={"xatol": 1e-4},
        )
        return float(result.x)

    def scoreline_matrix(self, home_team: str, away_team: str) -> np.ndarray:
        lam, mu = self.expected_goals(home_team, away_team)
        home_probs = np.array([_poisson_pmf(i, lam) for i in range(self.max_goals + 1)])
        away_probs = np.array([_poisson_pmf(j, mu) for j in range(self.max_goals + 1)])
        matrix = np.outer(home_probs, away_probs)
        if self.rho:
            for i in (0, 1):
                for j in (0, 1):
                    matrix[i, j] *= _dc_tau(i, j, lam, mu, self.rho)
        return matrix / matrix.sum()
