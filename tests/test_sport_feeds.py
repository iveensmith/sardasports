"""Basketball and tennis: the feeds, the ratings, and the predictions stored in advance.

What these protect:

* a game only becomes a result when it finished with a real winner, and a finished game is
  never walked back to scheduled;
* the tennis feed keeps singles only, skips byes and matches that were not played to a
  finish, and finds the stored player for an ESPN name instead of creating a duplicate;
* when tennis-data later publishes a match the feed already holds, the existing row is
  updated in place, so nothing is counted twice and anything stored against it survives;
* Elo continues from the last rating for new results, and replays the sport when a result
  arrives that is older than ratings already written;
* a prediction is stored before the match, frozen as kick-off nears, never stored for a
  side with too little history, and graded apart from anything made afterwards.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.models import EloHistory, Match, SportPrediction, Team
from app.services import basketball_feed, sport_predictions, tennis_feed
from app.services.elo_sync import sync_elo
from ml.basketball_catalogue import display_name, free_plan_seasons
from ml.prediction.predict_basketball import predict_game


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


# --- basketball feed -------------------------------------------------------------------


def _game(game_id=1, status="FT", home=100, away=90, league_id=12, name="NBA"):
    return {
        "id": game_id,
        "date": "2026-10-08T00:00:00+00:00",
        "status": {"short": status},
        "league": {"id": league_id, "name": name, "season": "2026-2027"},
        "country": {"name": "USA"},
        "teams": {"home": {"name": "Boston Celtics"}, "away": {"name": "Miami Heat"}},
        "scores": {"home": {"total": home}, "away": {"total": away}},
    }


def test_a_finished_game_is_a_result_and_a_game_not_started_is_scheduled():
    done = basketball_feed.parse_item(_game(status="FT"))
    ahead = basketball_feed.parse_item(_game(game_id=2, status="NS", home=None, away=None))

    assert (done["status"], done["home_score"], done["away_score"]) == ("completed", 100, 90)
    assert (ahead["status"], ahead["home_score"]) == ("scheduled", None)


def test_games_without_a_real_outcome_are_left_out():
    for status in ("POST", "CANC", "SUSP", "ABD", "AWD"):
        assert basketball_feed.parse_item(_game(status=status)) is None
    assert basketball_feed.parse_item(_game(home=88, away=88)) is None  # a tie cannot be final


def test_an_awarded_game_scored_20_0_is_not_a_result():
    assert basketball_feed.parse_item(_game(home=20, away=0)) is None
    assert basketball_feed.parse_item(_game(home=0, away=20)) is None


def test_a_game_in_play_is_kept_scheduled_so_no_score_is_taken_early():
    live = basketball_feed.parse_item(_game(status="Q3", home=50, away=48))

    assert live["status"] == "scheduled"
    assert live["home_score"] is None and live["away_score"] is None


def test_league_names_are_unambiguous_across_countries():
    assert display_name(12, "NBA", "USA") == "NBA"
    assert display_name(2, "LNB", "France") == "LNB (France)"
    assert display_name(114, "LNB", "Chile") == "LNB (Chile)"


def test_the_free_plan_seasons_are_only_those_it_serves():
    seasons = free_plan_seasons(12)
    assert seasons and all(2022 <= int(s[:4]) <= 2024 for s in seasons)


def test_upsert_inserts_then_completes_and_never_walks_a_result_back(db_session):
    scheduled = basketball_feed.parse_item(_game(status="NS", home=None, away=None))
    finished = basketball_feed.parse_item(_game(status="FT"))

    assert basketball_feed.upsert(db_session, [scheduled])["inserted"] == 1
    again = basketball_feed.upsert(db_session, [finished])
    assert again == {"inserted": 0, "completed": 1, "updated": 1}
    match = db_session.query(Match).one()
    assert (match.status, match.home_score, match.away_score) == ("completed", 100, 90)

    # A later feed that still lists it as not started must not undo the result.
    basketball_feed.upsert(db_session, [scheduled])
    db_session.refresh(match)
    assert match.status == "completed" and match.home_score == 100


def test_nothing_is_spent_when_the_quota_cannot_be_read(db_session, monkeypatch):
    monkeypatch.setattr(basketball_feed, "requests_left", lambda settings: None)
    spent = []
    monkeypatch.setattr(basketball_feed, "fetch_games", lambda *a, **k: spent.append(1) or [])

    assert "skipped" in basketball_feed.sync_date_window(db_session)
    assert "skipped" in basketball_feed.backfill(db_session)
    assert spent == []


def test_the_backfill_skips_what_is_already_fetched(tmp_path, monkeypatch):
    monkeypatch.setattr(basketball_feed, "RAW_DIR", tmp_path)
    first = basketball_feed.backfill_plan()[0]
    assert first[0] == 12 or first[0] == 120  # the best-known leagues come first

    (tmp_path / f"league{first[0]}_{first[1]}.json").write_text("[]")

    assert first not in basketball_feed.backfill_plan()


# --- basketball statistical totals and thin history ----------------------------------------


def _history(team_a, team_b, games, start):
    out = []
    for i in range(games):
        out.append(
            {
                "match_date": start + timedelta(days=3 * i),
                "home_team": team_a if i % 2 == 0 else team_b,
                "away_team": team_b if i % 2 == 0 else team_a,
                "home_score": 80 + (i % 5),
                "away_score": 75 + (i % 4),
            }
        )
    return out


def test_statistical_totals_are_centred_on_the_expectation_and_five_points_apart():
    start = datetime(2026, 1, 1)
    history = _history("A", "B", 20, start)

    result = predict_game(
        "A", "B", datetime(2026, 4, 1), history, 1500, 1500,
        league_totals={"std": 17.0, "n": 200, "mean": 160.0},
    )  # fmt: skip

    lines = [m.line for m in result.total_points_markets]
    assert lines[1] - lines[0] == pytest.approx(5.0) and lines[2] - lines[1] == pytest.approx(5.0)
    assert all(m.source == "statistical" and not m.model_used for m in result.total_points_markets)
    overs = [m.prob_over for m in result.total_points_markets]
    assert overs[0] > overs[1] > overs[2]  # a higher line is less likely to be beaten
    assert abs(overs[1] - 50.0) < 15  # the middle line sits near the expected total


def test_a_side_with_too_little_history_is_not_priced():
    history = _history("A", "B", 3, datetime(2026, 1, 1))

    result = predict_game(
        "A", "B", datetime(2026, 4, 1), history, 1500, 1500,
        league_totals={"std": 17.0, "n": 200, "mean": 160.0},
    )  # fmt: skip

    assert result.thin_history is True
    assert result.total_points_markets == []


def test_old_ratings_are_pulled_towards_a_coin_flip_and_flagged():
    history = _history("A", "B", 20, datetime(2024, 1, 1))
    fresh = predict_game("A", "B", datetime(2024, 3, 20), history, 1700, 1400)
    stale = predict_game("A", "B", datetime(2026, 1, 1), history, 1700, 1400)

    assert stale.stale_ratings is True and not fresh.stale_ratings
    assert stale.ratings_age_days > 300
    assert abs(stale.home_win - 50) < abs(fresh.home_win - 50)


# --- tennis feed -----------------------------------------------------------------------


def _competitor(name, sets, order=1):
    return {
        "order": order,
        "athlete": {"fullName": name},
        "linescores": [{"value": 6.0, "winner": w} for w in sets],
    }


def _comp(comp_id, status, a, b):
    return {
        "id": str(comp_id),
        "date": "2026-10-08T07:00Z",
        "status": {"type": {"name": status}},
        "competitors": [a, b],
    }


def _board(*competitions, grouping="mens-singles", major=False, name="Shanghai Masters"):
    return {
        "events": [
            {
                "name": name,
                "major": major,
                "venue": {"displayName": "Shanghai, China"},
                "groupings": [
                    {"grouping": {"slug": grouping}, "competitions": list(competitions)},
                ],
            }
        ]
    }


def test_the_scoreboard_keeps_singles_that_were_played_to_a_finish():
    final = _comp(
        1, "STATUS_FINAL", _competitor("Carlos Alcaraz", [True, True]),
        _competitor("Jannik Sinner", [False, False], 2),
    )  # fmt: skip
    ahead = _comp(
        2, "STATUS_SCHEDULED", _competitor("Carlos Alcaraz", []), _competitor("Jannik Sinner", [])
    )  # fmt: skip
    retired = _comp(
        3, "STATUS_RETIRED", _competitor("Carlos Alcaraz", [True]), _competitor("Jannik Sinner", [])
    )  # fmt: skip
    bye = _comp(4, "STATUS_SCHEDULED", _competitor("Carlos Alcaraz", []), {"order": 2})

    rows = tennis_feed.parse_scoreboard(_board(final, ahead, retired, bye), "ATP")

    assert {r["external_id"] for r in rows} == {"espn-tennis-1", "espn-tennis-2"}
    done = next(r for r in rows if r["status"] == "completed")
    assert done["sets"] == (2, 0) and done["surface"] == "Hard"
    assert done["tournament"] == "Shanghai Masters"


def test_doubles_are_not_loaded():
    final = _comp(
        1,
        "STATUS_FINAL",
        _competitor("A One", [True, True]),
        _competitor("B Two", [False, False], 2),
    )

    assert tennis_feed.parse_scoreboard(_board(final, grouping="mens-doubles"), "ATP") == []


def test_a_men_s_grand_slam_is_best_of_five_and_other_matches_best_of_three():
    slam = _comp(
        1, "STATUS_SCHEDULED", _competitor("Carlos Alcaraz", []), _competitor("Jannik Sinner", [])
    )  # fmt: skip

    assert tennis_feed.parse_scoreboard(_board(slam, major=True), "ATP")[0]["best_of"] == 5
    assert tennis_feed.parse_scoreboard(_board(slam, major=False), "ATP")[0]["best_of"] == 3
    women = _board(slam, grouping="womens-singles", major=True)
    assert tennis_feed.parse_scoreboard(women, "WTA")[0]["best_of"] == 3


def _player(db, name):
    team = Team(name=name, sport="tennis", league="ATP")
    db.add(team)
    db.flush()
    return team


def test_an_espn_name_finds_the_stored_player_by_surname_and_initial(db_session):
    minaur = _player(db_session, "De Minaur A.")
    rigele = _player(db_session, "Te R.")
    index = tennis_feed.PlayerIndex(db_session)

    assert index.resolve("Alex de Minaur", "ATP").id == minaur.id
    assert index.resolve("Te Rigele", "WTA").id == rigele.id  # surname first
    assert index.resolve("Arthur Gea", "ATP").name == "Gea A."  # unseen: created in the same form


def test_a_known_tournament_gets_its_surface_and_an_unknown_one_gets_none():
    assert tennis_feed.surface_for("Rolex Shanghai Masters", "Shanghai, China")[0] == "Hard"
    assert tennis_feed.surface_for("Completely Unknown Classic", "Nowhere")[0] is None


def _espn_row(external_id="espn-tennis-9", status="scheduled", sets=None, when=None):
    return {
        "external_id": external_id,
        "match_date": when or _now() + timedelta(hours=5),
        "competition": "ATP",
        "season": "2026",
        "surface": "Hard",
        "best_of": 3,
        "names": ["Carlos Alcaraz", "Jannik Sinner"],
        "status": status,
        "tournament": "Shanghai Masters",
        "sets": sets,
        "games": None if sets is None else (12, 8),
    }


def test_the_feed_stores_a_fixture_then_completes_it(db_session):
    _player(db_session, "Alcaraz C.")
    _player(db_session, "Sinner J.")

    assert tennis_feed.upsert(db_session, [_espn_row()])["inserted"] == 1
    assert tennis_feed.upsert(db_session, [_espn_row()])["inserted"] == 0  # idempotent
    done = tennis_feed.upsert(db_session, [_espn_row(status="completed", sets=(2, 0))])

    assert done["completed"] == 1
    match = db_session.query(Match).filter(Match.sport == "tennis").one()
    assert match.status == "completed"
    assert sorted([match.home_score, match.away_score]) == [0, 2]
    assert match.tournament == "Shanghai Masters" and match.neutral_venue is True


def test_the_workbook_row_takes_over_the_feeds_row_in_place(db_session):
    from scripts.fetch_tennis import load_rows

    alcaraz = _player(db_session, "Alcaraz C.")
    sinner = _player(db_session, "Sinner J.")
    tennis_feed.upsert(db_session, [_espn_row(status="completed", sets=(2, 0))])
    espn_match = db_session.query(Match).filter(Match.external_id == "espn-tennis-9").one()
    kept_id = espn_match.id
    # Anything stored against the match must keep pointing at it.
    db_session.add(
        SportPrediction(
            match_id=kept_id, sport="tennis", created_at=_now(), updated_at=_now(),
            home_win_pct=60.0, away_win_pct=40.0, payload={},
        )
    )  # fmt: skip
    db_session.commit()

    when = espn_match.match_date
    workbook = {
        "external_id": "tennis-ATP-2026-77",
        "match_date": when - timedelta(days=1),
        "competition": "ATP",
        "season": "2026",
        "surface": "Hard",
        "best_of": 3,
        "tournament": "Shanghai Masters",
        "home_team": "Alcaraz C.",
        "away_team": "Sinner J.",
        "home_score": 2,
        "away_score": 0,
        "home_games": 12,
        "away_games": 8,
        "odds_home_win": 1.8,
        "odds_away_win": 2.1,
    }
    load_rows(db_session, [workbook])
    db_session.commit()

    matches = db_session.query(Match).filter(Match.sport == "tennis").all()
    assert len(matches) == 1 and matches[0].id == kept_id  # one row, the original
    assert matches[0].external_id == "tennis-ATP-2026-77"
    winner_id = alcaraz.id
    won = (
        matches[0].home_team_id
        if matches[0].home_score > matches[0].away_score
        else matches[0].away_team_id
    )
    assert won == winner_id and sinner.id != winner_id  # the result is mapped to the right player
    assert db_session.query(SportPrediction).filter_by(match_id=kept_id).count() == 1


# --- Elo ------------------------------------------------------------------------------------


def _basketball_pair(db):
    a = Team(name="Boston Celtics", sport="basketball", league="NBA")
    b = Team(name="Miami Heat", sport="basketball", league="NBA")
    db.add_all([a, b])
    db.flush()
    return a, b


def _bb_match(db, a, b, when, score=(100, 90), status="completed"):
    m = Match(
        sport="basketball", match_date=when, competition="NBA", season="2026-2027",
        home_team_id=a.id, away_team_id=b.id,
        home_score=score[0] if status == "completed" else None,
        away_score=score[1] if status == "completed" else None,
        status=status,
    )  # fmt: skip
    db.add(m)
    db.flush()
    return m


def test_new_results_continue_from_the_last_rating(db_session):
    a, b = _basketball_pair(db_session)
    _bb_match(db_session, a, b, datetime(2026, 1, 1))
    db_session.commit()
    sync_elo(db_session, "basketball")
    first = db_session.query(EloHistory).filter_by(team_id=a.id).one().rating_after

    _bb_match(db_session, a, b, datetime(2026, 2, 1))
    db_session.commit()
    result = sync_elo(db_session, "basketball")

    assert result == {"added": 1, "rebuilt": False}
    second = (
        db_session.query(EloHistory).filter_by(team_id=a.id).order_by(EloHistory.id.desc()).first()
    )
    assert second.rating_before == pytest.approx(first)  # continued, not restarted at 1500
    assert sync_elo(db_session, "basketball") == {"added": 0, "rebuilt": False}  # nothing twice


def test_a_result_older_than_the_ratings_replays_the_sport(db_session):
    a, b = _basketball_pair(db_session)
    _bb_match(db_session, a, b, datetime(2026, 3, 1))
    db_session.commit()
    sync_elo(db_session, "basketball")

    _bb_match(db_session, a, b, datetime(2026, 1, 1))  # arrives late, but is older
    db_session.commit()
    result = sync_elo(db_session, "basketball")

    assert result["rebuilt"] is True
    dates = [r.match_date for r in db_session.query(EloHistory).filter_by(team_id=a.id)]
    assert sorted(dates) == [datetime(2026, 1, 1), datetime(2026, 3, 1)]


# --- predictions stored in advance, the board and the record ---------------------------------


def _payload(home=60.0, thin=False, total=(160.5, 55.0)):
    return {
        "home_win": home,
        "away_win": round(100 - home, 1),
        "confidence": 20.0,
        "thin_history": thin,
        "expected_total_points": 161.0,
        "total_points_markets": [
            {
                "line": total[0],
                "prob_over": total[1],
                "prob_under": 100 - total[1],
                "model_used": False,
            }
        ],
        "model_version": "v1",
    }


@pytest.fixture
def priced(monkeypatch):
    """Pricing needs trained models; these tests are about what is done with the output."""
    state = {"thin": set(), "home": 60.0}

    def fake(db, matches):
        return [_payload(state["home"], thin=m.id in state["thin"]) for m in matches]

    monkeypatch.setattr(sport_predictions, "predict_for_matches", fake)
    sport_predictions.clear_cache()
    yield state
    sport_predictions.clear_cache()


def test_predictions_are_stored_ahead_and_a_thin_side_is_skipped(db_session, priced):
    a, b = _basketball_pair(db_session)
    soon = _bb_match(db_session, a, b, _now() + timedelta(hours=10), status="scheduled")
    thin = _bb_match(db_session, b, a, _now() + timedelta(hours=12), status="scheduled")
    far = _bb_match(db_session, a, b, _now() + timedelta(days=5), status="scheduled")
    db_session.commit()
    priced["thin"].add(thin.id)

    counts = sport_predictions.store_upcoming(db_session)

    assert counts["stored"] == 1 and counts["unpriced"] == 1
    stored = db_session.query(SportPrediction).one()
    assert stored.match_id == soon.id and stored.home_win_pct == 60.0
    assert stored.total_line == 160.5 and stored.created_at < soon.match_date
    assert db_session.query(SportPrediction).filter_by(match_id=far.id).count() == 0


def test_each_job_stores_only_its_own_sport(db_session, priced):
    a, b = _basketball_pair(db_session)
    _bb_match(db_session, a, b, _now() + timedelta(hours=10), status="scheduled")
    db_session.commit()

    assert sport_predictions.store_upcoming(db_session, sports=("tennis",))["stored"] == 0
    assert db_session.query(SportPrediction).count() == 0
    assert sport_predictions.store_upcoming(db_session, sports=("basketball",))["stored"] == 1


def test_a_stored_prediction_is_refreshed_while_far_off_and_frozen_near_kick_off(
    db_session, priced
):
    a, b = _basketball_pair(db_session)
    match = _bb_match(db_session, a, b, _now() + timedelta(hours=20), status="scheduled")
    db_session.commit()
    sport_predictions.store_upcoming(db_session)
    row = db_session.query(SportPrediction).one()

    # Stale enough to refresh, and the match is still far off: it is updated.
    row.updated_at = _now() - timedelta(hours=8)
    db_session.commit()
    priced["home"] = 70.0
    assert sport_predictions.store_upcoming(db_session)["refreshed"] == 1
    db_session.refresh(row)
    assert row.home_win_pct == 70.0

    # Kick-off is now near: it is frozen, whatever the engine now thinks.
    match.match_date = _now() + timedelta(hours=1)
    row.updated_at = _now() - timedelta(hours=8)
    db_session.commit()
    priced["home"] = 30.0
    assert sport_predictions.store_upcoming(db_session)["frozen"] == 1
    db_session.refresh(row)
    assert row.home_win_pct == 70.0


def test_the_record_counts_stored_picks_apart_from_ones_made_afterwards(db_session, priced):
    a, b = _basketball_pair(db_session)
    live = _bb_match(db_session, a, b, _now() - timedelta(days=1), score=(100, 90))
    late = _bb_match(db_session, b, a, _now() - timedelta(days=2), score=(70, 80))
    db_session.commit()
    for match, created in ((live, match_created(live, -3)), (late, match_created(late, +1))):
        db_session.add(
            SportPrediction(
                match_id=match.id, sport="basketball", created_at=created, updated_at=created,
                home_win_pct=60.0, away_win_pct=40.0, total_line=160.5, prob_over_pct=40.0,
                payload={},
            )
        )  # fmt: skip
    db_session.commit()

    record = sport_predictions.sport_record(db_session, "basketball")

    # live: backed home (60%), home won 100-90: winner right; backed under 160.5, total 190: wrong
    assert record["live"]["winner"] == {"settled": 1, "won": 1}
    assert record["live"]["total"] == {"settled": 1, "won": 0}
    # late: stored after the match started, so it is not a live pick
    assert record["reconstructed"]["winner"] == {"settled": 1, "won": 0}
    assert record["live_since"] is not None


def match_created(match, hours):
    return match.match_date + timedelta(hours=hours)


def test_the_board_groups_by_league_and_labels_where_each_prediction_came_from(db_session, priced):
    a, b = _basketball_pair(db_session)
    day = (_now() + timedelta(days=1)).replace(hour=18, minute=0, second=0, microsecond=0)
    stored = _bb_match(db_session, a, b, day, status="scheduled")
    unstored = _bb_match(db_session, b, a, day + timedelta(hours=2), status="scheduled")
    db_session.add(
        SportPrediction(
            match_id=stored.id, sport="basketball", created_at=_now(), updated_at=_now(),
            home_win_pct=65.0, away_win_pct=35.0, payload={},
        )
    )  # fmt: skip
    db_session.commit()

    board = sport_predictions.build_board(db_session, "basketball", day)

    assert board["counts"]["fixtures"] == 2 and board["counts"]["competitions"] == 1
    entries = {e["match_id"]: e for e in board["competitions"][0]["matches"]}
    assert entries[stored.id]["source"] == "stored" and entries[stored.id]["home_win"] == 65.0
    assert entries[unstored.id]["source"] == "calculated"
    assert board["counts"]["stored_in_advance"] == 1
    with pytest.raises(KeyError):
        sport_predictions.build_board(db_session, "football", day)


def test_the_board_and_record_routes(client, db_session, priced):
    a, b = _basketball_pair(db_session)
    day = _now() + timedelta(days=1)
    _bb_match(db_session, a, b, day, status="scheduled")
    db_session.commit()

    board = client.get(f"/sports/basketball/board?on_date={day.date().isoformat()}")
    record = client.get("/sports/tennis/record")

    assert board.status_code == 200 and board.json()["counts"]["fixtures"] == 1
    assert record.status_code == 200 and record.json()["stored_total"] == 0
    assert client.get("/sports/football/board").status_code == 404
    assert client.get("/sports/football/record").status_code == 404
