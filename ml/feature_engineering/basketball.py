"""Walk-forward feature engineering for basketball.

Separate from `features.py` because almost nothing in the football feature
set means anything here. Football features are built around a low-count
goal process with three outcomes; basketball is a high-count scoring process
with two. Concretely:

- **No draws.** Of 1,311 finished NBA games in one checked season, zero were
  ties — the league plays overtime until one side wins. So there is no
  draw rate to model and no "points per game" (3-1-0) table; the form
  feature is a plain win rate.
- **Scoring is ~100x football's.** Teams average ~113 points each. Rolling
  goals-scored/conceded counts still apply in spirit, but the useful signal
  is *pace and efficiency* (points for/against per game), not totals.
- **Rest matters differently.** The football feature set already has
  `home_rest_days`/`home_fixture_congestion`, so rest itself is not new —
  what is new is the *back-to-back*, an NBA team playing on consecutive
  nights, which essentially never happens in league football. That is why
  `is_back_to_back` is a distinct flag here rather than something the
  continuous rest-days value already captures.

What *is* shared: `TeamHistoryIndex` from `features.py` — it's a
sport-agnostic "this team's prior matches, sorted, O(log k) lookup" index,
and the same leakage rule applies here as everywhere else in this codebase:
only matches strictly *before* the target match's date are ever read.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ml.feature_engineering.features import TeamHistoryIndex, _team_matches_before

# How many recent games the rolling form/pace features average over. Ten is
# a common basketball convention ("last 10" is a standings column in the NBA)
# and spans ~3 weeks of a dense schedule, so it reflects current form without
# being dominated by a single result the way a last-3 window would.
FORM_WINDOW = 10

# A team playing its second game in as many days. Measured in days between
# tip-offs, so 1 means "played yesterday"; 0 would mean a same-day
# double-header, which doesn't happen in the leagues here but costs nothing
# to treat the same way.
BACK_TO_BACK_MAX_REST_DAYS = 1

FEATURE_COLUMNS = [
    "elo_home",
    "elo_away",
    "elo_diff",
    "home_avg_points_scored",
    "home_avg_points_conceded",
    "away_avg_points_scored",
    "away_avg_points_conceded",
    "home_win_rate",
    "away_win_rate",
    "home_rest_days",
    "away_rest_days",
    "home_back_to_back",
    "away_back_to_back",
    "h2h_home_win_rate",
]


@dataclass
class TeamPace:
    """Rolling scoring profile over a team's last `FORM_WINDOW` games."""

    games: int = 0
    wins: int = 0
    points_scored: int = 0
    points_conceded: int = 0

    @property
    def win_rate(self) -> float:
        return self.wins / self.games if self.games else 0.0

    @property
    def avg_points_scored(self) -> float:
        return self.points_scored / self.games if self.games else 0.0

    @property
    def avg_points_conceded(self) -> float:
        return self.points_conceded / self.games if self.games else 0.0


def compute_team_pace(
    team: str,
    history: list[dict] | TeamHistoryIndex,
    before_date: datetime,
    window: int = FORM_WINDOW,
) -> TeamPace:
    """`team`'s rolling profile from its last `window` games before `before_date`."""
    prior = _team_matches_before(team, history, before_date)[-window:]
    pace = TeamPace()
    for m in prior:
        is_home = m["home_team"] == team
        scored = m["home_score"] if is_home else m["away_score"]
        conceded = m["away_score"] if is_home else m["home_score"]
        if scored is None or conceded is None:
            continue
        pace.games += 1
        pace.points_scored += int(scored)
        pace.points_conceded += int(conceded)
        if scored > conceded:
            pace.wins += 1
    return pace


def compute_rest_days(
    team: str,
    history: list[dict] | TeamHistoryIndex,
    before_date: datetime,
    cap_days: float = 14.0,
) -> float:
    """Days since `team`'s previous game, capped at `cap_days`.

    Capped because the gap before a team's first game of a season (or its
    first game in the dataset) is either meaningless or unbounded, and an
    uncapped value would hand the model a number that encodes "start of
    season" rather than "rested" — two very different things. A team with no
    prior game returns the cap, i.e. maximally rested, which is the right
    reading for a season opener.
    """
    prior = _team_matches_before(team, history, before_date)
    if not prior:
        return cap_days
    delta = before_date - prior[-1]["match_date"]
    return min(float(delta.days), cap_days)


def compute_h2h_home_win_rate(
    home_team: str,
    away_team: str,
    history: list[dict] | TeamHistoryIndex,
    before_date: datetime,
) -> float:
    """Share of prior meetings `home_team` won, from either venue.

    Returns 0.5 when they've never met — a neutral prior, not 0.0, which
    would otherwise read as "lost every meeting".
    """
    prior = [
        m
        for m in _team_matches_before(home_team, history, before_date)
        if away_team in (m["home_team"], m["away_team"])
    ]
    if not prior:
        return 0.5
    wins = 0
    for m in prior:
        home_won = m["home_score"] > m["away_score"]
        if (m["home_team"] == home_team and home_won) or (
            m["away_team"] == home_team and not home_won
        ):
            wins += 1
    return wins / len(prior)


def build_game_features(
    home_team: str,
    away_team: str,
    match_date: datetime,
    history: list[dict] | TeamHistoryIndex,
    elo_home: float,
    elo_away: float,
) -> dict:
    """The full basketball feature row for one game, from prior games only."""
    home_pace = compute_team_pace(home_team, history, match_date)
    away_pace = compute_team_pace(away_team, history, match_date)
    home_rest = compute_rest_days(home_team, history, match_date)
    away_rest = compute_rest_days(away_team, history, match_date)

    return {
        "elo_home": elo_home,
        "elo_away": elo_away,
        "elo_diff": elo_home - elo_away,
        "home_avg_points_scored": home_pace.avg_points_scored,
        "home_avg_points_conceded": home_pace.avg_points_conceded,
        "away_avg_points_scored": away_pace.avg_points_scored,
        "away_avg_points_conceded": away_pace.avg_points_conceded,
        "home_win_rate": home_pace.win_rate,
        "away_win_rate": away_pace.win_rate,
        "home_rest_days": home_rest,
        "away_rest_days": away_rest,
        "home_back_to_back": float(home_rest <= BACK_TO_BACK_MAX_REST_DAYS),
        "away_back_to_back": float(away_rest <= BACK_TO_BACK_MAX_REST_DAYS),
        "h2h_home_win_rate": compute_h2h_home_win_rate(home_team, away_team, history, match_date),
    }
