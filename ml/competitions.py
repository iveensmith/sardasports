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

# National-team competitions. Keep in sync with the international block of
# `ml.training.common.KNOWN_COMPETITIONS`.
INTERNATIONAL_COMPETITIONS: frozenset[str] = frozenset(
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

# The bucket key every international competition shares. Chosen to be
# impossible as a real competition name so it can never collide with one.
INTERNATIONAL_POOL = "__international__"


def is_international(competition: str | None) -> bool:
    return competition in INTERNATIONAL_COMPETITIONS


def fit_pool(competition: str | None) -> str | None:
    """The key to group `competition` under when fitting a Poisson model.

    Domestic leagues map to themselves. Every international competition maps
    to one shared pool. `None` — meaning "don't scope at all" — is preserved,
    since callers use it to fit on the whole history window.
    """
    if competition is None:
        return None
    return INTERNATIONAL_POOL if competition in INTERNATIONAL_COMPETITIONS else competition
