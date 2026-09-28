"""The Poisson fit's indexed inner loop: same answer, far less work.

`PoissonModel.fit` used to scan every match once per team on each of its 50
iterations — O(50 x 2 x teams x matches) — even though a team appears in a
small fraction of the rows. It was 57% of a prediction board's runtime and
also slowed every training run.

The rewrite indexes each team's own appearances once. These tests pin the
part that matters: the numbers must be *identical*, not merely close, since
a speed-up that quietly moves probabilities is a regression wearing a
disguise.
"""

from __future__ import annotations

import time

import pytest

from ml.poisson.model import PoissonModel, TeamStrength


def _reference_fit(model: PoissonModel, matches: list[dict]) -> PoissonModel:
    """The original O(teams x matches) implementation, kept verbatim."""
    teams = sorted({m["home_team"] for m in matches} | {m["away_team"] for m in matches})
    n = len(matches)
    model.league_avg_home_goals = sum(m["home_score"] for m in matches) / n
    model.league_avg_away_goals = sum(m["away_score"] for m in matches) / n
    strengths = {t: TeamStrength() for t in teams}

    for _ in range(50):
        for team in teams:
            scored = expected = 0.0
            for m in matches:
                if m["home_team"] == team:
                    scored += m["home_score"]
                    expected += model.league_avg_home_goals * strengths[m["away_team"]].defense
                elif m["away_team"] == team:
                    scored += m["away_score"]
                    expected += model.league_avg_away_goals * strengths[m["home_team"]].defense
            if expected > 0:
                strengths[team].attack = max(0.05, scored / expected)
        for team in teams:
            conceded = expected = 0.0
            for m in matches:
                if m["home_team"] == team:
                    conceded += m["away_score"]
                    expected += model.league_avg_away_goals * strengths[m["away_team"]].attack
                elif m["away_team"] == team:
                    conceded += m["home_score"]
                    expected += model.league_avg_home_goals * strengths[m["home_team"]].attack
            if expected > 0:
                strengths[team].defense = max(0.05, conceded / expected)

    model.team_strength = strengths
    model._is_fitted = True
    return model


def _synthetic_league(teams: int = 20, seed: int = 7) -> list[dict]:
    """A full double round-robin with deterministic, uneven scorelines."""
    import random

    rng = random.Random(seed)
    names = [f"Team {i:02d}" for i in range(teams)]
    matches = []
    for home in names:
        for away in names:
            if home == away:
                continue
            matches.append(
                {
                    "home_team": home,
                    "away_team": away,
                    "home_score": rng.randint(0, 4),
                    "away_score": rng.randint(0, 3),
                }
            )
    return matches


def test_fit_is_numerically_identical_to_the_original():
    """Not 'close' — identical. Same arithmetic, same order, fewer reads."""
    matches = _synthetic_league()
    reference = _reference_fit(PoissonModel(), list(matches))
    optimised = PoissonModel().fit(list(matches))

    assert optimised.league_avg_home_goals == reference.league_avg_home_goals
    assert optimised.league_avg_away_goals == reference.league_avg_away_goals
    assert set(optimised.team_strength) == set(reference.team_strength)
    for team, expected in reference.team_strength.items():
        actual = optimised.team_strength[team]
        assert actual.attack == expected.attack, team
        assert actual.defense == expected.defense, team


def test_derived_probabilities_are_identical():
    """The strengths feed everything downstream, so check the outputs too."""
    matches = _synthetic_league()
    reference = _reference_fit(PoissonModel(), list(matches))
    optimised = PoissonModel().fit(list(matches))

    home, draw, away = reference.result_probabilities("Team 00", "Team 01")
    home2, draw2, away2 = optimised.result_probabilities("Team 00", "Team 01")
    assert (home, draw, away) == (home2, draw2, away2)
    assert reference.expected_goals("Team 00", "Team 01") == optimised.expected_goals(
        "Team 00", "Team 01"
    )


def test_fit_is_substantially_faster_than_the_original():
    """A loose floor, to catch a revert rather than to benchmark.

    The gain grows with team count (it removes a factor of `teams` from the
    inner loop), so a 30-team league is a conservative place to assert it.
    """
    matches = _synthetic_league(teams=30)

    start = time.perf_counter()
    _reference_fit(PoissonModel(), list(matches))
    reference_seconds = time.perf_counter() - start

    start = time.perf_counter()
    PoissonModel().fit(list(matches))
    optimised_seconds = time.perf_counter() - start

    assert (
        optimised_seconds * 3 < reference_seconds
    ), f"expected a large speed-up, got {reference_seconds:.3f}s -> {optimised_seconds:.3f}s"


def test_empty_history_still_raises():
    """The guard that callers rely on to fall back to league averages."""
    with pytest.raises(ValueError):
        PoissonModel().fit([])
