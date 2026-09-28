/**
 * Confidence as a ring.
 *
 * A ring rather than a bar because it sits at the end of a dense row where
 * a horizontal bar would compete with the probability split for the same
 * reading direction. The number stays inside it, so the value is legible
 * without decoding the arc — the arc is reinforcement, not the encoding.
 */

interface Props {
  value: number;
  label: string;
  size?: number;
}

export function ConfidenceRing({ value, label, size = 46 }: Props) {
  const clamped = Math.min(Math.max(value, 0), 100);
  const stroke = 3;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const filled = (clamped / 100) * circumference;

  return (
    <div
      className="relative shrink-0"
      style={{ width: size, height: size }}
      role="meter"
      aria-valuenow={Math.round(clamped)}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={`Model confidence: ${label}, ${clamped.toFixed(0)} of 100`}
      title={`${label} confidence (${clamped.toFixed(1)}/100)`}
    >
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="var(--color-line)"
          strokeWidth={stroke}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="var(--color-gold)"
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={`${filled} ${circumference - filled}`}
        />
      </svg>
      <span
        className="absolute inset-0 flex items-center justify-center text-[13px] font-semibold"
        style={{ color: "var(--color-gold-bright)" }}
      >
        {clamped.toFixed(0)}
      </span>
    </div>
  );
}
