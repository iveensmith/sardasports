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

export interface LeagueEntry {
  competition: string;
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
