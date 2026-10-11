/**
 * The board, as a table.
 *
 * A board row is a different shape from a prediction. A prediction is "here
 * are probabilities for every market"; a row is "here is the fixture, its
 * price, the engine's pick in each column, the one pick worth leading with,
 * and — once played — whether each came in".
 *
 * `outcome` is the field that makes the product honest, and the reason it is
 * `null` rather than a default: a fixture that has not kicked off has no
 * verdict, and a default of "lost" would mark every upcoming tip as already
 * failed. Three states, three renderings, no coercion between them.
 */

/** "won" | "lost" | "void" once played, null before kick-off. */
export type Outcome = "won" | "lost" | "void" | null;

/** One market's cell: what was picked, at what price, and how it went. */
export interface Tip {
  market: string;
  selection: string;
  /** "Home or draw" — for the fixture page, where a sentence fits. */
  label: string;
  /** "1X" — for a board column, which has room for two characters. */
  short_label: string;
  probability: number;
  /** How often this selection lands across every completed match on record. */
  base_rate: number | null;
  /** Points above that base rate. Null where there is no measured yardstick. */
  lift: number | null;
  notable: boolean;
  /** True when the engine rates this tip at 70% or more. Absent on older copies. */
  strong?: boolean;
  /** Best offered price, or a fair price derived from `probability` where no
   * bookmaker line covers this pick at all — see `odds_is_estimated`. */
  odds: number | null;
  /** True when `odds` is that fallback rather than a real market price. */
  odds_is_estimated: boolean;
  outcome: Outcome;
}

export interface CompetitionRef {
  name: string;
  short_name: string;
  /** Null for a competition we have not catalogued — ungrouped, not guessed. */
  country: string | null;
  country_code: string | null;
  tier: number | null;
}

/** What to render beside a team name: a flag, or initials for a club. */
export interface Badge {
  kind: "flag" | "monogram";
  /** Lowercase ISO code — "br", "gb-eng". Null for a monogram. */
  code: string | null;
  /** One or two letters. Null for a flag. */
  initials: string | null;
}

export interface BoardRow {
  match_id: number;
  /** "spain-vs-croatia-prediction-144414" */
  slug: string;
  match_date: string;
  status: string;
  sport: string;
  competition: CompetitionRef;
  home_team: string;
  away_team: string;
  home_badge: Badge | null;
  away_badge: Badge | null;
  /** Null until played. Not 0-0, which is a real scoreline. */
  score: { home: number; away: number } | null;
  /** In play right now: minute and score so far. Null otherwise, and never the result. */
  live?: {
    status: string | null;
    minute: number | null;
    label: string;
    home: number;
    away: number;
  } | null;
  /** Quoted bookmaker price, or the engine's fair price where none was quoted
   * — `odds_estimated` says which, per selection. */
  odds: { home: number | null; draw: number | null; away: number | null };
  odds_estimated: { home: boolean; draw: boolean; away: boolean };
  /** Keyed by market: "match_result", "goals", "btts". */
  tips: Record<string, Tip>;
  best_tip: Tip | null;
  /** Out of ten, matching how the column is labelled. */
  confidence: number | null;
  confidence_label: string | null;
}

export interface BoardGroup {
  competition: CompetitionRef;
  rows: BoardRow[];
}

export interface CountryCount {
  country: string;
  country_code: string | null;
  count: number;
}

export interface DayBoard {
  date: string;
  counts: {
    fixtures: number;
    /** Fixtures the engine produced a prediction for. The gap from
     *  `fixtures` is competitions with no trained model, reported not hidden. */
    predicted: number;
    upcoming: number;
    finished: number;
    /** Best tips that were won or lost: a refunded draw is not in this count. */
    settled?: number;
    won: number;
    /** Tips the engine rated 70% or more before kick-off: a subset of the above. */
    strong_finished?: number;
    strong_won?: number;
  };
  countries: CountryCount[];
  groups: BoardGroup[];
}

export interface BoardDay {
  date: string;
  /** -1, 0, 1 relative to today. */
  offset: number;
  /** "Yesterday" | "Today" | "Tomorrow" | "Oct 2" */
  label: string;
  fixtures: number;
}

export interface BoardDates {
  today: string;
  days: BoardDay[];
  /**
   * The most recent day with a settled result on it.
   *
   * Not the same as yesterday. Fixtures are ingested forward but their scores
   * are not fetched back yet, so yesterday is routinely ungraded — a results
   * strip bound to it would simply never appear.
   */
  last_settled: string | null;
}

/** Every row in a response, flattened out of its competition groups. */
export function allRows(board: DayBoard): BoardRow[] {
  return board.groups.flatMap((group) => group.rows);
}

/**
 * Kick-off time, or "FT" once the match is played.
 *
 * The board's first column answers "when?", and for a finished match the
 * useful answer is that it is over — the time it started is no longer what
 * the reader is scanning for.
 */
export function kickoffLabel(row: BoardRow): string {
  if (row.score) return "FT";
  const at = new Date(row.match_date);
  return at.toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

/** How a settled tip should read. Unsettled returns null, never a colour. */
export function outcomeColor(outcome: Outcome): string | null {
  if (outcome === "won") return "var(--color-won)";
  if (outcome === "lost") return "var(--color-lost)";
  if (outcome === "void") return "var(--color-text-faint)";
  return null;
}

/**
 * Recover a match id from a URL segment.
 *
 * Accepts both `144414` and `spain-vs-croatia-prediction-144414`. The name
 * part is decoration: a team renamed since the URL was shared still
 * resolves, and a hand-edited slug cannot land on the wrong fixture, because
 * only the trailing number is ever read.
 *
 * Mirrors `match_id_from_slug` in app/services/board_service.py. If the two
 * disagree, a link the board generated stops opening.
 */
export function matchIdFromSlug(segment: string): number | null {
  const found = /(\d+)$/.exec(segment ?? "");
  if (!found) return null;
  const id = Number(found[1]);
  return Number.isSafeInteger(id) ? id : null;
}
