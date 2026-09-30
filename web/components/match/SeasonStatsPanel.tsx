/**
 * Season averages, both sides — shots, corners, cards, possession,
 * offsides, fouls. Goals themselves live on the Form tab
 * (`TeamFormSummary.goals_scored`/`goals_conceded`), so they aren't
 * repeated here.
 *
 * Not every row will have data for every team: possession, offsides and
 * fouls only exist from the point `scripts/fetch_match_stats.py` started
 * running, so a team can have a full season of goals and zero of those —
 * genuinely, not a bug. A row is skipped entirely when *neither* side has
 * anything for it, the same "absent, not a fabricated zero" rule the rest
 * of this product holds to.
 */

import type { SeasonStat, SeasonStats } from "@/lib/types";
import { CenterBar } from "@/components/match/CenterBar";

interface Row {
  label: string;
  home: SeasonStat | undefined;
  away: SeasonStat | undefined;
  suffix?: string;
}

function StatRow({ row }: { row: Row }) {
  const home = row.home?.value ?? null;
  const away = row.away?.value ?? null;
  if (home === null && away === null) return null;
  const scale = Math.max(home ?? 0, away ?? 0) * 1.05 || 1;

  return (
    <div>
      <div className="flex items-baseline justify-between gap-3 text-[14px]">
        <span className="font-semibold tabular-nums">
          {home !== null ? home.toFixed(1) : "—"}
          {row.suffix ?? ""}
        </span>
        <span className="text-[11px] tracking-wider text-[var(--color-text-faint)] uppercase">
          {row.label}
        </span>
        <span className="font-semibold tabular-nums">
          {away !== null ? away.toFixed(1) : "—"}
          {row.suffix ?? ""}
        </span>
      </div>
      <div className="mt-1.5">
        <CenterBar
          homeFraction={(home ?? 0) / scale}
          awayFraction={(away ?? 0) / scale}
        />
      </div>
    </div>
  );
}

export function SeasonStatsPanel({
  home,
  away,
  homeLabel,
  awayLabel,
}: {
  home: SeasonStats | null;
  away: SeasonStats | null;
  homeLabel: string;
  awayLabel: string;
}) {
  if (!home && !away) return null;

  const rows: Row[] = [
    { label: "Shots", home: home?.shots, away: away?.shots },
    {
      label: "Shots on target",
      home: home?.shots_on_target,
      away: away?.shots_on_target,
    },
    { label: "Corners", home: home?.corners, away: away?.corners },
    { label: "Cards", home: home?.cards, away: away?.cards },
    {
      label: "Possession",
      home: home?.possession,
      away: away?.possession,
      suffix: "%",
    },
    { label: "Offsides", home: home?.offsides, away: away?.offsides },
    { label: "Fouls", home: home?.fouls, away: away?.fouls },
  ];
  const visibleRows = rows.filter(
    (r) => r.home?.value != null || r.away?.value != null,
  );
  if (visibleRows.length === 0) return null;

  const season = home?.season ?? away?.season;

  return (
    <section className="rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] p-6">
      <h2 className="text-[15px] font-semibold">Season statistics</h2>
      <p className="mt-1 mb-5 text-[13px] text-[var(--color-text-dim)]">
        Average per match{season ? `, ${season}` : ""} &mdash; each side&rsquo;s
        own season, and a stat neither team has recorded yet is left off rather
        than shown as zero.
      </p>
      <div className="mb-4 flex justify-between text-[12.5px] font-medium text-[var(--color-text-dim)]">
        <span>{homeLabel}</span>
        <span>{awayLabel}</span>
      </div>
      <div className="space-y-5">
        {visibleRows.map((row) => (
          <StatRow key={row.label} row={row} />
        ))}
      </div>
    </section>
  );
}
