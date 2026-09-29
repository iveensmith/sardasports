/**
 * The public track record.
 *
 * `live` and `backtest` are separate fields and must stay separate in the
 * interface. A backtest was generated after the match from history truncated
 * at kick-off — leakage-safe, but never exposed to the risk of being wrong in
 * public. Presenting one as the other is the commonest dishonesty in this
 * industry, and the API splits them precisely so a component cannot merge
 * them by accident.
 */

/**
 * Wins, losses, and the calls that were never settleable.
 *
 * Named `SettledRecord` rather than `Record`, which is a built-in TypeScript
 * utility type — shadowing it makes every `Record<string, T>` in the file
 * silently resolve to this instead.
 */
export interface SettledRecord {
  won: number;
  lost: number;
  /** Calls about a stat the match does not record. Excluded from the rate. */
  void: number;
  /** won + lost — the sample the rate is actually over. */
  settled: number;
  /** Null when nothing was settleable, which is not the same as 0%. */
  win_rate: number | null;
}

export interface Span {
  first: string;
  last: string;
}

export interface MonthRecord extends SettledRecord {
  month: string;
}
export interface DayRecord extends SettledRecord {
  date: string;
}
export interface MarketRecord extends SettledRecord {
  market: string;
}
export interface CompetitionRecord extends SettledRecord {
  competition: string;
}
export interface ConfidenceRecord extends SettledRecord {
  bucket: string;
  from: number;
}

export interface Progress {
  generated_at: string;
  overall: SettledRecord;
  span: Span | null;
  live: { record: SettledRecord; span: Span | null };
  backtest: { record: SettledRecord; span: Span | null };
  by_month: MonthRecord[];
  recent_days: DayRecord[];
  by_market: MarketRecord[];
  by_competition: CompetitionRecord[];
  by_confidence: ConfidenceRecord[];
}

const MARKET_NAMES: Record<string, string> = {
  match_result: "Match result",
  double_chance: "Double chance",
  goals: "Goals",
  btts: "Both teams to score",
  ht_goals: "Half-time goals",
  corners: "Corners",
  cards: "Cards",
};

export function marketName(market: string): string {
  return MARKET_NAMES[market] ?? market;
}

/** "77.7%", or an em dash where nothing was settleable. */
export function rate(record: SettledRecord): string {
  return record.win_rate === null ? "—" : `${record.win_rate.toFixed(1)}%`;
}
