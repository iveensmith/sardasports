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
import { LeagueDirectory } from "@/components/league/LeagueDirectory";
import { EngineError, getLeagues } from "@/lib/api";
import type { Leagues } from "@/lib/discover";
import { pageMetadata } from "@/lib/seo";

export const revalidate = 3600;

export const metadata = pageMetadata({
  title: "Football Leagues & Competitions Covered",
  description:
    "Every football league and competition our engine models, from top flights to lower divisions, with how much match history each is built from.",
  path: "/leagues",
});

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
      <div className="mx-auto w-full max-w-[1200px] px-4 sm:px-6 lg:px-10 py-12">
        <div className="rounded-[var(--radius-lg)] border border-[var(--color-line-strong)] bg-[var(--color-surface)] p-6">
          <p className="text-[15px] font-medium">The engine is unreachable</p>
          <p className="mt-2 text-[14px] text-[var(--color-text-dim)]">
            {error}
          </p>
        </div>
      </div>
    );
  }

  const deepest = leagues.countries
    .flatMap((country) =>
      country.competitions.map((entry) => ({
        ...entry,
        country: country.country,
      })),
    )
    .sort((a, b) => b.completed - a.completed)
    .slice(0, 6);

  return (
    <div className="mx-auto w-full max-w-[1200px] px-4 sm:px-6 lg:px-10 py-12">
      <header className="mb-8 max-w-[72ch]">
        <p className="text-[11px] tracking-[0.14em] text-[var(--color-gold-bright)] uppercase">
          {leagues.competition_count} competitions · {leagues.country_count}{" "}
          countries
        </p>
        <h1 className="mt-2.5 text-[clamp(1.9rem,4.5vw,2.6rem)] leading-tight font-bold tracking-[-0.02em]">
          Football leagues and competitions
        </h1>
        <p className="mt-3 text-[15px] leading-relaxed text-[var(--color-text-dim)]">
          Every competition the engine has a trained model for. The match count
          beside each is how much completed history the model was built from. It
          varies by two orders of magnitude, and it is the best single guide to
          how much to trust a pick in that competition.
        </p>
      </header>

      {/* Ranked by match history, not "popular": popularity is not something
          this site measures, and history is the thing that varies here. */}
      <section className="mb-8">
        <h2 className="text-[15px] font-semibold">Most match history</h2>
        <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          {deepest.map((entry) => (
            <Link
              key={entry.competition}
              href={`/leagues/${entry.slug}`}
              className="rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] p-4 transition-colors hover:border-[var(--color-line-strong)] hover:bg-[var(--color-surface-raised)]"
            >
              <p className="truncate text-[13.5px] font-semibold">
                {entry.short_name}
              </p>
              <p className="mt-1 truncate text-[12px] text-[var(--color-text-faint)]">
                {entry.country}
              </p>
              <p className="mt-2 text-[12px] text-[var(--color-text-dim)] tabular-nums">
                {entry.completed.toLocaleString()} matches
              </p>
            </Link>
          ))}
        </div>
      </section>

      <LeagueDirectory countries={leagues.countries} />
    </div>
  );
}
