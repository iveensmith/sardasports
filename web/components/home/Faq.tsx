/**
 * The questions a first-time visitor asks, answered plainly and in this
 * engine's own terms.
 *
 * Two answers carry live figures (accuracy, coverage). Both fall back to a
 * qualitative sentence rather than a guessed number when the engine cannot be
 * reached. Everything else describes a policy or a definition, so it is static.
 *
 * Two claims are deliberately not made here, because the code does not back
 * them: that a pick is "never altered" once published (the stored prediction
 * is refreshed when it is recomputed), and that every pick is published before
 * kick-off (the reconstructed record is not). The answers say what is true.
 *
 * The banker threshold quoted below mirrors BANKER_PROBABILITY in
 * app/api/routes_discover.py; change them together.
 */

import { FaqItem } from "@/components/FaqItem";
import { rate, type SettledRecord } from "@/lib/progress";
import { JsonLd } from "@/components/seo/JsonLd";
import { faqLd } from "@/lib/seo";

const BANKER_PERCENT = 80;

export function Faq({
  live,
  backtest,
  competitionCount,
  countryCount,
}: {
  live: SettledRecord | null;
  backtest: SettledRecord | null;
  competitionCount: number | null;
  countryCount: number | null;
}) {
  const accuracyParts: string[] = [];
  if (live) {
    accuracyParts.push(
      `Of ${live.settled.toLocaleString()} picks stored before kick-off and since graded, ${live.won.toLocaleString()} won (${rate(live)}). That sample is still small.`,
    );
  }
  if (backtest) {
    accuracyParts.push(
      `Across ${backtest.settled.toLocaleString()} picks reconstructed from past matches, ${backtest.won.toLocaleString()} won (${rate(backtest)}).`,
    );
  }
  const accuracyAnswer = accuracyParts.length
    ? `${accuracyParts.join(" ")} Both figures, with every loss, are on the track record page. Neither is a promise about the next pick.`
    : "Every pick is graded against the final score, and the full history, wins and losses both, is on the track record page. Past accuracy is not a promise about the next pick.";

  const coverageAnswer =
    competitionCount && countryCount
      ? `${competitionCount} competitions across ${countryCount} countries, from top domestic leagues down to divisions most sites skip. The leagues page lists them all, with how much history sits behind each.`
      : "Every competition the engine has a trained model for. The leagues page lists them, with how much history sits behind each.";

  const items = [
    { q: "How accurate are the predictions?", a: accuracyAnswer },
    {
      q: "Do I need an account to see today's picks?",
      a: "No. Every board on this site is free to read, with no registration.",
    },
    {
      q: "Can I see the picks that lost?",
      a: "Yes. The track record page lists every graded pick, wins and losses, and the full history can be downloaded as a spreadsheet. Nothing is removed from the record.",
    },
    {
      q: "When do new predictions appear?",
      a: "Fixtures, prices and results are pulled in on a schedule through the day. A fixture appears on the board with its picks once it has been ingested, and its picks can change as new results arrive before kick-off. The board always shows the latest view.",
    },
    {
      q: "What do the columns on each row mean?",
      a: "The first three show the home win, draw and away win prices. The 1X2, O/U and BTTS columns show the engine's pick in each market with its price. Best tip is the one pick the fixture leads with, and the ring is the confidence score out of ten. A price marked ≈ is the engine's own fair price, used where no bookmaker price was stored.",
    },
    {
      q: "What does the confidence score mean?",
      a: "It is a score out of ten for how closely the engine's three estimators agree on the fixture. It measures agreement, not the chance of winning; the percentage beside each pick is that. Most fixtures score high, so the score separates them poorly, which is why bankers are chosen on probability instead.",
    },
    {
      q: "How is the best tip chosen?",
      a: "From every market priced for the fixture, the engine takes the likeliest pick among those that beat how often their market lands anyway. Where none does, it takes the likeliest pick overall.",
    },
    {
      q: "What is a banker?",
      a: `A banker is a pick the engine rates at least ${BANKER_PERCENT}% likely. The Bankers page lists them for each day, with the record of how the settled ones went. A near-certain pick usually carries a short price, so a banker is a safe pick, not necessarily a valuable one.`,
    },
    {
      q: "Can a model really predict a football match?",
      a: "Not any single match, and no model can. The engine produces probabilities and is judged on whether they hold up over many matches. A pick rated 70% is expected to miss three times in ten.",
    },
    { q: "Which competitions are covered?", a: coverageAnswer },
    {
      q: "Does a high win rate mean I will make money?",
      a: "No. A win rate says how often picks land, not whether the price paid for them was good. A short price on a near-certainty is usually priced about right already, so winning often can still lose money.",
    },
    {
      q: "Is this betting advice, and can I place a bet here?",
      a: "No to both. The site is for information, prices are shown for context, and nothing here links to a bookmaker. If you do bet, stake only what you can afford to lose. You must be 18 or over.",
    },
    {
      q: "Do you sell fixed matches?",
      a: "No. Every pick is a statistical estimate produced by the engine. Nobody can sell a guaranteed result, and this site does not claim to.",
    },
  ];

  return (
    <section>
      <JsonLd data={faqLd(items)} />
      <h2 className="text-[clamp(1.5rem,3vw,1.9rem)] font-bold tracking-[-0.02em]">
        Frequently asked questions
      </h2>
      <div className="mt-6 space-y-3">
        {items.map((item) => (
          <FaqItem key={item.q} q={item.q} a={item.a} />
        ))}
      </div>
    </section>
  );
}
