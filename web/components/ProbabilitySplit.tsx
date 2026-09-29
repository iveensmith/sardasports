/**
 * The outcome split — the single most-repeated element in the product.
 *
 * Built as one bar rather than three tiles because the quantity being shown
 * is a *distribution*: the whole point is that the three numbers sum to 100
 * and trade against each other, which three separate cards hide.
 *
 * Football passes a draw; basketball and tennis do not, and the component
 * takes `draw` as optional rather than defaulting it to 0 — a zero-width
 * draw segment would still render a legend entry claiming a draw exists,
 * which is false for both of those sports.
 */

interface Props {
  home: number;
  away: number;
  draw?: number;
  homeLabel: string;
  awayLabel: string;
  /** Compact suppresses the legend for dense list rows. */
  compact?: boolean;
}

export function ProbabilitySplit({
  home,
  away,
  draw,
  homeLabel,
  awayLabel,
  compact = false,
}: Props) {
  const segments = [
    { key: "home", value: home, color: "var(--color-home)", label: homeLabel },
    ...(draw === undefined
      ? []
      : [
          {
            key: "draw",
            value: draw,
            color: "var(--color-draw)",
            label: "Draw",
          },
        ]),
    { key: "away", value: away, color: "var(--color-away)", label: awayLabel },
  ];

  return (
    <div className={compact ? "" : "space-y-2"}>
      <div
        className="flex h-9 w-full overflow-hidden rounded-[var(--radius-sm)]"
        role="img"
        aria-label={segments
          .map((s) => `${s.label} ${s.value.toFixed(1)}%`)
          .join(", ")}
      >
        {segments.map((s) => (
          <div
            key={s.key}
            className="flex items-center justify-center text-[13px] font-semibold text-[#06090d] transition-[flex-grow] duration-500"
            style={{ flexGrow: Math.max(s.value, 0.001), background: s.color }}
          >
            {/* Below ~8% the label cannot fit legibly; the legend carries it. */}
            {s.value >= 8 ? `${s.value.toFixed(1)}%` : ""}
          </div>
        ))}
      </div>

      {!compact && (
        <div className="flex flex-wrap gap-x-5 gap-y-1 text-[13px] text-[var(--color-text-dim)]">
          {segments.map((s) => (
            <span key={s.key} className="flex items-center gap-2">
              <span
                aria-hidden
                className="inline-block h-2 w-2 rounded-full"
                style={{ background: s.color }}
              />
              <span className="truncate">{s.label}</span>
              <span className="text-[var(--color-text)]">
                {s.value.toFixed(1)}%
              </span>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
