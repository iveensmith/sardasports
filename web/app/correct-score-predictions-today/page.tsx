import type { MarketCopy } from "@/components/markets/MarketPage";
import { MarketRoute } from "@/components/markets/MarketRoute";

export const revalidate = 300;

export const metadata = {
  title: "Correct score predictions today — UniquePredict",
  description:
    "The likeliest exact score for each of today's fixtures, with the honest hit rate for the last 30 days — every settled call, not just the winners.",
};

const copy: MarketCopy = {
  eyebrow: "Correct score",
  title: "Correct score predictions today",
  intro:
    "The single likeliest exact score for each fixture on the card, likeliest first. Correct score is the hardest mainstream market to call, so the hit rate below is stated plainly and counts the misses.",
  picksHeading: "Today's correct score picks",
  pickColumn: "Likeliest score",
  rateNote:
    "This is every settled call over the window, not only the winners. Even the likeliest single scoreline carries a modest chance, so a rate in the low double digits is what this market looks like; treat any page that shows only its hits as showing you a different thing.",
  emptyTitle: "No scoreline to show for this card",
  emptyBody:
    "The engine had no scoreline view for any fixture on this day — either nothing is scheduled for competitions it models, or the fixtures have not been priced yet.",
  hitsHeading: "Recent correct score hits",
  explainerHeading: "How the likeliest score is chosen",
  explainer: [
    "Each fixture's scoreline comes from the engine's Poisson goal model. It estimates how many goals each side is expected to score from its attacking record and the opponent's defensive record, then prices every exact scoreline from those two expectations. The likeliest one is the pick, and its probability is printed beside it.",
    "Because the pick is the single most likely of many scorelines, its probability is small by construction — commonly somewhere around one in eight to one in ten. That is not a flaw in the call; it is what a correct score is. It also means the price on offer for a correct score is long, which is why the fair price shown here is a long one.",
  ],
  faqs: [
    {
      q: "How accurate are correct score predictions?",
      a: "Far less than win/draw/loss. The record above gives the real figure for the last 30 days: every settled call, hits and misses, split into live and reconstructed. It is a rate in the low double digits, not a majority.",
    },
    {
      q: "Why show the probability if it is so low?",
      a: "Because it is the honest number. A 13% pick is still the likeliest exact score for that match; it just is not likely in absolute terms. Hiding that would make the market look safer than it is.",
    },
    {
      q: "Where do the prices come from?",
      a: "No bookmaker correct-score line is stored, so each price is the pick's own fair price, 100 divided by its probability, marked ≈. It has no bookmaker margin and is not a price you can bet at.",
    },
    {
      q: "Do extra time and penalties count?",
      a: "No. The call is settled on the 90-minute score, including for cup matches.",
    },
    {
      q: "Why are only winners listed under the record?",
      a: "The list shows recent calls that landed so you can check them against the results. The rate above it counts the calls that did not land as well, so the list is never the whole picture on its own.",
    },
  ],
};

export default function CorrectScorePage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  return (
    <MarketRoute kind="correct-score" copy={copy} searchParams={searchParams} />
  );
}
