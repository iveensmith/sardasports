"""The free allowance: 15 football predictions a day are free, the rest are for premium members.

These tests look at it the way a visitor and a member would, through the engine's own endpoints:
a day with more than 15 fixtures, what each of them is sent, and (the one that matters most) that
what is sent to a premium member never reaches anyone else through a cache.
"""

from __future__ import annotations

import itertools
from datetime import UTC, datetime, timedelta

import pytest

from app.models import Match, Team
from app.models.account import ROLE_ADMIN, User
from app.services import access, auth_service, premium_service
from app.services.auth_service import hash_password

PASSWORD = "correct-horse-battery"
_names = itertools.count()
LEAGUE = "English Premier League"


def _now():
    return datetime.now(UTC).replace(tzinfo=None)


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    auth_service.reset_rate_limits()
    access.clear_cache()
    # Boards and day rows are cached in the engine; a test must not see another's.
    from app.api import routes_board_table, routes_discover

    routes_board_table._board_cache = type(routes_board_table._board_cache)(
        routes_board_table.BOARD_CACHE_SECONDS, stale_seconds=routes_board_table.BOARD_STALE_SECONDS
    )
    routes_discover._day_cache = type(routes_discover._day_cache)(routes_discover.DAY_CACHE_SECONDS)
    yield
    access.clear_cache()
    auth_service.reset_rate_limits()


def _day(offset_days: int) -> datetime:
    today = _now().replace(hour=0, minute=0, second=0, microsecond=0)
    return today + timedelta(days=offset_days)


def _fixtures(db_session, day, count, competition=LEAGUE, first_hour=10, odds=False):
    """`count` football fixtures on `day`, one an hour apart from `first_hour`."""
    made = []
    for i in range(count):
        home = Team(name=f"H{next(_names)}", league="x", sport="football")
        away = Team(name=f"A{next(_names)}", league="x", sport="football")
        db_session.add_all([home, away])
        db_session.flush()
        match = Match(
            match_date=day + timedelta(hours=first_hour, minutes=i * 7),
            competition=competition,
            season="2026-2027",
            home_team_id=home.id,
            away_team_id=away.id,
            status="scheduled",
            sport="football",
        )
        if odds:
            match.odds_home_win, match.odds_draw, match.odds_away_win = 2.1, 3.4, 3.6
        db_session.add(match)
        made.append(match)
    db_session.commit()
    return made


def _member(db_session, email, role="member", premium=False):
    user = User(
        email=email,
        password_hash=hash_password(PASSWORD),
        role=role,
        email_verified_at=_now(),
        over_18_confirmed_at=_now(),
    )
    db_session.add(user)
    db_session.commit()
    if premium:
        premium_service.grant_manually(db_session, user=user, days=30, actor_id=None)
        db_session.commit()
    return user


def _headers(client, email):
    token = client.post("/auth/login", json={"email": email, "password": PASSWORD}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _rows(board):
    return [row for group in board["groups"] for row in group["rows"]]


@pytest.fixture
def busy_day(db_session):
    """Tomorrow: 18 Premier League fixtures and 2 from a lesser league: 20, so 5 are locked."""
    tomorrow = _day(1)
    premier = _fixtures(db_session, tomorrow, 18)
    other = _fixtures(db_session, tomorrow, 2, competition="Test League", first_hour=9)
    return tomorrow, premier, other


def _board(client, day, headers=None):
    return client.get("/board", params={"on_date": day.date().isoformat()}, headers=headers).json()


# --- which fifteen ------------------------------------------------------------------------------


def test_the_free_matches_are_the_biggest_competitions_first_then_by_kick_off(
    client, db_session, busy_day, monkeypatch
):
    day, premier, other = busy_day
    free = access.free_match_ids(db_session, day.date())

    assert len(free) == 15
    # All fifteen come from the Premier League, though the other league kicks off earlier in the
    # day, and they are its earliest fifteen.
    assert free == {m.id for m in sorted(premier, key=lambda m: (m.match_date, m.id))[:15]}
    assert not free & {m.id for m in other}


def test_the_free_set_does_not_depend_on_what_the_engine_thinks_of_the_matches(
    client, db_session, busy_day
):
    day, _, _ = busy_day
    before = access.free_match_ids(db_session, day.date())
    access.clear_cache()
    client.get("/board", params={"on_date": day.date().isoformat()})  # computes predictions

    assert access.free_match_ids(db_session, day.date()) == before


def test_a_smaller_allowance_takes_the_priority_order_then_the_clock(db_session, monkeypatch):
    monkeypatch.setattr(access, "FREE_DAILY_LIMIT", 3)
    day = _day(2)
    late_big = _fixtures(db_session, day, 1, competition=LEAGUE, first_hour=20)
    early_small = _fixtures(db_session, day, 3, competition="Test League", first_hour=8)

    free = access.free_match_ids(db_session, day.date())

    # The big league's one match first even though it kicks off last, then the two earliest others.
    assert free == {late_big[0].id, early_small[0].id, early_small[1].id}


# --- what a visitor is sent ---------------------------------------------------------------------


def test_a_visitor_gets_fifteen_open_rows_and_the_rest_with_no_prediction(
    client, db_session, busy_day
):
    day, _, _ = busy_day

    rows = _rows(_board(client, day))

    assert len(rows) == 20
    locked = [r for r in rows if r["locked"]]
    assert len(locked) == 5 and len([r for r in rows if not r["locked"]]) == 15
    for row in locked:
        assert row["tips"] == {} and row["best_tip"] is None
        assert row["confidence"] is None and row["confidence_label"] is None
    for row in rows:
        if not row["locked"]:
            assert row["best_tip"] is not None  # the free ones are fully open


def test_a_locked_row_keeps_the_bookmakers_price_but_not_the_engines_own(client, db_session):
    day = _day(3)
    _fixtures(db_session, day, 15)  # these fill the free allowance
    quoted, bare = _fixtures(db_session, day, 1, competition="Test League", odds=True), _fixtures(
        db_session, day, 1, competition="Test League", first_hour=23
    )

    rows = {r["match_id"]: r for r in _rows(_board(client, day))}

    priced = rows[quoted[0].id]
    assert priced["locked"] and priced["odds"] == {"home": 2.1, "draw": 3.4, "away": 3.6}
    # No quote: the open board shows a price the engine worked out (a "fair price", 100 over its
    # probability). That is the prediction in another form, so a locked row gets none.
    unpriced = rows[bare[0].id]
    assert unpriced["locked"]
    assert all(price is None for price in unpriced["odds"].values())
    assert not any(unpriced["odds_estimated"].values())


def test_a_match_that_has_kicked_off_is_never_hidden(client, db_session):
    day = _day(-1)  # yesterday: every match on it has kicked off
    _fixtures(db_session, day, 20)

    rows = _rows(_board(client, day))

    assert len(rows) == 20 and not any(r["locked"] for r in rows)
    assert all(r["best_tip"] is not None for r in rows)


def test_basketball_is_not_limited(client, db_session):
    day = _day(1)
    home = Team(name="Hoops H", league="x", sport="basketball")
    away = Team(name="Hoops A", league="x", sport="basketball")
    db_session.add_all([home, away])
    db_session.flush()
    _fixtures(db_session, day, 16)
    db_session.add(
        Match(
            match_date=day + timedelta(hours=22),
            competition="NBA",
            season="2026",
            home_team_id=home.id,
            away_team_id=away.id,
            status="scheduled",
            sport="basketball",
        )
    )
    db_session.commit()

    body = client.get("/board", params={"on_date": day.date().isoformat(), "sport": "basketball"})

    assert [r["locked"] for r in _rows(body.json())] == [False]


# --- what a member is sent ----------------------------------------------------------------------


def test_a_premium_member_gets_every_row_open(client, db_session, busy_day):
    day, _, _ = busy_day
    _member(db_session, "paid@example.com", premium=True)

    rows = _rows(_board(client, day, _headers(client, "paid@example.com")))

    assert len(rows) == 20
    assert not any(r.get("locked") for r in rows)
    assert all(r["best_tip"] is not None for r in rows)


def test_an_administrator_counts_as_premium(client, db_session, busy_day):
    day, _, _ = busy_day
    _member(db_session, "boss@example.com", role=ROLE_ADMIN)

    rows = _rows(_board(client, day, _headers(client, "boss@example.com")))

    assert not any(r.get("locked") for r in rows)


def test_a_member_without_premium_sees_what_a_visitor_sees(client, db_session, busy_day):
    day, _, _ = busy_day
    _member(db_session, "free@example.com")

    rows = _rows(_board(client, day, _headers(client, "free@example.com")))

    assert len([r for r in rows if r["locked"]]) == 5


def test_what_a_premium_member_was_sent_never_reaches_a_visitor_through_a_cache(
    client, db_session, busy_day
):
    """The engine caches built boards. A cache that kept the member's copy would hand every
    locked prediction to the next visitor, so the order of requests must not matter."""
    day, _, _ = busy_day
    _member(db_session, "paid@example.com", premium=True)

    member_view = _rows(_board(client, day, _headers(client, "paid@example.com")))
    visitor_view = _rows(_board(client, day))
    member_again = _rows(_board(client, day, _headers(client, "paid@example.com")))

    assert not any(r.get("locked") for r in member_view)
    assert len([r for r in visitor_view if r["locked"]]) == 5
    assert not any(r.get("locked") for r in member_again)


# --- the other places a prediction leaves the engine --------------------------------------------


def _locked_and_free_ids(db_session, day):
    free = access.free_match_ids(db_session, day.date())
    everyone = [
        m.id
        for m in db_session.query(Match).filter(
            Match.match_date >= day, Match.match_date < day + timedelta(days=1)
        )
    ]
    return free, [i for i in everyone if i not in free]


def test_a_locked_match_page_carries_who_is_playing_and_nothing_the_engine_worked_out(
    client, db_session, busy_day
):
    day, _, _ = busy_day
    free, locked = _locked_and_free_ids(db_session, day)

    body = client.get(f"/predict/{locked[0]}").json()

    assert body["locked"] is True
    assert body["home_team"] and body["away_team"] and body["match_date"]
    for key in ("home_win", "draw", "away_win", "confidence", "goals_markets", "calls", "value"):
        assert key not in body
    assert client.get(f"/predict/{next(iter(free))}").json().get("home_win") is not None


def test_a_premium_member_gets_the_full_match_prediction(client, db_session, busy_day):
    day, _, _ = busy_day
    _, locked = _locked_and_free_ids(db_session, day)
    _member(db_session, "paid@example.com", premium=True)

    body = client.get(f"/predict/{locked[0]}", headers=_headers(client, "paid@example.com")).json()

    assert "locked" not in body and body["home_win"] is not None


def test_the_other_ways_to_ask_for_one_match_are_closed_too(client, db_session, busy_day):
    day, _, _ = busy_day
    _, locked = _locked_and_free_ids(db_session, day)

    assert client.get(f"/history/{locked[0]}").status_code == 403
    assert client.get(f"/value/{locked[0]}").status_code in (403,)
    assert client.post(f"/analyst/{locked[0]}").status_code == 403


def test_predictions_today_hides_the_engines_view_of_a_locked_fixture(client, db_session, busy_day):
    day, _, _ = busy_day

    body = client.get("/predictions/today", params={"on_date": day.date().isoformat()}).json()

    locked = [f for f in body["fixtures"] if f["locked"]]
    assert len(locked) == 5
    for entry in locked:
        assert entry["prediction"] is None and entry["forecast"] is None
        assert entry["calls"] is None and entry["pick"] is None and entry["agreement"] is None


def test_the_bankers_leave_out_locked_matches_and_say_how_many(client, db_session, busy_day):
    day, _, _ = busy_day
    params = {"on_date": day.date().isoformat(), "min_probability": 50}
    _member(db_session, "paid@example.com", premium=True)

    visitor = client.get("/bankers", params=params).json()
    member = client.get(
        "/bankers", params=params, headers=_headers(client, "paid@example.com")
    ).json()

    assert visitor["locked_count"] > 0
    assert not any(r["locked"] for r in visitor["rows"])
    assert len(member["rows"]) == len(visitor["rows"]) + visitor["locked_count"]
    assert member["locked_count"] == 0


def test_the_slip_is_built_only_from_matches_the_viewer_may_see(client, db_session, busy_day):
    day, _, _ = busy_day

    slip = client.get("/slip", params={"on_date": day.date().isoformat()}).json()

    assert slip["locked_matches"] == 5
    free = access.free_match_ids(db_session, day.date())
    assert {leg["match_id"] for leg in slip.get("legs", [])} <= free


def test_a_market_page_leaves_out_locked_picks_and_counts_them(client, db_session, busy_day):
    day, _, _ = busy_day
    _member(db_session, "paid@example.com", premium=True)
    params = {"on_date": day.date().isoformat()}

    visitor = client.get("/markets/btts", params=params).json()
    member = client.get(
        "/markets/btts", params=params, headers=_headers(client, "paid@example.com")
    ).json()

    free = access.free_match_ids(db_session, day.date())
    assert {p["match_id"] for p in visitor["picks"]} <= free
    assert len(visitor["picks"]) + visitor["locked_count"] == len(member["picks"])


def test_a_league_page_hides_its_locked_fixtures(client, db_session, busy_day, monkeypatch):
    from app.services import league_service

    # The page lists the next few fixtures; make it long enough to reach the locked ones.
    monkeypatch.setattr(league_service, "FIXTURE_LIMIT", 30)

    visitor = client.get("/leagues/english-premier-league").json()

    fixtures = visitor["fixtures"]
    assert [f["locked"] for f in fixtures].count(True) == 3
    assert all(f["best_tip"] is None for f in fixtures if f["locked"])


# --- how a member's browser fills the gaps ------------------------------------------------------


def test_the_rows_route_is_for_premium_members_only(client, db_session, busy_day):
    day, _, _ = busy_day
    _, locked = _locked_and_free_ids(db_session, day)
    _member(db_session, "free@example.com")

    ids = ",".join(str(i) for i in locked)
    assert client.get("/premium/rows", params={"ids": ids}).status_code == 401
    refused = client.get(
        "/premium/rows", params={"ids": ids}, headers=_headers(client, "free@example.com")
    )
    assert refused.status_code == 403 and refused.json()["detail"]["code"] == "premium_required"


def test_the_rows_route_returns_the_hidden_predictions_to_a_premium_member(
    client, db_session, busy_day
):
    day, _, _ = busy_day
    _, locked = _locked_and_free_ids(db_session, day)
    _member(db_session, "paid@example.com", premium=True)

    body = client.get(
        "/premium/rows",
        params={"ids": ",".join(str(i) for i in locked) + ",abc,,-4"},
        headers=_headers(client, "paid@example.com"),
    ).json()

    assert [r["match_id"] for r in body["rows"]] == locked
    assert all(r["best_tip"] is not None and r["locked"] is False for r in body["rows"])
