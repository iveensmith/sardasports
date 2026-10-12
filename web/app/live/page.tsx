/**
 * Live: the football matches being played right now.
 *
 * Read from the engine's live feed (`/board/live`), which on the paid data plan is polled
 * every couple of minutes, and re-read here every 20 seconds while the tab is open. A
 * match leaves this page the moment it is finished and settles on the boards with its
 * graded tip. Nothing is shown for a match the feed has not reported: an empty page says
 * so, and links to the day's fixtures.
 */

import Link from "next/link";
import { AutoRefresh } from "@/components/live/AutoRefresh";
import { LiveMatch } from "@/components/live/LiveMatch";
import { getLiveBoard } from "@/lib/api";
import type { BoardRow } from "@/lib/board";
import { pageMetadata } from "@/lib/seo";

export const revalidate = 10;

export const metadata = pageMetadata({
  title: "Live football scores and predictions",
  description:
    "Football matches being played right now, with the minute, the score so far and the engine's pre-match tip for each.",
  path: "/live",
});

export default async function LivePage() {
  const board = await getLiveBoard();
  const rows = board?.rows ?? [];

  const groups = new Map<string, { name: string; rows: BoardRow[] }>();
  for (const row of rows) {
    const key = row.competition.name;
    if (!groups.has(key)) {
      groups.set(key, {
        name: row.competition.short_name || row.competition.name,
        rows: [],
      });
    }
    groups.get(key)!.rows.push(row);
  }

  return (
    <div className="mx-auto w-full max-w-[1200px] px-4 py-10 sm:px-6 lg:px-10">
      <AutoRefresh seconds={20} />
      <header className="max-w-[72ch]">
        <p className="flex items-center gap-2 text-[12px] font-extrabold tracking-[0.14em] text-[var(--color-lost)] uppercase">
          <span
            aria-hidden
            className="h-2 w-2 animate-pulse rounded-full bg-[var(--color-lost)] motion-reduce:animate-none"
          />
          Live now
        </p>
        <h1 className="mt-2 text-[clamp(1.9rem,4.5vw,2.6rem)] leading-tight font-black tracking-[-0.02em]">
          Live football scores
        </h1>
        <p className="mt-3 text-[15px] leading-relaxed text-[var(--color-text-dim)]">
          {rows.length > 0
            ? `${rows.length} ${rows.length === 1 ? "match is" : "matches are"} in play. Scores update about every two minutes and this page refreshes itself; each match shows the tip the engine stored before kick-off.`
            : "No football match is in play right now. This page fills in by itself when one kicks off."}
        </p>
      </header>

      {rows.length === 0 ? (
        <div className="mt-8 rounded-[14px] border border-dashed border-[var(--color-line-strong)] bg-[var(--color-surface)] p-6">
          <p className="text-[15px] font-semibold">Nothing in play</p>
          <p className="mt-2 text-[14px] text-[var(--color-text-dim)]">
            See what kicks off next on{" "}
            <Link
              href="/matches"
              className="text-[var(--color-gold-bright)] underline underline-offset-4"
            >
              today&rsquo;s board
            </Link>
            .
          </p>
        </div>
      ) : (
        <div className="mt-8 space-y-8">
          {[...groups.values()].map((group) => (
            <section key={group.name} aria-label={group.name}>
              <h2 className="text-[13px] font-extrabold tracking-[0.12em] text-[var(--color-text-faint)] uppercase">
                {group.name}
              </h2>
              <div className="mt-3 grid gap-3 md:grid-cols-2">
                {group.rows.map((row) => (
                  <LiveMatch key={row.match_id} row={row} />
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
