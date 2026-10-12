/**
 * "Browse by sport": one tile each for the sports the engine covers, and one marked
 * as not here yet.
 *
 * The three real tiles carry how many matches are on record for that sport, from the
 * same summary the rest of the site reads. The last tile says "Coming soon" and is not
 * a link: there is no page behind it, so there is nothing to click.
 */

import Link from "next/link";
import { ArrowRight, Dots } from "@/components/home/icons";
import { SportMark } from "@/components/sport/SportMark";
import type { SportKey } from "@/lib/sports";

export interface SportSummaryRow {
  sport: string;
  matches_on_record: number;
}

const TILES: Array<{
  sport: SportKey;
  href: string;
  title: string;
  text: string;
  tint: string;
}> = [
  {
    sport: "football",
    href: "/matches",
    title: "Football",
    text: "Leagues & competitions",
    tint: "rgba(53,208,138,0.22)",
  },
  {
    sport: "basketball",
    href: "/basketball",
    title: "Basketball",
    text: "NBA & international",
    tint: "rgba(255,154,60,0.22)",
  },
  {
    sport: "tennis",
    href: "/tennis",
    title: "Tennis",
    text: "ATP & WTA",
    tint: "rgba(200,228,28,0.2)",
  },
];

export function BrowseSports({ sports }: { sports: SportSummaryRow[] | null }) {
  const counts = new Map(
    (sports ?? []).map((s) => [s.sport, s.matches_on_record]),
  );
  return (
    <section aria-labelledby="browse-sports">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h2
          id="browse-sports"
          className="flex items-center gap-3 text-[clamp(1.35rem,2.8vw,1.8rem)] leading-none font-black tracking-[-0.02em]"
        >
          <span className="flex h-9 w-9 items-center justify-center rounded-full bg-[var(--color-gold)]">
            <SportMark sport="football" size={20} />
          </span>
          <span>
            Browse by <span className="text-[var(--color-gold)]">sport</span>
          </span>
        </h2>
      </div>

      <ul className="mt-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        {TILES.map((tile) => {
          const count = counts.get(tile.sport);
          return (
            <li key={tile.sport}>
              <Link
                href={tile.href}
                className="group relative flex h-full min-h-[132px] flex-col justify-end overflow-hidden rounded-[14px] border border-[var(--color-line-strong)] bg-[var(--color-surface)] p-4 transition-colors hover:border-[var(--color-gold)]/70"
              >
                <span
                  aria-hidden
                  className="absolute inset-0"
                  style={{
                    background: `radial-gradient(70% 90% at 78% 8%, ${tile.tint}, transparent 70%)`,
                  }}
                />
                <span
                  aria-hidden
                  className="absolute top-3 right-3 transition-transform duration-300 ease-out group-hover:scale-110"
                >
                  <SportMark sport={tile.sport} size={64} />
                </span>
                <span className="relative flex items-end justify-between gap-2">
                  <span>
                    <span className="block text-[16px] leading-tight font-black tracking-[0.02em] uppercase">
                      {tile.title}
                    </span>
                    <span className="mt-0.5 block text-[12.5px] text-[var(--color-text-dim)]">
                      {tile.text}
                      {count ? (
                        <span className="tabular-nums">
                          {" · "}
                          {count.toLocaleString("en-GB")} matches
                        </span>
                      ) : null}
                    </span>
                  </span>
                  <span className="text-[var(--color-gold-bright)] transition-transform duration-200 group-hover:translate-x-0.5">
                    <ArrowRight size={20} />
                  </span>
                </span>
              </Link>
            </li>
          );
        })}

        <li>
          <div className="relative flex h-full min-h-[132px] flex-col justify-end rounded-[14px] border border-dashed border-[var(--color-line-strong)] bg-[var(--color-surface)] p-4">
            <span className="absolute top-4 right-4 flex h-12 w-12 items-center justify-center rounded-full border border-[var(--color-line-strong)] text-[var(--color-text-dim)]">
              <Dots size={26} />
            </span>
            <span className="block text-[16px] leading-tight font-black tracking-[0.02em] uppercase">
              More sports
            </span>
            <span className="mt-0.5 block text-[12.5px] text-[var(--color-text-dim)]">
              Coming soon
            </span>
          </div>
        </li>
      </ul>
    </section>
  );
}
