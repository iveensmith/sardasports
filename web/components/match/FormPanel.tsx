/**
 * Both sides' last-10 form, side by side.
 *
 * Computed the same way the engine's own leakage-safe features are (see
 * `ml.feature_engineering.features.compute_team_form`/`compute_goal_rate_form`)
 * — this is that same window, just surfaced for a reader rather than fed to
 * a model. A team with fewer than 10 completed matches on record shows
 * whatever it actually has; the "10" in each fraction is the window asked
 * for, not a promise every team has played that many.
 */

import type { TeamDetail } from "@/lib/types";

function FormRow({
  label,
  home,
  homeOutOf,
  away,
  awayOutOf,
}: {
  label: string;
  home: number;
  homeOutOf: number;
  away: number;
  awayOutOf: number;
}) {
  return (
    <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3 text-[14px]">
      <span className="text-right font-semibold tabular-nums">
        {home}/{homeOutOf}
      </span>
      <span className="text-[11px] tracking-wider text-[var(--color-text-faint)] uppercase">
        {label}
      </span>
      <span className="font-semibold tabular-nums">
        {away}/{awayOutOf}
      </span>
    </div>
  );
}

export function FormPanel({
  home,
  away,
  homeLabel,
  awayLabel,
}: {
  home: TeamDetail | null;
  away: TeamDetail | null;
  homeLabel: string;
  awayLabel: string;
}) {
  if (!home && !away) return null;

  const h = home?.form_last10 ?? null;
  const a = away?.form_last10 ?? null;
  const homeOutOf = h?.matches_played ?? 0;
  const awayOutOf = a?.matches_played ?? 0;
  if (homeOutOf === 0 && awayOutOf === 0) return null;

  return (
    <section className="rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] p-6">
      <h2 className="text-[15px] font-semibold">Form</h2>
      <p className="mt-1 mb-5 text-[13px] text-[var(--color-text-dim)]">
        Each side&rsquo;s own last 10 completed matches &mdash; the denominator
        differs when one side has played fewer.
      </p>
      <div className="mb-3 flex justify-between text-[12.5px] font-medium text-[var(--color-text-dim)]">
        <span>{homeLabel}</span>
        <span>{awayLabel}</span>
      </div>
      <div className="space-y-3.5">
        <FormRow
          label="Wins"
          home={h?.wins ?? 0}
          homeOutOf={homeOutOf}
          away={a?.wins ?? 0}
          awayOutOf={awayOutOf}
        />
        <FormRow
          label="Over 1.5 goals"
          home={h?.over_1_5 ?? 0}
          homeOutOf={homeOutOf}
          away={a?.over_1_5 ?? 0}
          awayOutOf={awayOutOf}
        />
        <FormRow
          label="Over 2.5 goals"
          home={h?.over_2_5 ?? 0}
          homeOutOf={homeOutOf}
          away={a?.over_2_5 ?? 0}
          awayOutOf={awayOutOf}
        />
        <FormRow
          label="Over 3.5 goals"
          home={h?.over_3_5 ?? 0}
          homeOutOf={homeOutOf}
          away={a?.over_3_5 ?? 0}
          awayOutOf={awayOutOf}
        />
        <FormRow
          label="Both teams scored"
          home={h?.btts ?? 0}
          homeOutOf={homeOutOf}
          away={a?.btts ?? 0}
          awayOutOf={awayOutOf}
        />
      </div>
    </section>
  );
}
