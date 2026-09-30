/**
 * What the engine expected, beside what actually happened.
 *
 * Goals is the only row with a genuine predicted number — `expected_goals_*`
 * is a first-class model output. Corners and cards are priced as over/under
 * lines with a probability each, not a single expected count, and inventing
 * one by interpolating those probabilities would be a number the model
 * never actually produced. So every other row here is actual-only: real,
 * once `fetch_match_stats.py` has reported it, and simply absent from the
 * list otherwise — never a fabricated "predicted" figure standing in for
 * one the engine doesn't have.
 */

import type { ActualStats, MatchScore } from "@/lib/types";

interface Row {
  label: string;
  home: number | null;
  away: number | null;
  predictedHome?: number;
  predictedAway?: number;
  /** Shown after the value — "%" for possession. */
  suffix?: string;
}

function StatRow({ row }: { row: Row }) {
  if (row.home === null && row.away === null) return null;
  const total = (row.home ?? 0) + (row.away ?? 0);
  const homeShare = total > 0 ? (row.home ?? 0) / total : 0.5;
  const awayShare = total > 0 ? (row.away ?? 0) / total : 0.5;
  const hasPrediction =
    row.predictedHome !== undefined && row.predictedAway !== undefined;

  return (
    <div>
      <div className="flex items-baseline justify-between gap-3 text-[14px]">
        <span className="font-semibold tabular-nums">
          {row.home ?? "—"}
          {row.suffix ?? ""}
        </span>
        <span className="text-[11px] tracking-wider text-[var(--color-text-faint)] uppercase">
          {row.label}
        </span>
        <span className="font-semibold tabular-nums">
          {row.away ?? "—"}
          {row.suffix ?? ""}
        </span>
      </div>
      <div className="mt-1.5 flex h-1.5 w-full overflow-hidden rounded-full bg-[var(--color-line)]">
        <div
          className="transition-[flex-grow] duration-500"
          style={{
            flexGrow: Math.max(homeShare, 0.02),
            background: "var(--color-home)",
          }}
        />
        <div
          className="transition-[flex-grow] duration-500"
          style={{
            flexGrow: Math.max(awayShare, 0.02),
            background: "var(--color-away)",
          }}
        />
      </div>
      {hasPrediction && (
        <div className="mt-1 flex items-baseline justify-between text-[11px] text-[var(--color-text-faint)]">
          <span>predicted {row.predictedHome!.toFixed(2)}</span>
          <span>predicted {row.predictedAway!.toFixed(2)}</span>
        </div>
      )}
    </div>
  );
}

export function StatsComparison({
  expectedGoalsHome,
  expectedGoalsAway,
  score,
  actual,
}: {
  expectedGoalsHome: number;
  expectedGoalsAway: number;
  score: MatchScore | null;
  actual: ActualStats | null;
}) {
  const rows: Row[] = [
    {
      label: "Goals",
      home: score?.home ?? null,
      away: score?.away ?? null,
      predictedHome: expectedGoalsHome,
      predictedAway: expectedGoalsAway,
    },
  ];

  if (actual) {
    rows.push(
      { label: "Shots", home: actual.shots.home, away: actual.shots.away },
      {
        label: "Shots on target",
        home: actual.shots_on_target.home,
        away: actual.shots_on_target.away,
      },
      {
        label: "Corners",
        home: actual.corners.home,
        away: actual.corners.away,
      },
      {
        label: "Cards",
        home:
          actual.yellow_cards.home === null && actual.red_cards.home === null
            ? null
            : (actual.yellow_cards.home ?? 0) + (actual.red_cards.home ?? 0),
        away:
          actual.yellow_cards.away === null && actual.red_cards.away === null
            ? null
            : (actual.yellow_cards.away ?? 0) + (actual.red_cards.away ?? 0),
      },
      {
        label: "Possession",
        home: actual.possession.home,
        away: actual.possession.away,
        suffix: "%",
      },
      {
        label: "Offsides",
        home: actual.offsides.home,
        away: actual.offsides.away,
      },
      { label: "Fouls", home: actual.fouls.home, away: actual.fouls.away },
    );
  }

  const visibleRows = rows.filter((r) => r.home !== null || r.away !== null);
  if (visibleRows.length === 0) return null;

  return (
    <section className="rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] p-6">
      <h2 className="text-[15px] font-semibold">Predicted vs actual</h2>
      <p className="mt-1 mb-5 text-[13px] text-[var(--color-text-dim)]">
        {score
          ? "Goals is the only row with a genuine predicted figure — corners and cards are priced as over/under lines, not a single count, so the rest is what actually happened."
          : "Fills in once the match has been played."}
      </p>
      <div className="space-y-4">
        {visibleRows.map((row) => (
          <StatRow key={row.label} row={row} />
        ))}
      </div>
    </section>
  );
}
