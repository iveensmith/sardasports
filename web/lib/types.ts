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

export interface FootballPrediction {
  sport: "football";
  match_id: number;
  home_team: string;
  away_team: string;
  match_date: string;
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
  btts_model_used: boolean;
  explanation: FeatureImpact[] | null;
  generated_at: string;
}

export interface BasketballPrediction {
  sport: "basketball";
  match_id: number;
  home_team: string;
  away_team: string;
  match_date: string;
  competition: string;
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
  | FootballPrediction
  | BasketballPrediction
  | TennisPrediction;

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
