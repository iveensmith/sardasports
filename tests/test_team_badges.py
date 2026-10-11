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

from ml.team_badges import NATIONAL_TEAM_CODES, badge_dict, badge_for, crest_url

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


def test_smaller_national_associations_get_flags_too():
    """These four showed up as monograms on a real international-break board
    (Eritrea, Seychelles, Sri Lanka and New Caledonia all had live fixtures
    that day) purely because the dictionary only covered the confederations'
    more prominent members — not because a monogram was the right call for
    them. A national side lacking a well-known league is still a national
    side."""
    assert badge_for("Eritrea").code == "er"
    assert badge_for("Seychelles").code == "sc"
    assert badge_for("Sri Lanka").code == "lk"
    assert badge_for("New Caledonia").code == "nc"


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


def test_the_national_teams_actually_on_our_board_are_covered():
    """A coverage check against the real database rather than a fixture.

    Skips when there is no database or no scheduled national-team fixtures: this runs
    against the developer's ingested data and is a warning about the flag catalogue
    drifting, not a unit test of the lookup.

    It looks at national-team fixtures only. The catalogue maps *countries* to flags;
    clubs have no licensed crest and are shown as initials by design, so counting them
    would make the test pass or fail on whether the week's fixtures happen to include
    internationals, which says nothing about the catalogue.
    """
    from ml.competitions import INTERNATIONAL_COMPETITIONS

    db = Path(__file__).resolve().parent.parent / "data" / "uniquepredict.db"
    if not db.exists():
        pytest.skip("no ingested database in this environment")

    competitions = sorted(INTERNATIONAL_COMPETITIONS)
    marks = ",".join("?" * len(competitions))
    connection = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        names = [
            row[0]
            for row in connection.execute(
                f"""SELECT DISTINCT t.name FROM teams t
                   WHERE t.id IN (
                     SELECT home_team_id FROM matches
                       WHERE status='scheduled' AND competition IN ({marks})
                     UNION
                     SELECT away_team_id FROM matches
                       WHERE status='scheduled' AND competition IN ({marks}))""",
                competitions + competitions,
            )
        ]
    finally:
        connection.close()

    if not names:
        pytest.skip("no scheduled national-team fixtures ingested")

    unresolved = [n for n in names if badge_for(n).kind == "monogram"]
    # A few national sides may legitimately fall through; a board that is mostly
    # unresolved means the catalogue has drifted from what the feed is sending.
    assert len(unresolved) / len(names) < 0.5, f"mostly unresolved: {unresolved[:10]}"


# --- club crests ----------------------------------------------------------


def test_a_club_with_a_provider_id_gets_its_crest_and_keeps_its_initials():
    badge = badge_for("Manchester City", 50)
    assert badge.kind == "crest"
    assert badge.logo == "https://media.api-sports.io/football/teams/50.png"
    # The monogram travels with it, so a crest that fails to load falls back to it.
    assert badge.initials == "MC"


def test_a_club_without_an_id_stays_a_monogram_and_never_a_guessed_crest():
    badge = badge_for("Manchester City", None)
    assert badge.kind == "monogram" and badge.logo is None


def test_a_national_side_keeps_its_flag_even_if_it_has_an_id():
    badge = badge_for("Spain", 9)
    assert badge.kind == "flag" and badge.code == "es" and badge.logo is None


@pytest.mark.parametrize("value", [None, 0, -3])
def test_no_crest_is_built_from_a_missing_or_nonsense_id(value):
    assert crest_url(value) is None
    assert badge_for("Arsenal", value).kind == "monogram"


def test_the_payload_carries_the_logo_field_for_every_kind():
    assert badge_dict("Spain")["logo"] is None
    assert badge_dict("Arsenal")["logo"] is None
    assert badge_dict("Arsenal", 42)["logo"].endswith("/42.png")
