/**
 * Leagues, bankers, and the slip builder.
 *
 * `combined_probability` on a slip is not optional and not decoration. Six
 * legs at 80% is a 26% chance of a return, and an interface that shows the
 * combined price without it is advertising the upside of a bet whose
 * downside it has already calculated.
 */

import type { BoardRow } from "./board";
import type { SettledRecord } from "./progress";

/**
 * "2nd tier", "3rd tier" … for a competition below its country's top flight;
 * null for the top flight itself and for cups and internationals, where a
 * tier number means nothing.
 */
export function tierLabel(tier: number | null): string | null {
  if (tier === null || tier < 2) return null;
  const suffix = { 2: "nd", 3: "rd" }[tier] ?? "th";
  return `${tier}${suffix} tier`;
}

export interface LeagueEntry {
  competition: string;
  /** URL segment for the competition's own page. */
  slug: string;
  short_name: string;
  tier: number | null;
  /** Completed matches on record — what the model for it was built from. */
  completed: number;
  upcoming: number;
}

export interface LeagueCountry {
  country: string;
  country_code: string | null;
  competitions: LeagueEntry[];
  completed: number;
  upcoming: number;
}

export interface Leagues {
  countries: LeagueCountry[];
  competition_count: number;
  country_count: number;
}

export interface Bankers {
  date: string;
  min_probability: number;
  count: number;
  /** How many fixtures were on the card before filtering. */
  considered: number;
  record: SettledRecord;
  rows: BoardRow[];
}

export interface SlipLeg {
  match_id: number;
  slug: string;
  home_team: string;
  away_team: string;
  competition: string;
  match_date: string;
  market: string;
  selection: string;
  label: string;
  short_label: string;
  probability: number;
  odds: number;
  confidence: number | null;
}

export interface Slip {
  date: string;
  legs: SlipLeg[];
  leg_count: number;
  combined_odds: number;
  /** The chance every leg lands. Always shown beside the price. */
  combined_probability: number;
  target_odds: number;
  reached_target: boolean;
  /** The day's card could not supply enough eligible legs. */
  short_of_minimum: boolean;
  candidates_considered: number;
}

/** One row of a competition's table, computed from results on record. */
export interface StandingRow {
  team: string;
  played: number;
  won: number;
  drawn: number;
  lost: number;
  goals_for: number;
  goals_against: number;
  goal_difference: number;
  points: number;
}

/** A team's last five results, ranked by points. See `form_window`. */
export interface FormEntry {
  team: string;
  points: number;
  goal_difference: number;
  /** "WWDLW", oldest first. */
  results: string;
}

export interface LeagueResult {
  match_id: number;
  match_date: string;
  home_team: string;
  away_team: string;
  home_score: number;
  away_score: number;
}

/** Rates over completed matches on record, as percentages. */
export interface LeagueHistory {
  matches: number;
  home_win: number | null;
  draw: number | null;
  away_win: number | null;
  over_1_5: number | null;
  over_2_5: number | null;
  over_3_5: number | null;
  btts: number | null;
  first: string | null;
  last: string | null;
}

export interface LeagueDetail {
  competition: string;
  slug: string;
  short_name: string;
  country: string;
  country_code: string | null;
  tier: number | null;
  /** No table or form for these: a table of friendlies is not a table. */
  is_international: boolean;
  /** True for national-team competitions (World Cup, friendlies). False for a
   *  continental club competition such as the Champions League, which is also
   *  grouped under a confederation but is made of clubs. */
  national_teams: boolean;
  history: LeagueHistory;
  /** Days since the newest result on record. Null with no results at all. */
  last_match_age_days: number | null;
  /** The season the table and form are for, as a reader would write it. */
  season: string | null;
  teams: number | null;
  standings: StandingRow[];
  form_window: number;
  /** Null unless the competition's newest result is recent enough that
   *  "hot" and "cold" describe now rather than a past season. */
  hot_team: FormEntry | null;
  cold_team: FormEntry | null;
  /** The engine's own settled record here; live and backtest never blended. */
  record: {
    overall: SettledRecord;
    live: SettledRecord;
    backtest: SettledRecord;
  };
  fixtures: BoardRow[];
  results: LeagueResult[];
}
