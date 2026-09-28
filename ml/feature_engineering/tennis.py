"""Walk-forward feature engineering for tennis.

The sport's defining modelling fact, and the reason this isn't a variation
on the football or basketball feature sets: **skill is surface-specific.**
A player's clay ability is genuinely a different quantity from their
hard-court ability — it is routine for a top-10 clay player to be ordinary
on grass — so a single rating per player throws away most of the signal.
Every match therefore contributes to two ratings: an overall one and one for
the surface it was played on, and both are offered as features so the model
can weigh them itself rather than having a blend hard-coded for it.

Other structural differences from the team sports here:

- **No home advantage.** The "home"/"away" slots are an arbitrary,
  deterministic assignment made at ingest purely to de-leak the source's
  winner/loser columns (see `scripts/fetch_tennis.py`). They carry no venue
  meaning, which is why every tennis row is stored `neutral_venue=True`.
  Any feature that treated the home slot as advantaged would be modelling
  a hash function.
- **No draws.** Every completed match has a winner on sets.
- **Sets decide, games describe.** `home_score`/`away_score` are sets;
  `home_games`/`away_games` are total games, which is what the totals
  market is priced on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from ml.feature_engineering.features import TeamHistoryIndex, _team_matches_before

# Rolling window for form. Tennis players compete far less often than a
# basketball team (a busy season is ~70 matches, many in short tournament
# bursts), so a 20-match window covers a meaningful stretch of a season
# without reaching back into a prior year's form.
FORM_WINDOW = 20

FEATURE_COLUMNS = [
    "elo_home",
    "elo_away",
    "elo_diff",
    "elo_surface_home",
    "elo_surface_away",
    "elo_surface_diff",
    "home_win_rate",
    "away_win_rate",
    "home_surface_win_rate",
    "away_surface_win_rate",
    "home_avg_games_won",
    "home_avg_games_lost",
    "away_avg_games_won",
    "away_avg_games_lost",
    "h2h_home_win_rate",
    "home_matches_played",
    "away_matches_played",
    # Match format: 3 or 5 sets. Roughly caps total games, so it matters a
    # great deal to the totals market and barely at all to the winner —
    # offered to both and left for each model to weigh.
    "best_of",
]


@dataclass
class SurfaceElo:
    """Elo ratings kept separately per surface, plus an overall pool.

    Not an `EloEngine` per surface because the update rule needed here is
    the plain two-outcome one — no draws, and no home-advantage offset to
    apply or suppress, since the slots are arbitrary.
    """

    k_factor: float = 24.0
    initial_rating: float = 1500.0
    overall: dict[str, float] = field(default_factory=dict)
    by_surface: dict[str, dict[str, float]] = field(default_factory=dict)

    def get(self, player: str, surface: str | None = None) -> float:
        if surface is None:
            return self.overall.get(player, self.initial_rating)
        return self.by_surface.setdefault(surface, {}).get(player, self.initial_rating)

    @staticmethod
    def expected(rating_a: float, rating_b: float) -> float:
        return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400.0))

    def _update(self, table: dict[str, float], winner: str, loser: str) -> None:
        winner_rating = table.get(winner, self.initial_rating)
        loser_rating = table.get(loser, self.initial_rating)
        expected_w = self.expected(winner_rating, loser_rating)
        table[winner] = winner_rating + self.k_factor * (1.0 - expected_w)
        table[loser] = loser_rating - self.k_factor * (1.0 - expected_w)

    def apply(self, winner: str, loser: str, surface: str | None) -> None:
        """Record a result against the overall pool and the surface pool."""
        self._update(self.overall, winner, loser)
        if surface:
            self._update(self.by_surface.setdefault(surface, {}), winner, loser)


@dataclass
class PlayerForm:
    matches: int = 0
    wins: int = 0
    games_won: int = 0
    games_lost: int = 0

    @property
    def win_rate(self) -> float:
        return self.wins / self.matches if self.matches else 0.5

    @property
    def avg_games_won(self) -> float:
        return self.games_won / self.matches if self.matches else 0.0

    @property
    def avg_games_lost(self) -> float:
        return self.games_lost / self.matches if self.matches else 0.0


def compute_player_form(
    player: str,
    history: list[dict] | TeamHistoryIndex,
    before_date: datetime,
    surface: str | None = None,
    window: int = FORM_WINDOW,
) -> PlayerForm:
    """Rolling form over a player's last `window` matches before `before_date`.

    With `surface`, only matches on that surface count — which is the whole
    point: form on clay says little about the next grass match.

    An unseen player returns `win_rate` 0.5, a neutral prior. Zero would read
    as "has lost every match", which is a different and wrong claim.
    """
    prior = _team_matches_before(player, history, before_date)
    if surface is not None:
        prior = [m for m in prior if m.get("surface") == surface]
    prior = prior[-window:]

    form = PlayerForm()
    for m in prior:
        is_home = m["home_team"] == player
        sets_for = m["home_score"] if is_home else m["away_score"]
        sets_against = m["away_score"] if is_home else m["home_score"]
        if sets_for is None or sets_against is None:
            continue
        form.matches += 1
        if sets_for > sets_against:
            form.wins += 1
        games_for = m.get("home_games") if is_home else m.get("away_games")
        games_against = m.get("away_games") if is_home else m.get("home_games")
        if games_for is not None and games_against is not None:
            form.games_won += int(games_for)
            form.games_lost += int(games_against)
    return form


def compute_h2h_win_rate(
    player: str,
    opponent: str,
    history: list[dict] | TeamHistoryIndex,
    before_date: datetime,
) -> float:
    """Share of prior meetings `player` won; 0.5 when they've never met."""
    prior = [
        m
        for m in _team_matches_before(player, history, before_date)
        if opponent in (m["home_team"], m["away_team"])
    ]
    if not prior:
        return 0.5
    wins = 0
    for m in prior:
        home_won = m["home_score"] > m["away_score"]
        if (m["home_team"] == player and home_won) or (m["away_team"] == player and not home_won):
            wins += 1
    return wins / len(prior)


def build_match_features(
    home_player: str,
    away_player: str,
    match_date: datetime,
    surface: str | None,
    history: list[dict] | TeamHistoryIndex,
    elo: SurfaceElo,
    best_of: int | None = None,
) -> dict:
    """The full tennis feature row for one match, from prior matches only."""
    elo_home = elo.get(home_player)
    elo_away = elo.get(away_player)
    elo_surface_home = elo.get(home_player, surface) if surface else elo_home
    elo_surface_away = elo.get(away_player, surface) if surface else elo_away

    home_form = compute_player_form(home_player, history, match_date)
    away_form = compute_player_form(away_player, history, match_date)
    home_surface_form = compute_player_form(home_player, history, match_date, surface=surface)
    away_surface_form = compute_player_form(away_player, history, match_date, surface=surface)

    return {
        "elo_home": elo_home,
        "elo_away": elo_away,
        "elo_diff": elo_home - elo_away,
        "elo_surface_home": elo_surface_home,
        "elo_surface_away": elo_surface_away,
        "elo_surface_diff": elo_surface_home - elo_surface_away,
        "home_win_rate": home_form.win_rate,
        "away_win_rate": away_form.win_rate,
        "home_surface_win_rate": home_surface_form.win_rate,
        "away_surface_win_rate": away_surface_form.win_rate,
        "home_avg_games_won": home_form.avg_games_won,
        "home_avg_games_lost": home_form.avg_games_lost,
        "away_avg_games_won": away_form.avg_games_won,
        "away_avg_games_lost": away_form.avg_games_lost,
        "h2h_home_win_rate": compute_h2h_win_rate(home_player, away_player, history, match_date),
        "home_matches_played": float(home_form.matches),
        "away_matches_played": float(away_form.matches),
        # Default 3: best-of-3 is the overwhelmingly common format (every
        # WTA match and all non-Slam ATP), so it's the right assumption when
        # a source row doesn't say.
        "best_of": float(best_of or 3),
    }
