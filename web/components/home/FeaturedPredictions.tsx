/**
 * "Featured predictions": the day's strongest picks as four cards, one per sport and
 * a second football one, each linking to its own analysis.
 *
 * Every figure on a card is the engine's own number for that match: the tip's label,
 * its probability, its price where one exists. A price the engine had to derive (no
 * bookmaker quoted it) is shown with a "≈", and basketball and tennis show no price at
 * all because there is no odds feed for them: the row is omitted, never zero-filled.
 * Kick-off times are UTC and say so.
 */

import Link from "next/link";
import { CountryMark } from "@/components/board/CountryMark";
import { TeamCrest } from "@/components/board/TeamCrest";
import { ArrowRight, Trophy } from "@/components/home/icons";
import { SportMark } from "@/components/sport/SportMark";
import type { FeaturedCard } from "@/lib/featured";

const SPORT_STYLE: Record<
  FeaturedCard["sport"],
  { label: string; color: string; bg: string }
> = {
  football: { label: "Football", color: "#35d08a", bg: "rgba(53,208,138,0.14)" },
  basketball: {
    label: "Basketball",
    color: "#ff9a3c",
    bg: "rgba(255,154,60,0.14)",
  },
  tennis: { label: "Tennis", color: "#c8e41c", bg: "rgba(200,228,28,0.14)" },
};

function when(iso: string): string {
  const at = new Date(iso);
  const date = at.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
  const time = at.toLocaleTimeString("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "UTC",
  });
  return `${date} · ${time} UTC`;
}

function Card({ card }: { card: FeaturedCard }) {
  const style = SPORT_STYLE[card.sport];
  return (
    <li>
      <article className="flex h-full flex-col rounded-[14px] border border-[var(--color-line-strong)] bg-[linear-gradient(180deg,var(--color-surface-raised),var(--color-surface))] p-4 transition-colors hover:border-[var(--color-gold)]/60">
        <header className="flex items-center justify-between gap-2">
          <span
            className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[11px] font-extrabold tracking-[0.1em] uppercase"
            style={{ color: style.color, background: style.bg }}
          >
            <SportMark sport={card.sport} size={13} />
            {style.label}
          </span>
        </header>

        <p className="mt-3 flex items-center gap-2 text-[12.5px] text-[var(--color-text-dim)]">
          <CountryMark code={card.countryCode} />
          <span className="truncate">{card.competition}</span>
        </p>

        <div className="mt-4 grid grid-cols-[1fr_auto_1fr] items-start gap-2">
          <div className="flex min-w-0 flex-col items-center gap-2 text-center">
            <TeamCrest badge={card.homeBadge} name={card.home} size={48} />
            <span className="line-clamp-2 text-[13.5px] leading-tight font-bold">
              {card.home}
            </span>
          </div>
          <span className="pt-4 text-[12px] font-extrabold text-[var(--color-gold-bright)]">
            VS
          </span>
          <div className="flex min-w-0 flex-col items-center gap-2 text-center">
            <TeamCrest badge={card.awayBadge} name={card.away} size={48} />
            <span className="line-clamp-2 text-[13.5px] leading-tight font-bold">
              {card.away}
            </span>
          </div>
        </div>

        <p className="mt-4 text-center text-[12px] text-[var(--color-text-dim)] tabular-nums">
          {when(card.kickoff)}
        </p>

        <p className="mt-3 rounded-md bg-[var(--color-gold)] px-2 py-2 text-center text-[12.5px] leading-tight font-extrabold tracking-[0.02em] text-[var(--color-ink-on-accent)] uppercase">
          Tip: {card.tip}
        </p>

        <div className="mt-3 space-y-1 text-center text-[12.5px] font-semibold tabular-nums">
          {card.odds !== null && (
            <p className="text-[var(--color-text-dim)]">
              Odds:{" "}
              <span className="text-[var(--color-text)]">
                {card.oddsEstimated ? "≈" : ""}
                {card.odds.toFixed(2)}
              </span>
            </p>
          )}
          <p className="text-[var(--color-won)]">
            <span className="text-[var(--color-text-dim)]">
              Win probability:{" "}
            </span>
            {Math.round(card.probability)}%
          </p>
        </div>

        <div className="mt-auto pt-4">
          <Link
            href={card.href}
            prefetch={false}
            className="nt-cta nt-cta--ghost w-full !px-3 !py-2.5 text-[12.5px]"
          >
            View analysis
            <ArrowRight size={16} />
          </Link>
        </div>
      </article>
    </li>
  );
}

export function FeaturedPredictions({ cards }: { cards: FeaturedCard[] }) {
  if (cards.length === 0) return null;
  return (
    <section aria-labelledby="featured" className="scroll-mt-20">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2
            id="featured"
            className="flex items-center gap-3 text-[clamp(1.5rem,3.2vw,2.1rem)] leading-none font-black tracking-[-0.02em]"
          >
            <span className="text-[var(--color-gold)]">
              <Trophy size={30} />
            </span>
            <span>
              Featured{" "}
              <span className="text-[var(--color-gold)]">Predictions</span>
            </span>
          </h2>
          <p className="mt-2 text-[14px] text-[var(--color-text-dim)]">
            The engine&rsquo;s most likely picks still to play, backed by the
            numbers and graded in public.
          </p>
        </div>
        <a
          href="#today"
          className="inline-flex items-center gap-2 text-[13px] font-semibold text-[var(--color-gold-bright)] hover:underline"
        >
          View all predictions
          <ArrowRight size={16} />
        </a>
      </div>

      <ul className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {cards.map((card) => (
          <Card key={`${card.sport}-${card.href}`} card={card} />
        ))}
      </ul>
    </section>
  );
}
