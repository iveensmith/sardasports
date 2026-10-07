/**
 * Single-market landing pages ("Over 2.5 goals today", "Correct score today").
 *
 * The record beside the picks is counted from the engine's stored predictions
 * and split into live (stored before kick-off) and backtest (reconstructed
 * after) — the same two-way split the track-record page keeps, for the same
 * reason: a reconstruction is evidence, but weaker evidence than a published
 * forecast, and the interface must not present one as the other.
 */

import type { Badge, CompetitionRef, Outcome } from "./board";

export type MarketKind = "over-2-5" | "correct-score";

export interface MarketPick {
  /** "Over 2.5 goals", or the scoreline "2-1". */
  label: string;
  /** Percentage. */
  probability: number;
  /** A bookmaker price where one was quoted, else the pick's fair price. */
  odds: number | null;
  odds_is_estimated: boolean;
  outcome: Outcome;
}

export interface MarketPickRow {
  match_id: number;
  slug: string;
  match_date: string;
  competition: CompetitionRef;
  home_team: string;
  away_team: string;
  home_badge: Badge | null;
  away_badge: Badge | null;
  score: { home: number; away: number } | null;
  pick: MarketPick;
}

export interface MarketTally {
  settled: number;
  won: number;
  /** Null when nothing has settled, never 0. */
  rate: number | null;
}

export interface MarketHit {
  match_id: number;
  match_date: string;
  competition: string;
  home_team: string;
  away_team: string;
  score: { home: number; away: number };
  pick: string;
  probability: number;
  /** True when the call was stored before kick-off. */
  live: boolean;
}

export interface MarketRecord {
  window_days: number;
  overall: MarketTally;
  live: MarketTally;
  backtest: MarketTally;
  recent_hits: MarketHit[];
}

export interface MarketPageData {
  kind: MarketKind;
  date: string;
  /** Fixtures on the day, before any filtering. */
  fixtures: number;
  /** Fixtures the engine had a view on for this market. */
  considered: number;
  picks: MarketPickRow[];
  /** How often the market lands over every completed match on record. Null
   * for markets with no such yardstick (correct score). */
  base_rate: number | null;
  record: MarketRecord;
}
