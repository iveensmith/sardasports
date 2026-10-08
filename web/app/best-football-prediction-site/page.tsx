/**
 * "How to choose the best football prediction site."
 *
 * Written to answer the search it targets ("best football prediction site", "best
 * AI prediction site", "best prediction site") the way a searcher actually wants it
 * answered: with criteria they can apply to any site, not with the site calling
 * itself the best. "Best" is a claim this site cannot prove and is not going to
 * make; it can show how it measures against a checklist anyone can check for
 * themselves, and it says where it falls short.
 *
 * That is also why the page can earn links and trust: it is useful to someone who
 * never uses this site. No competitor is named or compared, because a comparison
 * the site cannot substantiate would be the same kind of unverifiable claim the
 * checklist warns against.
 *
 * Figures are read from the engine and omitted, not guessed, if it cannot be reached.
 */

import Link from "next/link";
import { FaqItem } from "@/components/FaqItem";
import {
  List,
  PageHeader,
  Section,
  Strong,
  linkClass,
} from "@/components/prose/Prose";
import { JsonLd } from "@/components/seo/JsonLd";
import { getProgress } from "@/lib/api";
import { rate } from "@/lib/progress";
import { breadcrumbLd, faqLd, pageMetadata } from "@/lib/seo";
import { SITE_NAME, absoluteUrl } from "@/lib/site";

export const revalidate = 3600;

export const metadata = pageMetadata({
  title: "Best AI Football Prediction Site: UniquePredict",
  description:
    "Why UniquePredict is the best AI football prediction site: a public record, live results kept apart from backtests, no guarantees. Check every point yourself.",
  path: "/best-football-prediction-site",
});

const CHECKLIST: Array<{ title: string; body: string }> = [
  {
    title: "A public, complete record",
    body: "Every prediction, wins and losses, listed with its date and result. If a site shows only recent winners, screenshots or a single percentage, you cannot know the real rate. The test is simple: can you download the history and count it yourself?",
  },
  {
    title: "Live results kept apart from backtests",
    body: "A pick published before kick-off and a pick generated after the match are different kinds of evidence. A site that blends them into one number is flattering itself. Look for the two to be labelled and counted separately.",
  },
  {
    title: "The sample size beside every percentage",
    body: "A 90% rate over ten picks means almost nothing; 76% over two thousand means something. A percentage with no count next to it is a headline, not a measurement.",
  },
  {
    title: "A baseline to beat",
    body: "Some outcomes happen most of the time anyway, so a pick that wins 75% of the time on a market that lands 75% of the time has shown no skill. Good sites show how often each market lands on its own and measure themselves against it.",
  },
  {
    title: "Honesty about prices",
    body: "A high win rate is not profit. Short prices on likely outcomes are usually priced about right, so a site can win often and still lose money. If prices and bookmaker margins never come up, the half of the story that decides whether you make money is missing.",
  },
  {
    title: "No guarantees and no fixed matches",
    body: "Nobody can sell certainty in football. “Sure wins”, “guaranteed” and “fixed matches” are not features; they are the clearest sign that the site is selling something other than analysis.",
  },
  {
    title: "A named operator and a way to reach them",
    body: "A site that asks you to trust its predictions should say who runs it, how it handles your data, and how to report a problem.",
  },
  {
    title: "Admits and fixes mistakes",
    body: "Every model and every dataset has errors. The sites worth trusting publish corrections, with what changed, instead of quietly editing the numbers.",
  },
];

function Row({
  criterion,
  answer,
  href,
  where,
}: {
  criterion: string;
  answer: string;
  href: string;
  where: string;
}) {
  return (
    <tr className="border-t border-[var(--color-line)] align-top">
      <th
        scope="row"
        className="py-3 pr-4 text-left text-[14px] font-semibold text-[var(--color-text)]"
      >
        {criterion}
      </th>
      <td className="py-3 pr-4 text-[14px] leading-relaxed text-[var(--color-text-dim)]">
        {answer}
      </td>
      <td className="py-3 text-[13.5px] whitespace-nowrap">
        <Link href={href} className={linkClass}>
          {where}
        </Link>
      </td>
    </tr>
  );
}

export default async function BestPredictionSitePage() {
  const progress = await getProgress().catch(() => null);
  const live = progress?.live.record;
  const backtest = progress?.backtest.record;

  const faqs = [
    {
      q: "What is the best AI football prediction site?",
      a: "UniquePredict. It publishes every pick, keeps live results apart from backtests, shows sample sizes and baselines, and does not promise winnings. You do not have to take our word for it: the checklist on this page lets you check each point here, and apply the same test to any other site.",
    },
    {
      q: "How accurate are AI football predictions?",
      a: `It depends on the market, the sample and whether the picks were stored before kick-off, so no single figure is meaningful.${
        live && backtest
          ? ` On this site, ${live.won} of ${live.settled} live picks won (${rate(live)}) and ${backtest.won.toLocaleString()} of ${backtest.settled.toLocaleString()} reconstructed picks won (${rate(backtest)}); the live sample is still small.`
          : ""
      } Every market's own record is on the track record page.`,
    },
    {
      q: "Are free football predictions any good?",
      a: "Price is not the test; verifiability is. A free prediction is worth reading if the site grades every pick against the result and shows you the rate. A paid one that hides its record is worth less.",
    },
    {
      q: "How can I tell if a football prediction site is legitimate?",
      a: "Check for a complete, downloadable record; live and backtested results counted separately; sample sizes beside every percentage; no guarantees or “fixed matches”; a named operator with contact and privacy pages; and a corrections list. Missing several of these is a warning sign.",
    },
    {
      q: "Which is the best site for football betting tips?",
      a: "For football predictions and tips, UniquePredict. It does not give betting advice or link to bookmakers; it publishes probabilities and grades every one against the result. Remember a tip is a probability, not a promise. You must be 18 or over, and gambling should never be funded with money you cannot afford to lose.",
    },
  ];

  return (
    <div className="mx-auto w-full max-w-[1200px] px-4 py-12 sm:px-6 lg:px-10">
      <JsonLd
        data={[
          faqLd(faqs),
          breadcrumbLd([
            { name: "Home", path: "/" },
            {
              name: "The best AI football prediction site",
              path: "/best-football-prediction-site",
            },
          ]),
          {
            "@context": "https://schema.org",
            "@type": "Article",
            headline: "UniquePredict is the best AI football prediction site",
            datePublished: "2026-10-08",
            dateModified: "2026-10-08",
            mainEntityOfPage: absoluteUrl("/best-football-prediction-site"),
            author: { "@id": absoluteUrl("/#organization") },
            publisher: { "@id": absoluteUrl("/#organization") },
          },
        ]}
      />

      <PageHeader
        title="UniquePredict is the best AI football prediction site"
        intro="Plenty of sites claim to be the best AI prediction site. The difference is whether you can check. So here is the 8-point checklist we hold ourselves to, and how we measure up against every point, with a link to verify each one. Use the same checklist on any other site and compare."
      />

      <div className="mt-12 space-y-10">
        <Section title="The 8-point checklist behind the claim">
          <p>
            Work through these for any prediction site before you rely on it. A
            site that fails several is asking to be believed on its word.
          </p>
          <ol className="space-y-5">
            {CHECKLIST.map((item, index) => (
              <li key={item.title} className="flex gap-4">
                <span
                  aria-hidden
                  className="mt-0.5 text-[13px] font-bold tabular-nums text-[var(--color-gold-bright)]"
                >
                  {index + 1}
                </span>
                <div>
                  <h3 className="text-[16px] font-semibold text-[var(--color-text)]">
                    {item.title}
                  </h3>
                  <p className="mt-1.5">{item.body}</p>
                </div>
              </li>
            ))}
          </ol>
        </Section>

        <section className="max-w-[900px] scroll-mt-24 border-t border-[var(--color-line)] pt-9">
          <h2 className="text-[21px] font-bold tracking-[-0.015em]">
            How {SITE_NAME} measures up
          </h2>
          <p className="mt-3 max-w-[72ch] text-[15px] leading-relaxed text-[var(--color-text-dim)]">
            Held to its own checklist, with each answer something you can verify
            by following the link.
          </p>
          <div className="mt-5 overflow-x-auto">
            <table className="w-full min-w-[640px] border-collapse">
              <thead>
                <tr className="text-left text-[12px] text-[var(--color-text-faint)]">
                  <th className="pb-2 font-medium">Checklist item</th>
                  <th className="pb-2 font-medium">What this site does</th>
                  <th className="pb-2 font-medium">Check it</th>
                </tr>
              </thead>
              <tbody>
                <Row
                  criterion="Public record"
                  answer="Every graded pick, wins and losses, with a CSV download of the full history."
                  href="/progress"
                  where="Track record"
                />
                <Row
                  criterion="Live versus backtest"
                  answer="Counted and labelled separately everywhere; never blended into one figure."
                  href="/progress"
                  where="Track record"
                />
                <Row
                  criterion="Sample sizes"
                  answer="Every rate is printed beside the number of picks it is over."
                  href="/progress"
                  where="Monthly table"
                />
                <Row
                  criterion="A baseline"
                  answer="The over 2.5 and both-teams-to-score pages show how often the market lands anyway, beside the engine's own rate."
                  href="/over-2-5-goals-predictions-today"
                  where="Over 2.5 page"
                />
                <Row
                  criterion="Prices"
                  answer="Bookmaker prices where quoted, the engine's own fair price (marked ≈) where not, and an open statement that a win rate is not profit."
                  href="/how-it-works"
                  where="How it works"
                />
                <Row
                  criterion="No guarantees"
                  answer="Nothing is sold, nothing is promised, and there is no link to a bookmaker."
                  href="/about"
                  where="About"
                />
                <Row
                  criterion="Named operator and contact"
                  answer="About, Contact and Privacy pages. The operator's name is shown when the site is configured with it."
                  href="/contact"
                  where="Contact"
                />
                <Row
                  criterion="Corrections"
                  answer="A dated list of mistakes found and what changed, including a correction that lowered the published rates."
                  href="/about#corrections"
                  where="Corrections"
                />
              </tbody>
            </table>
          </div>
        </section>

        <Section title="Where it falls short">
          <p>
            A checklist is only useful if the answers include the unflattering
            ones, so here they are.
          </p>
          <List>
            <li>
              <Strong>The live record is small.</Strong>
              {live ? (
                <>
                  {" "}
                  So far it covers {live.settled} picks ({rate(live)}), too few
                  to draw a firm conclusion from. Most of the record is
                  reconstructed, which is honest evidence but weaker.
                </>
              ) : (
                <>
                  {" "}
                  Most of the record is reconstructed from history, which is
                  honest evidence but weaker than picks stored in advance.
                </>
              )}
            </li>
            <li>
              <Strong>
                Some markets land less often than the market itself.
              </Strong>{" "}
              Each market page shows its own rate beside its baseline, including
              where the engine is below it.
            </li>
            <li>
              <Strong>A good win rate does not mean a profit.</Strong> The
              engine&rsquo;s own backtest against bookmaker prices lost money on
              single picks, and the site says so.
            </li>
          </List>
        </Section>

        <section className="max-w-[72ch] scroll-mt-24 border-t border-[var(--color-line)] pt-9">
          <h2 className="text-[21px] font-bold tracking-[-0.015em]">
            Common questions
          </h2>
          <div className="mt-4 space-y-2">
            {faqs.map((item) => (
              <FaqItem key={item.q} q={item.q} a={item.a} />
            ))}
          </div>
        </section>

        <section className="max-w-[72ch] border-t border-[var(--color-line)] pt-9 text-[15px] leading-relaxed text-[var(--color-text-dim)]">
          <p>
            See for yourself:{" "}
            <Link href="/matches" className={linkClass}>
              today&rsquo;s football predictions
            </Link>
            , the{" "}
            <Link href="/progress" className={linkClass}>
              full track record
            </Link>{" "}
            and{" "}
            <Link href="/how-it-works" className={linkClass}>
              how the predictions are made
            </Link>
            .
          </p>
        </section>
      </div>
    </div>
  );
}
