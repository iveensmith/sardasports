/**
 * "Live now": up to four matches in play, on the home page, only while there are any.
 *
 * Absent entirely when nothing is being played: an empty "live" box on a front page is
 * worse than none. Each card is the same one the Live page uses.
 */

import Link from "next/link";
import { ArrowRight } from "@/components/home/icons";
import { LiveMatch } from "@/components/live/LiveMatch";
import type { BoardRow } from "@/lib/board";

export function LiveNow({ rows }: { rows: BoardRow[] }) {
  if (rows.length === 0) return null;
  return (
    <section aria-labelledby="live-now">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h2
          id="live-now"
          className="flex items-center gap-3 text-[clamp(1.35rem,2.8vw,1.8rem)] leading-none font-black tracking-[-0.02em]"
        >
          <span
            aria-hidden
            className="h-3 w-3 animate-pulse rounded-full bg-[var(--color-lost)] motion-reduce:animate-none"
          />
          <span>
            Live <span className="text-[var(--color-gold)]">now</span>
          </span>
        </h2>
        <Link
          href="/live"
          className="inline-flex items-center gap-2 text-[13px] font-semibold text-[var(--color-gold-bright)] hover:underline"
        >
          All live matches ({rows.length})
          <ArrowRight size={16} />
        </Link>
      </div>
      <div className="mt-5 grid gap-3 md:grid-cols-2">
        {rows.slice(0, 4).map((row) => (
          <LiveMatch key={row.match_id} row={row} />
        ))}
      </div>
    </section>
  );
}
