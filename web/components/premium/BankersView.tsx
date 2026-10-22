"use client";

/**
 * The bankers page's list, record and slip.
 *
 * The page is built from what the engine gives anyone: the day's bankers whose predictions are open
 * (free, or already kicked off), and how many more there are behind the lock. A premium member's
 * browser asks again with the member's token and gets the whole list and the slip; everyone else
 * keeps what they were sent.
 */

import Link from "next/link";
import { useEffect, useState } from "react";
import { BoardTable } from "@/components/board/BoardTable";
import { Lock } from "@/components/home/icons";
import { usePremium } from "@/components/premium/PremiumProvider";
import { SlipOfTheDay } from "@/components/slip/SlipOfTheDay";
import { api } from "@/lib/clientApi";
import type { Bankers, Slip } from "@/lib/discover";
import { rate } from "@/lib/progress";

/** The same query the page used to build the slip, so a member's slip is the one the page described. */
function slipQuery(date: string, target: number): string {
  const query = new URLSearchParams({
    target_odds: String(target),
    min_legs: "2",
    max_legs: "4",
  });
  if (date) query.set("on_date", date);
  return query.toString();
}

export function BankersView({
  initial,
  initialSlip,
  date,
  slipTarget,
}: {
  initial: Bankers;
  initialSlip: Slip | null;
  date: string;
  slipTarget: number;
}) {
  const { premium } = usePremium();
  const [bankers, setBankers] = useState<Bankers>(initial);
  const [slip, setSlip] = useState<Slip | null>(initialSlip);

  useEffect(() => {
    if (premium !== true) return;
    let live = true;
    api<Bankers>(`/api/engine/bankers${date ? `?on_date=${date}` : ""}`).then(
      (result) => {
        if (live && result.ok && result.data) setBankers(result.data);
      },
    );
    if (initial.upcoming > 0) {
      api<Slip>(`/api/engine/slip?${slipQuery(date, slipTarget)}`).then(
        (result) => {
          if (live && result.ok && result.data) setSlip(result.data);
        },
      );
    }
    return () => {
      live = false;
    };
  }, [premium, date, slipTarget, initial.upcoming]);

  const settled = bankers.record.settled > 0;
  const hidden = bankers.locked_count ?? 0;

  return (
    <>
      <p className="mb-6 max-w-[72ch] text-[15px] leading-relaxed text-[var(--color-text-dim)]">
        {bankers.count === 1
          ? "The one open pick"
          : `The ${bankers.count} ${hidden > 0 && premium !== true ? "open " : ""}picks`}{" "}
        from this card&rsquo;s {bankers.considered} fixtures that the engine makes
        at least {bankers.min_probability.toFixed(0)}% likely, likeliest first.
        These are the safest picks on the card, which is not the same as the most
        valuable: a short price on a near-certainty is usually priced about
        right.
      </p>

      {settled && (
        <div
          className="mb-6 rounded-[var(--radius-lg)] border p-5"
          style={{ borderColor: "var(--color-line-strong)" }}
        >
          <p className="text-[10.5px] tracking-wider text-[var(--color-text-faint)] uppercase">
            How this batch went
          </p>
          <p className="mt-1.5 flex flex-wrap items-baseline gap-x-3">
            <span
              className="text-[28px] leading-none font-bold tabular-nums"
              style={{
                color:
                  (bankers.record.win_rate ?? 0) >= 50
                    ? "var(--color-won)"
                    : "var(--color-lost)",
              }}
            >
              {rate(bankers.record)}
            </span>
            <span className="text-[13.5px] text-[var(--color-text-dim)]">
              {bankers.record.won} won, {bankers.record.lost} lost
              {bankers.record.void > 0 && `, ${bankers.record.void} void`}
            </span>
          </p>
        </div>
      )}

      {bankers.count === 0 ? (
        <div className="rounded-[var(--radius-lg)] border border-dashed border-[var(--color-line-strong)] bg-[var(--color-surface)] p-8">
          <p className="text-[15px] font-medium">
            {hidden > 0
              ? "The banker picks on this card are for premium members"
              : `Nothing on this card clears ${bankers.min_probability.toFixed(0)}%`}
          </p>
          <p className="mt-2 max-w-[54ch] text-[14px] leading-relaxed text-[var(--color-text-dim)]">
            {hidden > 0
              ? "15 predictions are free every day, and none of the picks the engine rates this highly is among today’s. They open for everyone once the matches kick off."
              : "That is a result, not a gap. Some days have no near-certainties on them, and padding the page out with 70% calls would misname them."}
          </p>
        </div>
      ) : (
        <BoardTable rows={bankers.rows} />
      )}

      {hidden > 0 && premium !== true && (
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-[var(--radius-lg)] border border-[var(--color-gold)]/40 bg-[var(--color-surface)] px-5 py-4">
          <p className="flex items-center gap-2.5 text-[13.5px] text-[var(--color-text-dim)]">
            <span className="text-[var(--color-gold-bright)]">
              <Lock size={17} />
            </span>
            {hidden === 1
              ? "1 more banker pick is locked"
              : `${hidden} more banker picks are locked`}
            : they are for premium members until the matches kick off.
          </p>
          <Link
            href="/premium"
            className="rounded-[var(--radius-md)] bg-[var(--color-gold)] px-4 py-2 text-[13px] font-extrabold text-[var(--color-ink-on-accent)] transition-colors hover:bg-[var(--color-gold-bright)]"
          >
            Unlock all predictions
          </Link>
        </div>
      )}

      {slip && <SlipOfTheDay slip={slip} />}
    </>
  );
}
