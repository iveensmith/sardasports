"""The basketball and tennis pages' data: what is on record, how fresh it is, who is
rated highest, and how each model measures against its baseline.

The point of these tests is honesty. The pages state the date the data runs to and
list no upcoming fixtures when there are none, so an empty sport has to say
"nothing" rather than invent something, a model is only reported with the baseline
it recorded, and ratings come from the Elo history (the `teams.elo_rating` column is
a default most competitors never leave).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.models import EloHistory, Match, ModelVersion, Team
from app.services import sport_service


@pytest.fixture(autouse=True)
def _fresh_cache():
    sport_service.clear_cache()
    yield
    sport_service.clear_cache()


@pytest.fixture(autouse=True)
def _no_models(monkeypatch):
    """Pricing needs trained models; these tests are about the page, not the model."""

    def fake(db, matches):
        return [{"home_win": 70.0, "away_win": 30.0} for _ in matches]

    monkeypatch.setattr(sport_service, "predict_for_matches", fake)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _players(db_session, sport, *names, league="ATP"):
    teams = [Team(name=n, sport=sport, league=league, elo_rating=1500) for n in names]
    db_session.add_all(teams)
    db_session.flush()
    return teams


def _match(db_session, sport, home, away, when, score, *, competition="ATP", surface=None):
    played = score is not None
    match = Match(
        match_date=when,
        competition=competition,
        season="2025",
        sport=sport,
        home_team_id=home.id,
        away_team_id=away.id,
        status="completed" if played else "scheduled",
        home_score=score[0] if played else None,
        away_score=score[1] if played else None,
        surface=surface,
    )
    db_session.add(match)
    db_session.flush()
    return match


def _rate(db_session, team, match, rating):
    db_session.add(
        EloHistory(
            team_id=team.id,
            match_id=match.id,
            match_date=match.match_date,
            rating_before=1500.0,
            rating_after=rating,
        )
    )


def test_an_unknown_sport_is_a_404_and_football_is_not_served_here(client):
    assert client.get("/sports/curling").status_code == 404
    # Football has its own pages and a stored record; this endpoint is not for it.
    assert client.get("/sports/football").status_code == 404


def test_the_summary_lists_every_sport_and_says_when_nothing_is_scheduled(client, db_session):
    a, b = _players(db_session, "tennis", "Sinner J.", "Alcaraz C.")
    when = _now() - timedelta(days=300)
    _match(db_session, "tennis", a, b, when, (2, 0))
    db_session.commit()

    sports = {s["sport"]: s for s in client.get("/sports").json()["sports"]}

    assert set(sports) == {"football", "basketball", "tennis"}
    assert sports["tennis"]["matches_on_record"] == 1
    assert sports["tennis"]["last_result_date"].startswith(when.date().isoformat())
    assert sports["tennis"]["upcoming_fixtures"] == 0
    assert sports["tennis"]["next_fixture_date"] is None
    # A sport with no data reports zero and no date, not a made-up one.
    assert sports["basketball"]["matches_on_record"] == 0
    assert sports["basketball"]["last_result_date"] is None


def test_the_page_reports_how_old_the_data_is(client, db_session):
    a, b = _players(db_session, "tennis", "Sinner J.", "Alcaraz C.")
    _match(db_session, "tennis", a, b, _now() - timedelta(days=326), (2, 1))
    db_session.commit()

    page = client.get("/sports/tennis").json()

    assert page["days_since_last_result"] == 326
    assert page["upcoming"] == []
    assert page["competitions"][0]["name"] == "ATP"


def test_upcoming_fixtures_appear_only_when_they_are_really_scheduled(client, db_session):
    a, b = _players(db_session, "basketball", "Boston Celtics", "Miami Heat", league="NBA")
    _match(db_session, "basketball", a, b, _now() + timedelta(days=2), None, competition="NBA")
    _match(db_session, "basketball", b, a, _now() + timedelta(days=60), None, competition="NBA")
    _match(
        db_session, "basketball", a, b, _now() - timedelta(days=4), (110, 100), competition="NBA"
    )
    db_session.commit()

    page = client.get("/sports/basketball").json()

    # The one two days out, not the one two months out, and nothing already played.
    assert [m["home"] for m in page["upcoming"]] == ["Boston Celtics"]
    assert page["upcoming"][0]["pick"]["name"] == "Boston Celtics"


def test_ratings_come_from_the_elo_history_not_the_default_column(client, db_session):
    a, b, c = _players(db_session, "tennis", "Sinner J.", "Alcaraz C.", "Gasquet R.")
    first = _match(db_session, "tennis", a, b, _now() - timedelta(days=40), (2, 0))
    second = _match(db_session, "tennis", c, b, _now() - timedelta(days=20), (0, 2))
    _rate(db_session, a, first, 2200.0)
    _rate(db_session, b, first, 2100.0)
    _rate(db_session, b, second, 2150.0)
    _rate(db_session, c, second, 1900.0)
    db_session.commit()

    top = client.get("/sports/tennis").json()["top_rated"]

    # One group per competition: ratings only compare within a pool.
    assert [g["competition"] for g in top] == ["ATP"]
    assert [(t["name"], t["rating"]) for t in top[0]["teams"]] == [
        ("Sinner J.", 2200),
        ("Alcaraz C.", 2150),  # the later update, not the earlier 2100
        ("Gasquet R.", 1900),
    ]


def test_ratings_are_ranked_within_each_competition_not_across_them(client, db_session):
    men = _players(db_session, "tennis", "Sinner J.", "Alcaraz C.")
    women = _players(db_session, "tennis", "Sabalenka A.", "Swiatek I.", league="WTA")
    atp = _match(db_session, "tennis", men[0], men[1], _now() - timedelta(days=5), (2, 0))
    wta = _match(
        db_session, "tennis", women[0], women[1], _now() - timedelta(days=5), (2, 0),
        competition="WTA",
    )  # fmt: skip
    _rate(db_session, men[0], atp, 2300.0)
    _rate(db_session, men[1], atp, 2100.0)
    _rate(db_session, women[0], wta, 2900.0)  # higher than any man, and still not "number one"
    _rate(db_session, women[1], wta, 2000.0)
    db_session.commit()

    groups = {
        g["competition"]: g["teams"] for g in client.get("/sports/tennis").json()["top_rated"]
    }

    assert set(groups) == {"ATP", "WTA"}
    assert groups["ATP"][0]["name"] == "Sinner J." and groups["WTA"][0]["name"] == "Sabalenka A."


def test_recent_results_are_marked_right_or_wrong_against_the_score(client, db_session):
    a, b = _players(db_session, "tennis", "Sinner J.", "Alcaraz C.")
    day = _now() - timedelta(days=30)
    _match(db_session, "tennis", a, b, day, (2, 0), surface="Hard")  # engine backs home: right
    _match(
        db_session, "tennis", b, a, day, (0, 2), surface="Clay"
    )  # backs home b, home lost: wrong
    db_session.commit()

    recent = client.get("/sports/tennis").json()["recent"]

    verdicts = {r["surface"]: r["pick_correct"] for r in recent}
    assert verdicts == {"Hard": True, "Clay": False}


def _model(db_session, name, metrics):
    db_session.add(
        ModelVersion(
            model_name=name,
            version="v1",
            artifact_path="x",
            metrics=metrics,
            is_active=True,
            trained_at=_now(),
        )
    )


def test_a_model_is_reported_with_the_baseline_it_recorded_and_the_gap(client, db_session):
    _model(
        db_session,
        "lightgbm_tennis_winner",
        {"accuracy": 0.6471, "elo_baseline_accuracy": 0.6428, "num_test_samples": 13734},
    )
    _model(
        db_session,
        "lightgbm_tennis_total_games_23_5",
        {"accuracy": 0.649, "majority_class_base_rate": 0.559, "num_test_samples": 13734},
    )
    # A model with no recorded baseline is reported without a comparison.
    _model(db_session, "lightgbm_tennis_total_games_21_5", {"accuracy": 0.6})
    db_session.commit()

    models = {m["model"]: m for m in client.get("/sports/tennis").json()["models"]}

    winner = models["lightgbm_tennis_winner"]
    assert winner["accuracy"] == 64.7
    assert winner["baseline"] == 64.3
    assert winner["baseline_kind"] == "Always pick the higher-rated side"
    assert winner["edge"] == 0.4
    assert models["lightgbm_tennis_total_games_23_5"]["edge"] == 9.0
    unmeasured = models["lightgbm_tennis_total_games_21_5"]
    assert unmeasured["baseline"] is None
    assert unmeasured["edge"] is None


def test_a_failed_recompute_serves_the_last_good_answer_marked_stale(db_session, monkeypatch):
    a, b = _players(db_session, "tennis", "Sinner J.", "Alcaraz C.")
    _match(db_session, "tennis", a, b, _now() - timedelta(days=5), (2, 0))
    db_session.commit()

    first = sport_service.sport_overview(db_session, "tennis")
    assert "stale" not in first

    # Expire the cache entry, then make the recompute fail.
    sport_service._cache["tennis"] = (-1e9, first)

    def boom(*_args, **_kwargs):
        raise RuntimeError("database is locked")

    monkeypatch.setattr(sport_service, "_compute", boom)

    again = sport_service.sport_overview(db_session, "tennis")
    assert again["stale"] is True
    assert again["matches_on_record"] == first["matches_on_record"]


# --- the football pages must not show other sports ----------------------------------------------


def test_the_football_pages_do_not_show_basketball_or_tennis(client, db_session, monkeypatch):
    """Basketball and tennis fixtures live in the same table as football's. The football
    board once listed NBA games under 'Football predictions' because nothing filtered on
    sport; every football endpoint that reads fixtures must."""
    from app.services import stored_predictions

    monkeypatch.setattr(
        stored_predictions, "predict_for_matches", lambda db, matches, **k: [None] * len(matches)
    )
    when = _now().replace(hour=15, minute=0, second=0, microsecond=0)
    arsenal = Team(name="Arsenal", sport="football", league="English Premier League")
    chelsea = Team(name="Chelsea", sport="football", league="English Premier League")
    celtics, heat = _players(db_session, "basketball", "Boston Celtics", "Miami Heat", league="NBA")
    sinner, alcaraz = _players(db_session, "tennis", "Sinner J.", "Alcaraz C.")
    db_session.add_all([arsenal, chelsea])
    db_session.flush()
    db_session.add(
        Match(
            sport="football", competition="English Premier League", season="2026",
            match_date=when, home_team_id=arsenal.id, away_team_id=chelsea.id, status="scheduled",
        )
    )  # fmt: skip
    _match(db_session, "basketball", celtics, heat, when, None, competition="NBA")
    _match(db_session, "tennis", sinner, alcaraz, when, None, competition="ATP")
    db_session.commit()
    day = when.date().isoformat()

    board = client.get(f"/board?on_date={day}").json()
    names = {g["competition"]["name"] for g in board["groups"]}
    dates = client.get("/board/dates").json()
    today = next(d for d in dates["days"] if d["date"] == day)
    fixtures = client.get(f"/fixtures/today?on_date={day}").json()

    assert names == {"English Premier League"}
    assert today["fixtures"] == 1
    assert [f["competition"] for f in fixtures["fixtures"]] == ["English Premier League"]
    leagues = client.get("/leagues").json()
    listed = {c["competition"] for country in leagues["countries"] for c in country["competitions"]}
    assert "NBA" not in listed and "ATP" not in listed
