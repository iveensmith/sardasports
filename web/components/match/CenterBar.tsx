/**
 * A bidirectional bar split at a shared centre line, each side filling
 * outward from it rather than the two sides splitting one track — the
 * shape every stat comparison on the match page uses (Form, Predicted vs
 * Actual), so it lives here once instead of being redrawn per panel.
 *
 * `hatchFraction` is optional per side: a hatched extension past the solid
 * fill, for a panel that has a second number to show on the same track
 * (Predicted vs Actual's predicted figure). Reuses this site's own
 * "hatched = not a hard number" texture — the same one `BoardTable` already
 * puts on an estimated price — rather than a flat second colour.
 */

function CenterBarHalf({
  fraction,
  hatchFraction,
  color,
  side,
}: {
  fraction: number;
  hatchFraction: number;
  color: string;
  side: "home" | "away";
}) {
  const solidFraction = Math.max(fraction, 0.001);
  const emptyFraction = Math.max(1 - fraction - hatchFraction, 0);

  const solid = (
    <div
      key="solid"
      className="transition-[flex-grow] duration-500"
      style={{ flexGrow: solidFraction, background: color }}
    />
  );
  const hatch = hatchFraction > 0.001 && (
    <div
      key="hatch"
      className="transition-[flex-grow] duration-500"
      style={{
        flexGrow: hatchFraction,
        backgroundImage: `repeating-linear-gradient(135deg, ${color} 0 3px, transparent 3px 7px)`,
        opacity: 0.65,
      }}
    />
  );
  const empty = (
    <div key="empty" aria-hidden style={{ flexGrow: emptyFraction }} />
  );

  return (
    <div className="flex h-2 flex-1 overflow-hidden">
      {side === "home" ? [empty, hatch, solid] : [solid, hatch, empty]}
    </div>
  );
}

export function CenterBar({
  homeFraction,
  awayFraction,
  homeHatchFraction = 0,
  awayHatchFraction = 0,
  homeColor = "var(--color-home)",
  awayColor = "var(--color-away)",
}: {
  /** Each 0–1, the share of a shared per-row scale — not required to sum
   *  to 1, since home and away are independent measurements, not a split
   *  of one total. */
  homeFraction: number;
  awayFraction: number;
  homeHatchFraction?: number;
  awayHatchFraction?: number;
  homeColor?: string;
  awayColor?: string;
}) {
  return (
    <div className="flex w-full overflow-hidden rounded-full bg-[var(--color-line)]">
      <CenterBarHalf
        fraction={homeFraction}
        hatchFraction={homeHatchFraction}
        color={homeColor}
        side="home"
      />
      <div className="w-px shrink-0 bg-[var(--color-line-strong)]" />
      <CenterBarHalf
        fraction={awayFraction}
        hatchFraction={awayHatchFraction}
        color={awayColor}
        side="away"
      />
    </div>
  );
}
