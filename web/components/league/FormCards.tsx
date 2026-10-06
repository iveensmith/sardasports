/**
 * The hottest and coldest side over the last few results.
 *
 * The rule is printed, because "hot" is otherwise a label with nothing behind
 * it: the most points over the last `window` matches this season, goal
 * difference breaking a tie. It is a description of recent results, not a
 * rating or a forecast. The engine only supplies these for a competition whose
 * newest result is recent — otherwise they would describe a past season.
 */

import type { FormEntry } from "@/lib/discover";

function Card({
  heading,
  accent,
  entry,
}: {
  heading: string;
  accent: string;
  entry: FormEntry;
}) {
  return (
    <div
      className="rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] p-4"
      style={{ borderLeft: `3px solid ${accent}` }}
    >
      <p className="text-[10.5px] tracking-wider text-[var(--color-text-faint)] uppercase">
        {heading}
      </p>
      <p className="mt-1.5 text-[17px] font-semibold">{entry.team}</p>
      <p className="mt-1 text-[12.5px] text-[var(--color-text-dim)] tabular-nums">
        {entry.points} pts &middot;{" "}
        <span className="tracking-[0.18em]">{entry.results}</span>
      </p>
    </div>
  );
}

export function FormCards({
  hot,
  cold,
  window,
}: {
  hot: FormEntry;
  cold: FormEntry;
  window: number;
}) {
  return (
    <section>
      <div className="grid gap-3 sm:grid-cols-2">
        <Card heading="Hottest" accent="var(--color-won)" entry={hot} />
        <Card heading="Coldest" accent="var(--color-lost)" entry={cold} />
      </div>
      <p className="mt-2 text-[12px] leading-relaxed text-[var(--color-text-faint)]">
        Most and fewest points over each team&rsquo;s last {window} results this
        season, goal difference breaking a tie. A description of recent results,
        not a rating.
      </p>
    </section>
  );
}
