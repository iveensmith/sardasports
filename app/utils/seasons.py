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


def european_season_code(today) -> str:
    """The Football-Data season code for the season running on `today`.

    A season starts in the summer, so July onwards belongs to the season that
    began that year ("2627" in October 2026) and January to June to the one that
    began the year before ("2526" in March 2027).
    """
    start = today.year if today.month >= 7 else today.year - 1
    return f"{start % 100:02d}{(start + 1) % 100:02d}"


def season_codes_to_refresh(today) -> list[str]:
    """The season codes a daily refresh should pull.

    Always the current one. From July to September the previous season is pulled
    too: its last results and any corrections land in the weeks after it ends,
    and a refresh that had already moved on would never collect them.
    """
    current = european_season_code(today)
    if 7 <= today.month <= 9:
        previous = european_season_code(today.replace(year=today.year - 1))
        return [current, previous]
    return [current]


def season_start_year(label: str) -> int | None:
    """The year a stored season label begins in, whatever shape it is written in.

    "2024-2025" -> 2024; the old calendar-year spelling "2025-2025" -> 2025; a
    doubled two-digit year "2525" -> 2025; a bare year "2022" -> 2022. None for
    anything else. Matching a label against a year with `startswith` cannot work:
    "2424" is the 2024 season and does not start with "2024".
    """
    if len(label) == 9 and label[4] == "-" and label[:4].isdigit() and label[5:].isdigit():
        return int(label[:4])
    if len(label) == 4 and label.isdigit():
        if label[:2] == label[2:]:
            return 2000 + int(label[:2])
        return int(label)
    return None
