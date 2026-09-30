"""Parsing Football-Data.co.uk's "extra" country files.

This one source has already produced three silent data-loss bugs this
session — a whitespace-inconsistent League column, an int/string Season
dtype mismatch, and (here) two genuinely different Season shapes depending
on the country. None of them raised; each one just quietly kept less data
than it should have. These tests pin the parsing so a fourth one doesn't
ship the same way.
"""

from __future__ import annotations

from scripts.fetch_extra_league import _parse_season_value, _season_code

# --- reading a source Season value back to its starting year --------------


def test_a_bare_year_is_its_own_starting_year():
    assert _parse_season_value("2024") == "2024"
    assert _parse_season_value(2024) == "2024"


def test_a_split_year_seasons_starting_year_is_the_first_half():
    assert _parse_season_value("2019/2020") == "2019"


def test_an_unrecognisable_value_is_skipped_rather_than_guessed():
    """This source has carried stray non-year season labels historically —
    treating one as a match would silently pull the wrong rows into a
    requested season's file."""
    assert _parse_season_value("nan") is None
    assert _parse_season_value("") is None
    assert _parse_season_value("Summer") is None


# --- writing the season file's suffix --------------------------------------


def test_a_bare_year_source_writes_a_same_year_pair():
    """Argentina (since 2024), Brazil, Japan, MLS: a calendar-year season,
    correctly filed as e.g. 2024-2024, not the split-year 2024-2025 a plain
    two-digit-pair reading would otherwise suggest."""
    assert _season_code("2024", 2024) == "2424"


def test_a_split_year_source_writes_the_real_pair():
    """Mexico, Russia, Poland: an August-May season like the European
    leagues `download_data.py` covers, so it gets a real split code, not the
    same-year fallback."""
    assert _season_code("2024/2025", 2024) == "2425"


def test_the_season_code_follows_the_sources_own_shape_not_the_country():
    """Detected per row from the value itself, not hardcoded per country —
    the same script already serves both shapes today and a country's
    convention is not guaranteed to hold across its own history."""
    assert _season_code("2019", 2019) == "1919"
    assert _season_code("2019/2020", 2019) == "1920"
