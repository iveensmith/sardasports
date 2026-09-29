/**
 * Confidence — the one thing gold is spent on.
 *
 * This is the product's whole argument: a prediction without its confidence
 * is a tip, and this engine is not a tipster. So confidence gets the only
 * saturated colour in the palette and appears at most once per view.
 *
 * The scale is the engine's own 0-100 and its own four labels; nothing is
 * re-derived here. A high number means the model's outcome distribution is
 * far from a coin flip, not that the model is guaranteed right — which is
 * why the label is shown next to the number rather than the number alone.
 */

import type { ConfidenceLabel } from "@/lib/types";

interface Props {
  value: number;
  label: ConfidenceLabel;
  /** `bar` for detail views, `pill` for dense rows. */
  variant?: "bar" | "pill";
}

export function ConfidenceMeter({ value, label, variant = "bar" }: Props) {
  const clamped = Math.min(Math.max(value, 0), 100);

  if (variant === "pill") {
    return (
      <span
        className="inline-flex items-center gap-2 rounded-full border px-2.5 py-1 text-[12px] font-medium"
        style={{
          borderColor: "var(--color-gold-dim)",
          color: "var(--color-gold-bright)",
        }}
        title={`${label} confidence (${clamped.toFixed(1)}%)`}
      >
        <span
          aria-hidden
          className="inline-block h-1.5 w-1.5 rounded-full"
          style={{ background: "var(--color-gold)" }}
        />
        {clamped.toFixed(0)}
      </span>
    );
  }

  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between">
        <span className="text-[13px] text-[var(--color-text-dim)]">
          Model confidence
        </span>
        <span className="text-[13px] text-[var(--color-text-dim)]">
          {label}
        </span>
      </div>

      <div
        className="h-2 w-full overflow-hidden rounded-full bg-[var(--color-line)]"
        role="meter"
        aria-valuenow={Math.round(clamped)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`Model confidence: ${label}`}
      >
        <div
          className="h-full rounded-full transition-[width] duration-700"
          style={{
            width: `${clamped}%`,
            background:
              "linear-gradient(90deg, var(--color-gold-dim), var(--color-gold-bright))",
          }}
        />
      </div>

      <div className="text-[28px] leading-none font-semibold text-[var(--color-gold-bright)]">
        {clamped.toFixed(1)}
        <span className="ml-1 text-[14px] font-normal text-[var(--color-text-faint)]">
          / 100
        </span>
      </div>
    </div>
  );
}
