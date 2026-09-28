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

        for _ in range(50):  # fixed-point iterations, converges quickly in practice
            # --- attack strengths: goals scored vs. opponents' defense ---
            for team in teams:
                scored, expected = 0.0, 0.0
                for m in matches:
                    if m["home_team"] == team:
                        scored += m["home_score"]
                        expected += self.league_avg_home_goals * strengths[m["away_team"]].defense
                    elif m["away_team"] == team:
                        scored += m["away_score"]
                        expected += self.league_avg_away_goals * strengths[m["home_team"]].defense
                if expected > 0:
                    strengths[team].attack = max(0.05, scored / expected)

            # --- defense strengths: goals conceded vs. opponents' attack ---
            for team in teams:
                conceded, expected = 0.0, 0.0
                for m in matches:
                    if m["home_team"] == team:
                        conceded += m["away_score"]
                        expected += self.league_avg_away_goals * strengths[m["away_team"]].attack
                    elif m["away_team"] == team:
                        conceded += m["home_score"]
                        expected += self.league_avg_home_goals * strengths[m["home_team"]].attack
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
