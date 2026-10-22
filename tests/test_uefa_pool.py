"""The UEFA club competitions fit as one shrunk pool, not three raw ones.

Measured on 2,028 held-out UEFA matches (see `ml.competitions.POOL_PRIOR_MATCHES`), the plain
per-competition goals fit was worse than assuming every team is average, and gave some
fixtures expected goals of 4 to 5 a side. The same failure is documented there for
international football; the remedy is the same pooling, plus a shrinkage prior.
"""

from __future__ import annotations

import math
from datetime import datetime

from ml.competitions import POOL_PRIOR_MATCHES, UEFA_CLUB_POOL, fit_pool
from ml.poisson.model import DixonColesModel
from ml.prediction.predict import build_shared_fits

UCL, UEL, UECL = "UEFA Champions League", "UEFA Europa League", "UEFA Conference League"


def _history(competition, home, away, home_score, away_score, n=1, day=1):
    return [
        {
            "home_team": home,
            "away_team": away,
            "home_score": home_score,
            "away_score": away_score,
            "competition": competition,
            "match_date": datetime(2025, 10, day + i),
        }
        for i in range(n)
    ]


def test_the_three_uefa_club_competitions_share_one_pool():
    assert fit_pool(UCL) == fit_pool(UEL) == fit_pool(UECL) == UEFA_CLUB_POOL


def test_domestic_leagues_and_nations_are_not_in_the_uefa_pool():
    assert fit_pool("English Premier League") == "English Premier League"
    assert fit_pool("UEFA Nations League") != UEFA_CLUB_POOL


def test_only_the_uefa_pool_is_shrunk():
    assert POOL_PRIOR_MATCHES == {UEFA_CLUB_POOL: 8.0}
    assert POOL_PRIOR_MATCHES.get(fit_pool("English Premier League"), 0.0) == 0.0


def test_a_card_with_two_uefa_competitions_fits_once_and_shrinks():
    history = _history(UCL, "Real Madrid", "Kairat", 5, 0) + _history(UEL, "Roma", "Kairat", 2, 1)
    fits = build_shared_fits(history, [UCL, UEL])

    assert fits[UCL] is fits[UEL]
    assert fits[UCL].poisson.prior_matches == 8.0


def test_a_league_fit_is_not_shrunk():
    history = _history("English Premier League", "Arsenal", "Luton", 2, 0)
    fit = build_shared_fits(history, ["English Premier League"])["English Premier League"]

    assert fit.poisson.prior_matches == 0.0


def test_a_club_met_in_another_uefa_competition_is_known_to_the_fit():
    """A Europa League fit used to see only Europa League matches. A club that came down from a
    Champions League qualifier, or went up, was a stranger."""
    history = _history(UCL, "Real Madrid", "Kairat", 4, 0, n=6)
    poisson = build_shared_fits(history, [UEL])[UEL].poisson

    assert "Real Madrid" in poisson.team_strength


def test_zero_prior_is_the_plain_fit():
    matches = _history("x", "A", "B", 3, 1, n=5) + _history("x", "B", "C", 0, 2, n=5, day=10)
    plain = DixonColesModel().fit(matches)
    explicit = DixonColesModel(prior_matches=0.0).fit(matches)

    for team in ("A", "B", "C"):
        assert explicit.team_strength[team].attack == plain.team_strength[team].attack
        assert explicit.team_strength[team].defense == plain.team_strength[team].defense


def test_a_prior_pulls_a_thinly_seen_team_toward_average():
    """One 5-0 win is not evidence of a five-times-average attack. The plain fit says it is;
    with the prior the team is still the stronger one, but not absurdly so."""
    matches = _history("x", "Winner", "Loser", 5, 0) + _history("x", "Loser", "Other", 1, 1)

    plain = DixonColesModel().fit(matches)
    shrunk = DixonColesModel(prior_matches=8.0).fit(matches)

    # Average strength is 1.0, so the distance of log-strength from zero is how extreme a team is.
    # The plain fit's most extreme value is cut, not merely nudged.
    def extreme(model):
        return max(
            abs(math.log(getattr(s, side)))
            for s in model.team_strength.values()
            for side in ("attack", "defense")
        )

    assert extreme(shrunk) < 0.8 * extreme(plain)
