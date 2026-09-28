/**
 * Model analytics.
 *
 * The page's argument: accuracy on its own is close to meaningless here, and
 * the engine already records what each number has to beat. A totals line far
 * from 50/50 is an easier problem, so 71.9% can be a model barely improving
 * on "always guess the majority". Everything below is ranked and read by the
 * *gap* to that baseline.
 *
 * The ROI backtest is deliberately not loaded here — see the note in the
 * markup. It re-simulates every value edge across the held-out test period
 * and now takes over ten minutes on the full dataset, so auto-loading it
 * would hang the page the way it once hung the old dashboard.
 */

import { getModelPerformance, getMonitoring } from "@/lib/api";
import {
  CalibrationChart,
  type CalibrationBucket,
} from "@/components/CalibrationChart";
import { ModelAccuracyChart, type ModelRow } from "@/components/ModelAccuracyChart";

export const revalidate = 600;

export const metadata = {
  title: "Model analytics — UniquePredict",
};

/**
 * Every trained model, with the human label and the sport it belongs to.
 * Kept explicit rather than parsed from the name: the name encodes a line
 * (`..._corners_8_5`) in a form that is convenient for the registry and
 * unreadable in a chart axis.
 */
const MODELS: Array<{ name: string; label: string; sport: string }> = [
  { name: "xgboost_match_result", label: "Match result", sport: "football" },
  { name: "gbm_btts", label: "Both teams to score", sport: "football" },
  { name: "lightgbm_over_under_1_5", label: "Goals over 1.5", sport: "football" },
  { name: "lightgbm_over_under_2_5", label: "Goals over 2.5", sport: "football" },
  {
    name: "lightgbm_over_under_ht_goals_0_5",
    label: "Half-time goals over 0.5",
    sport: "football",
  },
  { name: "lightgbm_over_under_corners_7_5", label: "Corners over 7.5", sport: "football" },
  { name: "lightgbm_over_under_corners_8_5", label: "Corners over 8.5", sport: "football" },
  { name: "lightgbm_over_under_corners_9_5", label: "Corners over 9.5", sport: "football" },
  { name: "gbm_over_under_cards_2_5", label: "Cards over 2.5", sport: "football" },
  { name: "gbm_over_under_cards_3_5", label: "Cards over 3.5", sport: "football" },
  { name: "gbm_over_under_cards_4_5", label: "Cards over 4.5", sport: "football" },
  { name: "lightgbm_basketball_winner", label: "NBA winner", sport: "basketball" },
  { name: "lightgbm_basketball_total_215_5", label: "NBA total 215.5", sport: "basketball" },
  { name: "lightgbm_basketball_total_225_5", label: "NBA total 225.5", sport: "basketball" },
  { name: "lightgbm_basketball_total_235_5", label: "NBA total 235.5", sport: "basketball" },
  { name: "lightgbm_tennis_winner", label: "Tennis winner", sport: "tennis" },
  { name: "lightgbm_tennis_total_games_19_5", label: "Tennis games over 19.5", sport: "tennis" },
  { name: "lightgbm_tennis_total_games_21_5", label: "Tennis games over 21.5", sport: "tennis" },
  { name: "lightgbm_tennis_total_games_23_5", label: "Tennis games over 23.5", sport: "tennis" },
];

/**
 * Pull whichever baseline a model recorded.
 *
 * The trainers each store the comparison that is meaningful for their
 * market: "always pick the home team" for a basketball winner, "always pick
 * the higher-Elo player" for tennis, the majority class for a totals line.
 * A model with none is reported as having none rather than being given a
 * flattering 50%.
 */
function baselineFrom(metrics: Record<string, unknown> | undefined): {
  value: number | null;
  kind: string | null;
} {
  if (!metrics) return { value: null, kind: null };
  const candidates: Array<[string, string]> = [
    ["elo_baseline_accuracy", "Always pick the higher rating"],
    ["home_win_base_rate", "Always pick the home side"],
    ["majority_class_base_rate", "Always pick the majority class"],
  ];
  for (const [key, kind] of candidates) {
    const raw = metrics[key];
    if (typeof raw === "number") return { value: raw * 100, kind };
  }
  return { value: null, kind: null };
}

function StatTile({
  value,
  label,
  note,
}: {
  value: string;
  label: string;
  note?: string;
}) {
  return (
    <div className="rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] p-5">
      <p className="text-[30px] leading-none font-bold tracking-[-0.02em]">
        {value}
      </p>
      <p className="mt-2 text-[13px] text-[var(--color-text-dim)]">{label}</p>
      {note && (
        <p className="mt-2 text-[12px] leading-snug text-[var(--color-text-faint)]">
          {note}
        </p>
      )}
    </div>
  );
}

export default async function AnalyticsPage() {
  let rows: ModelRow[] = [];
  let buckets: CalibrationBucket[] = [];
  let brier: number | null = null;
  let evaluated = 0;
  let overallAccuracy: number | null = null;
  let driftNote: string | null = null;
  let error: string | null = null;

  try {
    const [monitoring, ...performances] = await Promise.all([
      getMonitoring("xgboost_match_result"),
      ...MODELS.map((m) => getModelPerformance(m.name).catch(() => null)),
    ]);

    buckets = monitoring.calibration?.buckets ?? [];
    brier = monitoring.calibration?.brier_score ?? null;
    evaluated = monitoring.calibration?.num_predictions ?? 0;
    overallAccuracy = monitoring.calibration?.overall_accuracy ?? null;
    driftNote = monitoring.drift?.reasons?.[0] ?? null;

    rows = MODELS.map((model, i) => {
      const performance = performances[i];
      const metrics = performance?.active_version?.metrics as
        | Record<string, unknown>
        | undefined;
      const accuracy = typeof metrics?.accuracy === "number" ? metrics.accuracy : null;
      if (accuracy === null) return null;
      const { value, kind } = baselineFrom(metrics);
      return {
        name: model.name,
        label: model.label,
        sport: model.sport,
        accuracy: accuracy * 100,
        baseline: value,
        baselineKind: kind,
      };
    })
      .filter((r): r is ModelRow => r !== null)
      // Ranked by real edge, not by headline accuracy — a model with no
      // recorded baseline sorts last rather than being assumed good.
      .sort((a, b) => {
        const edgeA = a.baseline === null ? -Infinity : a.accuracy - a.baseline;
        const edgeB = b.baseline === null ? -Infinity : b.accuracy - b.baseline;
        return edgeB - edgeA;
      });
  } catch (e) {
    error = e instanceof Error ? e.message : "The engine could not be reached.";
  }

  const withBaseline = rows.filter((r) => r.baseline !== null);
  const beating = withBaseline.filter((r) => r.accuracy - r.baseline! > 1);

  return (
    <div className="mx-auto max-w-6xl px-4 py-12">
      <header className="mb-8">
        <h1 className="text-[32px] font-bold tracking-[-0.02em]">
          Model analytics
        </h1>
        <p className="mt-2 max-w-[68ch] text-[15px] leading-relaxed text-[var(--color-text-dim)]">
          How the models actually perform, measured against what each one has
          to beat. Accuracy on its own flatters an easy market, so everything
          here is ranked by the gap to that baseline instead.
        </p>
      </header>

      {error ? (
        <div className="rounded-[var(--radius-lg)] border border-[var(--color-line-strong)] bg-[var(--color-surface)] p-6">
          <p className="text-[15px] font-medium">The engine is unreachable</p>
          <p className="mt-2 text-[14px] text-[var(--color-text-dim)]">{error}</p>
        </div>
      ) : (
        <>
          <section className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <StatTile value={String(rows.length)} label="Active models" />
            <StatTile
              value={`${beating.length}/${withBaseline.length}`}
              label="Beating their baseline"
              note="By more than one percentage point."
            />
            <StatTile
              value={brier === null ? "—" : brier.toFixed(3)}
              label="Brier score"
              note="Lower is better. Measures the whole probability, not just the pick."
            />
            <StatTile
              value={evaluated.toLocaleString()}
              label="Evaluated predictions"
              note={
                overallAccuracy === null
                  ? undefined
                  : `${overallAccuracy.toFixed(1)}% correct overall.`
              }
            />
          </section>

          <section className="mb-4 rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] p-6">
            <h2 className="text-[17px] font-semibold">Calibration</h2>
            <p className="mt-1 mb-5 max-w-[70ch] text-[14px] leading-relaxed text-[var(--color-text-dim)]">
              When the model says 70%, does it happen 70% of the time? Each
              point is a probability band; the dashed line is perfect
              calibration. Points below it mean the model was overconfident in
              that band.
            </p>
            <CalibrationChart buckets={buckets} />
            {driftNote && (
              <p className="mt-4 border-t border-[var(--color-line)] pt-4 text-[13px] text-[var(--color-text-dim)]">
                Drift check: {driftNote}
              </p>
            )}
          </section>

          <section className="rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] p-6">
            <h2 className="text-[17px] font-semibold">
              Every model, against its baseline
            </h2>
            <p className="mt-1 mb-5 max-w-[70ch] text-[14px] leading-relaxed text-[var(--color-text-dim)]">
              Sorted by real edge. The thin bar is the baseline each model has
              to beat — for a totals line that is “always guess the majority”,
              for tennis “always pick the higher-rated player”. Where the two
              bars nearly meet, the model is not adding much.
            </p>
            <ModelAccuracyChart rows={rows} />
          </section>

          <section className="mt-4 rounded-[var(--radius-lg)] border border-dashed border-[var(--color-line-strong)] bg-[var(--color-surface)] p-6">
            <h2 className="text-[17px] font-semibold">Return on investment</h2>
            <p className="mt-2 max-w-[70ch] text-[14px] leading-relaxed text-[var(--color-text-dim)]">
              The ROI backtest flat-stakes every value edge over the held-out
              test period. It is not loaded here: measured on the full
              144,000-match dataset it takes roughly twenty minutes, so
              fetching it with the page would simply hang it.
            </p>
            <p className="mt-3 max-w-[70ch] text-[14px] leading-relaxed text-[var(--color-text-dim)]">
              The last figure on record is{" "}
              <strong className="text-[var(--color-text)]">−6.74%</strong>, from
              a smaller single-league dataset. It is quoted as history rather
              than as the current number, because it predates every league,
              sport and model added since — a real, unfavourable result, which
              is what an early-stage model should produce against efficient
              bookmaker odds.
            </p>
          </section>
        </>
      )}
    </div>
  );
}
