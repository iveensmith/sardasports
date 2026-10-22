"""Which competitions belong together, and why that differs by model.

Two different groupings live here, because "same competition" is the wrong
question to ask twice.

Per-competition fitting is right for domestic leagues. The Bundesliga and
Serie A genuinely differ in goals per game and home advantage, they never
share a team, and each has thousands of matches — so fitting them separately
costs nothing and captures something real.

It is wrong for international football, for the opposite reasons. A national
team is the *same* team in the Nations League, a friendly and a World Cup, so
splitting its record across them throws away most of what we know about it.
And the splits are tiny: at the time of writing our completed international
history is 1106 friendlies, 350 Nations League, 142 AFCON qualifiers, 64
World Cup, 52 AFCON, 51 Euros and 32 Copa America matches. Spread over 356
competitors, a per-competition Poisson fit sees roughly ten matches per team
and produces attack/defence strengths that are mostly noise — then states
them with enormous confidence.

Measured on a chronological split (train before 2024-06-01, test after), the
per-competition international fit was badly over-confident:

    predicted favourite   actual         gap
        70-80%             46.2%       -29.0
        80-90%             58.1%       -27.2
        90-100%            62.5%       -33.0

It also produced no fit at all for 83 of 404 test matches, because their
competition had no training rows yet. Pooling every international competition
into one fit took log loss from 1.2407 to 0.9823 and the skipped matches to
zero.

So: pool internationals, keep leagues separate. The cost of pooling is that a
World Cup match and a friendly contribute equally to a team's attack
strength, which is a real approximation — but a mild one next to fitting ten
matches and calling it 95%.

Note that this grouping is for *fitting* only. The one-hot competition
feature the trained models use stays per-competition (see
`ml.training.common.one_hot_competition`), so a model can still learn that
tournament football is lower-scoring than a friendly.
"""

from __future__ import annotations

from ml.api_competitions import BY_ID, enabled_national, family_of

# The national-team competitions the engine launched with. Keep in sync with the
# international block of `ml.training.common.KNOWN_COMPETITIONS`.
_BASE_INTERNATIONAL_COMPETITIONS: frozenset[str] = frozenset(
    {
        "FIFA World Cup",
        "UEFA European Championship",
        "UEFA Nations League",
        "Copa America",
        "Africa Cup of Nations",
        "Africa Cup of Nations Qualifiers",
        "International Friendlies",
    }
)

# Plus every national-team competition enabled in the API registry, so they join
# the one shared pool and get their Elo K. Empty until something is enabled.
INTERNATIONAL_COMPETITIONS: frozenset[str] = _BASE_INTERNATIONAL_COMPETITIONS | frozenset(
    c.name for c in enabled_national()
)

# The bucket key every international competition shares. Chosen to be
# impossible as a real competition name so it can never collide with one.
INTERNATIONAL_POOL = "__international__"

# The UEFA club competitions (Champions, Europa and Conference League), by registry id. They are
# clubs, not national teams, but they have the same problem international football has: clubs
# from dozens of leagues meet a few times a season, so a fit per competition sees a handful of
# matches per club against unrelated opponents. They fit as one pool, since a club moves between
# the three (a Champions League qualifier drops into the Europa League) and that is what joins
# the graph of who has played whom.
UEFA_CLUB_COMPETITIONS: frozenset[str] = frozenset(BY_ID[i].name for i in (2, 3, 848))
UEFA_CLUB_POOL = "__uefa_clubs__"

# Shrinkage, in matches, applied to a pool's team strengths (`DixonColesModel.prior_matches`).
# A pool not listed here is fitted plainly. Measured walk-forward on the 2,028 UEFA club matches
# played between September 2024 and October 2026, each month fitted on everything before it:
#
#                                   1X2 log loss   Over 2.5 log loss   xG under 0.4 or over 3.0
#   fit per competition, no prior       1.0791          0.7895                10.9%
#   one pool, no prior                  0.9982          0.7275                 6.5%
#   one pool, prior of 2 matches        0.9714          0.6988                 1.1%
#   one pool, prior of 8 matches        0.9876          0.6873                 0.1%
#   every team average (a constant)     1.0413          0.6875                 0.0%
#
# The first row is worse than assuming every team is average, and put expected goals of 4 to 5
# on a side in some fixtures. 8 is where Over 2.5 stops being worse than a constant, and 1X2
# keeps most of the gain; the blend with Elo and the trained model sharpens 1X2 further.
POOL_PRIOR_MATCHES: dict[str, float] = {UEFA_CLUB_POOL: 8.0}


def is_international(competition: str | None) -> bool:
    return competition in INTERNATIONAL_COMPETITIONS


def fit_pool(competition: str | None) -> str | None:
    """The key to group `competition` under when fitting a Poisson model.

    Domestic leagues map to their family, which is themselves unless they are
    one group of a regional tier. Every international competition maps to one
    shared pool. `None` — meaning "don't scope at all" — is preserved,
    since callers use it to fit on the whole history window.
    """
    if competition is None:
        return None
    if competition in INTERNATIONAL_COMPETITIONS:
        return INTERNATIONAL_POOL
    if competition in UEFA_CLUB_COMPETITIONS:
        return UEFA_CLUB_POOL
    # A regional group fits with its whole tier: eighteen Tercera RFEF groups
    # never share a team, play the same kind of football, and are far too small
    # alone. Every other domestic competition is its own family.
    return family_of(competition)
