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
