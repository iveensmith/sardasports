/**
 * Countries down the side, with a fixture count each.
 *
 * Counts are for the whole day and do not change when a country is selected.
 * A sidebar that renumbered itself on every click would make it impossible to
 * see what else was on.
 *
 * International competitions group under their confederation — Europe,
 * Africa, South America, World — because that is where a reader scanning for
 * the Nations League looks, even though it is not a country.
 */

import Link from "next/link";
import type { CountryCount } from "@/lib/board";

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

  const row = (label: string, count: number, href: string, isActive: boolean) => (
    <Link
      key={label}
      href={href}
      aria-current={isActive ? "true" : undefined}
      className="flex items-center justify-between rounded-[var(--radius-md)] px-2.5 py-1.5 text-[13px] transition-colors hover:bg-[var(--color-surface-raised)]"
      style={{
        background: isActive ? "var(--color-surface-raised)" : undefined,
        color: isActive ? "var(--color-text)" : "var(--color-text-dim)",
        fontWeight: isActive ? 600 : undefined,
      }}
    >
      <span className="truncate">{label}</span>
      <span className="ml-2 shrink-0 text-[11.5px] text-[var(--color-text-faint)] tabular-nums">
        {count}
      </span>
    </Link>
  );

  return (
    <nav aria-label="Filter by country" className="flex flex-col gap-0.5">
      <p className="px-2.5 pb-1.5 text-[10.5px] tracking-wider text-[var(--color-text-faint)] uppercase">
        Countries
      </p>
      {row("All countries", total, `${basePath}?date=${date}`, active === null)}
      {countries.map((c) =>
        row(
          c.country,
          c.count,
          `${basePath}?date=${date}&country=${encodeURIComponent(c.country)}`,
          active === c.country,
        ),
      )}
    </nav>
  );
}
