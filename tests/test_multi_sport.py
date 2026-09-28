"""Multi-sport correctness: sport isolation, neutral venues, basketball.

These cover the failure modes that only become possible once more than one
sport shares the `matches` table — each of which is silent rather than
loud, which is exactly why they're pinned here.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.models import Match, Team
from app.services.prediction_service import _all_completed_history
from ml.elo.engine import EloEngine, MatchResult
from ml.feature_engineering.basketball import (
    build_game_features,
    compute_rest_days,
    compute_team_pace,
)
from ml.feature_engineering.tennis import SurfaceElo, compute_player_form
from ml.prediction.predict_basketball import TOTAL_POINTS_LINES, predict_game
from ml.prediction.predict_tennis import TOTAL_GAMES_LINES
from ml.prediction.predict_tennis import predict_match as predict_tennis_match
from ml.training.common import KNOWN_COMPETITIONS
from scripts.clean_data import LEAGUE_NAMES, NEUTRAL_VENUE_COMPETITIONS, _season_label

# --------------------------------------------------------------------------
# Neutral venues
# --------------------------------------------------------------------------


def test_neutral_venue_removes_home_advantage_from_elo():
    """On neutral ground the two sides must be rated symmetrically.

    Tournament football (World Cup, Euros) has no real home team, so an
    identically-rated pair should be a genuine 50/50 — if the home-advantage
    offset leaked through, whichever side the fixture list happened to call
    "home" would be favoured for no reason.
    """
    engine = EloEngine(home_advantage=60.0)
    engine.set_rating("Brazil", 1600.0)
    engine.set_rating("Argentina", 1600.0)

    home, draw, away = engine.result_probabilities("Brazil", "Argentina", neutral_venue=True)
    assert home == pytest.approx(away, abs=1e-9)

    # And the normal (non-neutral) path must still favour the home side,
    # otherwise this test would also pass with home advantage removed
    # entirely — which would be a regression, not a fix.
    home_hv, _, away_hv = engine.result_probabilities("Brazil", "Argentina")
    assert home_hv > away_hv


def test_neutral_venue_changes_the_elo_update_not_just_the_prediction():
    """A draw on neutral ground shouldn't move ratings the way a home draw does.

    With home advantage the home side is *expected* to win, so a draw costs
    it rating points. On neutral ground an even match-up expects 0.5, so a
    draw between equals should leave both ratings untouched.
    """
    neutral = EloEngine(home_advantage=60.0)
    neutral.set_rating("A", 1500.0)
    neutral.set_rating("B", 1500.0)
    neutral.apply_result(MatchResult("A", "B", 1, 1, datetime(2024, 1, 1), neutral_venue=True))
    assert neutral.get_rating("A") == pytest.approx(1500.0)
    assert neutral.get_rating("B") == pytest.approx(1500.0)

    home = EloEngine(home_advantage=60.0)
    home.set_rating("A", 1500.0)
    home.set_rating("B", 1500.0)
    home.apply_result(MatchResult("A", "B", 1, 1, datetime(2024, 1, 1)))
    assert home.get_rating("A") < 1500.0  # drew a game it was favoured to win


def test_afcon_finals_are_neutral_but_its_qualifiers_are_not():
    """Two halves of the same competition need opposite venue flags.

    The AFCON finals are one host nation's tournament; the qualifiers that
    feed it are ordinary home-and-away fixtures. Flagging the whole
    competition family neutral would strip home advantage from 142 real home
    games, so this pins the distinction rather than leaving it to a name
    prefix match.
    """
    assert "Africa Cup of Nations" in NEUTRAL_VENUE_COMPETITIONS
    assert "Africa Cup of Nations Qualifiers" not in NEUTRAL_VENUE_COMPETITIONS

    # The same holds for the other home-and-away international competitions.
    assert "UEFA Nations League" not in NEUTRAL_VENUE_COMPETITIONS
    assert "International Friendlies" not in NEUTRAL_VENUE_COMPETITIONS
    # ...and every flagged competition must be one we actually ingest.
    assert NEUTRAL_VENUE_COMPETITIONS <= set(KNOWN_COMPETITIONS)


def test_every_ingested_competition_has_a_one_hot_column():
    """A competition missing from KNOWN_COMPETITIONS one-hot-encodes as all
    zeroes, silently losing its league-specific signal — so the ingestion
    mapping and the feature schema must stay in step."""
    for name in LEAGUE_NAMES.values():
        assert name in KNOWN_COMPETITIONS, f"{name} is ingested but has no one-hot column"


def test_tournament_season_code_is_not_read_as_a_split_season():
    """`2022` is a World Cup year; `2324` is the 2023-24 season."""
    assert _season_label("2324") == "2023-2024"
    assert _season_label("1920") == "2019-2020"
    assert _season_label("2022") == "2022"  # would be "2020-2022" without the fix


# --------------------------------------------------------------------------
# Sport isolation
# --------------------------------------------------------------------------


def test_prediction_history_is_scoped_to_one_sport(db_session):
    """Football predictions must never see basketball scorelines.

    Without the sport filter a 113-point basketball game would be fed to a
    Poisson goal model truncated at 8 — corrupting every football prediction
    silently rather than raising anything.
    """
    arsenal = Team(name="Arsenal", sport="football")
    chelsea = Team(name="Chelsea", sport="football")
    lakers = Team(name="Los Angeles Lakers", sport="basketball")
    celtics = Team(name="Boston Celtics", sport="basketball")
    db_session.add_all([arsenal, chelsea, lakers, celtics])
    db_session.flush()

    db_session.add_all(
        [
            Match(
                sport="football",
                match_date=datetime(2024, 1, 1),
                competition="English Premier League",
                season="2023-2024",
                home_team_id=arsenal.id,
                away_team_id=chelsea.id,
                home_score=2,
                away_score=1,
                status="completed",
            ),
            Match(
                sport="basketball",
                match_date=datetime(2024, 1, 2),
                competition="NBA",
                season="2023-2024",
                home_team_id=lakers.id,
                away_team_id=celtics.id,
                home_score=115,
                away_score=110,
                status="completed",
            ),
        ]
    )
    db_session.flush()

    football = _all_completed_history(db_session, datetime(2024, 6, 1), sport="football")
    basketball = _all_completed_history(db_session, datetime(2024, 6, 1), sport="basketball")

    assert [m["home_team"] for m in football] == ["Arsenal"]
    assert [m["home_team"] for m in basketball] == ["Los Angeles Lakers"]
    assert max(m["home_score"] for m in football) < 10


def test_same_name_in_two_sports_is_two_separate_competitors(db_session):
    """`teams.name` is unique per sport, not globally.

    Real collisions exist across sports, and merging them would silently
    fuse two competitors' rating histories.
    """
    db_session.add_all(
        [
            Team(name="Phoenix", sport="football"),
            Team(name="Phoenix", sport="basketball"),
        ]
    )
    db_session.flush()

    rows = db_session.query(Team).filter(Team.name == "Phoenix").all()
    assert {t.sport for t in rows} == {"football", "basketball"}


# --------------------------------------------------------------------------
# Basketball features
# --------------------------------------------------------------------------


def _game(home, away, hs, as_, date):
    return {
        "home_team": home,
        "away_team": away,
        "home_score": hs,
        "away_score": as_,
        "match_date": date,
    }


def test_basketball_pace_uses_only_prior_games():
    """The leakage rule holds here exactly as it does for football."""
    history = [
        _game("Lakers", "Celtics", 100, 90, datetime(2024, 1, 1)),
        _game("Lakers", "Heat", 120, 110, datetime(2024, 1, 5)),
        # Must be invisible to a lookup dated 2024-01-10:
        _game("Lakers", "Bulls", 999, 0, datetime(2024, 1, 20)),
    ]
    pace = compute_team_pace("Lakers", history, datetime(2024, 1, 10))
    assert pace.games == 2
    assert pace.avg_points_scored == pytest.approx(110.0)
    assert pace.win_rate == pytest.approx(1.0)


def test_rest_days_and_back_to_back():
    """Back-to-backs are a real basketball effect with no football analogue."""
    history = [_game("Lakers", "Celtics", 100, 90, datetime(2024, 1, 9))]
    features = build_game_features(
        home_team="Lakers",
        away_team="Suns",
        match_date=datetime(2024, 1, 10),
        history=history,
        elo_home=1500.0,
        elo_away=1500.0,
    )
    assert features["home_rest_days"] == pytest.approx(1.0)
    assert features["home_back_to_back"] == 1.0
    # Suns have no prior game at all: maximally rested, not zero-rested.
    assert features["away_back_to_back"] == 0.0


def test_rest_days_capped_for_a_team_with_no_history():
    """No prior game means "season opener", not "played infinitely long ago"."""
    assert compute_rest_days("Nobody", [], datetime(2024, 1, 10)) == pytest.approx(14.0)


# --------------------------------------------------------------------------
# Basketball prediction
# --------------------------------------------------------------------------


def _basketball_history():
    games, date = [], datetime(2024, 1, 1)
    for i in range(12):
        # Lakers are consistently the stronger side.
        games.append(_game("Lakers", "Celtics", 115, 105, date.replace(day=1 + i)))
    return games


def test_basketball_prediction_is_two_way_and_has_no_draw():
    """Home and away must sum to 100 on their own — there is no draw."""
    result = predict_game(
        home_team="Lakers",
        away_team="Celtics",
        match_date=datetime(2024, 2, 1),
        history=_basketball_history(),
        elo_home=1600.0,
        elo_away=1500.0,
    )
    assert result.home_win + result.away_win == pytest.approx(100.0, abs=0.2)
    assert not hasattr(result, "draw")
    assert result.home_win > result.away_win


def test_untrained_total_lines_report_unavailable_rather_than_guessing():
    """There is no Poisson fallback for basketball totals.

    With no trained model a line is genuinely unknown, so it must say so
    instead of deriving a number from expected_total — the same honesty rule
    the football markets follow for a competition with no data.
    """
    result = predict_game(
        home_team="Lakers",
        away_team="Celtics",
        match_date=datetime(2024, 2, 1),
        history=_basketball_history(),
        elo_home=1600.0,
        elo_away=1500.0,
        total_models=None,
    )
    assert [m.line for m in result.total_points_markets] == TOTAL_POINTS_LINES
    assert all(m.prob_over is None and not m.model_used for m in result.total_points_markets)
    # The expected total is still a real number computed from real form —
    # it just isn't passed off as a market probability.
    assert result.expected_total_points > 0


def test_expected_points_come_from_both_sides_of_the_matchup():
    """Expected points blend what a team scores with what its opponent concedes."""
    result = predict_game(
        home_team="Lakers",
        away_team="Celtics",
        match_date=datetime(2024, 2, 1),
        history=_basketball_history(),
        elo_home=1500.0,
        elo_away=1500.0,
    )
    # Lakers scored 115 and Celtics conceded 115 in every prior game.
    assert result.expected_points_home == pytest.approx(115.0)
    assert result.expected_points_away == pytest.approx(105.0)


# --------------------------------------------------------------------------
# Tennis
# --------------------------------------------------------------------------


def _tennis_match(home, away, hs, as_, date, surface="Hard", hg=12, ag=8):
    return {
        "home_team": home,
        "away_team": away,
        "home_score": hs,  # sets
        "away_score": as_,
        "home_games": hg,
        "away_games": ag,
        "surface": surface,
        "match_date": date,
    }


def test_tennis_ratings_are_kept_per_surface():
    """A clay record must not inflate a player's grass rating.

    This is the single most important modelling claim in the tennis path:
    surface-specific skill is real, so one rating per player would discard
    it. A player who only ever wins on clay should be rated highly on clay
    and left at the default on grass.
    """
    elo = SurfaceElo()
    for _ in range(10):
        elo.apply("ClayCourter", "Rival", "Clay")

    assert elo.get("ClayCourter", "Clay") > elo.initial_rating
    assert elo.get("ClayCourter", "Grass") == elo.initial_rating
    # The overall pool still reflects the wins.
    assert elo.get("ClayCourter") > elo.initial_rating


def test_tennis_surface_form_ignores_other_surfaces():
    history = [
        _tennis_match("A", "B", 2, 0, datetime(2024, 1, 1), surface="Clay"),
        _tennis_match("A", "C", 0, 2, datetime(2024, 1, 5), surface="Grass"),
    ]
    clay = compute_player_form("A", history, datetime(2024, 2, 1), surface="Clay")
    grass = compute_player_form("A", history, datetime(2024, 2, 1), surface="Grass")
    assert clay.matches == 1 and clay.win_rate == pytest.approx(1.0)
    assert grass.matches == 1 and grass.win_rate == pytest.approx(0.0)


def test_unseen_player_form_is_a_neutral_prior_not_zero():
    """0.5, not 0.0 — "never played" is not "lost everything"."""
    assert compute_player_form("Nobody", [], datetime(2024, 1, 1)).win_rate == pytest.approx(0.5)


def test_tennis_prediction_is_two_way_with_monotonic_total_lines():
    history = [_tennis_match("Strong", "Weak", 2, 0, datetime(2024, 1, 1 + i)) for i in range(10)]
    result = predict_tennis_match(
        home_player="Strong",
        away_player="Weak",
        match_date=datetime(2024, 3, 1),
        surface="Hard",
        best_of=3,
        history=history,
    )
    assert result.home_win + result.away_win == pytest.approx(100.0, abs=0.2)
    assert result.home_win > result.away_win  # Strong has won every prior meeting
    assert [m.line for m in result.total_games_markets] == TOTAL_GAMES_LINES
    # No trained models passed in: totals are genuinely unavailable, not guessed.
    assert all(m.prob_over is None and not m.model_used for m in result.total_games_markets)


def test_tennis_slots_carry_no_home_advantage():
    """The home/away slots are a de-leaking hash, not a venue.

    Two players with identical histories must come out at 50/50 — if any
    home-advantage term leaked in, the prediction would be modelling which
    side the ingest hash happened to put first.
    """
    history = [
        _tennis_match("P1", "Other", 2, 0, datetime(2024, 1, 1)),
        _tennis_match("P2", "Other", 2, 0, datetime(2024, 1, 2)),
        _tennis_match("Other", "P1", 2, 0, datetime(2024, 1, 3)),
        _tennis_match("Other", "P2", 2, 0, datetime(2024, 1, 4)),
    ]
    result = predict_tennis_match(
        home_player="P1",
        away_player="P2",
        match_date=datetime(2024, 3, 1),
        surface="Hard",
        best_of=3,
        history=history,
    )
    assert result.home_win == pytest.approx(50.0, abs=0.5)
