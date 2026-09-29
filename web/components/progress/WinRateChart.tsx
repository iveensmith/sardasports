"use client";

/**
 * Win rate by month, with the sample behind each point.
 *
 * The sample size is the reason this is a composed chart rather than a line.
 * A month with four settled calls and a month with two hundred plot as the
 * same kind of dot, and a reader will draw a trend through both. The bars
 * underneath carry the count, so a spike over a handful of fixtures is
 * visibly a spike over a handful of fixtures.
 *
 * Months with nothing settled are dropped rather than plotted at zero — "no
 * gradeable calls" and "lost every one" are opposite facts.
 */

import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { MonthRecord } from "@/lib/progress";

export function WinRateChart({ months }: { months: MonthRecord[] }) {
  const data = months
    .filter((m) => m.win_rate !== null && m.settled > 0)
    .map((m) => ({
      month: m.month,
      rate: m.win_rate as number,
      settled: m.settled,
    }));

  if (data.length < 2) return null;

  return (
    <section className="rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] p-5">
      <h2 className="text-[15px] font-semibold">Win rate by month</h2>
      <p className="mt-1.5 max-w-[68ch] text-[13px] leading-relaxed text-[var(--color-text-dim)]">
        The line is the rate; the bars are how many calls it is over. Read them
        together — a month standing on a dozen settled calls is not evidence of
        a trend, however high the line goes.
      </p>

      <div className="mt-4 h-[260px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 4, left: -18 }}>
            <CartesianGrid stroke="var(--color-line)" vertical={false} />
            <XAxis
              dataKey="month"
              tick={{ fill: "var(--color-text-faint)", fontSize: 11 }}
              tickLine={false}
              axisLine={{ stroke: "var(--color-line-strong)" }}
            />
            <YAxis
              yAxisId="rate"
              domain={[0, 100]}
              tick={{ fill: "var(--color-text-faint)", fontSize: 11 }}
              tickLine={false}
              axisLine={false}
              unit="%"
            />
            <YAxis yAxisId="count" orientation="right" hide />
            <Tooltip
              contentStyle={{
                background: "var(--color-surface-raised)",
                border: "1px solid var(--color-line-strong)",
                borderRadius: 8,
                fontSize: 12,
              }}
              labelStyle={{ color: "var(--color-text)" }}
              formatter={(value, name) => {
                const figure = typeof value === "number" ? value : Number(value);
                return name === "rate"
                  ? [`${figure.toFixed(1)}%`, "Win rate"]
                  : [String(figure), "Settled calls"];
              }}
            />
            <Bar
              yAxisId="count"
              dataKey="settled"
              fill="var(--color-line-strong)"
              radius={[3, 3, 0, 0]}
              maxBarSize={28}
            />
            <Line
              yAxisId="rate"
              type="monotone"
              dataKey="rate"
              stroke="var(--color-gold-bright)"
              strokeWidth={2}
              dot={{ r: 3, fill: "var(--color-gold-bright)", strokeWidth: 0 }}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
