/**
 * Predictions / Standings, as `?tab=` links.
 *
 * Plain links rather than client state, for the reason `MatchTabs` gives: the
 * server renders whichever tab is asked for, so there is nothing to hydrate
 * and nothing to hide with CSS.
 */

import Link from "next/link";

export type LeagueTab = "predictions" | "standings";

const LABELS: Record<LeagueTab, string> = {
  predictions: "Match Predictions",
  standings: "Standings",
};

export function LeagueTabs({
  slug,
  active,
  tabs,
}: {
  slug: string;
  active: LeagueTab;
  tabs: LeagueTab[];
}) {
  return (
    <nav
      aria-label="League sections"
      className="flex flex-wrap gap-1 border-b border-[var(--color-line)]"
    >
      {tabs.map((tab) => {
        const isActive = tab === active;
        return (
          <Link
            key={tab}
            href={
              tab === "predictions"
                ? `/leagues/${slug}`
                : `/leagues/${slug}?tab=${tab}`
            }
            aria-current={isActive ? "page" : undefined}
            className="relative px-3 py-2.5 text-[13.5px] font-medium transition-colors"
            style={{
              color: isActive ? "var(--color-text)" : "var(--color-text-dim)",
            }}
          >
            {LABELS[tab]}
            {isActive && (
              <span
                aria-hidden
                className="absolute inset-x-0 -bottom-px h-[2px] rounded-full"
                style={{ background: "var(--color-gold)" }}
              />
            )}
          </Link>
        );
      })}
    </nav>
  );
}
