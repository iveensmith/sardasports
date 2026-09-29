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
  /** Best offered price, or null where no bookmaker line was ingested. */
  odds: number | null;
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
  /** Null until played. Not 0-0, which is a real scoreline. */
  score: { home: number; away: number } | null;
  odds: { home: number | null; draw: number | null; away: number | null };
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
    won: number;
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
