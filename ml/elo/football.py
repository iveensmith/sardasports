"""Football-specific Elo parameters.

`ml.elo.engine` is deliberately domain-agnostic — it takes a mapping and
applies it. This module holds the football values, so the engine stays
reusable and the numbers stay in one place with the reasoning attached.

Why internationals need their own K
-----------------------------------
A flat K assumes every rating pool plays enough matches to converge on its
true spread. Club football does: each of our domestic leagues has thousands
of completed matches, and the club pool reaches a standard deviation of
112.9 rating points.

The international pool does not. National teams play roughly ten matches a
year, our international history starts in 2022, and Spain — the shortest
price on any board we produce — had played 36 recorded matches. At K=20 that
is not enough to leave the 1500 starting point: the pool's standard
deviation was 43.8 with ninety percent of teams inside a 100-point band, so
*no* rating gap in it was large enough to express "this side is an 80%
favourite". The engine's most extreme international prediction was in the
60-70% bucket, and it only got there 25 times.

That showed up as measurable under-confidence, not just a wrong vibe.
Scored walk-forward on our own completed internationals:

    predicted favourite   actual         gap
        30-40%             38.3%        +0.2
        40-50%             47.3%        +2.8
        50-60%             67.4%       +14.0     <-- 14 points adrift

Clubs over the same harness sit within 2 points across the mass of the
distribution. So this was specific to one pool, and it was a data-volume
problem wearing a calibration problem's clothes.

Raising K for internationals is the standard remedy — eloratings.net has
weighted by competition for decades — and it is also right on the merits
rather than just convenient: a friendly is played with rotated squads and
nothing at stake, so it should move a rating less than a World Cup match.

The values below were chosen by sweeping schemes through
`scripts/elo_calibration.py` and keeping the one that calibrated best. It
takes the international pool's worst bucket gap from 14.0 to 3.8 points and
its rating spread from 43.8 to 92.8 — close to the club pool's 112.9 — while
leaving club ratings untouched (club log loss is identical to four decimal
places, because no club competition appears in this mapping).

A flat international K of 70 scored marginally better on log loss (1.0223 vs
1.0265) but worse on calibration (worst gap 4.5) and it is one number tuned
to one dataset. Decaying K — high while a side is new, settling as it builds
a record — was tried too and overshot, turning the under-confidence into
5-8 points of over-confidence.

This is a mitigation, not a cure. The real fix is more international
history; with three and a half years of it, these ratings are doing the best
that little data allows.
"""

from __future__ import annotations

from ml.competitions import INTERNATIONAL_COMPETITIONS

# One entry per international competition; the assertion below keeps this
# honest if a competition is ever added to `ml.competitions` and forgotten
# here, which would silently leave it on the club K of 20.
INTERNATIONAL_ELO_K: dict[str, float] = {
    # Highest stakes, strongest squads, most informative result.
    "FIFA World Cup": 90.0,
    # Continental finals: the same intensity over a shorter tournament.
    "UEFA European Championship": 80.0,
    "Copa America": 80.0,
    "Africa Cup of Nations": 80.0,
    # Competitive but lower-stakes fixtures — still full-strength squads.
    "UEFA Nations League": 70.0,
    "Africa Cup of Nations Qualifiers": 70.0,
    # Rotated squads, experimental line-ups, nothing at stake. Still well
    # above the club K of 20, because for many national teams friendlies are
    # most of the record we have.
    "International Friendlies": 45.0,
}

assert set(INTERNATIONAL_ELO_K) == set(INTERNATIONAL_COMPETITIONS), (
    "INTERNATIONAL_ELO_K and ml.competitions.INTERNATIONAL_COMPETITIONS disagree: "
    f"{set(INTERNATIONAL_COMPETITIONS) ^ set(INTERNATIONAL_ELO_K)}"
)

# Domestic league matches keep the default K. Listing nothing here is the
# point: a competition absent from the mapping above is unaffected, which is
# what makes this change provably club-neutral.
FOOTBALL_COMPETITION_K: dict[str, float] = dict(INTERNATIONAL_ELO_K)
