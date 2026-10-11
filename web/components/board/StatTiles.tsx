/**
 * The day's totals.
 *
 * `predicted` is deliberately shown against `fixtures` rather than alone. The
 * gap between them is competitions we have no trained model for, and a board
 * that showed only what it had predicted would look like it covered the whole
 * card. Reporting the shortfall is the difference between a coverage figure
 * and a boast.
 *
 * The won tile appears only once something has been settled, because "0 won"
 * on a day that has not kicked off yet reads as a bad day rather than an
 * early one.
 */

import type { DayBoard } from "@/lib/board";

function Tile({
  label,
  value,
  note,
  accent,
}: {
  label: string;
  value: string | number;
  note?: string;
  accent?: string;
}) {
  return (
    <div className="rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] px-4 py-3">
      <p className="text-[10.5px] tracking-wider text-[var(--color-text-faint)] uppercase">
        {label}
      </p>
      <p
        className="mt-1 text-[26px] leading-none font-bold tabular-nums"
        style={accent ? { color: accent } : undefined}
      >
        {value}
      </p>
      {note && (
        <p className="mt-1 text-[11.5px] text-[var(--color-text-faint)]">
          {note}
        </p>
      )}
    </div>
  );
}

export function StatTiles({ counts }: { counts: DayBoard["counts"] }) {
  // Won out of the tips that were won or lost; a refunded draw is held apart, as everywhere.
  const gradedCount = counts.settled ?? counts.finished;
  const settled = counts.finished > 0 && gradedCount > 0;
  const winRate = settled ? Math.round((counts.won / gradedCount) * 100) : null;
  // The headline figure is the tips the engine was surest of (rated 70% or more before
  // kick-off); the all-tips figure stays on the tile so nothing is hidden.
  const strongFinished = counts.strong_finished ?? 0;
  const strongWon = counts.strong_won ?? 0;
  const hasStrong = strongFinished >= 3;

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <Tile
        label="Fixtures"
        value={counts.fixtures}
        note={
          counts.predicted === counts.fixtures
            ? "all priced"
            : `${counts.fixtures - counts.predicted} with no trained model`
        }
      />
      <Tile label="Predicted" value={counts.predicted} />
      <Tile label="Upcoming" value={counts.upcoming} />
      {settled && hasStrong ? (
        <Tile
          label="Strong tips won"
          value={`${strongWon}/${strongFinished}`}
          note={`${Math.round((strongWon / strongFinished) * 100)}% of tips rated 70%+. All ${gradedCount} best tips: ${counts.won} won`}
          accent="var(--color-won)"
        />
      ) : settled ? (
        <Tile
          label="Best tips won"
          value={`${counts.won}/${gradedCount}`}
          note={winRate === null ? undefined : `${winRate}% of settled`}
          accent="var(--color-won)"
        />
      ) : (
        <Tile
          label="Finished"
          value={counts.finished}
          note="nothing settled yet"
        />
      )}
    </div>
  );
}
