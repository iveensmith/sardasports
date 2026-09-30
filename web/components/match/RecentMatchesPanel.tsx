/**
 * Each side's own recent results, independent of each other and of any
 * head-to-head history — this is "how have they been playing", not "how
 * have they done against this opponent" (see `H2HPanel` for that).
 *
 * Two independent toggles per side, matching the reference: which matches
 * count (Total / Home / Away — a client-side filter of the same last-10
 * list, not a deeper fetch, confirmed against the reference's own
 * behaviour) and which score to read (Full Time / Half Time). Switching to
 * Half Time recomputes the W/D/L result for each row too, not just the
 * printed score — a match led at half-time and drawn by full-time is a
 * different result each way, and the reference shows exactly that. A
 * match with no half-time score on record (not every competition has one)
 * shows "—" and a neutral marker in that mode, never a fabricated 0-0.
 */

"use client";

import { useState } from "react";
import Link from "next/link";
import type { RecentMatch } from "@/lib/types";

type Venue = "total" | "home" | "away";
type Timeframe = "ft" | "ht";

function scoreFor(m: RecentMatch, timeframe: Timeframe) {
  return timeframe === "ft"
    ? { home: m.home_score, away: m.away_score }
    : { home: m.home_ht_score, away: m.away_ht_score };
}

function resultFor(
  home: number | null,
  away: number | null,
  isHome: boolean,
): "W" | "D" | "L" | null {
  if (home === null || away === null) return null;
  const scored = isHome ? home : away;
  const conceded = isHome ? away : home;
  if (scored > conceded) return "W";
  if (scored === conceded) return "D";
  return "L";
}

const RESULT_COLOR: Record<"W" | "D" | "L", string> = {
  W: "var(--color-won)",
  D: "var(--color-unknown)",
  L: "var(--color-lost)",
};

function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
}: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
}) {
  return (
    <div className="flex rounded-[var(--radius-md)] bg-[var(--color-surface-raised)] p-0.5 text-[12px]">
      {options.map((opt) => {
        const active = opt.value === value;
        return (
          <button
            key={opt.value}
            type="button"
            onClick={() => onChange(opt.value)}
            aria-pressed={active}
            className="flex-1 rounded-[calc(var(--radius-md)-2px)] px-2 py-1.5 font-medium transition-colors"
            style={{
              background: active ? "var(--color-surface)" : "transparent",
              color: active ? "var(--color-text)" : "var(--color-text-faint)",
            }}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}

function TeamRecentList({
  team,
  matches,
}: {
  team: string;
  matches: RecentMatch[];
}) {
  const [venue, setVenue] = useState<Venue>("total");
  const [timeframe, setTimeframe] = useState<Timeframe>("ft");

  const filtered = matches.filter((m) => {
    if (venue === "home") return m.home_team === team;
    if (venue === "away") return m.away_team === team;
    return true;
  });

  return (
    <div>
      <div className="mb-2.5 grid grid-cols-2 gap-2">
        <SegmentedControl
          value={venue}
          onChange={setVenue}
          options={[
            { value: "total", label: "Total" },
            { value: "home", label: "Home" },
            { value: "away", label: "Away" },
          ]}
        />
        <SegmentedControl
          value={timeframe}
          onChange={setTimeframe}
          options={[
            { value: "ft", label: "Full Time" },
            { value: "ht", label: "Half Time" },
          ]}
        />
      </div>

      <div className="mb-2.5 flex items-center gap-2">
        <h3 className="truncate text-[13.5px] font-semibold">{team}</h3>
        <span className="flex gap-1">
          {filtered.map((m) => {
            const { home, away } = scoreFor(m, timeframe);
            const result = resultFor(home, away, m.home_team === team);
            if (!result) return null;
            return (
              <span
                key={m.match_id}
                className="flex h-4 w-4 items-center justify-center rounded-full text-[9px] font-bold text-[var(--color-ink-on-accent)]"
                style={{ background: RESULT_COLOR[result] }}
              >
                {result}
              </span>
            );
          })}
        </span>
      </div>

      {filtered.length === 0 ? (
        <p className="text-[12.5px] text-[var(--color-text-faint)]">
          No {venue} matches in this window.
        </p>
      ) : (
        <ul className="space-y-1.5">
          {filtered.map((m) => {
            const opponent = m.home_team === team ? m.away_team : m.home_team;
            const isHome = m.home_team === team;
            const venueLabel = isHome ? "H" : "A";
            const { home, away } = scoreFor(m, timeframe);
            const result = resultFor(home, away, isHome);
            return (
              <li key={m.match_id}>
                <Link
                  href={`/match/${m.match_id}`}
                  className="flex items-center gap-2 rounded-[var(--radius-md)] px-2 py-1.5 text-[12.5px] transition-colors hover:bg-[var(--color-surface-raised)]"
                >
                  <span
                    className="flex h-4 w-4 shrink-0 items-center justify-center rounded-[3px] text-[9px] font-bold text-[var(--color-ink-on-accent)]"
                    style={{
                      background: result
                        ? RESULT_COLOR[result]
                        : "var(--color-unknown)",
                    }}
                  >
                    {result ?? "–"}
                  </span>
                  <span className="text-[var(--color-text-faint)]">
                    {venueLabel}
                  </span>
                  <span className="min-w-0 flex-1 truncate">{opponent}</span>
                  <span className="font-semibold tabular-nums">
                    {home !== null && away !== null ? `${home}-${away}` : "—"}
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

export function RecentMatchesPanel({
  home,
  away,
  homeMatches,
  awayMatches,
}: {
  home: string;
  away: string;
  homeMatches: RecentMatch[];
  awayMatches: RecentMatch[];
}) {
  if (homeMatches.length === 0 && awayMatches.length === 0) return null;

  return (
    <section className="rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] p-6">
      <h2 className="mb-5 text-[15px] font-semibold">Recent matches</h2>
      <div className="grid gap-6 sm:grid-cols-2">
        <TeamRecentList team={home} matches={homeMatches} />
        <TeamRecentList team={away} matches={awayMatches} />
      </div>
    </section>
  );
}
