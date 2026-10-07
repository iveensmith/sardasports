/**
 * A competition's table, from the results we hold.
 *
 * It is computed from ingested results rather than fetched from anywhere, so
 * it is only as current as those results — which is why the page captions it
 * with the season and the newest result it runs to, instead of presenting it
 * as live.
 */

import Link from "next/link";
import type { StandingRow } from "@/lib/discover";
import { teamSlug } from "@/lib/teams";

const COLUMNS: Array<{ key: keyof StandingRow; label: string }> = [
  { key: "played", label: "P" },
  { key: "won", label: "W" },
  { key: "drawn", label: "D" },
  { key: "lost", label: "L" },
  { key: "goals_for", label: "GF" },
  { key: "goals_against", label: "GA" },
  { key: "goal_difference", label: "GD" },
];

export function StandingsTable({ rows }: { rows: StandingRow[] }) {
  return (
    <div className="overflow-x-auto rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)]">
      <table className="w-full min-w-[520px] text-[13px]">
        <thead>
          <tr className="text-[11px] tracking-wider text-[var(--color-text-faint)] uppercase">
            <th className="w-10 px-4 py-3 text-left font-medium">#</th>
            <th className="py-3 text-left font-medium">Team</th>
            {COLUMNS.map((c) => (
              <th key={c.key} className="px-2 py-3 text-right font-medium">
                {c.label}
              </th>
            ))}
            <th className="px-4 py-3 text-right font-medium">Pts</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={row.team} className="border-t border-[var(--color-line)]">
              <td className="px-4 py-2.5 text-[var(--color-text-faint)] tabular-nums">
                {index + 1}
              </td>
              <td className="py-2.5 font-medium">
                <Link
                  href={`/teams/${teamSlug(row.team)}`}
                  className="hover:text-[var(--color-gold-bright)]"
                >
                  {row.team}
                </Link>
              </td>
              {COLUMNS.map((c) => {
                const value = row[c.key] as number;
                return (
                  <td
                    key={c.key}
                    className="px-2 py-2.5 text-right text-[var(--color-text-dim)] tabular-nums"
                  >
                    {c.key === "goal_difference" && value > 0
                      ? `+${value}`
                      : value}
                  </td>
                );
              })}
              <td
                className="px-4 py-2.5 text-right font-semibold tabular-nums"
                style={{ color: "var(--color-gold-bright)" }}
              >
                {row.points}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
