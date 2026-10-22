"use client";

/**
 * The line that says some predictions on the page are locked, and where to unlock them.
 *
 * A premium member never sees it. It is its own component so a page showing several tables (one
 * per competition) can say it once, above them, instead of once per table.
 */

import Link from "next/link";
import { Lock } from "@/components/home/icons";
import { usePremium } from "@/components/premium/PremiumProvider";

export function LockedBanner({
  count,
  bordered = false,
}: {
  /** How many predictions are locked on the page (or in the table). */
  count: number;
  /** A rounded card of its own, for use above a table instead of inside one. */
  bordered?: boolean;
}) {
  const { premium } = usePremium();
  if (count <= 0 || premium === true) return null;
  return (
    <div
      className={`flex flex-wrap items-center justify-between gap-3 bg-[var(--color-surface-raised)] px-4 py-3 sm:px-5 ${
        bordered
          ? "rounded-[var(--radius-lg)] border border-[var(--color-gold)]/40"
          : "border-b border-[var(--color-line)]"
      }`}
    >
      <p className="flex items-center gap-2.5 text-[13px] text-[var(--color-text-dim)]">
        <span className="text-[var(--color-gold-bright)]">
          <Lock size={16} />
        </span>
        <span>
          {count === 1
            ? "1 prediction here is locked"
            : `${count} predictions here are locked`}
          : 15 are free every day, the rest are for premium members until kick-off.
        </span>
      </p>
      <Link
        href="/premium"
        className="rounded-[var(--radius-md)] bg-[var(--color-gold)] px-3.5 py-1.5 text-[12.5px] font-extrabold text-[var(--color-ink-on-accent)] transition-colors hover:bg-[var(--color-gold-bright)]"
      >
        Unlock all predictions
      </Link>
    </div>
  );
}
