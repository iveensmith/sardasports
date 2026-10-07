/**
 * What the engine expected, beside what actually happened.
 *
 * The bar follows the reference site's own shape for this panel: one bar
 * per stat, split at a shared centre line, each side growing outward from
 * it rather than the two sides just splitting a single track. Where a
 * genuine prediction exists, the bar shows both numbers on the same track —
 * a solid fill out to the smaller of the two, then a hatched extension out
 * to the larger, so the *gap* between prediction and reality is the part
 * that's visible, not just the two figures printed beside each other.
 * Hatching reuses this site's own "not a hard number" texture (the same
 * dashed styling `BoardTable` already puts on an estimated price), rather
 * than borrowing the reference's plain grey.
 *
 * Goals is the only row with a genuine predicted number —
 * `expected_goals_*` is a first-class model output. Corners and cards are
 * priced as over/under lines with a probability each, not a single expected
 * count, and inventing one by interpolating those probabilities would be a
 * number the model never actually produced. So every other row is
 * actual-only: real, once `fetch_match_stats.py` has reported it, and
 * simply absent otherwise — never a fabricated "predicted" figure standing
 * in for one the engine doesn't have.
 */

import type { ActualStats, MatchScore } from "@/lib/types";
import { CenterBar } from "@/components/match/CenterBar";

interface Row {
  label: string;
  home: number | null;
  away: number | null;
  predictedHome?: number;
  predictedAway?: number;
  /** Shown after the value — "%" for possession. */
  suffix?: string;
  /** Round the displayed predicted figure to this many decimals (goals'
   *  expected value wants 2; everything else predicted is a whole count). */
  predictedDecimals?: number;
}

function StatRow({ row }: { row: Row }) {
  if (row.home === null && row.away === null) return null;
  const home = row.home ?? 0;
  const away = row.away ?? 0;
  const scale =
    Math.max(home, away, row.predictedHome ?? 0, row.predictedAway ?? 0) *
      1.05 || 1;
  const decimals = row.predictedDecimals ?? 0;

  const homeHi =
    row.predictedHome === undefined ? home : Math.max(home, row.predictedHome);
  const homeLo =
    row.predictedHome === undefined ? home : Math.min(home, row.predictedHome);
  const awayHi =
    row.predictedAway === undefined ? away : Math.max(away, row.predictedAway);
  const awayLo =
    row.predictedAway === undefined ? away : Math.min(away, row.predictedAway);

  return (
    <div>
      <div className="flex items-end justify-between gap-3">
        <div className="text-left">
          <p className="text-[14px] font-semibold tabular-nums">
            {row.home ?? "—"}
            {row.suffix ?? ""}
          </p>
          {row.predictedHome !== undefined && (
            <p className="text-[11px] tabular-nums text-[var(--color-text-faint)]">
              {row.predictedHome.toFixed(decimals)}
              {row.suffix ?? ""}
            </p>
          )}
        </div>
        <span className="pb-0.5 text-[11px] tracking-wider text-[var(--color-text-faint)] uppercase">
          {row.label}
        </span>
        <div className="text-right">
          <p className="text-[14px] font-semibold tabular-nums">
            {row.away ?? "—"}
            {row.suffix ?? ""}
          </p>
          {row.predictedAway !== undefined && (
            <p className="text-[11px] tabular-nums text-[var(--color-text-faint)]">
              {row.predictedAway.toFixed(decimals)}
              {row.suffix ?? ""}
            </p>
          )}
        </div>
      </div>
      <div className="mt-1.5">
        <CenterBar
          homeFraction={homeLo / scale}
          homeHatchFraction={(homeHi - homeLo) / scale}
          awayFraction={awayLo / scale}
          awayHatchFraction={(awayHi - awayLo) / scale}
        />
      </div>
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
      predictedDecimals: 2,
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
        Goals is the only row with a predicted figure (shown small, beneath the
        actual count). Corners and cards are priced as over/under lines, not a
        single count, so the other rows show only what actually happened.
      </p>
      <div className="space-y-5">
        {visibleRows.map((row) => (
          <StatRow key={row.label} row={row} />
        ))}
      </div>
    </section>
  );
}
