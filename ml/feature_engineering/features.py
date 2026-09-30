"""Leakage-safe feature engineering.

Every function here takes the target match plus a list of *prior* matches
(chronologically before the target) and computes features purely from that
prior history. Nothing here ever looks at the target match's own result or at
any match on/after its date — callers are responsible for filtering the
history list, and `build_match_features` re-asserts this by filtering
defensively itself.

`history` accepts either a plain `list[dict]` (fine for a single prediction,
or a small dataset — an O(n) scan per lookup) or a pre-built
`TeamHistoryIndex` (`build_team_history_index`), which turns each lookup
into an O(log k) bisect against that team's own matches (k), not a scan of
the whole dataset (n). The difference only matters once n gets large:
`ml.training.common.build_feature_frame`'s walk-forward loop calls these
functions once per match in the *entire* training set, so without the
index it degrades to O(n^2) overall — measured at ~56 minutes for an
18,000-match, 5-league dataset; with the index, low single-digit minutes.
Every public function here still accepts a plain list unchanged, so
existing callers and tests are unaffected.
"""

from __future__ import annotations

import bisect
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class TeamHistoryIndex:
    """Every match grouped by team (both home and away appearances), each
    per-team list sorted ascending by date — build once per dataset with
    `build_team_history_index`, then pass in place of a raw match list."""

    by_team: dict[str, list[dict]] = field(default_factory=dict)


def build_team_history_index(history: list[dict]) -> TeamHistoryIndex:
    by_team: dict[str, list[dict]] = defaultdict(list)
    for m in history:
        by_team[m["home_team"]].append(m)
        by_team[m["away_team"]].append(m)
    for matches in by_team.values():
        matches.sort(key=lambda m: m["match_date"])
    return TeamHistoryIndex(by_team=dict(by_team))


@dataclass
class TeamForm:
    matches_played: int = 0
    wins: int = 0
    draws: int = 0
    losses: int = 0
    goals_scored: int = 0
    goals_conceded: int = 0
    clean_sheets: int = 0

    @property
    def points(self) -> int:
        return self.wins * 3 + self.draws

    @property
    def goal_difference(self) -> int:
        return self.goals_scored - self.goals_conceded

    @property
    def points_per_game(self) -> float:
        return self.points / self.matches_played if self.matches_played else 0.0

    @property
    def avg_goals_scored(self) -> float:
        return self.goals_scored / self.matches_played if self.matches_played else 0.0

    @property
    def avg_goals_conceded(self) -> float:
        return self.goals_conceded / self.matches_played if self.matches_played else 0.0


@dataclass
class GoalRateForm:
    """How often a team's matches cleared common goals-market lines, over
    the same "last n" window `compute_team_form` uses.

    Display-only, for the match page's Form tab — unlike `TeamForm` above,
    nothing here is read by a training pipeline.
    """

    matches_played: int = 0
    over_1_5: int = 0
    over_2_5: int = 0
    over_3_5: int = 0
    btts: int = 0


def _team_matches_before(
    team: str, history: list[dict] | TeamHistoryIndex, before_date: datetime
) -> list[dict]:
    """All of `team`'s matches strictly before `before_date`, ascending by date."""
    if isinstance(history, TeamHistoryIndex):
        team_matches = history.by_team.get(team, [])
        cut = bisect.bisect_left(team_matches, before_date, key=lambda m: m["match_date"])
        return team_matches[:cut]

    relevant = [
        m
        for m in history
        if m["match_date"] < before_date and (m["home_team"] == team or m["away_team"] == team)
    ]
    return sorted(relevant, key=lambda m: m["match_date"])


def _prior_matches(
    team: str, history: list[dict] | TeamHistoryIndex, before_date: datetime
) -> list[dict]:
    """Matches involving `team`, strictly before `before_date`, most-recent first."""
    return list(reversed(_team_matches_before(team, history, before_date)))


def compute_team_form(
    team: str, history: list[dict] | TeamHistoryIndex, before_date: datetime, n: int | None = None
) -> TeamForm:
    """Form over the last `n` matches before `before_date` (all history if n is None)."""
    prior = _prior_matches(team, history, before_date)
    if n is not None:
        prior = prior[:n]

    form = TeamForm()
    for m in prior:
        is_home = m["home_team"] == team
        scored = m["home_score"] if is_home else m["away_score"]
        conceded = m["away_score"] if is_home else m["home_score"]

        form.matches_played += 1
        form.goals_scored += scored
        form.goals_conceded += conceded
        if conceded == 0:
            form.clean_sheets += 1
        if scored > conceded:
            form.wins += 1
        elif scored == conceded:
            form.draws += 1
        else:
            form.losses += 1
    return form


def compute_goal_rate_form(
    team: str, history: list[dict] | TeamHistoryIndex, before_date: datetime, n: int | None = None
) -> GoalRateForm:
    """Over the last `n` matches before `before_date`, how many cleared each
    goals line and how many saw both teams score."""
    prior = _prior_matches(team, history, before_date)
    if n is not None:
        prior = prior[:n]

    form = GoalRateForm(matches_played=len(prior))
    for m in prior:
        total = m["home_score"] + m["away_score"]
        if total > 1.5:
            form.over_1_5 += 1
        if total > 2.5:
            form.over_2_5 += 1
        if total > 3.5:
            form.over_3_5 += 1
        if m["home_score"] > 0 and m["away_score"] > 0:
            form.btts += 1
    return form


def compute_home_away_form(
    team: str,
    history: list[dict] | TeamHistoryIndex,
    before_date: datetime,
    is_home: bool,
    n: int = 10,
) -> TeamForm:
    """Form restricted to matches where `team` played at home (or away), most recent `n`."""
    prior = _prior_matches(team, history, before_date)
    prior = [m for m in prior if (m["home_team"] == team) == is_home][:n]

    form = TeamForm()
    for m in prior:
        scored = m["home_score"] if is_home else m["away_score"]
        conceded = m["away_score"] if is_home else m["home_score"]
        form.matches_played += 1
        form.goals_scored += scored
        form.goals_conceded += conceded
        if conceded == 0:
            form.clean_sheets += 1
        if scored > conceded:
            form.wins += 1
        elif scored == conceded:
            form.draws += 1
        else:
            form.losses += 1
    return form


def compute_rest_days(
    team: str, history: list[dict] | TeamHistoryIndex, before_date: datetime
) -> int | None:
    """Days since `team`'s most recent prior match, or None if it has no history."""
    prior = _prior_matches(team, history, before_date)
    if not prior:
        return None
    return (before_date - prior[0]["match_date"]).days


def compute_fixture_congestion(
    team: str, history: list[dict] | TeamHistoryIndex, before_date: datetime, window_days: int = 14
) -> int:
    """Number of matches `team` played in the `window_days` before `before_date`."""
    prior = _prior_matches(team, history, before_date)
    return sum(1 for m in prior if (before_date - m["match_date"]).days <= window_days)


def compute_head_to_head(
    home_team: str,
    away_team: str,
    history: list[dict] | TeamHistoryIndex,
    before_date: datetime,
    n: int = 5,
) -> dict:
    """Head-to-head record between the two sides from their last `n` meetings.

    Scans `home_team`'s own prior matches (via `_team_matches_before`, index-
    accelerated when available) rather than the whole dataset — cheaper, and
    correct since any meeting between the two teams is necessarily in
    `home_team`'s own match list regardless of which side they were on.
    """
    candidates = _team_matches_before(home_team, history, before_date)
    meetings = [m for m in candidates if {m["home_team"], m["away_team"]} == {home_team, away_team}]
    meetings = sorted(meetings, key=lambda m: m["match_date"], reverse=True)[:n]

    home_wins = draws = away_wins = 0
    for m in meetings:
        home_goals_for_home_team = (
            m["home_score"] if m["home_team"] == home_team else m["away_score"]
        )
        away_goals_for_away_team = (
            m["away_score"] if m["home_team"] == home_team else m["home_score"]
        )
        if home_goals_for_home_team > away_goals_for_away_team:
            home_wins += 1
        elif home_goals_for_home_team == away_goals_for_away_team:
            draws += 1
        else:
            away_wins += 1

    return {
        "h2h_matches_played": len(meetings),
        "h2h_home_team_wins": home_wins,
        "h2h_draws": draws,
        "h2h_away_team_wins": away_wins,
    }


def _is_missing(value) -> bool:
    """True for None and for the NaN a pandas-sourced dict carries for an
    unpopulated numeric column (e.g. corners aren't recorded for every
    league/season — see docs/architecture.md's "Non-native data sources"
    and "Corners and cards" sections) — `value is None` alone misses the
    NaN case, the same gotcha `app.utils.team_names.normalize_team_name`
    hit for team names."""
    return value is None or (isinstance(value, float) and math.isnan(value))


def compute_corner_form(
    team: str, history: list[dict] | TeamHistoryIndex, before_date: datetime, n: int = 10
) -> dict:
    """Average corners won/conceded over the last `n` prior matches that
    actually recorded corners — not every league/season does (MLS and the
    Saudi Pro League have none at all; several others have partial
    coverage), so matches missing it are skipped rather than treated as
    zero corners, which would understate a team's real corner rate.
    Returns `None` for either value if no prior match has corner data.
    """
    prior = _prior_matches(team, history, before_date)[:n]
    won, conceded = [], []
    for m in prior:
        is_home = m["home_team"] == team
        for_value = m.get("home_corners") if is_home else m.get("away_corners")
        against_value = m.get("away_corners") if is_home else m.get("home_corners")
        if not _is_missing(for_value):
            won.append(for_value)
        if not _is_missing(against_value):
            conceded.append(against_value)

    return {
        "avg_corners_won": (sum(won) / len(won)) if won else None,
        "avg_corners_conceded": (sum(conceded) / len(conceded)) if conceded else None,
    }


def build_match_features(
    home_team: str,
    away_team: str,
    match_date: datetime,
    history: list[dict] | TeamHistoryIndex,
    elo_home: float | None = None,
    elo_away: float | None = None,
) -> dict:
    """Build the full leakage-safe feature vector for a fixture.

    `history` may contain matches on/after `match_date` (e.g. the whole
    dataset) — this function filters to strictly-prior matches itself, so
    passing the full dataset is safe and is in fact the expected usage from
    the training pipeline. Pass a `TeamHistoryIndex` (`build_team_history_index`)
    instead of a raw list when calling this in a loop over many matches (e.g.
    walk-forward training) — see the module docstring for why that matters.
    """
    home_form_5 = compute_team_form(home_team, history, match_date, n=5)
    away_form_5 = compute_team_form(away_team, history, match_date, n=5)
    home_form_10 = compute_team_form(home_team, history, match_date, n=10)
    away_form_10 = compute_team_form(away_team, history, match_date, n=10)
    home_home_form = compute_home_away_form(home_team, history, match_date, is_home=True)
    away_away_form = compute_home_away_form(away_team, history, match_date, is_home=False)
    h2h = compute_head_to_head(home_team, away_team, history, match_date)
    home_corner_form = compute_corner_form(home_team, history, match_date)
    away_corner_form = compute_corner_form(away_team, history, match_date)

    features = {
        "home_form5_points_per_game": home_form_5.points_per_game,
        "away_form5_points_per_game": away_form_5.points_per_game,
        "home_form5_goal_diff": home_form_5.goal_difference,
        "away_form5_goal_diff": away_form_5.goal_difference,
        "home_form10_points_per_game": home_form_10.points_per_game,
        "away_form10_points_per_game": away_form_10.points_per_game,
        "home_form10_avg_goals_scored": home_form_10.avg_goals_scored,
        "away_form10_avg_goals_scored": away_form_10.avg_goals_scored,
        "home_form10_avg_goals_conceded": home_form_10.avg_goals_conceded,
        "away_form10_avg_goals_conceded": away_form_10.avg_goals_conceded,
        "home_form10_clean_sheets": home_form_10.clean_sheets,
        "away_form10_clean_sheets": away_form_10.clean_sheets,
        "home_home_form_points_per_game": home_home_form.points_per_game,
        "away_away_form_points_per_game": away_away_form.points_per_game,
        "home_rest_days": compute_rest_days(home_team, history, match_date),
        "away_rest_days": compute_rest_days(away_team, history, match_date),
        "home_fixture_congestion": compute_fixture_congestion(home_team, history, match_date),
        "away_fixture_congestion": compute_fixture_congestion(away_team, history, match_date),
        "elo_home": elo_home,
        "elo_away": elo_away,
        "elo_diff": (
            (elo_home - elo_away) if elo_home is not None and elo_away is not None else None
        ),
        "home_avg_corners_won": home_corner_form["avg_corners_won"],
        "home_avg_corners_conceded": home_corner_form["avg_corners_conceded"],
        "away_avg_corners_won": away_corner_form["avg_corners_won"],
        "away_avg_corners_conceded": away_corner_form["avg_corners_conceded"],
        **h2h,
    }
    return features


FEATURE_COMPLETENESS_KEYS = [
    "home_form10_points_per_game",
    "away_form10_points_per_game",
    "home_rest_days",
    "away_rest_days",
    "elo_diff",
]


def feature_completeness(features: dict) -> float:
    """Fraction of the "important" features that are non-null (used for confidence scoring)."""
    present = sum(1 for k in FEATURE_COMPLETENESS_KEYS if features.get(k) is not None)
    return present / len(FEATURE_COMPLETENESS_KEYS)
