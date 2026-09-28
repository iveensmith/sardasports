/**
 * Derive the estimator split from a prediction.
 *
 * The board endpoint computes this server-side for its tabs, but the match
 * page fetches `/predict/{id}` directly, so the same derivation lives here
 * rather than being requested twice or duplicated inline. It reads only
 * `estimator_probs`, which the engine now returns alongside the blend.
 */

import type { Agreement } from "./api";
import type { Prediction } from "./types";

const OUTCOMES = ["home", "draw", "away"] as const;
type Outcome = (typeof OUTCOMES)[number];

function pickFrom(probs: number[] | undefined): Outcome | null {
  if (!probs || probs.length === 0) return null;
  let best = 0;
  for (let i = 1; i < probs.length; i++) if (probs[i] > probs[best]) best = i;
  return OUTCOMES[best] ?? null;
}

export function agreementFrom(prediction: Prediction): Agreement | null {
  const estimators = (prediction as { estimator_probs?: Record<string, number[]> })
    .estimator_probs;
  // Fewer than two estimators is not weaker agreement, it is no comparison
  // at all — basketball and tennis blend one model with an Elo baseline.
  if (!estimators || Object.keys(estimators).length < 2) return null;

  const blended = [
    prediction.home_win,
    "draw" in prediction ? prediction.draw : 0,
    prediction.away_win,
  ];
  const consensus = pickFrom(blended);
  if (!consensus) return null;

  const byEstimator: Record<string, Outcome | null> = {};
  let agreeing = 0;
  for (const [name, probs] of Object.entries(estimators)) {
    const pick = pickFrom(probs);
    byEstimator[name] = pick;
    if (pick === consensus) agreeing += 1;
  }
  const total = Object.keys(byEstimator).length;

  return {
    pick: consensus,
    agreeing,
    total,
    unanimous: agreeing === total,
    by_estimator: byEstimator,
  };
}
