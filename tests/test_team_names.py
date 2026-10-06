"""Tests for app.utils.team_names.normalize_team_name."""

from __future__ import annotations

import math

from app.utils.team_names import normalize_team_name


def test_normalizes_known_alias():
    assert normalize_team_name("man utd") == "Manchester United"


def test_collapses_whitespace():
    assert normalize_team_name("  Aston   Villa ") == "Aston Villa"


def test_passes_through_unknown_name_unchanged():
    assert normalize_team_name("Girona") == "Girona"


def test_non_string_input_returns_empty_string_not_raise():
    """Regression test: a pandas NaN float from a source CSV with a blank
    team-name field used to crash the whole cleaning pipeline (found when
    ingesting a Ligue 1 season file with such a row) — must degrade to an
    empty string instead."""
    assert normalize_team_name(math.nan) == ""
    assert normalize_team_name(None) == ""  # type: ignore[arg-type]


def test_a_cp1252_apostrophe_read_as_latin1_becomes_an_apostrophe():
    """Football-Data files are cp1252; read as latin-1, the curly apostrophe in
    "King's Lynn" arrives as U+0092 and would otherwise become a team row
    named with a control character."""
    assert normalize_team_name("King\x92s Lynn") == "King's Lynn"


def test_the_other_cp1252_punctuation_is_mapped_too():
    assert normalize_team_name("A\x91B\x92") == "A'B'"
    assert normalize_team_name("A\x93B\x94") == 'A"B"'
    assert normalize_team_name("A\x96B\x97C") == "A-B-C"


def test_other_control_characters_are_left_alone_not_guessed_at():
    """Only unambiguous punctuation is repaired. "\x9f" is a letter's byte in
    some encodings, and rewriting it would change names — and the ids built
    from them — that are already stored."""
    assert normalize_team_name("Preu\x9fen") == "Preu\x9fen"
