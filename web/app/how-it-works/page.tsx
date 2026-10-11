/**
 * How the engine produces and grades a prediction, in detail.
 *
 * Process only, and deliberately static: nothing here is a claim about
 * performance, so there is no figure on the page to go stale. Performance is on
 * the track-record page, where it is counted and kept split into live and
 * reconstructed calls.
 *
 * Everything described is what the code does. The reference site's equivalent
 * page also names expected goals, odds movement and a fixed "four days before
 * kick-off" analysis window; none of those exist in this engine, so none are
 * claimed. If they are ever built, this is the page to add them to.
 */

import Link from "next/link";
import { FaqItem } from "@/components/FaqItem";
import { MarketGlossary } from "@/components/MarketGlossary";
import { breadcrumbLd, faqLd, pageMetadata } from "@/lib/seo";
import { JsonLd } from "@/components/seo/JsonLd";

export const metadata = pageMetadata({
  title: "How Our AI Football Predictions Work",
  description:
    "How the engine turns past results into football predictions: Elo, Poisson and boosted models blended, then every pick graded against the final score.",
  path: "/how-it-works",
});

const STAGES: Array<{ title: string; body: string[] }> = [
  {
    title: "Results in",
    body: [
      "The engine starts from completed matches: final scores, half-time scores where the source records them, and corner and card counts where it does. Historical results come from public football datasets and a licensed sports-data feed; fixtures, prices and final scores are pulled in on a schedule, never typed by hand.",
      "Different competitions record different things. Where a statistic is not recorded for a competition, the engine does not treat it as zero. The market that depends on it is simply not priced there, and the board shows that rather than a guess.",
    ],
  },
  {
    title: "Features that cannot see the result",
    body: [
      "For each fixture the engine builds features from what was known strictly before kick-off: each side's Elo rating, its recent form, head-to-head history, and its goal, corner and card rates. The same feature code is used for training and for prediction, and it is built to look only backwards in time.",
      "That discipline is what makes a reconstructed prediction meaningful. A match played last month can be re-predicted from history cut off at its kick-off, and the model cannot have seen the result.",
    ],
  },
  {
    title: "Three estimators, blended",
    body: [
      "An Elo rating system turns every past result into a strength for each team. A Poisson goal model estimates how many goals each side should score from its attacking and defensive record, which prices every exact scoreline. A gradient-boosted classifier, trained per market, learns patterns the other two cannot express.",
      "The three are blended into one probability per outcome. Because they are built differently, they make different mistakes, and where they disagree the engine says so: that disagreement is what the confidence score measures.",
    ],
  },
  {
    title: "One analysis, many markets",
    body: [
      "The same underlying probabilities price several markets: match result, double chance, draw no bet, goals over and under several lines, both teams to score, and, for competitions that record them, corners and cards. Double chance and draw no bet are derived from the match-result probabilities, so they cannot disagree with them.",
      "Each market also has a base rate: how often it lands across the completed matches on record in that competition, since over 8.5 corners or over 3.5 cards is routine in one league and rare in another. A pick that merely restates that rate says little, so the best tip for a fixture favours the likeliest call among those that beat their base rate, and falls back to the likeliest overall where none do. Corners and cards are priced but are never offered as the best tip. A draw no bet pick returns the stake on a draw, so a draw counts as neither a win nor a loss and is reported separately.",
    ],
  },
  {
    title: "Graded against the final score",
    body: [
      "Every pick is settled against the 90-minute result, including in cup competitions where extra time and penalties would otherwise blur the call. A pick is won, lost, or void when the match never recorded the statistic it depended on. Voids are excluded from every rate and reported separately, because counting them either way would misstate the sample.",
      "Nothing is removed after the fact. A losing pick stays on the record exactly as it was called, and the whole record is on the track-record page, downloadable, with live and reconstructed calls counted apart.",
    ],
  },
  {
    title: "Basketball and tennis",
    body: [
      "The engine prices basketball (the NBA, the EuroLeague and dozens of other leagues) and ATP and WTA tennis with the same discipline and different mathematics. Neither sport has a draw, so there is no Poisson goal model: each gets a rating system, a boosted model for the winner and, for totals, either a trained model (NBA points, tennis games) or a statistical estimate around the expected total (other basketball leagues). Tennis keeps a separate rating for each surface, because clay ability is not grass ability.",
      "They are graded the same way: a prediction is stored before the match and settled against the result, in a record of its own for each sport, with live and reconstructed predictions counted apart. A basketball or tennis match with a side that has too little history is not priced and is not listed at all, and ratings that are months out of date are pulled towards a coin flip and labelled.",
    ],
  },
];

const FAQS: Array<{ q: string; a: string }> = [
  {
    q: "What is the difference between a live and a reconstructed prediction?",
    a: "A live prediction was stored before kick-off, so nobody could have known the result. A reconstructed one was generated afterwards from history cut off at kick-off. The second is still honest evidence, because the features cannot see the result, but it was never exposed to being wrong in public, so the two are always counted and labelled separately.",
  },
  {
    q: "Does a high win rate mean these picks make money?",
    a: "No. A win rate says how often a pick lands, not whether the price paid for it was good. A pick that lands 80% of the time at a price that implies 85% loses money. This site reports how often picks land; it does not claim they are profitable.",
  },
  {
    q: "What does the confidence score mean?",
    a: "It is how closely the engine's independent estimators agree about a fixture, scored out of ten. It is not the chance of winning; that is the percentage on each pick. Confidence runs high for most fixtures, so it is shown beside the pick but is not what selects the day's bankers.",
  },
  {
    q: "Why do some fixtures have no prediction?",
    a: "The engine only predicts competitions it has a trained model for, and a fixture needs enough history for both sides. A football fixture without a prediction is shown without one rather than with a placeholder; a basketball or tennis match without one is left off the board.",
  },
  {
    q: "Is this betting advice?",
    a: "No. Every number is a probability computed from past results. Probabilities describe likelihood, not certainty, and nothing here links out to a bookmaker.",
  },
];

export default function HowItWorksPage() {
  return (
    <div className="mx-auto w-full max-w-[1200px] px-4 py-12 sm:px-6 lg:px-10">
      <JsonLd
        data={[
          faqLd(FAQS),
          breadcrumbLd([
            { name: "Home", path: "/" },
            { name: "How it works", path: "/how-it-works" },
          ]),
        ]}
      />
      <header className="max-w-[72ch]">
        <p className="text-[11px] tracking-[0.14em] text-[var(--color-gold-bright)] uppercase">
          Behind the predictions
        </p>
        <h1 className="mt-2.5 text-[clamp(1.9rem,4.5vw,2.75rem)] leading-tight font-bold tracking-[-0.02em]">
          How our football predictions are made and judged
        </h1>
        <p className="mt-3 text-[15px] leading-relaxed text-[var(--color-text-dim)]">
          Every pick on this site is computed, not written. This page walks
          through how a set of past results becomes a probability, and how that
          probability is judged afterwards.
        </p>
      </header>

      <ol className="mt-10 max-w-[72ch] space-y-8">
        {STAGES.map((stage, index) => (
          <li key={stage.title} className="flex gap-4">
            <span
              aria-hidden
              className="mt-0.5 text-[12px] font-bold tracking-wider text-[var(--color-gold-bright)]"
            >
              {String(index + 1).padStart(2, "0")}
            </span>
            <div>
              <h2 className="text-[17px] font-bold tracking-[-0.01em]">
                {stage.title}
              </h2>
              {stage.body.map((paragraph) => (
                <p
                  key={paragraph}
                  className="mt-2.5 text-[14px] leading-relaxed text-[var(--color-text-dim)]"
                >
                  {paragraph}
                </p>
              ))}
            </div>
          </li>
        ))}
      </ol>

      <MarketGlossary heading="What the markets mean" />

      <section className="mt-14 max-w-[72ch]">
        <h2 className="text-[18px] font-bold tracking-[-0.015em]">
          Questions about the method
        </h2>
        <div className="mt-4 space-y-2">
          {FAQS.map((item) => (
            <FaqItem key={item.q} q={item.q} a={item.a} />
          ))}
        </div>
      </section>

      <nav
        aria-label="Next"
        className="mt-12 flex flex-wrap gap-x-5 gap-y-2 text-[13px]"
      >
        <Link className="hover:text-[var(--color-gold-bright)]" href="/matches">
          Today&rsquo;s matches
        </Link>
        <Link
          className="hover:text-[var(--color-gold-bright)]"
          href="/progress"
        >
          The full track record
        </Link>
        <Link
          className="hover:text-[var(--color-gold-bright)]"
          href="/leaderboard"
        >
          The models
        </Link>
      </nav>
    </div>
  );
}
