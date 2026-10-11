/**
 * About.
 *
 * Says what the site is, how it earns trust, and what it does not do, in plain
 * terms. Every figure is read from the engine when the page is built and falls
 * back to a sentence without a number if the engine cannot be reached, so the page
 * never states a count it did not just measure.
 *
 * It names no person, company, address or founding story, because none is on
 * record here and an invented one is the thing a page like this must not contain.
 * The operator is shown only if NEXT_PUBLIC_OPERATOR_NAME is set.
 *
 * The corrections list is real: a mistake found in the track record is published
 * here with what changed, which is the strongest thing a prediction site can say
 * about itself.
 */

import Link from "next/link";
import {
  List,
  PageHeader,
  Section,
  Strong,
  linkClass,
} from "@/components/prose/Prose";
import { JsonLd } from "@/components/seo/JsonLd";
import { getLeagues, getProgress } from "@/lib/api";
import { rate } from "@/lib/progress";
import { breadcrumbLd, pageMetadata } from "@/lib/seo";
import { OPERATOR_NAME, absoluteUrl } from "@/lib/site";

export const revalidate = 3600;

export const metadata = pageMetadata({
  title: "About SARDASPORTS: Football Predictions, Graded in Public",
  description:
    "SARDASPORTS publishes football predictions from a statistical engine and grades every one against the final score, wins and losses both, on a public record.",
  path: "/about",
});

function Fact({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] px-5 py-4">
      <p className="text-[12.5px] text-[var(--color-text-faint)]">{label}</p>
      <p className="mt-2 text-[28px] leading-none font-bold tabular-nums">
        {value ?? "—"}
      </p>
    </div>
  );
}

export default async function AboutPage() {
  const [progress, leagues] = await Promise.all([
    getProgress().catch(() => null),
    getLeagues().catch(() => null),
  ]);

  const graded = progress?.overall.settled ?? 0;
  const live = progress?.live.record.settled ?? 0;

  return (
    <div className="mx-auto w-full max-w-[1200px] px-4 py-12 sm:px-6 lg:px-10">
      <JsonLd
        data={[
          {
            "@context": "https://schema.org",
            "@type": "AboutPage",
            name: "About SARDASPORTS",
            url: absoluteUrl("/about"),
            about: { "@id": absoluteUrl("/#organization") },
          },
          breadcrumbLd([
            { name: "Home", path: "/" },
            { name: "About", path: "/about" },
          ]),
        ]}
      />

      <PageHeader
        title="About SARDASPORTS"
        intro="SARDASPORTS publishes football predictions produced by a statistical engine, and grades every one of them against the final score, in public. The aim is a prediction site you can check, and we believe that makes it the best AI prediction site for football."
      />

      <div className="mt-10 grid max-w-[72ch] grid-cols-2 gap-3 sm:grid-cols-4">
        <Fact
          label="Picks graded"
          value={graded > 0 ? graded.toLocaleString() : null}
        />
        <Fact
          label="Of which live"
          value={live > 0 ? live.toLocaleString() : null}
        />
        <Fact
          label="Competitions"
          value={leagues ? String(leagues.competition_count) : null}
        />
        <Fact
          label="Countries"
          value={leagues ? String(leagues.country_count) : null}
        />
      </div>

      <div className="mt-12 space-y-10">
        <Section title="What makes it different">
          <p>
            Most prediction sites show you their wins. This one is built around
            the opposite habit.
          </p>
          <List>
            <li>
              <Strong>Every pick is graded.</Strong> Each one is settled as won,
              lost or void against the final score, automatically. A losing pick
              stays on the record.
            </li>
            <li>
              <Strong>Two kinds of record, never blended.</Strong> A{" "}
              <em>live</em> pick was stored before kick-off. A{" "}
              <em>reconstructed</em> pick was generated after the match from
              history cut off at kick-off. The second is honest evidence but
              weaker, so the two are always counted and labelled separately.
            </li>
            <li>
              <Strong>You can check the numbers.</Strong> The full graded
              history is on the{" "}
              <Link href="/progress" className={linkClass}>
                track record page
              </Link>
              {progress ? (
                <>
                  {" "}
                  (currently {rate(progress.live.record)} live and{" "}
                  {rate(progress.backtest.record)} reconstructed)
                </>
              ) : null}
              , and it can be downloaded as a spreadsheet.
            </li>
            <li>
              <Strong>It says when it does not know.</Strong> Where a market
              cannot be priced for a competition, the site shows nothing rather
              than a guess. A price marked ≈ is the engine&rsquo;s own fair
              price, not a bookmaker&rsquo;s.
            </li>
          </List>
        </Section>

        <Section title="How the predictions are made">
          <p>
            An Elo rating system, a Poisson goal model and a gradient-boosted
            classifier trained for each market each form their own view of a
            match. They are blended into one probability per outcome, and how
            closely they agree becomes the confidence score. The inputs are
            ratings, recent form, head-to-head history, and goal, corner and
            card rates, all computed only from what was known before kick-off.
          </p>
          <p>
            The full explanation, including the markets and the grading rules,
            is on the{" "}
            <Link href="/how-it-works" className={linkClass}>
              how it works
            </Link>{" "}
            page.
          </p>
        </Section>

        <Section title="Basketball and tennis">
          <p>
            The same engine also prices basketball and tennis, on their own
            pages for{" "}
            <Link href="/basketball" className={linkClass}>
              basketball
            </Link>{" "}
            and{" "}
            <Link href="/tennis" className={linkClass}>
              tennis
            </Link>
            . Basketball covers the NBA, the EuroLeague and dozens of other
            leagues around the world, women&rsquo;s competitions included;
            tennis covers every ATP and WTA match. Their predictions are stored
            before the match and graded, and counted in a record of their own,
            kept apart from football&rsquo;s because the two are different
            sports with different amounts of history behind them.
          </p>
          <p>
            They are reported more cautiously than football, for honest reasons.
            The records are young, so the samples are small. Basketball history
            is loaded league by league within the data provider&rsquo;s request
            limit and the latest full season is not yet available, so some
            ratings are months old and are marked as such. A side with too
            little history is not priced at all. And where a model adds nothing,
            as the tennis match-winner model currently does over simply picking
            the higher-rated player, the page says so.
          </p>
        </Section>

        <Section title="Where the data comes from">
          <p>
            Historical results come from the public{" "}
            <a
              href="https://www.football-data.co.uk"
              className={linkClass}
              rel="noopener noreferrer"
              target="_blank"
            >
              football-data.co.uk
            </a>{" "}
            datasets. Fixtures, prices and results are pulled in on a schedule
            from{" "}
            <a
              href="https://www.api-football.com"
              className={linkClass}
              rel="noopener noreferrer"
              target="_blank"
            >
              API-Football
            </a>
            . Basketball results come from API-Basketball and tennis results
            from{" "}
            <a
              href="http://www.tennis-data.co.uk"
              className={linkClass}
              rel="noopener noreferrer"
              target="_blank"
            >
              tennis-data.co.uk
            </a>
            . SARDASPORTS does not own this data and does not claim to; the
            predictions, ratings and the graded record built from it are the
            site&rsquo;s own work.
          </p>
        </Section>

        <Section title="What this site does not do">
          <List>
            <li>It does not sell tips, subscriptions or “fixed matches”.</li>
            <li>It does not promise winnings or guarantee any outcome.</li>
            <li>
              It does not link to bookmakers or take payment from them to change
              what it shows.
            </li>
            <li>
              It does not give personal betting advice. Everything here is
              information about probability, and probability is not certainty.
            </li>
          </List>
        </Section>

        <Section id="corrections" title="Corrections">
          <p>
            When a mistake is found in the record, it is fixed and listed here
            with what changed. To report one, use the{" "}
            <Link href="/contact" className={linkClass}>
              contact page
            </Link>
            .
          </p>
          <div className="rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] p-5">
            <p className="text-[13px] font-semibold text-[var(--color-text)]">
              11 October 2026: corners and cards out, draw no bet in
            </p>
            <p className="mt-2">
              Corners and cards are no longer offered as the best tip; they are
              still priced and listed on each match page. Draw no bet joined the
              markets a best tip can come from. A draw returns the stake on that
              pick, so it is neither a win nor a loss and is reported separately
              from the win rate, as an unrecorded statistic already was. On the
              graded predictions the same fixtures would have read 65.8% won
              with corners and cards removed and 72.7% of settled tips with draw
              no bet added, with 12.2% of tips refunded on a draw.
            </p>
          </div>
          <div className="rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] p-5">
            <p className="text-[13px] font-semibold text-[var(--color-text)]">
              10 October 2026: how the best tip is chosen
            </p>
            <p className="mt-2">
              Corners and cards were taking too many best tips, because each
              call was compared with how often its market lands across all
              leagues rather than in its own league, and the corner and card
              probabilities had run about five points high. Calls are now
              compared with their own competition&rsquo;s rate, corners and
              cards must clear a higher bar to lead, and a competition that
              records no corners or cards gets no calls for them. The track
              record grades the same pick the boards now lead with, so the
              published rates fell: the reconstructed record from 76.2% to
              68.6%, and the overall from 76.2% to 68.9%. The old figures were
              flattered by easy, high-probability lines.
            </p>
          </div>
          <div className="rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] p-5">
            <p className="text-[13px] font-semibold text-[var(--color-text)]">
              7 October 2026: track-record headline picks
            </p>
            <p className="mt-2">
              The track record chose each prediction&rsquo;s headline pick by
              comparing probabilities that were stored on two different scales
              (match result and both-teams-to-score as fractions, every other
              market as percentages). Match-result picks could therefore never
              lead, so the record was grading different picks from the ones the
              match boards show. It now grades the same pick the boards lead
              with. The published rates changed: the live record went from 28 of
              31 (90.3%) to 27 of 31 (87.1%), and the reconstructed record from
              77.9% to 76.2%.
            </p>
          </div>
        </Section>

        <Section id="responsible-gambling" title="Responsible gambling">
          <p>
            SARDASPORTS is for people aged 18 and over and is for information
            only. Football is unpredictable and no model changes that: a pick
            the engine rates at 70% is expected to lose three times in ten.
            Never stake money you cannot afford to lose, and do not use betting
            to try to recover losses.
          </p>
          <p>
            If gambling is causing you or someone close to you harm, free,
            confidential help is available from{" "}
            <a
              href="https://www.gambleaware.org"
              className={linkClass}
              rel="noopener noreferrer"
              target="_blank"
            >
              BeGambleAware
            </a>{" "}
            and{" "}
            <a
              href="https://www.gamblingtherapy.org"
              className={linkClass}
              rel="noopener noreferrer"
              target="_blank"
            >
              Gambling Therapy
            </a>
            .
          </p>
        </Section>

        <Section title="Who runs this site">
          <p>
            {OPERATOR_NAME ? (
              <>
                SARDASPORTS is operated by <Strong>{OPERATOR_NAME}</Strong>
                .{" "}
              </>
            ) : null}
            The operator can be reached through the{" "}
            <Link href="/contact" className={linkClass}>
              contact page
            </Link>
            . Questions about how personal data is handled are answered in the{" "}
            <Link href="/privacy" className={linkClass}>
              privacy policy
            </Link>
            .
          </p>
        </Section>
      </div>
    </div>
  );
}
