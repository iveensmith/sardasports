"""The international pool's data-starvation bugs, pinned.

Both failures here were silent. Nothing crashed, no test went red, and the
accuracy metrics looked fine — because both are errors of *confidence*, not
of which side gets picked. The engine named the right favourite and then put
the wrong number on it, which is the one kind of wrong a prediction board
cannot survive: Spain were quoted at 1.22 to beat Croatia and the board said
Croatia had a 21% chance.

What was wrong
--------------
1. **Elo under-confidence.** A flat K=20 assumes every pool plays enough
   matches to converge. Club football does; national teams, at ~10 matches a
   year from a 2022 start, do not. The pool never left 1500: standard
   deviation 43.8 against the club pool's 112.9, so no rating gap in it could
   express an 80% favourite. Measured walk-forward, the favourite in a 50-60%
   international fixture actually won 67.4%.

2. **Poisson over-confidence, in the opposite direction.** Fitting attack and
   defence strengths per competition gave the Nations League 350 matches
   across ~55 teams. On a chronological split that fit said 90-100% about
   fixtures the favourite won 62.5% of, and produced no fit at all for 83 of
   404 test matches.

The two errors pointed opposite ways, which is why the blended number looked
merely unremarkable rather than obviously broken, and why neither showed up
until someone who knew the sport looked at a specific fixture.

These tests do not re-derive the tuning — `scripts/elo_calibration.py` does
that against real history. They pin the structural properties that the fix
depends on, so a later refactor cannot quietly restore either failure.
"""

from __future__ import annotations

from datetime import datetime

from ml.competitions import (
    INTERNATIONAL_COMPETITIONS,
    INTERNATIONAL_POOL,
    fit_pool,
    is_international,
)
from ml.elo.engine import EloEngine, MatchResult
from ml.elo.football import FOOTBALL_COMPETITION_K, INTERNATIONAL_ELO_K
from ml.prediction.predict import build_shared_fits


def _result(competition, home_score=1, away_score=0, home="A", away="B"):
    return MatchResult(
        home_team=home,
        away_team=away,
        home_score=home_score,
        away_score=away_score,
        match_date=datetime(2024, 6, 1),
        competition=competition,
    )


# --- the engine stays backward-compatible --------------------------------


def test_no_competition_k_reproduces_flat_k_exactly():
    """Every caller predating competition weighting must be unaffected."""
    flat = EloEngine(k_factor=20.0)
    weighted = EloEngine(k_factor=20.0, competition_k=FOOTBALL_COMPETITION_K)
    # A club competition is absent from the mapping, so both must agree.
    a = flat.apply_result(_result("English Premier League"))
    b = weighted.apply_result(_result("English Premier League"))
    assert a.home_rating_after == b.home_rating_after
    assert a.away_rating_after == b.away_rating_after


def test_a_match_with_no_competition_uses_the_default_k():
    """`competition=None` is what the pre-existing callers pass."""
    engine = EloEngine(k_factor=20.0, competition_k=FOOTBALL_COMPETITION_K)
    assert engine._k_for(None) == 20.0


def test_an_unlisted_competition_falls_back_to_the_default_k():
    engine = EloEngine(k_factor=20.0, competition_k=FOOTBALL_COMPETITION_K)
    assert engine._k_for("Some Cup We Do Not Model") == 20.0


def test_club_competitions_are_not_in_the_weighting_map():
    """The club pool is already well calibrated; this change must not touch it."""
    for competition in (
        "English Premier League",
        "Spanish La Liga",
        "German Bundesliga",
        "Major League Soccer",
    ):
        assert competition not in FOOTBALL_COMPETITION_K


# --- the weighting itself ------------------------------------------------


def test_a_world_cup_result_moves_a_rating_more_than_a_friendly():
    """The ordering is the whole point, and it is right on the merits:
    a friendly is played with rotated squads and nothing at stake."""
    world_cup = EloEngine(competition_k=FOOTBALL_COMPETITION_K)
    friendly = EloEngine(competition_k=FOOTBALL_COMPETITION_K)
    wc = world_cup.apply_result(_result("FIFA World Cup"))
    fr = friendly.apply_result(_result("International Friendlies"))
    assert wc.home_rating_after > fr.home_rating_after > 1500.0


def test_every_international_competition_moves_ratings_more_than_a_club_match():
    """The starved pool needs to converge faster than the well-fed one."""
    club = EloEngine(competition_k=FOOTBALL_COMPETITION_K).apply_result(
        _result("English Premier League")
    )
    club_gain = club.home_rating_after - 1500.0
    for competition in INTERNATIONAL_COMPETITIONS:
        engine = EloEngine(competition_k=FOOTBALL_COMPETITION_K)
        update = engine.apply_result(_result(competition))
        assert update.home_rating_after - 1500.0 > club_gain, competition


def test_the_k_map_covers_every_international_competition():
    """A competition added to one list and forgotten in the other would
    silently keep the club K — the failure this change exists to fix."""
    assert set(INTERNATIONAL_ELO_K) == set(INTERNATIONAL_COMPETITIONS)


def test_weighting_widens_the_gap_a_strong_side_can_open_up():
    """The mechanism behind the fix: ratings that can actually separate.

    Same fixtures, same results, only K differs. A pool that cannot open a
    gap cannot express a short-priced favourite, which is what left Croatia
    at 21% against Spain.
    """
    fixtures = [_result("UEFA Nations League", 2, 0, home="Strong", away="Weak") for _ in range(10)]
    flat, weighted = EloEngine(k_factor=20.0), EloEngine(
        k_factor=20.0, competition_k=FOOTBALL_COMPETITION_K
    )
    for engine in (flat, weighted):
        for fixture in fixtures:
            engine.apply_result(fixture)

    flat_gap = flat.get_rating("Strong") - flat.get_rating("Weak")
    weighted_gap = weighted.get_rating("Strong") - weighted.get_rating("Weak")
    assert weighted_gap > flat_gap * 2

    # And that gap has to translate into a materially shorter price.
    flat_home = flat.result_probabilities("Strong", "Weak")[0]
    weighted_home = weighted.result_probabilities("Strong", "Weak")[0]
    assert weighted_home > flat_home + 0.10


# --- Poisson fitting pools -----------------------------------------------


def test_every_international_competition_shares_one_fitting_pool():
    pools = {fit_pool(c) for c in INTERNATIONAL_COMPETITIONS}
    assert pools == {INTERNATIONAL_POOL}


def test_domestic_leagues_keep_their_own_pool():
    """Leagues genuinely differ in scoring rate and never share a team, so
    pooling them would throw away something real."""
    assert fit_pool("English Premier League") == "English Premier League"
    assert fit_pool("Spanish La Liga") == "Spanish La Liga"
    assert fit_pool("English Premier League") != fit_pool("Spanish La Liga")


def test_no_scoping_is_preserved():
    """`None` means "fit on the whole window" and some callers rely on it."""
    assert fit_pool(None) is None


def test_the_pool_key_cannot_collide_with_a_real_competition():
    assert not is_international(INTERNATIONAL_POOL)
    assert INTERNATIONAL_POOL not in INTERNATIONAL_COMPETITIONS


def _history(competition, home, away, home_score, away_score, n=12):
    return [
        {
            "home_team": home,
            "away_team": away,
            "home_score": home_score,
            "away_score": away_score,
            "competition": competition,
            "match_date": datetime(2024, 1, 1 + (i % 27)),
        }
        for i in range(n)
    ]


def test_two_international_competitions_get_the_same_fit():
    """Not merely equal — the *same* object, so a card with friendlies and
    Nations League fixtures on it fits once rather than twice."""
    history = _history("International Friendlies", "Spain", "Malta", 4, 0) + _history(
        "UEFA Nations League", "Spain", "Malta", 3, 0
    )
    fits = build_shared_fits(history, ["International Friendlies", "UEFA Nations League"])
    assert fits["International Friendlies"] is fits["UEFA Nations League"]


def test_an_international_fit_sees_matches_from_other_international_competitions():
    """The bug: a Nations League fit used 350 matches when 1797 were available
    for the same teams."""
    friendlies_only = _history("International Friendlies", "Spain", "Malta", 5, 0, n=20)
    fits = build_shared_fits(friendlies_only, ["UEFA Nations League"])
    poisson = fits["UEFA Nations League"].poisson
    # Fit on friendlies alone, the Nations League fit still knows Spain score
    # heavily against Malta. Under per-competition scoping it knew nothing.
    home, _draw, away = poisson.result_probabilities("Spain", "Malta")
    assert home > away


def test_a_league_fit_does_not_see_international_matches():
    """Pooling must not leak the other way: a Premier League fit that
    absorbed national-team results would be worse, not better."""
    mixed = _history("English Premier League", "Arsenal", "Luton", 2, 0) + _history(
        "International Friendlies", "Arsenal", "Luton", 9, 0
    )
    league = build_shared_fits(mixed, ["English Premier League"])["English Premier League"]
    intl = build_shared_fits(mixed, ["International Friendlies"])["International Friendlies"]
    assert league.poisson is not intl.poisson
    # The lopsided 9-0 friendly must not reach the league fit, so the league
    # fit has to be the less emphatic of the two about the same pairing.
    league_home = league.poisson.result_probabilities("Arsenal", "Luton")[0]
    intl_home = intl.poisson.result_probabilities("Arsenal", "Luton")[0]
    assert league_home < intl_home
