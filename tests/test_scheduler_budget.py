"""The scheduler must be safe to switch on, and must keep the data current.

Two failures this pins, both silent until it is too late:

- With the scheduler on, one greedy job could spend a free plan's whole day.
  The injury sync looped over every team in the database (3,467, tennis players
  included) and would have used the quota at 03:30, leaving every other job to
  fail until midnight.
- The daily refresh fetched the Premier League's 2024-25 season and nothing
  else, so even a running scheduler would have left the whole domestic record
  frozen — which is exactly how it went a year stale.
"""

from __future__ import annotations

import math
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest

import app.scheduler as scheduler
from app.models import Match, Team
from app.services import api_budget
from app.utils.seasons import european_season_code, season_codes_to_refresh


def _status(used=0, limit=100, plan="Free"):
    return {"used": used, "limit": limit, "plan": plan}


def _settings(key="a-key"):
    return SimpleNamespace(
        enable_scheduler=True,
        api_football_key=key,
        api_football_base_url="https://api.example",
    )


@pytest.fixture
def job_env(monkeypatch):
    """A scheduler with a key and a controllable quota."""
    state = {"status": _status()}
    monkeypatch.setattr(scheduler, "get_settings", lambda: _settings())
    monkeypatch.setattr(scheduler, "api_status", lambda settings: state["status"])
    return state


# --- reading the quota -------------------------------------------------------


class _Response:
    def __init__(self, payload, status=200):
        self._payload, self.status_code = payload, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def _api_returns(monkeypatch, payload, status=200):
    monkeypatch.setattr(api_budget.requests, "get", lambda *a, **k: _Response(payload, status))


GOOD = {
    "response": {"subscription": {"plan": "Free"}, "requests": {"current": 8, "limit_day": 100}}
}


def test_the_quota_is_read_from_the_api_itself(monkeypatch):
    _api_returns(monkeypatch, GOOD)
    assert api_budget.api_status(_settings()) == {"used": 8, "limit": 100, "plan": "Free"}
    assert api_budget.remaining_requests(_settings()) == 92


def test_an_unreadable_status_is_unknown_not_a_guess(monkeypatch):
    _api_returns(monkeypatch, {"response": []})
    assert api_budget.api_status(_settings()) is None
    _api_returns(monkeypatch, GOOD, status=500)
    assert api_budget.api_status(_settings()) is None
    assert api_budget.api_status(_settings(key=None)) is None


def test_it_fails_closed_when_the_status_cannot_be_read(monkeypatch):
    _api_returns(monkeypatch, GOOD, status=500)
    assert api_budget.can_spend(_settings(), 1) is False
    assert api_budget.is_paid_plan(_settings()) is False


def test_spending_must_fit_with_a_margin_to_spare(monkeypatch):
    _api_returns(monkeypatch, GOOD)  # 92 left
    margin = api_budget.MARGIN
    assert api_budget.can_spend(_settings(), 92 - margin) is True
    assert api_budget.can_spend(_settings(), 92 - margin + 1) is False


def test_a_paid_plan_is_recognised_by_its_daily_limit(monkeypatch):
    _api_returns(monkeypatch, {"response": {"requests": {"current": 0, "limit_day": 7500}}})
    assert api_budget.is_paid_plan(_settings()) is True
    _api_returns(monkeypatch, GOOD)
    assert api_budget.is_paid_plan(_settings()) is False


# --- the arithmetic of the free plan -----------------------------------------


def _runs_per_day(cron: dict) -> int:
    hour = cron["hour"]
    return math.ceil(24 / int(hour[2:])) if isinstance(hour, str) else 1


def test_the_free_profiles_worst_case_day_fits_in_the_free_quota():
    """The numbers in PROFILES are chosen to sum under 100. If a cadence or a cap
    is changed, this is what stops the budget quietly breaking."""
    p = scheduler.PROFILES["free"]
    per_day = {
        "fixtures": _runs_per_day(p["fixtures"]["cron"]) * p["fixtures"]["days"],
        "odds": _runs_per_day(p["odds"]["cron"])
        * (p["odds"]["days"] * scheduler.ODDS_PAGES_PER_DAY + p["odds"]["backfill"]),
        "results": _runs_per_day(p["results"]["cron"]) * p["results"]["days"],
        "stats": _runs_per_day(p["stats"]["cron"]) * 2 * p["stats"]["fixtures"],
        "injuries": 2 * p["injuries"]["teams"],  # one daily run
    }
    assert sum(per_day.values()) <= 100, per_day


def test_a_single_free_plan_run_never_costs_more_than_the_margin_allows_for_a_second():
    """No one job may be able to eat the day on its own."""
    p = scheduler.PROFILES["free"]
    biggest = max(
        p["odds"]["days"] * scheduler.ODDS_PAGES_PER_DAY + p["odds"]["backfill"],
        2 * p["stats"]["fixtures"],
        2 * p["injuries"]["teams"],
    )
    assert biggest <= 40


# --- jobs run only when they fit -----------------------------------------------


def _capture(monkeypatch, module, name):
    calls = []
    monkeypatch.setattr(module, name, lambda *a, **k: calls.append((a, k)) or 0)
    return calls


def test_fixtures_look_only_as_far_ahead_as_the_free_plan_can_answer(monkeypatch, job_env):
    import scripts.fetch_upcoming_fixtures as target

    calls = _capture(monkeypatch, target, "main")
    scheduler.fetch_upcoming_fixtures_job()
    assert calls == [((["--days", "3"],), {})]


def test_a_paid_plan_looks_a_week_ahead(monkeypatch, job_env):
    import scripts.fetch_upcoming_fixtures as target

    job_env["status"] = _status(limit=7500, plan="Pro")
    calls = _capture(monkeypatch, target, "main")
    scheduler.fetch_upcoming_fixtures_job()
    assert calls == [((["--days", "7"],), {})]


def test_odds_carry_the_per_plan_backfill_cap(monkeypatch, job_env):
    import scripts.fetch_odds as target

    calls = _capture(monkeypatch, target, "main")
    scheduler.fetch_odds_job()
    assert calls == [((["--days", "3", "--max-backfill", "10"],), {})]


def test_results_and_stats_are_capped_by_plan(monkeypatch, job_env):
    import scripts.fetch_match_stats as stats
    import scripts.fetch_results as results

    result_calls = _capture(monkeypatch, results, "fetch_and_apply_results")
    stats_calls = _capture(monkeypatch, stats, "fetch_and_apply_match_stats")
    scheduler.fetch_results_job()
    scheduler.fetch_match_stats_job()
    assert result_calls == [((), {"days_back": 3})]
    assert stats_calls == [((), {"max_fixtures": 10})]


@pytest.mark.parametrize(
    "job,module,name",
    [
        ("fetch_upcoming_fixtures_job", "scripts.fetch_upcoming_fixtures", "main"),
        ("fetch_odds_job", "scripts.fetch_odds", "main"),
        ("fetch_results_job", "scripts.fetch_results", "fetch_and_apply_results"),
        ("fetch_match_stats_job", "scripts.fetch_match_stats", "fetch_and_apply_match_stats"),
    ],
)
class TestAJobThatDoesNotFit:
    def test_is_skipped_when_the_day_is_nearly_spent(self, monkeypatch, job_env, job, module, name):
        import importlib

        calls = _capture(monkeypatch, importlib.import_module(module), name)
        job_env["status"] = _status(used=98)
        getattr(scheduler, job)()
        assert calls == []

    def test_is_skipped_when_the_quota_cannot_be_read(
        self, monkeypatch, job_env, job, module, name
    ):
        import importlib

        calls = _capture(monkeypatch, importlib.import_module(module), name)
        job_env["status"] = None
        getattr(scheduler, job)()
        assert calls == []

    def test_is_skipped_without_an_api_key(self, monkeypatch, job_env, job, module, name):
        import importlib

        calls = _capture(monkeypatch, importlib.import_module(module), name)
        monkeypatch.setattr(scheduler, "get_settings", lambda: _settings(key=None))
        getattr(scheduler, job)()
        assert calls == []


# --- injuries: only teams that are about to play -------------------------------


def _fixture(db_session, home, away, when, status="scheduled", sport="football"):
    db_session.add(
        Match(
            match_date=when,
            competition="English Premier League",
            season="2026-2027",
            home_team_id=home.id,
            away_team_id=away.id,
            status=status,
            sport=sport,
        )
    )


def test_injuries_are_synced_only_for_teams_playing_in_the_next_few_days(
    monkeypatch, job_env, db_session
):
    import scripts.sync_injuries as target

    names = ["Soon A", "Soon B", "Later C", "Later D", "Idle E", "Done F", "Done G"]
    teams = {n: Team(name=n, league="x", sport="football") for n in names}
    db_session.add_all(teams.values())
    db_session.flush()
    now = datetime.now(UTC).replace(tzinfo=None)
    _fixture(db_session, teams["Soon A"], teams["Soon B"], now + timedelta(hours=20))
    _fixture(db_session, teams["Later C"], teams["Later D"], now + timedelta(days=9))
    _fixture(db_session, teams["Done F"], teams["Done G"], now - timedelta(days=1), "completed")
    db_session.commit()

    synced = []
    monkeypatch.setattr(target, "sync_team_injuries", lambda s, team, st: synced.append(team.name))
    scheduler.sync_injuries_job()

    assert synced == ["Soon A", "Soon B"]


def test_the_injury_sync_is_capped_and_takes_the_soonest_kickoffs_first(db_session):
    now = datetime.now(UTC).replace(tzinfo=None)
    teams = [Team(name=f"Club {i}", league="x", sport="football") for i in range(30)]
    db_session.add_all(teams)
    db_session.flush()
    for i in range(0, 30, 2):
        _fixture(db_session, teams[i], teams[i + 1], now + timedelta(hours=1 + i))
    db_session.commit()

    picked = scheduler._teams_playing_soon(db_session, limit=6)

    assert [t.name for t in picked] == [f"Club {i}" for i in range(6)]


def test_tennis_players_and_basketball_franchises_are_never_synced(db_session):
    now = datetime.now(UTC).replace(tzinfo=None)
    a = Team(name="Player A", league="x", sport="tennis")
    b = Team(name="Player B", league="x", sport="tennis")
    db_session.add_all([a, b])
    db_session.flush()
    _fixture(db_session, a, b, now + timedelta(hours=5), sport="tennis")
    db_session.commit()

    assert scheduler._teams_playing_soon(db_session, limit=10) == []


# --- cadence follows the plan ----------------------------------------------------


def _hours(started):
    out = {}
    for job in started.get_jobs():
        if not hasattr(job.trigger, "fields"):
            continue  # an interval job (the strip canary) has no hour field and no API cost
        hour = next(f for f in job.trigger.fields if f.name == "hour")
        out[job.id] = str(hour)
    return out


@pytest.fixture
def fresh_scheduler(monkeypatch):
    monkeypatch.setattr(scheduler, "needs_catch_up", lambda: False)
    scheduler._scheduler = None
    yield
    scheduler.stop_scheduler()


def test_a_free_account_gets_the_quota_safe_cadence(monkeypatch, fresh_scheduler):
    monkeypatch.setattr(scheduler, "get_settings", lambda: _settings())
    monkeypatch.setattr(scheduler, "is_paid_plan", lambda s: False)
    hours = _hours(scheduler.start_scheduler())
    assert hours["fetch_upcoming_fixtures"] == "*/8"
    assert hours["fetch_odds"] == "*/12"
    assert hours["fetch_results"] == "*/6"
    assert hours["fetch_match_stats"] == "5"


def test_a_paid_account_gets_the_busier_cadence(monkeypatch, fresh_scheduler):
    monkeypatch.setattr(scheduler, "get_settings", lambda: _settings())
    monkeypatch.setattr(scheduler, "is_paid_plan", lambda s: True)
    hours = _hours(scheduler.start_scheduler())
    assert hours["fetch_upcoming_fixtures"] == "*/4"
    # Results run every 15 minutes (a cron on the minute, so the hour field is "any").
    assert hours["fetch_results"] == "*"
    assert scheduler.PROFILES["paid"]["results"]["cron"] == {"minute": "*/15"}


# --- the daily refresh keeps the free data current ---------------------------------


@pytest.fixture
def refresh_env(monkeypatch, tmp_path):
    # The refresh records when it finished; keep that out of the real data folder.
    monkeypatch.setattr(scheduler, "PROCESSED_DIR", tmp_path)
    monkeypatch.setattr(scheduler, "LAST_REFRESH_MARKER", tmp_path / "last_refresh.txt")
    import scripts.clean_data as clean
    import scripts.download_data as download
    import scripts.fetch_extra_league as extra
    import scripts.load_to_db as load

    log = {"downloads": [], "extras": [], "order": []}

    def fake_download(league, code, *a, **k):
        log["downloads"].append((league, code))
        return None if league == "SC0" else "path"

    def fake_extra(country, league, code, years, *a, **k):
        if country == "USA":
            raise RuntimeError("source is down")
        log["extras"].append((country, tuple(years)))
        return ["file"]

    monkeypatch.setattr(download, "download_season", fake_download)
    monkeypatch.setattr(extra, "write_seasons", fake_extra)
    monkeypatch.setattr(clean, "main", lambda: log["order"].append("clean"))
    monkeypatch.setattr(load, "main", lambda: log["order"].append("load"))
    monkeypatch.setattr(scheduler, "season_codes_to_refresh", lambda today: ["2627"])
    return log


def test_the_refresh_pulls_every_league_for_the_current_season(refresh_env):
    from scripts.download_data import KNOWN_LEAGUES

    scheduler.refresh_data_job()

    assert {league for league, _ in refresh_env["downloads"]} == set(KNOWN_LEAGUES)
    assert {code for _, code in refresh_env["downloads"]} == {"2627"}
    assert len(KNOWN_LEAGUES) >= 19  # the lower English tiers are among them


def test_the_refresh_pulls_every_country_file_and_both_candidate_years(refresh_env):
    from scripts.fetch_extra_league import EXTRA_LEAGUES

    scheduler.refresh_data_job()

    year = datetime.now(UTC).year
    fetched = dict(refresh_env["extras"])
    # USA's source "was down", so it is the only one missing — and it did not
    # stop the other fifteen.
    assert set(fetched) == {spec.country for spec in EXTRA_LEAGUES} - {"USA"}
    assert all(years == (year - 1, year) for years in fetched.values())


def test_one_failure_does_not_stop_the_refresh_and_the_load_still_happens(refresh_env):
    scheduler.refresh_data_job()
    assert refresh_env["order"] == ["clean", "load"]


# --- the helpers and the league table ------------------------------------------------


def test_the_season_code_follows_the_football_calendar():
    assert european_season_code(date(2026, 10, 7)) == "2627"
    assert european_season_code(date(2027, 3, 1)) == "2627"
    assert european_season_code(date(2026, 7, 1)) == "2627"
    assert european_season_code(date(2026, 6, 30)) == "2526"
    assert european_season_code(date(2027, 12, 31)) == "2728"


def test_the_previous_season_is_also_pulled_through_the_summer_only():
    assert season_codes_to_refresh(date(2026, 8, 15)) == ["2627", "2526"]
    assert season_codes_to_refresh(date(2026, 10, 7)) == ["2627"]
    assert season_codes_to_refresh(date(2027, 5, 1)) == ["2627"]


def test_every_league_the_free_source_supplies_is_in_the_refresh():
    """A league missing from these tables is a league that silently stops
    updating, so the tables must account for every code the pipeline knows."""
    from scripts.clean_data import LEAGUE_NAMES
    from scripts.download_data import KNOWN_LEAGUES
    from scripts.fetch_extra_league import EXTRA_LEAGUES

    api_sourced = {"SAU1", "WC", "EURO", "UNL", "COPA", "AFCON", "AFCONQ", "FRND"}
    covered = set(KNOWN_LEAGUES) | {spec.code for spec in EXTRA_LEAGUES} | api_sourced
    assert set(LEAGUE_NAMES) == covered, set(LEAGUE_NAMES) ^ covered


@pytest.mark.parametrize(
    "status",
    [_status(used=98), None],
    ids=["quota nearly spent", "quota unreadable"],
)
def test_the_injury_sync_is_skipped_when_it_does_not_fit_even_with_teams_to_sync(
    monkeypatch, job_env, db_session, status
):
    """Seeded with real fixtures, so an empty result can only be the guard."""
    import scripts.sync_injuries as target

    a = Team(name="Playing A", league="x", sport="football")
    b = Team(name="Playing B", league="x", sport="football")
    db_session.add_all([a, b])
    db_session.flush()
    _fixture(db_session, a, b, datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=6))
    db_session.commit()

    synced = []
    monkeypatch.setattr(target, "sync_team_injuries", lambda s, team, st: synced.append(team.name))

    job_env["status"] = status
    scheduler.sync_injuries_job()
    assert synced == []

    job_env["status"] = _status()  # the same fixtures, with room in the day
    scheduler.sync_injuries_job()
    assert synced == ["Playing A", "Playing B"]


def test_the_injury_sync_is_skipped_without_an_api_key(monkeypatch, job_env, db_session):
    import scripts.sync_injuries as target

    synced = []
    monkeypatch.setattr(target, "sync_team_injuries", lambda s, team, st: synced.append(team.name))
    monkeypatch.setattr(scheduler, "get_settings", lambda: _settings(key=None))
    scheduler.sync_injuries_job()
    assert synced == []


# --- the retrain is not run inside the web process unless asked for --------------------------


def test_the_weekly_retrain_is_off_unless_it_is_asked_for(monkeypatch, fresh_scheduler):
    monkeypatch.setattr(scheduler, "get_settings", lambda: _settings())
    monkeypatch.setattr(scheduler, "is_paid_plan", lambda s: True)
    started = scheduler.start_scheduler()
    assert "weekly_retrain" not in {job.id for job in started.get_jobs()}


def test_the_weekly_retrain_can_still_be_switched_on(monkeypatch, fresh_scheduler):
    settings = _settings()
    settings.enable_weekly_retrain = True
    monkeypatch.setattr(scheduler, "get_settings", lambda: settings)
    monkeypatch.setattr(scheduler, "is_paid_plan", lambda s: True)
    started = scheduler.start_scheduler()
    assert "weekly_retrain" in {job.id for job in started.get_jobs()}


# --- a start-up that could not read the plan is corrected, not stranded ----------------------


def _live_minutes(started):
    job = next(j for j in started.get_jobs() if j.id == "fetch_live")
    return job.trigger.interval.total_seconds() / 60


def test_a_plan_read_wrongly_at_start_is_corrected_by_the_watcher(monkeypatch, fresh_scheduler):
    monkeypatch.setattr(scheduler, "get_settings", lambda: _settings())
    monkeypatch.setattr(scheduler, "is_paid_plan", lambda s: False)  # the start-up read failed
    started = scheduler.start_scheduler()
    assert _live_minutes(started) == scheduler.PROFILES["free"]["live"]["minutes"]

    monkeypatch.setattr(
        scheduler, "api_status", lambda s: {"used": 5, "limit": 7500, "plan": "Pro"}
    )
    scheduler.plan_watch_job()

    assert _live_minutes(started) == scheduler.PROFILES["paid"]["live"]["minutes"]


def test_the_watcher_changes_nothing_when_the_plan_cannot_be_read(monkeypatch, fresh_scheduler):
    monkeypatch.setattr(scheduler, "get_settings", lambda: _settings())
    monkeypatch.setattr(scheduler, "is_paid_plan", lambda s: True)
    started = scheduler.start_scheduler()
    before = _live_minutes(started)

    monkeypatch.setattr(scheduler, "api_status", lambda s: None)
    scheduler.plan_watch_job()

    assert _live_minutes(started) == before
