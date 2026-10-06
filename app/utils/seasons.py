"""Season labels, in whatever shape a competition's history already uses.

A season's label is a key: standings, form and "the current season" all group
by it. The stored history has these shapes, because it was loaded from several
sources over time:

    "2024-2025"   split-year competitions
    "2525"        a calendar-year league written as a doubled two-digit year,
                  so the 2025 season is "2525"
    "2025-2025"   an older spelling of the same calendar-year season
    "2025"        a bare year (internationals, tournaments)

A fixture arriving from the live feed must land in the *same* season bucket as
the rest of its competition. Labelling it `str(season)` — "2026" — beside a
history that says "2026-2027" puts one competition's season in two places, and
every table built from it comes out wrong.

Raw Football-Data codes such as "2425" never appear as stored labels (they are
expanded to "2024-2025" on the way in), so a four-digit label is either a
doubled year or a bare year, and the halves tell them apart.
"""

from __future__ import annotations


def label_like(sample: str, year: int) -> str | None:
    """`year`'s season label, written the way `sample` is written.

    Returns None if `sample` is in no shape we recognise, so the caller can fall
    back rather than guess.
    """
    if len(sample) == 9 and sample[4] == "-" and sample[:4].isdigit() and sample[5:].isdigit():
        split = int(sample[5:]) == int(sample[:4]) + 1
        return f"{year}-{year + 1}" if split else f"{year}-{year}"
    if len(sample) == 4 and sample.isdigit():
        if sample[:2] == sample[2:]:  # "2525": a doubled two-digit year
            return f"{year % 100:02d}{year % 100:02d}"
        return str(year)  # "2022": a bare year
    return None


def fallback_label(year: int, first_kickoff_month: int) -> str:
    """For a competition with no history: football starting July or later is split-year."""
    return f"{year}-{year + 1}" if first_kickoff_month >= 7 else str(year)
