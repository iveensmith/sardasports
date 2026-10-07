import type { MarketCopy } from "@/components/markets/MarketPage";
import { MarketRoute } from "@/components/markets/MarketRoute";
import { pageMetadata } from "@/lib/seo";

export const revalidate = 300;

export const metadata = pageMetadata({
  title: "Over 2.5 Goals Predictions & Tips Today",
  description:
    "Today's fixtures the engine rates likelier than not to have 3+ goals, ranked, with the market's 30-day record. Live and reconstructed picks kept apart.",
  path: "/over-2-5-goals-predictions-today",
});

const copy: MarketCopy = {
  path: "/over-2-5-goals-predictions-today",
  eyebrow: "Over 2.5 goals",
  title: "Over 2.5 goals predictions today",
  intro:
    "The day's fixtures that the engine rates more likely than not to produce three or more goals, most likely first. Each price is a bookmaker's where one was quoted, and the engine's own fair price where not.",
  picksHeading: "Today's over 2.5 goals picks",
  pickColumn: "Pick",
  rateNote:
    "Over 2.5 is only counted as a pick where the engine rates it above 50%. A fixture it rates under is not a pick that failed to land. Read the rate against how often over 2.5 happens anyway, quoted above: beating that is the claim, not the raw percentage.",
  emptyTitle: "No fixture on this card leans over 2.5",
  emptyBody:
    "That is a result, not a gap. Some cards are low-scoring on the engine's numbers, and listing fixtures it rates under would misname them.",
  hitsHeading: "Latest settled over 2.5 winners",
  explainerHeading: "How these picks are made",
  explainer: [
    "Over 2.5 goals means three or more goals in the match, by either side, in normal time. The probability on each row comes from a model trained on completed matches for that line, blended with the engine's Poisson goal model, which prices every scoreline from each team's attacking and defensive record.",
    "A high number here says the match is expected to be open, not that the bet is good value. A price already reflects how likely a market thinks the outcome is, so the question worth asking of any row is whether the engine's probability is meaningfully above what the price implies. The track record above is the evidence for whether it usually is.",
  ],
  faqs: [
    {
      q: "What counts as over 2.5 goals?",
      a: "Three or more goals scored in the match by both teams combined. Extra time and penalty shoot-outs do not count in cup matches; the 90-minute score settles the call.",
    },
    {
      q: "What does the percentage beside each pick mean?",
      a: "It is the engine's probability that the match finishes with three or more goals. It is a probability, not a guarantee. A 60% pick is expected to miss four times in ten.",
    },
    {
      q: "Why are some prices marked with a ≈?",
      a: "No bookmaker price was stored for that line, so the figure shown is the pick's own fair price: 100 divided by its probability. It carries no bookmaker margin, so it is not a price anyone will pay and should not be read as value against the market.",
    },
    {
      q: "What is the difference between live and reconstructed calls?",
      a: "A live call was stored before kick-off, so nobody could have known the result. A reconstructed call was generated after the match from history cut off at kick-off. Both are counted, separately, and the live figure is the stronger evidence.",
    },
    {
      q: "Why is the record only the last 30 days?",
      a: "It is a recent-form figure for this one market. The full record across every market is on the track-record page.",
    },
  ],
};

export default function Over25Page({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  return (
    <MarketRoute kind="over-2-5" copy={copy} searchParams={searchParams} />
  );
}
