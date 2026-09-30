/**
 * The match page's section switcher.
 *
 * A `?tab=` link rather than client-side state: every tab's content is a
 * server-rendered fetch of its own (Form/H2H/Recent Matches each call the
 * engine independently), so a plain link that changes what the page fetches
 * is simpler than shipping all five tabs' data on every load and hiding
 * four of them with CSS.
 */

import Link from "next/link";

export type MatchTab = "tips" | "stats" | "form" | "h2h" | "recent";

const LABELS: Record<MatchTab, string> = {
  tips: "Match Tips",
  stats: "Predicted vs Actual",
  form: "Form",
  h2h: "H2H",
  recent: "Recent Matches",
};

export function MatchTabs({
  matchId,
  active,
  tabs,
}: {
  matchId: number;
  active: MatchTab;
  tabs: MatchTab[];
}) {
  return (
    <nav
      aria-label="Match sections"
      className="flex flex-wrap gap-1 border-b border-[var(--color-line)]"
    >
      {tabs.map((tab) => {
        const isActive = tab === active;
        return (
          <Link
            key={tab}
            href={
              tab === "tips"
                ? `/match/${matchId}`
                : `/match/${matchId}?tab=${tab}`
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
