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

import type {
  CompetitionsResponse,
  FixturesResponse,
  MatchesResponse,
  Prediction,
} from "./types";

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
}

export interface BoardResponse {
  date: string;
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
export function getBoard(date?: string, limit = 50): Promise<BoardResponse> {
  const query = new URLSearchParams({ limit: String(limit) });
  if (date) query.set("on_date", date);
  return engineFetch<BoardResponse>(`/predictions/today?${query}`, {
    revalidate: 300,
  });
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
