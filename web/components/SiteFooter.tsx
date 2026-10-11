/**
 * The footer, after the reference site's own shape — a brand column beside
 * a couple of real link columns, then a plain disclaimer bar.
 *
 * The reference's footer also carries social links, app-store badges, a
 * "Company" column (About/Contact/Privacy/Terms), a support email, a named
 * legal entity, and a two-column "Popular Teams" link farm. About, Contact and
 * Privacy now exist and are linked below, and "Reach us" (WhatsApp, Telegram,
 * email, X) sits above them: each route there shows "Coming soon" until its real
 * value is set in `lib/site.ts`, and is never a link before then. The rest does
 * not exist for real here (no mobile app, no named legal entity), so rather than
 * wire up dead links or invent content for it, it is left out entirely.
 *
 * Two columns are real. "Top-rated teams" links to team pages under `/teams/`
 * and is ranked by the engine's own rating, not by popularity, because there
 * is no traffic figure to call anything popular. "Top leagues" is the six
 * competitions with the most completed matches on record, each linking to its
 * own page under `/leagues/`.
 */

import Link from "next/link";
import { CountryMark } from "@/components/board/CountryMark";
import { TeamCrest } from "@/components/board/TeamCrest";
import { Logo } from "@/components/Logo";
import { ReachUs } from "@/components/ReachUs";
import { EngineError, getLeagues, getTopTeams } from "@/lib/api";
import type { Badge } from "@/lib/board";

const SITE_LINKS = [
  { href: "/matches", label: "Matches" },
  { href: "/bankers", label: "Bankers" },
  { href: "/slip", label: "Slip builder" },
  { href: "/leagues", label: "Leagues" },
  { href: "/progress", label: "Track record" },
  { href: "/leaderboard", label: "Models" },
  { href: "/how-it-works", label: "How it works" },
];

const COMPANY_LINKS = [
  { href: "/about", label: "About" },
  { href: "/contact", label: "Contact" },
  { href: "/privacy", label: "Privacy policy" },
  { href: "/terms", label: "Terms of use" },
  { href: "/about#responsible-gambling", label: "Responsible gambling" },
];

const GUIDE_LINKS = [
  { href: "/basketball", label: "Basketball predictions" },
  { href: "/tennis", label: "Tennis predictions" },
  { href: "/over-2-5-goals-predictions-today", label: "Over 2.5 goals today" },
  {
    href: "/best-football-prediction-site",
    label: "Best AI prediction site",
  },
  {
    href: "/both-teams-to-score-predictions-today",
    label: "Both teams to score today",
  },
  { href: "/correct-score-predictions-today", label: "Correct scores today" },
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
  let topLeagues: {
    competition: string;
    slug: string;
    short_name: string;
    countryCode: string | null;
  }[] = [];
  try {
    const leagues = await getLeagues();
    topLeagues = leagues.countries
      .flatMap((c) =>
        c.competitions.map((entry) => ({
          ...entry,
          countryCode: c.country_code,
        })),
      )
      .sort((a, b) => b.completed - a.completed)
      .slice(0, 6);
  } catch (e) {
    // The footer's one real data dependency — if the engine is briefly
    // unreachable, the column disappears rather than showing a guess.
    if (!(e instanceof EngineError)) throw e;
  }

  let topTeams: { name: string; slug: string; badge: Badge }[] = [];
  try {
    topTeams = await getTopTeams(6);
  } catch (e) {
    if (!(e instanceof EngineError)) throw e;
  }

  return (
    <footer className="mt-24 border-t border-[var(--color-line)]">
      <div className="mx-auto w-full max-w-[1200px] px-4 py-12 sm:px-6 lg:px-10">
        <div className="grid gap-10 sm:grid-cols-2 lg:grid-cols-[1.3fr_1fr_1fr_1fr_1fr]">
          <div>
            <Link href="/" className="inline-block" aria-label="SARDASPORTS">
              <Logo className="h-10" />
            </Link>
            <p className="mt-3 max-w-[42ch] text-[13.5px] leading-relaxed text-[var(--color-text-dim)]">
              The best AI prediction site for football, with basketball and
              tennis too. Free picks are published every day with no account
              needed, and every football pick is graded against the final score,
              wins and losses both, on the public record.
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

          <Column title="Predictions">
            {GUIDE_LINKS.map((link) => (
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

          {topTeams.length > 0 && (
            <Column title="Top-rated teams">
              {topTeams.map((team) => (
                <li key={team.slug}>
                  <Link
                    href={`/teams/${team.slug}`}
                    className="flex items-center gap-2.5 text-[var(--color-text-dim)] transition-colors hover:text-[var(--color-text)]"
                  >
                    <TeamCrest badge={team.badge} name={team.name} size={20} />
                    <span>{team.name}</span>
                  </Link>
                </li>
              ))}
            </Column>
          )}

          {topLeagues.length > 0 && (
            <Column title="Top leagues">
              {topLeagues.map((entry) => (
                <li key={entry.competition}>
                  <Link
                    href={`/leagues/${entry.slug}`}
                    className="flex items-center gap-2.5 text-[var(--color-text-dim)] transition-colors hover:text-[var(--color-text)]"
                  >
                    <CountryMark code={entry.countryCode} />
                    <span>{entry.short_name}</span>
                  </Link>
                </li>
              ))}
            </Column>
          )}
        </div>

        <div className="mt-10 border-t border-[var(--color-line)] pt-8">
          <ReachUs />
        </div>

        <nav
          aria-label="About and legal"
          className="mt-10 flex flex-wrap gap-x-6 gap-y-2 border-t border-[var(--color-line)] pt-6 text-[13.5px]"
        >
          {COMPANY_LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="text-[var(--color-text-dim)] transition-colors hover:text-[var(--color-text)]"
            >
              {link.label}
            </Link>
          ))}
        </nav>

        <div className="mt-6 text-[12.5px] leading-relaxed text-[var(--color-text-faint)]">
          <p className="max-w-[68ch]">
            18+ &middot; For information only, not betting advice. Every number
            on this site is computed by the prediction engine from ingested
            match data; where a market cannot be priced, it is shown as
            unavailable rather than estimated. Predictions describe probability,
            not certainty, and nothing here links out to a bookmaker.
          </p>
          <p className="mt-3">&copy; {new Date().getFullYear()} SARDASPORTS</p>
        </div>
      </div>
    </footer>
  );
}
