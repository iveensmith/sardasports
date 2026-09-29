/**
 * Every competition we model, grouped by country.
 *
 * The match counts are the point of the page rather than decoration. A
 * competition with five thousand completed matches behind it produces very
 * different predictions from one with fifty, and a catalogue that listed
 * them identically would imply a uniformity that is not there. International
 * competitions in particular are thin — that is why their Elo needed its own
 * treatment — and this is where a reader can see it.
 */

import Link from "next/link";
import { EngineError, getLeagues } from "@/lib/api";
import type { Leagues } from "@/lib/discover";

export const revalidate = 3600;

export const metadata = {
  title: "Leagues — UniquePredict",
  description:
    "Every competition the engine models, with how much match history sits behind each.",
};

export default async function LeaguesPage() {
  let leagues: Leagues | null = null;
  let error: string | null = null;
  try {
    leagues = await getLeagues();
  } catch (e) {
    error =
      e instanceof EngineError || e instanceof Error
        ? e.message
        : "The engine could not be reached.";
  }

  if (error || !leagues) {
    return (
      <div className="mx-auto max-w-6xl px-4 py-12">
        <div className="rounded-[var(--radius-lg)] border border-[var(--color-line-strong)] bg-[var(--color-surface)] p-6">
          <p className="text-[15px] font-medium">The engine is unreachable</p>
          <p className="mt-2 text-[14px] text-[var(--color-text-dim)]">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl px-4 py-12">
      <header className="mb-8 max-w-[72ch]">
        <p className="text-[11px] tracking-[0.14em] text-[var(--color-gold)] uppercase">
          {leagues.competition_count} competitions · {leagues.country_count}{" "}
          countries
        </p>
        <h1 className="mt-2.5 text-[clamp(1.9rem,4.5vw,2.6rem)] leading-tight font-bold tracking-[-0.02em]">
          Leagues
        </h1>
        <p className="mt-3 text-[15px] leading-relaxed text-[var(--color-text-dim)]">
          Everything the engine has a trained model for. The match count beside
          each is how much completed history it was built from, and it varies
          by two orders of magnitude &mdash; which is the single best predictor
          of how much to trust a call in it.
        </p>
      </header>

      <div className="grid gap-4 sm:grid-cols-2">
        {leagues.countries.map((country) => (
          <section
            key={country.country}
            className="rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] p-5"
          >
            <div className="flex items-baseline justify-between gap-3">
              <h2 className="text-[15px] font-semibold">{country.country}</h2>
              <span className="text-[12px] text-[var(--color-text-faint)] tabular-nums">
                {country.completed.toLocaleString()} matches
              </span>
            </div>
            <ul className="mt-3 flex flex-col gap-1.5">
              {country.competitions.map((entry) => (
                <li key={entry.competition}>
                  <Link
                    href={`/matches?competition=${encodeURIComponent(entry.competition)}`}
                    className="flex items-baseline justify-between gap-3 rounded-[var(--radius-md)] px-2 py-1.5 text-[13.5px] transition-colors hover:bg-[var(--color-surface-raised)]"
                  >
                    <span className="truncate text-[var(--color-text-dim)]">
                      {entry.short_name}
                      {entry.tier === 2 && (
                        <span className="ml-1.5 text-[11px] text-[var(--color-text-faint)]">
                          2nd tier
                        </span>
                      )}
                    </span>
                    <span className="shrink-0 text-[12px] text-[var(--color-text-faint)] tabular-nums">
                      {entry.completed.toLocaleString()}
                      {entry.upcoming > 0 && (
                        <span style={{ color: "var(--color-gold)" }}>
                          {" "}
                          · {entry.upcoming} up
                        </span>
                      )}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </div>
  );
}
