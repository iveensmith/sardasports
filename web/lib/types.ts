/**
 * Types mirroring the prediction engine's API contract.
 *
 * Hand-written rather than generated, and deliberately so: the engine
 * returns a *union* discriminated on `sport`, and the whole point of that
 * union is that a basketball game has no draw probability and a tennis
 * match has no goal markets. A generated any-shaped type would let a
 * component read `prediction.draw` on a tennis match and render
 * `undefined%` — exactly the confusion the backend union exists to prevent.
 *
 * See docs/api_reference.md in the engine repo.
 */

import type { Badge } from "./board";

/**
 * One market's call.
 *
 * `probability` alone is not a prediction. Over 1.5 goals lands in 74.8% of
 * all matches and "either team to win" in 73.8%, so an engine reading of 76%
 * on either says nothing at all — ranked on raw probability, 26 of 29
 * fixtures on a real card led with a double chance. `lift` is the distance
 * above that selection's own base rate, and it is the part that carries
 * information. `notable` marks a lift big enough to be worth a reader's
 * attention.
 *
 * `base_rate` and `lift` are null where there is too little history to judge
 * the market, which is deliberately not the same as a lift of zero.
 */
export interface Call {
  market: string;
  market_name: string;
  selection: string;
  /** "Spain or draw", "Over 2.5 goals" — named for a reader, not as "1X". */
  label: string;
  probability: number;
  base_rate: number | null;
  lift: number | null;
  notable: boolean;
}

export interface Calls {
  /** Highest lift among calls likely enough to print as a prediction. */
  headline: Call | null;
  /** The strongest call in each market, in reading order. */
  by_market: Call[];
}

/**
 * Where the market price looks wrong.
 *
 * Not a prediction, and routinely the *least* likely selection on the
 * fixture — which is why it appears only here, on the page someone opened to
 * read the analysis, and never on a board row beside the call.
 *
 * `thin_evidence` is the field that matters. A large positive expected value
 * usually means the model lacks history for a competitor rather than that
 * the market is wrong, so it is never presented as free money.
 */
export interface Value {
  market: string;
  selection: string;
  label: string;
  model_probability: number;
  market_implied_probability: number;
  fair_price: number;
  offered_price: number;
  expected_value: number;
  positive_value: boolean;
  thin_evidence: boolean;
  min_competitor_matches: number | null;
  candidates_considered: number;
  rationale: string;
}

export type Sport = "football" | "basketball" | "tennis";

/**
 * One Over/Under line.
 *
 * `probOver` is `null` when the engine genuinely cannot price this market —
 * the competition has no data for the stat (MLS has no corner data; a
 * basketball line with no trained model has no Poisson fallback). It is
 * never a zero, and the UI must never render it as one.
 */
export interface MarketLine {
  line: number;
  prob_over: number | null;
  prob_under: number | null;
  model_used: boolean;
}

export interface FeatureImpact {
  feature: string;
  impact_percentage_points: number;
}

export interface Scoreline {
  score: string;
  probability: number;
}

export interface MatchScore {
  home: number;
  away: number;
}

/** Bookmaker 1X2 prices, read off the match row. `draw` is null for a sport
 *  with no draw market (basketball). */
export interface Odds1X2 {
  home: number | null;
  draw: number | null;
  away: number | null;
}

/** One stat, both sides. Independently nullable — a completed match whose
 *  competition doesn't report a given stat shows `null`, not a fabricated
 *  zero. */
export interface ActualStat {
  home: number | null;
  away: number | null;
}

/**
 * What actually happened, once the match has been played — see
 * `scripts/fetch_match_stats.py` in the engine. Present only once the
 * fixture is completed *and* statistics have been fetched for it; absent
 * beforehand, which is different from "fetched, nothing to report".
 */
export interface ActualStats {
  shots: ActualStat;
  shots_on_target: ActualStat;
  corners: ActualStat;
  yellow_cards: ActualStat;
  red_cards: ActualStat;
  possession: ActualStat;
  offsides: ActualStat;
  fouls: ActualStat;
}

/** One goal, in the order it happened. */
export interface MatchEvent {
  minute: number;
  added_time: number | null;
  side: "home" | "away";
  player: string;
  assist: string | null;
  detail: string;
  home_score_after: number;
  away_score_after: number;
}

export interface FootballPrediction {
  sport: "football";
  match_id: number;
  home_team: string;
  away_team: string;
  /** A flag for a national side, initials for a club we have no crest for. */
  home_badge: Badge | null;
  away_badge: Badge | null;
  match_date: string;
  competition: string;
  match_status: string;
  match_score: MatchScore | null;
  ht_score: MatchScore | null;
  odds_1x2: Odds1X2 | null;
  home_win: number;
  draw: number;
  away_win: number;
  expected_goals_home: number;
  expected_goals_away: number;
  top_scorelines: Scoreline[];
  btts_yes: number;
  btts_no: number;
  goals_markets: MarketLine[];
  ht_goals_markets: MarketLine[];
  corners_markets: MarketLine[];
  cards_markets: MarketLine[];
  confidence: number;
  confidence_label: ConfidenceLabel;
  model_version: string | null;
  model_weights_used: Record<string, number>;
  btts_model_used: boolean | null;
  explanation: FeatureImpact[] | null;
  /**
   * Calls across every market, ranked by lift over each selection's base
   * rate. Football only — the other sports have no base-rate table yet.
   */
  calls: Calls | null;
  /** The market comparison. Fixture page only. */
  value: Value | null;
  /** What actually happened, once there is something to report — null for a
   *  fixture yet to be played. Never zero-filled. */
  actual_stats: ActualStats | null;
  events: MatchEvent[];
  generated_at: string;
}

export interface BasketballPrediction {
  sport: "basketball";
  match_id: number;
  home_team: string;
  away_team: string;
  match_date: string;
  competition: string;
  match_status: string;
  match_score: MatchScore | null;
  odds_1x2: Odds1X2 | null;
  /** No `draw`: zero ties in 4,149 ingested NBA games. Sums to 100 alone. */
  home_win: number;
  away_win: number;
  expected_points_home: number;
  expected_points_away: number;
  expected_total_points: number;
  total_points_markets: MarketLine[];
  confidence: number;
  confidence_label: ConfidenceLabel;
  model_version: string | null;
  winner_model_used: boolean;
  generated_at: string;
}

export interface TennisPrediction {
  sport: "tennis";
  match_id: number;
  /**
   * Not a venue. Tennis sources record a winner and a loser, so the engine
   * assigns players to slots by a deterministic hash to stop the label
   * leaking. No home advantage is applied anywhere.
   */
  home_player: string;
  away_player: string;
  match_date: string;
  competition: string;
  surface: string | null;
  best_of: number | null;
  match_status: string;
  match_score: MatchScore | null;
  odds_1x2: Odds1X2 | null;
  home_win: number;
  away_win: number;
  /** Overall and per-surface ratings differ sharply for the same player. */
  elo_home: number;
  elo_away: number;
  elo_surface_home: number;
  elo_surface_away: number;
  expected_total_games: number;
  total_games_markets: MarketLine[];
  confidence: number;
  confidence_label: ConfidenceLabel;
  model_version: string | null;
  winner_model_used: boolean;
  generated_at: string;
}

export type Prediction =
  FootballPrediction | BasketballPrediction | TennisPrediction;

export type ConfidenceLabel = "Low" | "Medium" | "High" | "Very High";

export interface Fixture {
  match_id: number;
  match_date: string;
  competition: string;
  home_team: string;
  away_team: string;
  status?: string;
}

export interface FixturesResponse {
  date: string;
  count: number;
  fixtures: Fixture[];
}

export interface MatchSummary {
  match_id: number;
  match_date: string;
  sport: Sport;
  competition: string;
  season: string;
  home_team: string;
  away_team: string;
  home_score: number | null;
  away_score: number | null;
  status: string;
  has_odds: boolean;
}

export interface MatchesResponse {
  count: number;
  limit: number;
  offset: number;
  matches: MatchSummary[];
}

/**
 * A team's recent form, in the same "last 5 / last 10" windows the engine
 * uses for its own features — see `ml.feature_engineering.features`. The
 * `over_*`/`btts` counts are display-only, not read by any training
 * pipeline.
 */
export interface TeamFormSummary {
  matches_played: number;
  wins: number;
  draws: number;
  losses: number;
  goals_scored: number;
  goals_conceded: number;
  clean_sheets: number;
  points_per_game: number;
  over_1_5: number;
  over_2_5: number;
  over_3_5: number;
  btts: number;
}

export interface RecentMatch {
  match_id: number;
  match_date: string;
  competition: string;
  home_team: string;
  away_team: string;
  home_score: number | null;
  away_score: number | null;
  /** `null` where the source never recorded a half-time score — not every
   *  competition does. */
  home_ht_score: number | null;
  away_ht_score: number | null;
}

/** One stat's per-match average this season. `sample_size` is how many of
 *  this season's matches actually reported it — `value` is `null` when
 *  that's zero, never a fabricated 0. */
export interface SeasonStat {
  value: number | null;
  sample_size: number;
}

/** Season averages beyond goals (already on `TeamFormSummary`) — shots,
 *  corners, cards, and the three fields only the engine's
 *  `fetch_match_stats.py` can fill (possession, offsides, fouls). */
export interface SeasonStats {
  season: string;
  matches_played: number;
  shots: SeasonStat;
  shots_on_target: SeasonStat;
  corners: SeasonStat;
  cards: SeasonStat;
  possession: SeasonStat;
  offsides: SeasonStat;
  fouls: SeasonStat;
}

export interface TeamDetail {
  team: { id: number; name: string; league: string | null; elo_rating: number };
  form_last5: TeamFormSummary;
  form_last10: TeamFormSummary;
  recent_matches: RecentMatch[];
  /** `null` only for a team with no completed match history at all. */
  season_stats: SeasonStats | null;
}

export interface Competition {
  competition: string;
  sport: Sport;
  seasons: string[];
  match_count: number;
}

export interface CompetitionsResponse {
  competitions: Competition[];
}

/** Narrowing helpers — used instead of reading fields that may not exist. */
export const isFootball = (p: Prediction): p is FootballPrediction =>
  p.sport === "football";
export const isBasketball = (p: Prediction): p is BasketballPrediction =>
  p.sport === "basketball";
export const isTennis = (p: Prediction): p is TennisPrediction =>
  p.sport === "tennis";

/** The two sides of a match, whatever the sport calls them. */
export function competitors(p: Prediction): { home: string; away: string } {
  return isTennis(p)
    ? { home: p.home_player, away: p.away_player }
    : { home: p.home_team, away: p.away_team };
}
