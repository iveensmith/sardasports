/**
 * The footer, after the reference site's own shape — a brand column beside
 * a couple of real link columns, then a plain disclaimer bar.
 *
 * The reference's footer also carries social links, app-store badges, a
 * "Company" column (Tutorial/About/Contact/Privacy/Terms), a support
 * email, a named legal entity, and a two-column "Popular Teams" link farm.
 * None of those exist for real here — there is no social presence, no
 * mobile app, no About/Contact/Privacy/Terms pages, no support inbox, and
 * no per-team landing pages — so rather than wire up dead links or invent
 * content for pages that don't exist, they're left out entirely. "Top
 * leagues" is real: the six competitions with the most completed matches
 * on record, each linking to its own page under `/leagues/`.
 */

import Link from "next/link";
import { EngineError, getLeagues } from "@/lib/api";

const SITE_LINKS = [
  { href: "/matches", label: "Matches" },
  { href: "/bankers", label: "Bankers" },
  { href: "/slip", label: "Slip builder" },
  { href: "/leagues", label: "Leagues" },
  { href: "/progress", label: "Track record" },
  { href: "/leaderboard", label: "Models" },
];

function Column({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <p className="text-[11px] tracking-[0.12em] text-[var(--color-text-faint)] uppercase">
        {title}
      </p>
      <ul className="mt-3 space-y-2 text-[13.5px]">{children}</ul>
    </div>
  );
}

export async function SiteFooter() {
  let topLeagues: { competition: string; slug: string; short_name: string }[] =
    [];
  try {
    const leagues = await getLeagues();
    topLeagues = leagues.countries
      .flatMap((c) => c.competitions)
      .sort((a, b) => b.completed - a.completed)
      .slice(0, 6);
  } catch (e) {
    // The footer's one real data dependency — if the engine is briefly
    // unreachable, the column disappears rather than showing a guess.
    if (!(e instanceof EngineError)) throw e;
  }

  return (
    <footer className="mt-24 border-t border-[var(--color-line)]">
      <div className="mx-auto w-full max-w-[1200px] px-4 py-12 sm:px-6 lg:px-10">
        <div className="grid gap-10 sm:grid-cols-2 lg:grid-cols-[1.3fr_1fr_1fr]">
          <div>
            <Link href="/" className="text-[17px] font-bold tracking-[-0.02em]">
              Unique<span className="text-[var(--color-gold)]">Predict</span>
            </Link>
            <p className="mt-3 max-w-[42ch] text-[13.5px] leading-relaxed text-[var(--color-text-dim)]">
              A calibrated football prediction engine. Free picks are published
              every day with no account needed, and every call is settled
              against the final score &mdash; wins and losses both, on the
              public record.
            </p>
          </div>

          <Column title="Site">
            {SITE_LINKS.map((link) => (
              <li key={link.href}>
                <Link
                  href={link.href}
                  className="text-[var(--color-text-dim)] transition-colors hover:text-[var(--color-text)]"
                >
                  {link.label}
                </Link>
              </li>
            ))}
          </Column>

          {topLeagues.length > 0 && (
            <Column title="Top leagues">
              {topLeagues.map((entry) => (
                <li key={entry.competition}>
                  <Link
                    href={`/leagues/${entry.slug}`}
                    className="text-[var(--color-text-dim)] transition-colors hover:text-[var(--color-text)]"
                  >
                    {entry.short_name}
                  </Link>
                </li>
              ))}
            </Column>
          )}
        </div>

        <div className="mt-10 border-t border-[var(--color-line)] pt-6 text-[12.5px] leading-relaxed text-[var(--color-text-faint)]">
          <p className="max-w-[68ch]">
            18+ &middot; For information only, not betting advice. Every number
            on this site is computed by the prediction engine from ingested
            match data; where a market cannot be priced, it is shown as
            unavailable rather than estimated. Predictions describe probability,
            not certainty, and nothing here links out to a bookmaker.
          </p>
          <p className="mt-3">
            &copy; {new Date().getFullYear()} UniquePredict
          </p>
        </div>
      </div>
    </footer>
  );
}
