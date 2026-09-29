"use client";

/**
 * Calibration: predicted probability against what actually happened.
 *
 * This is the chart the whole product argues for. A tipster shows you its
 * winners; a calibrated model shows you that when it says 70%, the thing
 * happens about 70% of the time. The diagonal is perfect calibration, and
 * the distance from it is the honest error.
 *
 * Form choice: a scatter against a reference line, not a bar chart. The
 * question is "how far from the diagonal", which is a position-on-two-axes
 * question; bars would encode one number and throw away the comparison.
 *
 * Bucket sample sizes vary a lot (60 predictions in one, 250 in another), so
 * point area encodes count — a bucket of 12 should not read as loudly as one
 * of 250. Area, not radius, so the perception matches the number.
 *
 * One axis each, no dual scales. Both axes are the same 0–100 probability
 * scale, which is what makes the diagonal meaningful.
 */

import {
  CartesianGrid,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";

export interface CalibrationBucket {
  bucket_low: number;
  bucket_high: number;
  count: number;
  mean_predicted_probability: number;
  actual_accuracy: number;
}

const AXIS = "var(--color-text-faint)";
const GRID = "var(--color-line)";

function CalibrationTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ payload: CalibrationBucket }>;
}) {
  if (!active || !payload?.length) return null;
  const b = payload[0].payload;
  const delta = b.actual_accuracy - b.mean_predicted_probability;
  return (
    <div className="rounded-[var(--radius-md)] border border-[var(--color-line-strong)] bg-[var(--color-surface-raised)] px-3 py-2 text-[13px] shadow-lg">
      <p className="font-medium">
        {b.bucket_low}–{b.bucket_high}% band
      </p>
      <dl className="mt-1.5 space-y-0.5 text-[var(--color-text-dim)]">
        <div className="flex justify-between gap-6">
          <dt>Predicted</dt>
          <dd className="text-[var(--color-text)]">
            {b.mean_predicted_probability.toFixed(1)}%
          </dd>
        </div>
        <div className="flex justify-between gap-6">
          <dt>Actual</dt>
          <dd className="text-[var(--color-text)]">
            {b.actual_accuracy.toFixed(1)}%
          </dd>
        </div>
        <div className="flex justify-between gap-6">
          <dt>Difference</dt>
          <dd className="text-[var(--color-text)]">
            {delta >= 0 ? "+" : ""}
            {delta.toFixed(1)} pts
          </dd>
        </div>
        <div className="flex justify-between gap-6">
          <dt>Predictions</dt>
          <dd className="text-[var(--color-text)]">{b.count}</dd>
        </div>
      </dl>
    </div>
  );
}

export function CalibrationChart({
  buckets,
}: {
  buckets: CalibrationBucket[];
}) {
  if (buckets.length === 0) {
    return (
      <p className="py-10 text-center text-[14px] text-[var(--color-text-dim)]">
        No evaluated predictions yet. Calibration needs matches that have been
        predicted and then played.
      </p>
    );
  }

  return (
    <>
      <div className="h-[340px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <ScatterChart margin={{ top: 8, right: 16, bottom: 28, left: 8 }}>
            <CartesianGrid stroke={GRID} strokeDasharray="2 4" />
            <XAxis
              type="number"
              dataKey="mean_predicted_probability"
              domain={[0, 100]}
              ticks={[0, 25, 50, 75, 100]}
              tick={{ fill: AXIS, fontSize: 12 }}
              stroke={GRID}
              label={{
                value: "Predicted probability (%)",
                position: "insideBottom",
                offset: -16,
                fill: AXIS,
                fontSize: 12,
              }}
            />
            <YAxis
              type="number"
              dataKey="actual_accuracy"
              domain={[0, 100]}
              ticks={[0, 25, 50, 75, 100]}
              tick={{ fill: AXIS, fontSize: 12 }}
              stroke={GRID}
              label={{
                value: "Actually happened (%)",
                angle: -90,
                position: "insideLeft",
                fill: AXIS,
                fontSize: 12,
                style: { textAnchor: "middle" },
              }}
            />
            {/* Area, not radius, encodes sample size. */}
            <ZAxis type="number" dataKey="count" range={[60, 460]} />

            {/* Perfect calibration. Dashed and recessive: it is the
                yardstick, not a series. */}
            <ReferenceLine
              segment={[
                { x: 0, y: 0 },
                { x: 100, y: 100 },
              ]}
              stroke={AXIS}
              strokeDasharray="4 4"
              strokeWidth={2}
            />

            <Tooltip
              content={<CalibrationTooltip />}
              cursor={{ strokeDasharray: "3 3", stroke: GRID }}
            />
            <Legend
              verticalAlign="top"
              align="left"
              height={28}
              formatter={(value) => (
                <span style={{ color: "var(--color-text-dim)", fontSize: 13 }}>
                  {value}
                </span>
              )}
            />
            <Scatter
              name="Probability band (area = number of predictions)"
              data={buckets}
              fill="var(--color-home)"
              fillOpacity={0.85}
              stroke="var(--color-surface)"
              strokeWidth={2}
            />
          </ScatterChart>
        </ResponsiveContainer>
      </div>

      {/* The table view: identity and values never depend on colour alone. */}
      <details className="mt-3">
        <summary className="cursor-pointer text-[13px] text-[var(--color-text-dim)] hover:text-[var(--color-text)]">
          View as table
        </summary>
        <table className="mt-3 w-full text-[13px]">
          <thead>
            <tr className="text-left text-[12px] text-[var(--color-text-faint)]">
              <th className="pb-2 font-medium">Band</th>
              <th className="pb-2 text-right font-medium">Predicted</th>
              <th className="pb-2 text-right font-medium">Actual</th>
              <th className="pb-2 text-right font-medium">Difference</th>
              <th className="pb-2 text-right font-medium">Predictions</th>
            </tr>
          </thead>
          <tbody>
            {buckets.map((b) => {
              const delta = b.actual_accuracy - b.mean_predicted_probability;
              return (
                <tr
                  key={b.bucket_low}
                  className="border-t border-[var(--color-line)]/60"
                >
                  <td className="py-2">
                    {b.bucket_low}–{b.bucket_high}%
                  </td>
                  <td className="py-2 text-right">
                    {b.mean_predicted_probability.toFixed(1)}%
                  </td>
                  <td className="py-2 text-right">
                    {b.actual_accuracy.toFixed(1)}%
                  </td>
                  <td className="py-2 text-right">
                    {delta >= 0 ? "+" : ""}
                    {delta.toFixed(1)}
                  </td>
                  <td className="py-2 text-right">{b.count}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </details>
    </>
  );
}
