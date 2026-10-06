"use client";

/**
 * Every competition, by country, with a search box.
 *
 * The filter is client-side because the whole catalogue is forty rows: there
 * is nothing to fetch, and typing should answer instantly. It matches the
 * country, the full name and the short name, so "premier" finds England's,
 * Russia's and anyone else's.
 */

import Link from "next/link";
import { useMemo, useState } from "react";
import { CountryMark } from "@/components/board/CountryMark";
import type { LeagueCountry } from "@/lib/discover";

export function LeagueDirectory({ countries }: { countries: LeagueCountry[] }) {
  const [query, setQuery] = useState("");
  const needle = query.trim().toLowerCase();

  const visible = useMemo(() => {
    if (!needle) return countries;
    return countries
      .map((country) => {
        // A match on the country keeps all its competitions; otherwise only
        // the competitions that match themselves.
        if (country.country.toLowerCase().includes(needle)) return country;
        const competitions = country.competitions.filter(
          (entry) =>
            entry.competition.toLowerCase().includes(needle) ||
            entry.short_name.toLowerCase().includes(needle),
        );
        return { ...country, competitions };
      })
      .filter((country) => country.competitions.length > 0);
  }, [countries, needle]);

  return (
    <div>
      <label className="block">
        <span className="sr-only">Search countries and competitions</span>
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search country or competition"
          className="w-full rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] px-4 py-3 text-[14px] outline-none placeholder:text-[var(--color-text-faint)] focus:border-[var(--color-gold-dim)] sm:max-w-md"
        />
      </label>

      {visible.length === 0 ? (
        <p className="mt-6 text-[14px] text-[var(--color-text-dim)]">
          No competition matches &ldquo;{query.trim()}&rdquo;. The engine models{" "}
          {countries.reduce((n, c) => n + c.competitions.length, 0)}{" "}
          competitions, and this is the whole list.
        </p>
      ) : (
        <div className="mt-6 grid gap-4 sm:grid-cols-2">
          {visible.map((country) => (
            <section
              key={country.country}
              className="rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] p-5"
            >
              <div className="flex items-center justify-between gap-3">
                <h2 className="flex items-center gap-2.5 text-[15px] font-semibold">
                  <CountryMark code={country.country_code} />
                  {country.country}
                </h2>
                <span className="text-[12px] text-[var(--color-text-faint)] tabular-nums">
                  {country.completed.toLocaleString()} matches
                </span>
              </div>
              <ul className="mt-3 flex flex-col gap-1.5">
                {country.competitions.map((entry) => (
                  <li key={entry.competition}>
                    <Link
                      href={`/leagues/${entry.slug}`}
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
                          <span style={{ color: "var(--color-gold-bright)" }}>
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
      )}
    </div>
  );
}
