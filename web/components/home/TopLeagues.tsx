/**
 * "Top leagues": the quick way into a competition, at the foot of the picks.
 *
 * Follows the reference site's placement and shape: a divided block under the
 * day's boards, a centred label, and a two-row grid of tiles, each linking to
 * that competition's own page. Every tile here is a competition this engine
 * really models, so every link opens a real page.
 *
 * The reference fills its second row with the three UEFA club competitions, the
 * World Cup and the Euros. This engine does not cover the UEFA club competitions
 * yet (they are registered but switched off until the data plan includes them),
 * so they are not shown, and a tile is never drawn for a page that does not
 * exist. The list below keeps their slots: the moment a UEFA competition is
 * enabled and appears in the league catalogue, it takes the place of a filler,
 * with no change here.
 *
 * Marks are country flags, not league logos. League emblems are licensed
 * artwork this site has no source for, and a flag is derivable from the data
 * (see `TeamCrest` for the same reasoning applied to clubs). A competition that
 * belongs to no single nation, such as the World Cup, gets a globe.
 */

import Link from "next/link";
import { GlobeMark } from "@/components/board/CountryMark";
import type { LeagueCountry, LeagueEntry } from "@/lib/discover";

const SLOTS = 10;

/** Matched against the catalogue's own competition name, in display order. */
const FIRST_FIVE = [
  /^english premier league$/i,
  /^spanish la liga$/i,
  /^german bundesliga$/i,
  /^italian serie a$/i,
  /^french ligue 1$/i,
];
const UEFA = [
  /champions league/i,
  /(?<!conference )europa league/i,
  /conference league/i,
];
const LAST_TWO = [/^fifa world cup$/i, /^uefa european championship$/i];
/** Fills any slot a missing competition leaves, best-documented first. */
const FILLERS = [
  /^english championship$/i,
  /^dutch eredivisie$/i,
  /^portuguese primeira liga$/i,
  /^turkish super lig$/i,
  /^major league soccer$/i,
];

interface Tile {
  entry: LeagueEntry;
  countryCode: string | null;
}

function pick(patterns: RegExp[], pool: Tile[], used: Set<string>): Tile[] {
  const out: Tile[] = [];
  for (const pattern of patterns) {
    const found = pool.find(
      (tile) =>
        !used.has(tile.entry.slug) && pattern.test(tile.entry.competition),
    );
    if (found) {
      used.add(found.entry.slug);
      out.push(found);
    }
  }
  return out;
}

/** The ten tiles, in the reference's order, with real competitions only. */
export function topLeagueTiles(countries: LeagueCountry[]): Tile[] {
  const pool: Tile[] = countries.flatMap((country) =>
    country.competitions.map((entry) => ({
      entry,
      countryCode: country.country_code,
    })),
  );
  const used = new Set<string>();

  const first = pick(FIRST_FIVE, pool, used);
  const uefa = pick(UEFA, pool, used);
  const last = pick(LAST_TWO, pool, used);
  const room = Math.max(0, SLOTS - first.length - uefa.length - last.length);
  const fillers = pick(FILLERS, pool, used).slice(0, room);

  return [...first, ...uefa, ...fillers, ...last].slice(0, SLOTS);
}

function flagSrc(code: string, width: 20 | 80) {
  return `https://flagcdn.com/w${width}/${code.toLowerCase()}.png`;
}

function LeagueTile({ tile }: { tile: Tile }) {
  const { entry, countryCode } = tile;
  return (
    <li>
      <Link
        href={`/leagues/${entry.slug}`}
        // Each league page runs the engine over its fixtures; prefetching ten
        // of them on every home visit would make ten heavy requests for one click.
        prefetch={false}
        className="group relative flex h-[68px] items-center gap-3.5 overflow-hidden rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] px-5 transition-[border-color,transform] duration-200 hover:border-[var(--color-line-strong)] active:scale-[0.98]"
      >
        {/* The enlarged, faint mark on the right: the reference's watermark. */}
        <span
          aria-hidden
          className="pointer-events-none absolute -right-3 top-1/2 flex h-20 w-24 -translate-y-1/2 items-center justify-center text-[var(--color-text)] opacity-[0.07] transition-opacity duration-200 group-hover:opacity-[0.12]"
        >
          {countryCode ? (
            <img
              src={flagSrc(countryCode, 80)}
              alt=""
              width={80}
              height={54}
              loading="lazy"
              decoding="async"
              className="h-14 w-20 rotate-[-8deg] rounded-[4px] object-cover grayscale"
            />
          ) : (
            <span className="scale-[4]">
              <GlobeMark />
            </span>
          )}
        </span>

        <span className="relative flex h-6 w-7 shrink-0 items-center justify-center">
          {countryCode ? (
            <img
              src={flagSrc(countryCode, 20)}
              alt=""
              width={24}
              height={17}
              loading="lazy"
              decoding="async"
              className="h-[17px] w-6 rounded-[3px] object-cover"
            />
          ) : (
            <span className="text-[var(--color-text-faint)]">
              <GlobeMark />
            </span>
          )}
        </span>
        <span className="relative truncate text-[15px] font-semibold">
          {entry.short_name}
        </span>
      </Link>
    </li>
  );
}

export function TopLeagues({
  countries,
}: {
  countries: LeagueCountry[] | null;
}) {
  const tiles = countries ? topLeagueTiles(countries) : [];
  // Nothing to link to means no section, not a heading over an empty grid.
  if (tiles.length === 0) return null;

  return (
    <section aria-label="Top leagues">
      <h2 className="text-center text-[13px] font-semibold tracking-[0.18em] text-[var(--color-gold-bright)] uppercase">
        Top leagues
      </h2>
      <ul className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {tiles.map((tile) => (
          <LeagueTile key={tile.entry.slug} tile={tile} />
        ))}
      </ul>
    </section>
  );
}
