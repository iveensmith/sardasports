"use client";

/**
 * Model accuracy against the baseline each model actually has to beat.
 *
 * Raw accuracy alone is misleading here and the engine knows it: a market
 * line far from 50/50 is an easier binary problem, so "71.9% accurate" can
 * mean a model barely beating "always guess the majority". Every model that
 * records a baseline gets it drawn beside the bar, and the page ranks by the
 * *gap*, not by accuracy.
 *
 * Form: horizontal bars. The labels are long model names and there are ~19
 * of them, which a vertical bar chart cannot label without rotating text.
 *
 * Two series (accuracy, baseline) so a legend is always present, and both
 * are direct-labeled — identity never rests on colour alone.
 */

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export interface ModelRow {
  name: string;
  label: string;
  sport: string;
  accuracy: number;
  baseline: number | null;
  baselineKind: string | null;
}

const AXIS = "var(--color-text-faint)";
const GRID = "var(--color-line)";

const SPORT_COLOR: Record<string, string> = {
  football: "var(--color-home)",
  basketball: "var(--color-draw)",
  tennis: "var(--color-away)",
};

function AccuracyTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ payload: ModelRow }>;
}) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload;
  const edge = row.baseline === null ? null : row.accuracy - row.baseline;
  return (
    <div className="max-w-[20rem] rounded-[var(--radius-md)] border border-[var(--color-line-strong)] bg-[var(--color-surface-raised)] px-3 py-2 text-[13px] shadow-lg">
      <p className="font-medium">{row.label}</p>
      <p className="mt-0.5 text-[12px] text-[var(--color-text-faint)]">
        {row.sport}
      </p>
      <dl className="mt-1.5 space-y-0.5 text-[var(--color-text-dim)]">
        <div className="flex justify-between gap-6">
          <dt>Accuracy</dt>
          <dd className="text-[var(--color-text)]">
            {row.accuracy.toFixed(2)}%
          </dd>
        </div>
        {row.baseline !== null && (
          <>
            <div className="flex justify-between gap-6">
              <dt>{row.baselineKind ?? "Baseline"}</dt>
              <dd className="text-[var(--color-text)]">
                {row.baseline.toFixed(2)}%
              </dd>
            </div>
            <div className="flex justify-between gap-6">
              <dt>Real edge</dt>
              <dd className="text-[var(--color-text)]">
                {edge! >= 0 ? "+" : ""}
                {edge!.toFixed(2)} pts
              </dd>
            </div>
          </>
        )}
      </dl>
      {row.baseline === null && (
        <p className="mt-1.5 text-[12px] leading-snug text-[var(--color-text-faint)]">
          No baseline recorded for this model, so the accuracy alone does not
          say how much of it is skill.
        </p>
      )}
    </div>
  );
}

export function ModelAccuracyChart({ rows }: { rows: ModelRow[] }) {
  if (rows.length === 0) {
    return (
      <p className="py-10 text-center text-[14px] text-[var(--color-text-dim)]">
        No trained models found.
      </p>
    );
  }

  return (
    <div style={{ height: rows.length * 34 + 60 }} className="w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={rows}
          layout="vertical"
          margin={{ top: 4, right: 52, bottom: 8, left: 4 }}
          barCategoryGap={6}
        >
          <CartesianGrid stroke={GRID} strokeDasharray="2 4" horizontal={false} />
          <XAxis
            type="number"
            domain={[0, 100]}
            ticks={[0, 25, 50, 75, 100]}
            tick={{ fill: AXIS, fontSize: 12 }}
            stroke={GRID}
            unit="%"
          />
          <YAxis
            type="category"
            dataKey="label"
            width={210}
            tick={{ fill: "var(--color-text-dim)", fontSize: 12 }}
            stroke={GRID}
          />
          <Tooltip
            content={<AccuracyTooltip />}
            cursor={{ fill: "var(--color-surface-raised)", fillOpacity: 0.5 }}
          />
          <Legend
            verticalAlign="top"
            align="left"
            height={26}
            formatter={(value) => (
              <span style={{ color: "var(--color-text-dim)", fontSize: 13 }}>
                {value}
              </span>
            )}
          />
          <Bar
            name="Accuracy"
            dataKey="accuracy"
            radius={[0, 4, 4, 0]}
            label={{
              position: "right",
              fill: "var(--color-text-dim)",
              fontSize: 11,
              formatter: (value: unknown) =>
                typeof value === "number" ? `${value.toFixed(1)}%` : "",
            }}
          >
            {rows.map((row) => (
              <Cell
                key={row.name}
                fill={SPORT_COLOR[row.sport] ?? "var(--color-home)"}
              />
            ))}
          </Bar>
          <Bar
            name="Baseline to beat"
            dataKey="baseline"
            fill="var(--color-unknown)"
            radius={[0, 4, 4, 0]}
            barSize={6}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
