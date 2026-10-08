"""Serving a day's board cheaply and safely under concurrent requests.

The board used to recompute every prediction on every request and write two rows
per fixture each time. Several requests at once (the home page asks for three days,
Next prefetches) piled the thread pool up, collided on SQLite's single write lock
("database is locked", each costing the busy timeout and then returning no
prediction for that fixture) and exhausted the connection pool. These tests pin the
fixes: stored predictions are served instead of recomputed when nothing they read
has changed, the writes that remain are serialised and cannot lose a prediction, and
a burst of identical requests does the work once.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, text
from sqlalchemy.exc import OperationalError

import app.services.prediction_service as prediction_service
from app.database.session import SessionLocal
from app.main import app
from app.models import EloHistory, Match, ModelVersion, Prediction, PredictionHistory, Team
from app.services.prediction_service import predict_for_matches
from app.utils.coalesce import CoalescingCache, clear_all_caches

# Timestamps are written explicitly wherever a test depends on their order:
# `updated_at` has one-second resolution, and a test must not depend on how fast it ran.
LONG_AGO = datetime(2020, 1, 1)
SETTLED = datetime(2025, 1, 1)
LATER = datetime(2030, 1, 1)


def _fixture(session, tag, when=None, status="scheduled", competition="Test League"):
    home = Team(name=f"H-{tag}", league="Test", sport="football")
    away = Team(name=f"A-{tag}", league="Test", sport="football")
    session.add_all([home, away])
    session.flush()
    match = Match(
        external_id=f"serve-{tag}",
        sport="football",
        # Midday, so a test running near midnight cannot split one day in two.
        match_date=when or datetime.now().replace(hour=12, minute=0, second=0, microsecond=0),
        competition=competition,
        season="2026",
        home_team_id=home.id,
        away_team_id=away.id,
        status=status,
    )
    session.add(match)
    session.commit()
    return match


class _Spy:
    """Counts calls to the real per-match predictor, thread-safely."""

    def __init__(self, monkeypatch):
        self.calls: list[int] = []
        self._lock = threading.Lock()
        real = prediction_service.predict_for_match

        def wrapped(session, match_id, history=None, shared=None):
            with self._lock:
                self.calls.append(match_id)
            return real(session, match_id, history=history, shared=shared)

        monkeypatch.setattr(prediction_service, "predict_for_match", wrapped)


def _stored_row(session, match) -> Prediction:
    session.expire_all()
    return session.query(Prediction).filter(Prediction.match_id == match.id).one()


# --- stored predictions are served, and say what a recompute says ---------


def test_a_stored_prediction_is_served_without_recomputing(db_session, monkeypatch):
    match = _fixture(db_session, "s1")
    first = predict_for_matches(db_session, [match])[0]
    assert first is not None

    spy = _Spy(monkeypatch)
    served = predict_for_matches(db_session, [match], allow_stored=True)[0]

    assert spy.calls == []
    assert served is not None


def test_the_served_prediction_says_exactly_what_the_computed_one_said(db_session):
    """The whole point: faster, not different. Every number a caller can read
    from a stored payload equals the one the computation produced."""
    match = _fixture(db_session, "s2")
    computed = predict_for_matches(db_session, [match])[0]
    served = predict_for_matches(db_session, [match], allow_stored=True)[0]

    assert served.keys() <= computed.keys()
    for key, value in served.items():
        if key == "generated_at":
            continue
        assert value == computed[key], key


def test_a_stored_payload_does_not_invent_what_was_never_stored(db_session):
    """No per-estimator split or explanation is kept, so none is claimed."""
    match = _fixture(db_session, "s3")
    predict_for_matches(db_session, [match])
    served = predict_for_matches(db_session, [match], allow_stored=True)[0]

    for absent in ("estimator_probs", "explanation", "model_weights_used", "btts_model_used"):
        assert absent not in served


def test_stored_serving_is_opt_in(db_session, monkeypatch):
    """`/predictions/today` reads the estimator split, which a row cannot supply,
    so the default must keep recomputing."""
    match = _fixture(db_session, "s4")
    predict_for_matches(db_session, [match])

    spy = _Spy(monkeypatch)
    result = predict_for_matches(db_session, [match])[0]

    assert spy.calls == [match.id]
    assert "estimator_probs" in result


def test_serving_a_stored_prediction_writes_nothing(db_session):
    match = _fixture(db_session, "s5")
    predict_for_matches(db_session, [match], allow_stored=True)  # computes and stores
    before = (
        db_session.query(func.count(Prediction.id)).scalar(),
        db_session.query(func.count(PredictionHistory.id)).scalar(),
    )
    stamp = _stored_row(db_session, match).updated_at

    for _ in range(3):
        predict_for_matches(db_session, [match], allow_stored=True)

    assert (
        (
            db_session.query(func.count(Prediction.id)).scalar(),
            db_session.query(func.count(PredictionHistory.id)).scalar(),
        )
        == before
        == (1, 1)
    )
    assert _stored_row(db_session, match).updated_at == stamp


def test_a_fixture_with_no_stored_row_is_computed_and_stored(db_session, monkeypatch):
    stored = _fixture(db_session, "s6a")
    fresh = _fixture(db_session, "s6b")
    predict_for_matches(db_session, [stored])

    spy = _Spy(monkeypatch)
    results = predict_for_matches(db_session, [stored, fresh], allow_stored=True)

    assert spy.calls == [fresh.id]
    assert all(results)
    assert db_session.query(func.count(Prediction.id)).scalar() == 2


# --- a stored prediction is not served once what it read has changed ------


def _settle(session, match):
    """Make the stored row current and every input older than it, so a test can
    change exactly one thing and see it matter."""
    row = _stored_row(session, match)
    row.updated_at = SETTLED
    session.commit()
    session.query(Match).filter(Match.id == match.id).update({Match.updated_at: LONG_AGO})
    session.commit()
    session.refresh(match)


def _complete_an_earlier_match(session, match):
    other = _fixture(
        session, "earlier", when=match.match_date - timedelta(days=3), status="completed"
    )
    session.query(Match).filter(Match.id == other.id).update(
        {Match.home_score: 2, Match.away_score: 1, Match.updated_at: LATER}
    )
    session.commit()


def _rebuild_elo(session, match):
    session.add(
        EloHistory(
            team_id=match.home_team_id,
            match_date=match.match_date - timedelta(days=9),
            rating_before=1500.0,
            rating_after=1510.0,
            created_at=LATER,
        )
    )
    session.commit()


def _register_a_model(session, match):
    session.add(
        ModelVersion(
            model_name="some_other_line_model",
            version="v2",
            artifact_path="nowhere",
            is_active=True,
            trained_at=LATER,
            created_at=LATER,
        )
    )
    session.commit()


def _edit_the_fixture(session, match):
    session.query(Match).filter(Match.id == match.id).update(
        {Match.competition: "Another League", Match.updated_at: LATER}
    )
    session.commit()


def _change_the_active_match_model(session, match):
    # The stored row was written with no model; one is registered (long ago, so only
    # the version mismatch can be what matters) and becomes the active one.
    session.add(
        ModelVersion(
            model_name=prediction_service.MATCH_RESULT_MODEL_NAME,
            version="v9",
            artifact_path="nowhere",
            is_active=True,
            trained_at=LONG_AGO,
            created_at=LONG_AGO,
        )
    )
    session.commit()
    prediction_service.clear_active_model_cache()


@pytest.fixture(autouse=True)
def _forget_active_models():
    prediction_service.clear_active_model_cache()
    yield
    prediction_service.clear_active_model_cache()


@pytest.mark.parametrize(
    "change",
    [
        _complete_an_earlier_match,
        _rebuild_elo,
        _register_a_model,
        _edit_the_fixture,
        _change_the_active_match_model,
    ],
    ids=lambda f: f.__name__.strip("_"),
)
def test_a_stored_prediction_is_recomputed_once_its_inputs_change(db_session, monkeypatch, change):
    # Tomorrow: once a match has kicked off its prediction is final and never recomputed.
    match = _fixture(db_session, "stale", when=datetime.now() + timedelta(days=1))
    predict_for_matches(db_session, [match])
    _settle(db_session, match)

    # Control: with nothing newer than the row, it is still current.
    spy = _Spy(monkeypatch)
    predict_for_matches(db_session, [match], allow_stored=True)
    assert spy.calls == []

    change(db_session, match)
    db_session.refresh(match)
    predict_for_matches(db_session, [match], allow_stored=True)

    assert spy.calls == [match.id]


def test_a_recompute_makes_the_row_current_again_even_if_nothing_changed(db_session, monkeypatch):
    """`onupdate` does not fire for an identical recomputation, so the stamp is
    written explicitly; otherwise a row would stay older than the fixture's last
    edit and be recomputed on every view, forever."""
    # Tomorrow: a match that has kicked off is frozen and never recomputed at all.
    match = _fixture(db_session, "restamp", when=datetime.now() + timedelta(days=1))
    predict_for_matches(db_session, [match])
    _settle(db_session, match)
    # An edit newer than the stored row that changes no value the prediction reads
    # (an odds refresh does exactly this), so the recomputation comes out identical.
    db_session.query(Match).filter(Match.id == match.id).update(
        {Match.updated_at: datetime(2026, 1, 1)}
    )
    db_session.commit()
    db_session.refresh(match)

    spy = _Spy(monkeypatch)
    predict_for_matches(db_session, [match], allow_stored=True)  # stale: recomputes
    predict_for_matches(db_session, [match], allow_stored=True)  # current again
    assert spy.calls == [match.id]


def test_a_result_arriving_leaves_the_published_prediction_and_history_alone(db_session):
    """Once a match has kicked off its prediction is final (see
    `_persist_prediction`): a result arriving must not trigger a recompute that adds a
    hindsight snapshot to the history or replaces what was published. Nothing in the
    application reads the actual score off the history, so there is nothing to stamp."""
    match = _fixture(db_session, "ft")
    predict_for_matches(db_session, [match], allow_stored=True)
    _settle(db_session, match)
    published = db_session.query(Prediction).filter(Prediction.match_id == match.id).one()
    before = (published.prob_home, published.confidence)

    db_session.query(Match).filter(Match.id == match.id).update(
        {
            Match.status: "completed",
            Match.home_score: 3,
            Match.away_score: 0,
            Match.updated_at: LATER,
        }
    )
    db_session.commit()
    db_session.refresh(match)

    predict_for_matches(db_session, [match], allow_stored=True)
    history = db_session.query(PredictionHistory).order_by(PredictionHistory.id).all()
    assert [(h.actual_home_goals, h.actual_away_goals) for h in history] == [(None, None)]
    db_session.refresh(published)
    assert (published.prob_home, published.confidence) == before


# --- writes cannot lose a prediction --------------------------------------


def test_a_failed_write_does_not_lose_the_prediction(db_session, monkeypatch):
    """Storing is bookkeeping. If the commit fails, the computed prediction is
    still returned (it used to come back as None, an empty row on the board)."""
    match = _fixture(db_session, "w1")

    def refuse():
        raise OperationalError("COMMIT", {}, Exception("database is locked"))

    monkeypatch.setattr(db_session, "commit", refuse)

    result = predict_for_matches(db_session, [match])[0]

    assert result is not None
    assert result["match_id"] == match.id


def test_concurrent_first_views_store_one_row_each_and_lose_nothing(monkeypatch):
    """Two threads predicting the same unstored fixtures at once. Unserialised, both
    saw "no row yet" and both inserted; the loser hit the unique constraint (or the
    write lock) and its prediction was dropped."""
    seed = SessionLocal()
    matches = [_fixture(seed, f"c{i}") for i in range(4)]
    ids = [m.id for m in matches]
    seed.close()

    barrier = threading.Barrier(4)

    def predict_all():
        session = SessionLocal()
        try:
            loaded = session.query(Match).filter(Match.id.in_(ids)).order_by(Match.id).all()
            barrier.wait()
            return predict_for_matches(session, loaded)
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=4) as pool:
        outcomes = list(pool.map(lambda _: predict_all(), range(4)))

    assert all(all(r is not None for r in outcome) for outcome in outcomes)
    check = SessionLocal()
    try:
        assert check.query(func.count(Prediction.id)).scalar() == 4
    finally:
        check.close()


# --- the coalescing cache --------------------------------------------------


def test_simultaneous_callers_share_one_computation():
    cache = CoalescingCache(ttl_seconds=60)
    runs, gate = [], threading.Event()

    def compute():
        runs.append(1)
        gate.wait(5)
        return {"rows": [1, 2, 3]}

    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = [pool.submit(cache.get_or_compute, "day", compute) for _ in range(10)]
        time.sleep(0.2)  # let every caller reach the cache while the leader is busy
        gate.set()
        results = [f.result(timeout=10) for f in futures]

    assert len(runs) == 1
    assert all(r == {"rows": [1, 2, 3]} for r in results)


def test_callers_get_their_own_copy():
    cache = CoalescingCache(ttl_seconds=60)
    first = cache.get_or_compute("k", lambda: {"rows": [1]})
    first["rows"].append("scribbled on by a route")
    assert cache.get_or_compute("k", lambda: {"rows": [99]}) == {"rows": [1]}


def test_a_result_is_reused_until_it_expires():
    cache = CoalescingCache(ttl_seconds=0.15)
    runs = []

    def compute():
        runs.append(1)
        return len(runs)

    assert cache.get_or_compute("k", compute) == 1
    assert cache.get_or_compute("k", compute) == 1
    time.sleep(0.25)
    assert cache.get_or_compute("k", compute) == 2


def test_different_keys_are_computed_separately():
    cache = CoalescingCache(ttl_seconds=60)
    assert cache.get_or_compute("a", lambda: "A") == "A"
    assert cache.get_or_compute("b", lambda: "B") == "B"


def test_a_failure_is_not_cached_and_does_not_fail_the_waiters():
    cache = CoalescingCache(ttl_seconds=60)
    attempts, gate = [], threading.Event()

    def compute():
        attempts.append(1)
        if len(attempts) == 1:
            gate.wait(5)
            raise RuntimeError("database is locked")
        return "ok"

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(cache.get_or_compute, "k", compute) for _ in range(4)]
        time.sleep(0.2)
        gate.set()
        outcomes = []
        for f in futures:
            try:
                outcomes.append(f.result(timeout=10))
            except RuntimeError:
                outcomes.append("raised")

    # Exactly the leader saw the error; everyone else got a real answer.
    assert outcomes.count("raised") == 1
    assert outcomes.count("ok") == 3
    assert cache.get_or_compute("k", compute) == "ok"


def test_only_a_bounded_number_of_computations_run_at_once():
    cache = CoalescingCache(ttl_seconds=60, max_concurrent=2)
    running, peak, lock = 0, 0, threading.Lock()

    def compute():
        nonlocal running, peak
        with lock:
            running += 1
            peak = max(peak, running)
        time.sleep(0.1)
        with lock:
            running -= 1
        return "x"

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda i: cache.get_or_compute(i, compute), range(8)))

    assert peak == 2


def test_clear_forgets_stored_results():
    cache = CoalescingCache(ttl_seconds=60)
    assert cache.get_or_compute("k", lambda: 1) == 1
    cache.clear()
    assert cache.get_or_compute("k", lambda: 2) == 2


# --- the routes, under concurrent requests ---------------------------------


def _get(path: str):
    # One client per thread: a TestClient is not meant to be shared between them.
    return TestClient(app).get(path)


def test_ten_simultaneous_board_requests_all_succeed_and_compute_once(monkeypatch):
    seed = SessionLocal()
    matches = [_fixture(seed, f"b{i}") for i in range(5)]
    day = matches[0].match_date.date().isoformat()
    ids = [m.id for m in matches]
    seed.close()
    spy = _Spy(monkeypatch)

    with ThreadPoolExecutor(max_workers=10) as pool:
        responses = list(pool.map(lambda _: _get(f"/board?on_date={day}"), range(10)))

    assert [r.status_code for r in responses] == [200] * 10
    for response in responses:
        counts = response.json()["counts"]
        assert counts["fixtures"] == 5
        assert counts["predicted"] == 5
    # Five fixtures, computed once each — not ten times five.
    assert sorted(spy.calls) == sorted(ids)


def test_boards_that_differ_only_in_a_filter_still_all_succeed(monkeypatch, caplog):
    """These do not share a cache entry, so they genuinely run side by side and
    store the same fixtures' predictions at once — the original failure."""
    seed = SessionLocal()
    matches = [_fixture(seed, f"d{i}") for i in range(6)]
    day = matches[0].match_date.date().isoformat()
    seed.close()

    paths = [f"/board?on_date={day}&limit={400 - i}" for i in range(6)]
    with caplog.at_level("WARNING"), ThreadPoolExecutor(max_workers=6) as pool:
        responses = list(pool.map(_get, paths))

    assert [r.status_code for r in responses] == [200] * 6
    assert all(r.json()["counts"]["predicted"] == 6 for r in responses)
    assert "database is locked" not in caplog.text
    assert "Batch prediction failed" not in caplog.text
    check = SessionLocal()
    try:
        assert check.query(func.count(Prediction.id)).scalar() == 6
    finally:
        check.close()


def test_three_days_at_once_all_succeed(monkeypatch, caplog):
    """What the home page does: yesterday, today and tomorrow together."""
    seed = SessionLocal()
    base = datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)
    for offset in (-1, 0, 1):
        for i in range(3):
            _fixture(seed, f"t{offset}-{i}", when=base + timedelta(days=offset, minutes=i))
    seed.close()

    paths = [f"/board?on_date={(base + timedelta(days=o)).date().isoformat()}" for o in (-1, 0, 1)]
    with caplog.at_level("WARNING"), ThreadPoolExecutor(max_workers=3) as pool:
        responses = list(pool.map(_get, paths))

    assert [r.status_code for r in responses] == [200] * 3
    assert all(r.json()["counts"]["predicted"] == 3 for r in responses)
    assert "database is locked" not in caplog.text


def test_a_second_board_request_is_served_from_the_stored_predictions(monkeypatch):
    seed = SessionLocal()
    matches = [_fixture(seed, f"r{i}") for i in range(3)]
    day = matches[0].match_date.date().isoformat()
    seed.close()

    first = _get(f"/board?on_date={day}")
    assert first.json()["counts"]["predicted"] == 3

    # A different request (so not the in-process copy) after the cache is dropped.
    clear_all_caches()
    spy = _Spy(monkeypatch)
    second = _get(f"/board?on_date={day}")

    assert spy.calls == []
    assert second.json() == first.json()


def test_bankers_and_slip_share_one_priced_day(monkeypatch):
    seed = SessionLocal()
    matches = [_fixture(seed, f"k{i}") for i in range(3)]
    day = matches[0].match_date.date().isoformat()
    ids = [m.id for m in matches]
    seed.close()
    spy = _Spy(monkeypatch)

    with ThreadPoolExecutor(max_workers=6) as pool:
        responses = list(
            pool.map(
                _get,
                [f"/bankers?on_date={day}", f"/slip?on_date={day}"] * 3,
            )
        )

    assert [r.status_code for r in responses] == [200] * 6
    assert sorted(spy.calls) == sorted(ids)


def test_the_database_runs_in_wal_mode():
    """What lets a reader proceed while another request commits."""
    session = SessionLocal()
    try:
        assert session.execute(text("PRAGMA journal_mode")).scalar() == "wal"
    finally:
        session.close()
