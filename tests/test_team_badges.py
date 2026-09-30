"""What shows beside a team's name.

The failure mode worth guarding is not a missing badge — it is a *wrong* one.
A flag beside a fixture is a factual claim about who is playing, and
resolving an unknown name to the closest-looking country would put that error
on the board silently, on exactly the teams nobody double-checks.

So the rule is: resolve by exact lookup or fall back to initials. Never by
resemblance.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from ml.team_badges import NATIONAL_TEAM_CODES, badge_for

# --- national sides -------------------------------------------------------


@pytest.mark.parametrize(
    "name,code",
    [
        ("Brazil", "br"),
        ("Spain", "es"),
        ("Morocco", "ma"),
        ("Japan", "jp"),
        ("Congo DR", "cd"),
        ("Congo", "cg"),
    ],
)
def test_a_national_side_gets_its_flag(name, code):
    badge = badge_for(name)
    assert badge.kind == "flag"
    assert badge.code == code


def test_the_uk_nations_are_separate_flags():
    """Football treats them as four nations and the flag sets follow, so
    collapsing them to "gb" would put the union flag on a Scotland fixture."""
    assert badge_for("England").code == "gb-eng"
    assert badge_for("Scotland").code == "gb-sct"
    assert badge_for("Wales").code == "gb-wls"
    assert badge_for("Northern Ireland").code == "gb-nir"


def test_the_feeds_own_spelling_is_what_resolves():
    """Our fixture feed writes these, so these are what have to match — not
    the country's formal name."""
    assert badge_for("Türkiye").code == "tr"
    assert badge_for("Ivory Coast").code == "ci"
    assert badge_for("Czechia").code == "cz"
    assert badge_for("FYR Macedonia").code == "mk"


def test_youth_and_womens_sides_inherit_the_senior_flag():
    """ "Croatia U18" is still Croatia. A monogram beside it while the senior
    side showed a flag would look broken rather than precise."""
    for name in ("Croatia U18", "Switzerland U21", "Brazil W", "Spain U19"):
        assert badge_for(name).kind == "flag", name
    assert badge_for("Croatia U18").code == badge_for("Croatia").code


# --- clubs and the unknown ------------------------------------------------


def test_a_club_gets_initials_rather_than_a_flag():
    badge = badge_for("Leganes")
    assert badge.kind == "monogram"
    assert badge.code is None
    assert badge.initials == "LE"


def test_initials_skip_the_words_that_carry_no_identity():
    """ "Al-Hilal Saudi FC" is AH, not AS — "FC" and friends are structural."""
    assert badge_for("Al-Hilal Saudi FC").initials == "AH"
    assert badge_for("Real Madrid").initials == "RM"
    assert badge_for("FC Barcelona").initials == "BA"


def test_a_single_word_club_uses_two_letters():
    """One letter in a disc reads as a bullet, not a badge."""
    assert badge_for("Barcelona").initials == "BA"


def test_an_unrecognised_name_is_never_resolved_by_resemblance():
    """The bug this exists to prevent. A wrong flag is a factual error about
    who is playing, and worse than no flag at all."""
    for name in ("Northern Sporting Club", "Austria Wien", "Deportivo Brazil"):
        assert badge_for(name).kind == "monogram", name


def test_a_missing_name_degrades_rather_than_raises():
    for name in (None, "", "   "):
        badge = badge_for(name)
        assert badge.kind == "monogram"
        assert badge.initials


# --- the table itself -----------------------------------------------------


def test_every_code_is_lowercase_and_plausible():
    """Flag URLs are built from these directly, so an uppercase or stray
    entry is a broken image rather than a caught error."""
    for name, code in NATIONAL_TEAM_CODES.items():
        assert code == code.lower(), name
        assert len(code) in (2, 6), name  # "br", or "gb-eng"
        if len(code) == 6:
            assert code.startswith("gb-"), name


def test_no_two_nations_share_a_code_by_accident():
    """Aliases are deliberate ("Turkey"/"Türkiye", "USA"/"United States");
    anything else sharing a code is a copy-paste error."""
    deliberate = {"tr", "us"}
    seen: dict[str, str] = {}
    for name, code in NATIONAL_TEAM_CODES.items():
        if code in seen and code not in deliberate:
            pytest.fail(f"{name} and {seen[code]} both map to {code!r}")
        seen[code] = name


def test_the_teams_actually_on_our_board_are_covered():
    """A coverage check against the real database rather than a fixture.

    Skips when there is no database — this runs against the developer's
    ingested data and is a warning about the catalogue drifting, not a unit
    test of the lookup.
    """
    db = Path(__file__).resolve().parent.parent / "data" / "uniquepredict.db"
    if not db.exists():
        pytest.skip("no ingested database in this environment")

    connection = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        names = [row[0] for row in connection.execute("""SELECT DISTINCT t.name FROM teams t
                   WHERE t.id IN (
                     SELECT home_team_id FROM matches WHERE status='scheduled'
                     UNION
                     SELECT away_team_id FROM matches WHERE status='scheduled')""")]
    finally:
        connection.close()

    if not names:
        pytest.skip("no scheduled fixtures ingested")

    unresolved = [n for n in names if badge_for(n).kind == "monogram"]
    # Clubs legitimately fall through; a board that is mostly unresolved
    # means the catalogue has drifted from what the feed is sending.
    assert len(unresolved) / len(names) < 0.5, f"mostly unresolved: {unresolved[:10]}"
