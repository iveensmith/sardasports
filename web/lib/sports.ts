/**
 * The sports the site covers, and the numbers the basketball and tennis pages read.
 *
 * Football has its own pages and the longest record. Basketball and tennis are served
 * from `/sports/{sport}` on the engine: a daily board, a record of predictions stored
 * before the match, and how each model measures against the rule it has to beat. Every
 * figure carries the date the data runs to, because some leagues' history is months old.
 */

import type { Badge } from "./board";

export type SportKey = "football" | "basketball" | "tennis";
export type OtherSportKey = Exclude<SportKey, "football">;

export const SPORT_LABELS: Record<SportKey, string> = {
  football: "Football",
  basketball: "Basketball",
  tennis: "Tennis",
};

export const SPORT_PATHS: Record<SportKey, string> = {
  football: "/matches",
  basketball: "/basketball",
  tennis: "/tennis",
};

export interface SportSummary {
  sport: SportKey;
  label: string;
  matches_on_record: number;
  last_result_date: string | null;
  upcoming_fixtures: number;
  next_fixture_date: string | null;
}

export interface SportsSummary {
  sports: SportSummary[];
}

export interface SportMatchRow {
  match_id: number;
  match_date: string;
  competition: string;
  surface: string | null;
  home: string;
  away: string;
  home_score: number | null;
  away_score: number | null;
  home_win: number | null;
  away_win: number | null;
  pick: { name: string; side: "home" | "away"; probability: number } | null;
  pick_correct: boolean | null;
}

export interface SportModelRow {
  model: string;
  label: string;
  accuracy: number;
  baseline: number | null;
  baseline_kind: string | null;
  edge: number | null;
  test_matches: number | null;
  trained_at: string | null;
}

export interface SportOverview {
  sport: OtherSportKey;
  label: string;
  competitor: "team" | "player";
  matches_on_record: number;
  competitors_on_record: number;
  first_result_date: string | null;
  last_result_date: string | null;
  days_since_last_result: number | null;
  competitions: Array<{
    name: string;
    matches: number;
    first_date: string | null;
    last_date: string | null;
  }>;
  /** Ranked within each competition, because ratings only compare within one pool. */
  top_rated: Array<{
    competition: string;
    teams: Array<{ team_id: number; name: string; rating: number }>;
  }>;
  upcoming: SportMatchRow[];
  recent: SportMatchRow[];
  models: SportModelRow[];
  stale?: boolean;
}

export type EdgeVerdict = "clear" | "none" | "unknown";

/**
 * Does a model beat its baseline by more than chance could produce?
 *
 * Accuracy over n matches has a standard error of about sqrt(p(1-p)/n), so an edge
 * smaller than two of those is indistinguishable from luck. That is the whole
 * reason the tennis winner model is reported as no better than picking the
 * higher-rated player: +0.4 points on 13,734 matches is about one standard error.
 */
export function edgeVerdict(model: SportModelRow): EdgeVerdict {
  if (model.edge === null || model.baseline === null || !model.test_matches) {
    return "unknown";
  }
  const p = model.baseline / 100;
  const standardError = Math.sqrt((p * (1 - p)) / model.test_matches) * 100;
  return model.edge >= 2 * standardError ? "clear" : "none";
}

const MONTHS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

/** "16 Nov 2025" from an ISO timestamp, without a timezone shifting the day. */
export function shortDate(iso: string | null): string {
  if (!iso) return "unknown";
  const [year, month, day] = iso.slice(0, 10).split("-").map(Number);
  return `${day} ${MONTHS[month - 1]} ${year}`;
}

/** "11 months" / "3 weeks" / "2 days", for how old the newest result is. */
export function ageLabel(days: number | null): string {
  if (days === null) return "unknown";
  if (days < 1) return "today";
  if (days < 14) return `${days} ${days === 1 ? "day" : "days"}`;
  if (days < 60) return `${Math.round(days / 7)} weeks`;
  return `${Math.round(days / 30.4)} months`;
}

/** The result as a scoreline: sets for tennis, points for basketball. */
export function scoreline(row: SportMatchRow): string {
  if (row.home_score === null || row.away_score === null) return "–";
  return `${row.home_score}–${row.away_score}`;
}

/**
 * A monogram badge for a basketball team or a tennis player, from the name alone.
 *
 * There is no licensed crest or photo for either, and a flag would need a
 * nationality the data does not hold, so this is the same plain monogram clubs get.
 * "Sinner J." gives "SJ" and "Boston Celtics" gives "BC".
 */
export function monogramBadge(name: string): Badge {
  const words = name
    .replace(/[^\p{L}\s.-]/gu, "")
    .split(/[\s-]+/)
    .filter(Boolean);
  // A tennis name is "Surname I.", so the monogram is surname and given initial.
  const last = words[words.length - 1] ?? "";
  if (words.length > 1 && /^\p{L}\.?$/u.test(last)) {
    return {
      kind: "monogram",
      code: null,
      initials: `${words[0][0]}${last[0]}`.toUpperCase(),
    };
  }
  const letters = words
    .slice(0, 3)
    .map((word) => word[0]?.toUpperCase() ?? "")
    .join("");
  return { kind: "monogram", code: null, initials: letters || null };
}

export interface SportBoardMatch {
  match_id: number;
  kickoff: string;
  status: "scheduled" | "completed" | string;
  in_play: boolean;
  /** Six hours past the start with no result: shown as no result, not as in play. */
  overdue: boolean;
  home: string;
  away: string;
  home_score: number | null;
  away_score: number | null;
  home_games: number | null;
  away_games: number | null;
  surface: string | null;
  home_win: number | null;
  away_win: number | null;
  pick: { side: "home" | "away"; name: string; probability: number } | null;
  total: { line: number; prob_over: number } | null;
  expected_total: number | null;
  confidence: number | null;
  /** Set when the ratings behind the pick are old enough to have been pulled towards 50%. */
  ratings_age_days: number | null;
  /** stored: made before the match. calculated: made now. reconstructed: stored late. */
  source: "stored" | "calculated" | "reconstructed" | "unpriced";
  winner_correct: boolean | null;
  total_correct: boolean | null;
}

export interface SportBoardCompetition {
  name: string;
  tour: string | null;
  country: string | null;
  country_code: string | null;
  women: boolean;
  matches: SportBoardMatch[];
}

export interface SportBoard {
  sport: OtherSportKey;
  date: string;
  counts: {
    fixtures: number;
    finished: number;
    priced: number;
    stored_in_advance: number;
    competitions: number;
  };
  competitions: SportBoardCompetition[];
}

export interface RecordCount {
  settled: number;
  won: number;
}

export interface SportRecord {
  sport: OtherSportKey;
  live: { winner: RecordCount; total: RecordCount };
  reconstructed: { winner: RecordCount; total: RecordCount };
  live_since: string | null;
  stored_total: number;
}

/** "14:30 UTC" from an ISO timestamp. */
export function kickoffTime(iso: string): string {
  return `${iso.slice(11, 16)} UTC`;
}
