/**
 * One rate over completed matches, as a labelled bar.
 *
 * A null rate (no matches to divide by) renders as a dash with an empty
 * track, never as 0%: "never happens" and "nothing to measure" are opposite
 * claims.
 */

export function RateBar({
  label,
  value,
}: {
  label: string;
  value: number | null;
}) {
  return (
    <div className="rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] p-4">
      <p className="text-[10.5px] tracking-wider text-[var(--color-text-faint)] uppercase">
        {label}
      </p>
      <p className="mt-1.5 text-[24px] leading-none font-bold tabular-nums">
        {value === null ? "—" : `${value.toFixed(0)}%`}
      </p>
      <div
        className="mt-3 h-1.5 overflow-hidden rounded-full"
        style={{ background: "var(--color-line)" }}
        role="presentation"
      >
        <div
          className="h-full rounded-full"
          style={{
            width: `${value ?? 0}%`,
            background: "var(--color-gold-bright)",
          }}
        />
      </div>
    </div>
  );
}
