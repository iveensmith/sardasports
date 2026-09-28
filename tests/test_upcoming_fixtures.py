"""Upcoming-fixture ingestion and team-identity repair.

These guard the data layer the product pages read from. Every failure mode
below produces a *plausible-looking* prediction rather than an error, which
is why they are pinned rather than left to review.
"""

from __future__ import annotations

from app.utils.team_names import fold_team_key
from ml.training.common import KNOWN_COMPETITIONS
from scripts.fetch_upcoming_fixtures import (
    EXCLUDED_TEAM_PATTERN,
    LEAGUE_ID_TO_COMPETITION,
    rows_from_fixtures,
)
from scripts.repair_team_names import demojibake


def _fixture(home, away, league_id=10, status="NS", fixture_id=1):
    return {
        "fixture": {
            "id": fixture_id,
            "date": "2026-09-28T16:00:00+00:00",
            "status": {"short": status},
        },
        "league": {"id": league_id, "season": 2026},
        "teams": {"home": {"name": home}, "away": {"name": away}},
    }


def test_every_mapped_league_is_a_competition_the_engine_models():
    """The allowlist must land on a competition that has a one-hot column.

    A competition outside KNOWN_COMPETITIONS encodes as all-zero, so a
    fixture ingested under one would be predicted with no league signal at
    all — the failure is silent, which is why it's asserted here.
    """
    for league_id, competition in LEAGUE_ID_TO_COMPETITION.items():
        assert competition in KNOWN_COMPETITIONS, f"league {league_id} -> {competition!r}"


def test_only_upcoming_fixtures_are_ingested():
    """Finished and in-play fixtures belong to the historical path."""
    items = [
        _fixture("Georgia", "Ukraine", status="NS", fixture_id=1),
        _fixture("Latvia", "Cyprus", status="FT", fixture_id=2),
        _fixture("Malta", "Andorra", status="1H", fixture_id=3),
    ]
    rows, _ = rows_from_fixtures(items)
    assert [r["external_id"] for r in rows] == ["apif-1"]


def test_unmodelled_competitions_are_skipped_and_counted():
    """A busy board of leagues we can't predict is worse than a short one."""
    items = [
        _fixture("Georgia", "Ukraine", league_id=5, fixture_id=1),  # Nations League
        _fixture("Some FC", "Other FC", league_id=99999, fixture_id=2),  # unmodelled
    ]
    rows, skipped = rows_from_fixtures(items)
    assert len(rows) == 1 and skipped == 1


def test_youth_and_reserve_sides_are_excluded():
    """U17/U19/B/II sides are separate entities with no senior history.

    Included, they'd arrive with two default 1500 ratings and render a
    coin flip as a confident-looking prediction.
    """
    for name in ("England U17", "Serbia U18", "USA U19", "Real Madrid B", "Bayern Munich II"):
        assert EXCLUDED_TEAM_PATTERN.search(name), name


def test_real_clubs_are_not_caught_by_the_youth_filter():
    """Word boundaries matter: a bare `B` alternative would match everything."""
    for name in ("Barcelona", "Brighton", "West Brom", "Bournemouth", "Italy", "Benfica"):
        assert not EXCLUDED_TEAM_PATTERN.search(name), name


def test_youth_fixtures_never_reach_the_rows():
    rows, skipped = rows_from_fixtures([_fixture("England U17", "Israel U17")])
    assert rows == [] and skipped == 1


def test_scheduled_fixtures_carry_no_score():
    """A fixture with a score would enter training and Elo as a real result."""
    rows, _ = rows_from_fixtures([_fixture("Georgia", "Ukraine", league_id=5)])
    assert "home_score" not in rows[0] and "away_score" not in rows[0]


def test_neutral_venue_is_set_for_tournaments_only():
    wc, _ = rows_from_fixtures([_fixture("Brazil", "Croatia", league_id=1, fixture_id=1)])
    unl, _ = rows_from_fixtures([_fixture("Georgia", "Ukraine", league_id=5, fixture_id=2)])
    assert wc[0]["neutral_venue"] is True  # World Cup: one host
    assert unl[0]["neutral_venue"] is False  # Nations League: home-and-away


# --- team identity --------------------------------------------------------


def test_fold_key_matches_accent_and_punctuation_variants():
    """Sources disagree on diacritics for the same club/player.

    Two rows for one competitor split its history and leave the newer one
    with no Elo, so a real fixture gets a default-rated coin flip.
    """
    assert fold_team_key("Castellón") == fold_team_key("Castellon")
    assert fold_team_key("Türkiye") == fold_team_key("Turkiye")
    assert fold_team_key("andorra") == fold_team_key("Andorra")
    assert fold_team_key("O'Connell C.") == fold_team_key("O Connell C.")
    assert fold_team_key("Struff J-L.") == fold_team_key("Struff J.L.")


def test_fold_key_keeps_genuinely_different_competitors_apart():
    """Folding must not over-merge — these are different people/clubs."""
    assert fold_team_key("Zayed M.S.") != fold_team_key("Zayid M.S.")
    assert fold_team_key("Pous-T. L.") != fold_team_key("Pous-Tio L.")
    assert fold_team_key("Manchester United") != fold_team_key("Manchester City")


def test_demojibake_recovers_utf8_read_as_latin1():
    """clean_data used to read UTF-8 CSVs as latin-1, storing "TÃ¼rkiye"."""
    assert demojibake("TÃ¼rkiye") == "Türkiye"
    assert demojibake("CuraÃ§ao") == "Curaçao"
    assert demojibake("PreuÃ\x9fen MÃ¼nster") == "Preußen Münster"


def test_demojibake_leaves_clean_names_alone():
    """Idempotent: a correct name must not be mangled by a second pass."""
    for name in ("Türkiye", "Arsenal", "Bayern München", "Curaçao"):
        assert demojibake(name) is None
