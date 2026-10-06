/**
 * The only place the site talks to the prediction engine.
 *
 * Every call runs on the server (Server Components and Route Handlers), so
 * the browser never holds the engine's address and there is no CORS surface
 * to configure. That is also the architecture the brief asks for: the
 * frontend does not bypass the backend.
 *
 * The engine is the single source of truth. Nothing here computes a
 * probability, rounds one differently, or fills in a missing market — if
 * the engine returns null for a line, null is what reaches the page.
 */

import type { BoardDates, DayBoard } from "./board";
import type { Bankers, LeagueDetail, Leagues, Slip } from "./discover";
import type { Progress } from "./progress";
import type {
  Call,
  Calls,
  CompetitionsResponse,
  FixturesResponse,
  MatchesResponse,
  Prediction,
  TeamDetail,
  Value,
} from "./types";

// Re-exported so components can import every board type from one module.
export type { Call, Calls, Value };

const ENGINE_URL = process.env.ENGINE_URL ?? "http://127.0.0.1:8000";

/** Thrown with the engine's own detail message where it provides one. */
export class EngineError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly path: string,
  ) {
    super(message);
    this.name = "EngineError";
  }
}

interface FetchOptions {
  /**
   * Seconds to cache. Predictions for an upcoming fixture move as the
   * engine re-runs, and the engine already caches them for 10 minutes, so
   * there is no value in a longer window here — it would only add a second
   * layer of staleness with different expiry.
   */
  revalidate?: number;
  signal?: AbortSignal;
}

async function engineFetch<T>(
  path: string,
  { revalidate = 60, signal }: FetchOptions = {},
): Promise<T> {
  const url = `${ENGINE_URL}${path}`;
  let response: Response;
  try {
    response = await fetch(url, {
      next: { revalidate },
      signal,
      headers: { accept: "application/json" },
    });
  } catch (cause) {
    // A connection failure is the common local case (engine not running),
    // and "fetch failed" alone sends people hunting in the wrong place.
    throw new EngineError(
      `Could not reach the prediction engine at ${ENGINE_URL}. Is it running?`,
      503,
      path,
    );
  }

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body?.detail) detail = body.detail;
    } catch {
      // Body was not JSON; the status text stands.
    }
    throw new EngineError(detail, response.status, path);
  }

  return (await response.json()) as T;
}

/**
 * A file the engine serves for download, passed through as-is.
 *
 * Streamed rather than parsed: the browser asks this site for the file, so
 * the engine's address stays server-side like every other call here. Never
 * cached, because a download should be the record as it stands now.
 */
export async function engineDownload(path: string): Promise<Response> {
  let upstream: Response;
  try {
    upstream = await fetch(`${ENGINE_URL}${path}`, { cache: "no-store" });
  } catch {
    return new Response("The prediction engine could not be reached.", {
      status: 503,
    });
  }
  if (!upstream.ok) {
    return new Response("The engine could not produce that file.", {
      status: upstream.status,
    });
  }
  return new Response(upstream.body, {
    headers: {
      "content-type":
        upstream.headers.get("content-type") ?? "text/csv; charset=utf-8",
      "content-disposition":
        upstream.headers.get("content-disposition") ?? "attachment",
    },
  });
}

/**
 * Fixtures for a date (default: today, engine-side).
 *
 * Honest note for callers: this returns only competitions the engine has
 * models for. Most of a given day's worldwide card is deliberately absent —
 * see scripts/fetch_upcoming_fixtures.py.
 */
export function getFixtures(date?: string): Promise<FixturesResponse> {
  const query = date ? `?on_date=${encodeURIComponent(date)}` : "";
  return engineFetch<FixturesResponse>(`/fixtures/today${query}`, {
    revalidate: 300,
  });
}

/** The full prediction for one match, in that sport's own shape. */
export function getPrediction(matchId: number): Promise<Prediction> {
  return engineFetch<Prediction>(`/predict/${matchId}`, { revalidate: 60 });
}

export function getMatches(params: {
  sport?: string;
  competition?: string;
  team?: string;
  opponent?: string;
  status?: string;
  limit?: number;
  offset?: number;
}): Promise<MatchesResponse> {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") query.set(key, String(value));
  }
  const suffix = query.toString() ? `?${query}` : "";
  return engineFetch<MatchesResponse>(`/matches${suffix}`, { revalidate: 300 });
}

export function getCompetitions(sport?: string): Promise<CompetitionsResponse> {
  const query = sport ? `?sport=${encodeURIComponent(sport)}` : "";
  return engineFetch<CompetitionsResponse>(`/competitions${query}`, {
    revalidate: 3600,
  });
}

/** A team's current form and recent results — the match page's Form and
 *  Recent Matches tabs. Null for a team the engine has no match history
 *  for at all, rather than an empty-but-present shape. */
export async function getTeam(name: string): Promise<TeamDetail | null> {
  try {
    return await engineFetch<TeamDetail>(`/team/${encodeURIComponent(name)}`, {
      revalidate: 300,
    });
  } catch (error) {
    if (error instanceof EngineError && error.status === 404) return null;
    throw error;
  }
}

/**
 * How many independent estimators back the blended pick.
 *
 * Null for basketball and tennis: those blend one trained model with an Elo
 * baseline, so "2 of 3 agree" would be a category error rather than a
 * weaker signal.
 */
export interface Agreement {
  pick: "home" | "draw" | "away";
  agreeing: number;
  total: number;
  unanimous: boolean;
  by_estimator: Record<string, "home" | "draw" | "away" | null>;
}

/**
 * The outcome the model considers most likely — the fixture's forecast.
 *
 * This is what a reader means by "the prediction", and it is read off the
 * same blended probabilities the detail page renders, so a row and its own
 * detail page can never disagree. They used to: a row would lead with `Pick`
 * below (the best *price*, often a long shot) while the detail page showed
 * the favourite, with nothing on either page explaining why.
 */
export interface Forecast {
  selection: "home" | "draw" | "away";
  /** "Spain to win", or "Draw" — named for a reader, not for a market. */
  label: string;
  probability: number;
  short_label: string;
}

/**
 * Where the *price* looks wrong, by expected value against the best
 * available price. Not a forecast: frequently the least likely outcome.
 *
 * `thin_evidence` is the important field. A large positive expected value
 * usually means the model lacks history for one of the competitors rather
 * than that the market is wrong — the engine's own backtest returns -6.74%
 * against bookmaker odds — so the UI must not present it as a headline.
 */
export interface Pick {
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

/** One fixture on the board, with its prediction where one was possible. */
export interface BoardEntry {
  match_id: number;
  match_date: string;
  sport: string;
  competition: string;
  home_team: string;
  away_team: string;
  status: string;
  prediction: Prediction | null;
  agreement: Agreement | null;
  /** What the engine expects for the match result specifically. */
  forecast: Forecast | null;
  /** Calls across every market the engine can price, headline first. */
  calls: Calls | null;
  /** Where the price looks wrong. Shown as value, never as the forecast. */
  pick: Pick | null;
  odds_updated_at: string | null;
  passed: boolean;
}

export type BoardView = "all" | "consensus" | "disagreement" | "passed";

export interface BoardResponse {
  date: string;
  view: BoardView;
  /** Totals for every view, so the tabs can be labelled in one request. */
  counts: Record<BoardView, number>;
  count: number;
  predicted: number;
  fixtures: BoardEntry[];
}

/**
 * The day's board in one request.
 *
 * Deliberately *not* `/fixtures/today` followed by an N-way fan-out of
 * `/predict/{id}`. Each prediction loads the sport's whole completed
 * history to fit its baselines, so forty parallel calls meant forty full
 * reloads queued against one worker — measured at over two minutes for a
 * page the engine itself can answer in about five seconds.
 *
 * `/predictions/today` does the same work with the history loaded once,
 * and returns `prediction: null` per fixture it could not price rather than
 * dropping the row, so the page can say what it could not do.
 */
export function getBoard(
  options: {
    date?: string;
    view?: BoardView;
    sport?: string;
    competition?: string;
    minConfidence?: number;
    limit?: number;
  } = {},
): Promise<BoardResponse> {
  const query = new URLSearchParams({ limit: String(options.limit ?? 60) });
  if (options.date) query.set("on_date", options.date);
  if (options.view && options.view !== "all") query.set("view", options.view);
  if (options.sport) query.set("sport", options.sport);
  if (options.competition) query.set("competition", options.competition);
  if (options.minConfidence !== undefined) {
    query.set("min_confidence", String(options.minConfidence));
  }
  return engineFetch<BoardResponse>(`/predictions/today?${query}`, {
    revalidate: 300,
  });
}

/**
 * A day's card as a table, grouped by competition.
 *
 * Distinct from `getBoard` above, which serves `/predictions/today` and
 * answers a different question — how much the estimators agreed. This one is
 * the browsable board: any date, grouped by competition, graded once played.
 *
 * Short revalidate window because the board changes shape through the day:
 * fixtures kick off, scores arrive, and picks settle. A stale graded board is
 * worse than a stale unplayed one — it shows verdicts that have since changed.
 */
export function getDayBoard(
  options: {
    date?: string;
    country?: string;
    competition?: string;
    sport?: string;
  } = {},
): Promise<DayBoard> {
  const query = new URLSearchParams();
  if (options.date) query.set("on_date", options.date);
  if (options.country) query.set("country", options.country);
  if (options.competition) query.set("competition", options.competition);
  if (options.sport) query.set("sport", options.sport);
  const suffix = query.toString() ? `?${query}` : "";
  return engineFetch<DayBoard>(`/board${suffix}`, { revalidate: 120 });
}

/** The date strip, with a fixture count per day. */
export function getBoardDates(span = 3): Promise<BoardDates> {
  return engineFetch<BoardDates>(`/board/dates?span=${span}`, {
    revalidate: 600,
  });
}

/**
 * The public track record, regraded from stored predictions.
 *
 * Revalidated hourly: it only moves when yesterday's fixtures settle, and a
 * page this argumentative should not be recomputed on every view.
 */
export function getProgress(): Promise<Progress> {
  return engineFetch<Progress>("/progress", { revalidate: 3600 });
}

/** Every competition we model, grouped by country. */
export function getLeagues(): Promise<Leagues> {
  return engineFetch<Leagues>("/leagues", { revalidate: 3600 });
}

/** One competition's page: rates, table, record, fixtures and results.
 *  Null for a slug that names no competition. */
export async function getLeague(slug: string): Promise<LeagueDetail | null> {
  try {
    return await engineFetch<LeagueDetail>(
      `/leagues/${encodeURIComponent(slug)}`,
      { revalidate: 600 },
    );
  } catch (error) {
    if (error instanceof EngineError && error.status === 404) return null;
    throw error;
  }
}

/** The day's likeliest picks, with the record of the settled ones. */
export function getBankers(date?: string): Promise<Bankers> {
  const query = date ? `?on_date=${date}` : "";
  return engineFetch<Bankers>(`/bankers${query}`, { revalidate: 300 });
}

/** An accumulator assembled from the day's picks. */
export function getSlip(
  options: {
    date?: string;
    targetOdds?: number;
    minLegs?: number;
    maxLegs?: number;
    markets?: string;
  } = {},
): Promise<Slip> {
  const query = new URLSearchParams();
  if (options.date) query.set("on_date", options.date);
  if (options.targetOdds) query.set("target_odds", String(options.targetOdds));
  if (options.minLegs) query.set("min_legs", String(options.minLegs));
  if (options.maxLegs) query.set("max_legs", String(options.maxLegs));
  if (options.markets) query.set("markets", options.markets);
  const suffix = query.toString() ? `?${query}` : "";
  return engineFetch<Slip>(`/slip${suffix}`, { revalidate: 300 });
}

/** The active version and recent history for one model. */
export interface ModelPerformance {
  model_name: string;
  active_version: {
    version: string;
    trained_at: string;
    metrics: Record<string, unknown>;
  } | null;
  recent_versions: Array<{
    version: string;
    trained_at: string;
    is_active: boolean;
    metrics: Record<string, unknown>;
  }>;
}

export interface Monitoring {
  calibration: {
    num_predictions: number;
    brier_score: number;
    overall_accuracy: number;
    buckets: Array<{
      bucket_low: number;
      bucket_high: number;
      count: number;
      mean_predicted_probability: number;
      actual_accuracy: number;
    }>;
  } | null;
  drift: { drift_detected: boolean; reasons: string[] } | null;
  feature_drift: { shifted_features: string[]; reasons: string[] } | null;
}

export function getModelPerformance(
  modelName: string,
): Promise<ModelPerformance> {
  return engineFetch<ModelPerformance>(
    `/model/performance?model_name=${encodeURIComponent(modelName)}`,
    { revalidate: 600 },
  );
}

export function getMonitoring(modelName: string): Promise<Monitoring> {
  return engineFetch<Monitoring>(
    `/model/monitoring?model_name=${encodeURIComponent(modelName)}`,
    { revalidate: 600 },
  );
}

export type LeaderboardSort = "edge" | "accuracy" | "log_loss" | "samples";

export interface LeaderboardRow {
  rank: number;
  model_name: string;
  label: string;
  sport: string;
  market: string;
  version: string;
  trained_at: string | null;
  accuracy: number;
  log_loss: number | null;
  /** Null when the model records no baseline — not zero, which would read as "no edge". */
  baseline: number | null;
  baseline_kind: string | null;
  edge: number | null;
  samples: number | null;
  /** Evaluated on too few matches for the edge to be distinguishable from noise. */
  provisional: boolean;
  /** Accuracy change since the previous trained version; null if there is none. */
  trend: number | null;
}

export interface LeaderboardResponse {
  sort: LeaderboardSort;
  count: number;
  provisional_threshold: number;
  summary: {
    with_baseline: number;
    beating_baseline: number;
    provisional: number;
  };
  models: LeaderboardRow[];
}

export function getLeaderboard(
  options: { sort?: LeaderboardSort; sport?: string } = {},
): Promise<LeaderboardResponse> {
  const query = new URLSearchParams();
  if (options.sort) query.set("sort", options.sort);
  if (options.sport) query.set("sport", options.sport);
  const suffix = query.toString() ? `?${query}` : "";
  return engineFetch<LeaderboardResponse>(`/model/leaderboard${suffix}`, {
    revalidate: 600,
  });
}
