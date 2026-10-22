/**
 * The card that stands where a locked prediction would be.
 *
 * It says what is behind the lock, what is free, and where to go: nothing else. The predictions
 * themselves are not in the page (the engine withholds them), so there is nothing here to peek at.
 */

import Link from "next/link";
import { ArrowRight, Check, Lock } from "@/components/home/icons";

export function LockCard({
  title = "This prediction is for premium members",
  note,
}: {
  title?: string;
  /** One line under the title, when the page has something more specific to say. */
  note?: string;
}) {
  return (
    <section
      aria-labelledby="locked-prediction"
      className="rounded-[var(--radius-lg)] border border-[var(--color-gold)]/40 bg-[var(--color-surface)] p-6 sm:p-8"
    >
      <div className="flex items-start gap-4">
        <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-[var(--color-gold)]/50 text-[var(--color-gold-bright)]">
          <Lock size={20} />
        </span>
        <div className="min-w-0">
          <h2 id="locked-prediction" className="text-[17px] font-bold">
            {title}
          </h2>
          <p className="mt-1.5 max-w-[60ch] text-[14px] leading-relaxed text-[var(--color-text-dim)]">
            {note ??
              "15 predictions are free every day. This one is not among them, so it opens for premium members, and for everyone once the match kicks off."}
          </p>
        </div>
      </div>

      <ul className="mt-5 grid gap-2 text-[13.5px] sm:grid-cols-2">
        {[
          "The pick, with its confidence",
          "Win, draw and loss probabilities",
          "Goals and both-teams-to-score markets",
          "The estimator breakdown and expected goals",
        ].map((item) => (
          <li key={item} className="flex items-center gap-2 text-[var(--color-text-dim)]">
            <span className="text-[var(--color-won)]">
              <Check size={15} />
            </span>
            {item}
          </li>
        ))}
      </ul>

      <div className="mt-6 flex flex-wrap items-center gap-3">
        <Link
          href="/premium"
          className="inline-flex items-center gap-2 rounded-[var(--radius-md)] bg-[var(--color-gold)] px-5 py-2.5 text-[14px] font-extrabold text-[var(--color-ink-on-accent)] transition-colors hover:bg-[var(--color-gold-bright)]"
        >
          Unlock all predictions
          <ArrowRight size={16} />
        </Link>
        <Link
          href="/matches"
          className="text-[13.5px] font-semibold text-[var(--color-gold-bright)] underline underline-offset-4"
        >
          See today&rsquo;s free predictions
        </Link>
      </div>
    </section>
  );
}
