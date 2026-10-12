/**
 * "Latest results" and "Why you can trust it", side by side.
 *
 * The left is the newest graded best tips from the engine's stored predictions, each
 * with the pick it made and whether it came in. Wins and losses both appear; the list
 * is not filtered to the flattering ones, and a refunded pick (a draw-no-bet that
 * drew) is marked void, not as a win. The right replaces the testimonials a betting
 * site would show: this site has no member reviews and does not invent any, so the
 * space says why the record can be believed, using only things that are true of how
 * the picks are stored.
 */

import Link from "next/link";
import { ArrowRight, Check, Cross, Lock, Medal, Trophy } from "@/components/home/icons";
import { SportMark } from "@/components/sport/SportMark";
import type { BoardRow } from "@/lib/board";

function day(iso: string): string {
  return new Date(iso).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}

function Verdict({ outcome }: { outcome: "won" | "lost" | "void" | null }) {
  if (outcome === "won") {
    return (
      <span
        className="inline-flex h-6 w-6 items-center justify-center rounded-full text-[var(--color-ink-on-accent)]"
        style={{ background: "var(--color-won)" }}
        title="Won"
      >
        <Check size={14} />
        <span className="sr-only">Won</span>
      </span>
    );
  }
  if (outcome === "lost") {
    return (
      <span
        className="inline-flex h-6 w-6 items-center justify-center rounded-full text-[var(--color-ink-on-accent)]"
        style={{ background: "var(--color-lost)" }}
        title="Lost"
      >
        <Cross size={14} />
        <span className="sr-only">Lost</span>
      </span>
    );
  }
  return (
    <span className="text-[12px] text-[var(--color-text-faint)]">
      {outcome === "void" ? "Void" : "·"}
    </span>
  );
}

const REASONS = [
  {
    icon: Lock,
    title: "Saved before kick-off",
    text: "A pick is stored before the match starts and is not changed after the result is known.",
  },
  {
    icon: Medal,
    title: "Wins and losses both stay",
    text: "Every settled pick stays on the record, including the ones that missed.",
  },
  {
    icon: Trophy,
    title: "Two records, kept apart",
    text: "Live picks and picks rebuilt from history are counted separately, never blended.",
  },
];

export function LatestResults({
  rows,
  minProbability = null,
}: {
  rows: BoardRow[];
  /** Set when the list is only the tips the engine rated this highly, which it says. */
  minProbability?: number | null;
}) {
  const shown = rows.filter((row) => row.score && row.best_tip).slice(0, 5);
  return (
    <section aria-labelledby="latest-results">
      <div className="grid gap-8 lg:grid-cols-[1.25fr_1fr]">
        {shown.length > 0 && (
          <div>
            <div className="flex items-end justify-between gap-3">
              <h2
                id="latest-results"
                className="flex items-center gap-3 text-[clamp(1.35rem,2.8vw,1.8rem)] leading-none font-black tracking-[-0.02em]"
              >
                <span className="text-[var(--color-gold)]">
                  <Trophy size={26} />
                </span>
                <span>
                  Latest <span className="text-[var(--color-gold)]">results</span>
                </span>
              </h2>
              <Link
                href="/progress"
                className="inline-flex items-center gap-2 text-[13px] font-semibold text-[var(--color-gold-bright)] hover:underline"
              >
                View all results
                <ArrowRight size={16} />
              </Link>
            </div>

            <p className="mt-2 text-[13px] text-[var(--color-text-dim)]">
              {minProbability
                ? `The newest graded tips the engine rated ${minProbability}% or more before kick-off, wins and losses alike.`
                : "The newest graded best tips, wins and losses alike."}
            </p>

            <ul className="mt-4 overflow-hidden rounded-[14px] border border-[var(--color-line-strong)] bg-[var(--color-surface)]">
              {shown.map((row, index) => (
                <li
                  key={row.match_id}
                  className={index > 0 ? "border-t border-[var(--color-line)]" : ""}
                >
                  <Link
                    href={`/match/${row.slug}`}
                    prefetch={false}
                    className="grid grid-cols-[auto_1fr_auto] items-center gap-x-3 gap-y-1 px-3.5 py-3 transition-colors hover:bg-[var(--color-surface-raised)] sm:grid-cols-[88px_1fr_auto_auto_104px]"
                  >
                    <span className="flex items-center gap-2 text-[12.5px] text-[var(--color-text-dim)]">
                      <SportMark sport="football" size={16} />
                      <span className="hidden sm:inline">Football</span>
                    </span>
                    <span className="min-w-0 truncate text-[13.5px] font-semibold">
                      {row.home_team}{" "}
                      <span className="font-normal text-[var(--color-text-faint)]">
                        vs
                      </span>{" "}
                      {row.away_team}
                    </span>
                    <span className="text-[13.5px] font-bold tabular-nums sm:text-right">
                      {row.score!.home} - {row.score!.away}
                    </span>
                    <span className="hidden items-center gap-2 text-[12.5px] text-[var(--color-text-dim)] sm:flex">
                      <span className="max-w-[9ch] truncate">
                        {row.best_tip!.short_label}
                      </span>
                      <Verdict outcome={row.best_tip!.outcome} />
                    </span>
                    <span className="hidden text-right text-[12.5px] text-[var(--color-text-dim)] tabular-nums sm:block">
                      {day(row.match_date)}
                    </span>
                    <span className="col-span-3 flex items-center justify-between text-[12px] text-[var(--color-text-dim)] sm:hidden">
                      <span>
                        {row.best_tip!.label} · {day(row.match_date)}
                      </span>
                      <Verdict outcome={row.best_tip!.outcome} />
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className={shown.length === 0 ? "lg:col-span-2" : ""}>
          <h2 className="flex items-center gap-3 text-[clamp(1.35rem,2.8vw,1.8rem)] leading-none font-black tracking-[-0.02em]">
            <span className="text-[var(--color-gold)]">
              <Medal size={26} />
            </span>
            <span>
              Why you can <span className="text-[var(--color-gold)]">trust it</span>
            </span>
          </h2>
          <ul className="mt-5 space-y-3">
            {REASONS.map((reason) => (
              <li
                key={reason.title}
                className="flex gap-3.5 rounded-[14px] border border-[var(--color-line-strong)] bg-[var(--color-surface)] p-4"
              >
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-[var(--color-gold)]/50 text-[var(--color-gold-bright)]">
                  <reason.icon size={20} />
                </span>
                <span>
                  <span className="block text-[14.5px] font-bold">
                    {reason.title}
                  </span>
                  <span className="mt-0.5 block text-[13px] leading-relaxed text-[var(--color-text-dim)]">
                    {reason.text}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}
