/**
 * Countries down the side, with a fixture count each.
 *
 * Counts are for the whole day and do not change when a country is selected.
 * A sidebar that renumbered itself on every click would make it impossible to
 * see what else was on.
 *
 * International competitions group under their confederation — Europe,
 * Africa, South America, World — because that is where a reader scanning for
 * the Nations League looks, even though it is not a country. They get a
 * globe mark instead of a flag: there is no flag for "World", and reaching
 * for a nearby one would be a factual claim about geography this row isn't
 * making.
 */

import Link from "next/link";
import type { CountryCount } from "@/lib/board";
import { CountryMark, GlobeMark } from "@/components/board/CountryMark";

function activeStyle(isActive: boolean) {
  if (!isActive) return undefined;
  return {
    background: "color-mix(in srgb, var(--color-gold) 16%, transparent)",
    color: "var(--color-gold-bright)",
  };
}

export function CountrySidebar({
  countries,
  active,
  date,
  basePath = "/matches",
}: {
  countries: CountryCount[];
  active: string | null;
  date: string;
  basePath?: string;
}) {
  const total = countries.reduce((sum, c) => sum + c.count, 0);

  return (
    <nav
      aria-label="Filter by country"
      className="rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] p-3"
    >
      <p className="px-1.5 pb-2 text-[10.5px] font-semibold tracking-wider text-[var(--color-text-faint)] uppercase">
        Countries
      </p>

      <Link
        href={`${basePath}?date=${date}`}
        aria-current={active === null ? "true" : undefined}
        className="flex items-center justify-between rounded-[var(--radius-md)] px-2.5 py-2 text-[13.5px] font-semibold transition-colors"
        style={{
          ...activeStyle(active === null),
          color:
            active === null ? "var(--color-gold-bright)" : "var(--color-text)",
        }}
      >
        <span className="flex min-w-0 items-center gap-2">
          <span
            className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full"
            style={{
              background:
                active === null
                  ? "color-mix(in srgb, var(--color-gold) 28%, transparent)"
                  : "var(--color-surface-raised)",
            }}
          >
            <GlobeMark />
          </span>
          <span className="truncate">All countries</span>
        </span>
        <span
          className="ml-2 shrink-0 text-[11.5px] tabular-nums"
          style={{
            color:
              active === null
                ? "var(--color-gold-bright)"
                : "var(--color-text-faint)",
          }}
        >
          {total}
        </span>
      </Link>

      <ul className="mt-0.5 flex flex-col gap-0.5">
        {countries.map((c) => {
          const isActive = active === c.country;
          return (
            <li key={c.country}>
              <Link
                href={`${basePath}?date=${date}&country=${encodeURIComponent(c.country)}`}
                aria-current={isActive ? "true" : undefined}
                className="flex items-center justify-between rounded-[var(--radius-md)] px-2.5 py-1.5 text-[13px] transition-colors hover:bg-[var(--color-surface-raised)]"
                style={{
                  ...activeStyle(isActive),
                  color: isActive
                    ? "var(--color-gold-bright)"
                    : "var(--color-text-dim)",
                  fontWeight: isActive ? 600 : undefined,
                }}
              >
                <span className="flex min-w-0 items-center gap-2">
                  <CountryMark code={c.country_code} />
                  <span className="truncate">{c.country}</span>
                </span>
                <span
                  className="ml-2 shrink-0 text-[11.5px] tabular-nums"
                  style={{
                    color: isActive
                      ? "var(--color-gold-bright)"
                      : "var(--color-text-faint)",
                  }}
                >
                  {c.count}
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
