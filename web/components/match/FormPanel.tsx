/**
 * Both sides' last-10 form, side by side.
 *
 * Computed the same way the engine's own leakage-safe features are (see
 * `ml.feature_engineering.features.compute_team_form`/`compute_goal_rate_form`)
 * — this is that same window, just surfaced for a reader rather than fed to
 * a model. A team with fewer than 10 completed matches on record shows
 * whatever it actually has; the "10" in each fraction is the window asked
 * for, not a promise every team has played that many.
 *
 * Same bar as `StatsComparison` — a bidirectional track split at a shared
 * centre, each side filling outward from it — with no hatch, since there is
 * only one number per side here, not a predicted-vs-actual pair. Each side
 * is its own rate (value / that side's own matches-played), not a shared
 * scale, so an 8/10 and a 6/8 both read as what they are rather than being
 * skewed by whichever team has played more.
 */

import type { TeamDetail } from "@/lib/types";
import { CenterBar } from "@/components/match/CenterBar";

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
    <div>
      <div className="flex items-baseline justify-between gap-3 text-[14px]">
        <span className="font-semibold tabular-nums">
          {home}/{homeOutOf}
        </span>
        <span className="text-[11px] tracking-wider text-[var(--color-text-faint)] uppercase">
          {label}
        </span>
        <span className="font-semibold tabular-nums">
          {away}/{awayOutOf}
        </span>
      </div>
      <div className="mt-1.5">
        <CenterBar
          homeFraction={homeOutOf > 0 ? home / homeOutOf : 0}
          awayFraction={awayOutOf > 0 ? away / awayOutOf : 0}
        />
      </div>
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
        Each side&rsquo;s own last 10 completed matches. The denominator differs
        when one side has played fewer.
      </p>
      <div className="mb-4 flex justify-between text-[12.5px] font-medium text-[var(--color-text-dim)]">
        <span>{homeLabel}</span>
        <span>{awayLabel}</span>
      </div>
      <div className="space-y-5">
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
