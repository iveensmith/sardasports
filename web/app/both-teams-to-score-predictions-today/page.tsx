import type { MarketCopy } from "@/components/markets/MarketPage";
import { MarketRoute } from "@/components/markets/MarketRoute";
import { pageMetadata } from "@/lib/seo";

export const revalidate = 300;

export const metadata = pageMetadata({
  title: "Both Teams to Score (BTTS) Predictions Today",
  description:
    "Today's fixtures where both teams are likely to score, ranked, with the market's 30-day record. Live and reconstructed picks kept apart.",
  path: "/both-teams-to-score-predictions-today",
});

const copy: MarketCopy = {
  path: "/both-teams-to-score-predictions-today",
  eyebrow: "Both teams to score",
  title: "Both teams to score predictions today",
  intro:
    "The day's fixtures that the engine rates more likely than not to see both sides score, most likely first. Each price is a bookmaker's where one was quoted, and the engine's own fair price where not.",
  picksHeading: "Today's both teams to score picks",
  pickColumn: "Pick",
  rateNote:
    "BTTS is only counted as a pick where the engine rates yes above 50%. A fixture it rates under is not a pick that failed to land. Read the rate against how often both teams score anyway, quoted above: beating that is the claim, not the raw percentage.",
  emptyTitle: "No fixture on this card leans towards both teams scoring",
  emptyBody:
    "That is a result, not a gap. Some cards are cautious on the engine's numbers, and listing fixtures it rates under would misname them.",
  hitsHeading: "Latest settled BTTS winners",
  explainerHeading: "How these picks are made",
  explainer: [
    "Both teams to score, usually shortened to BTTS, means each side scores at least once in normal time. The final score and the winner do not matter, only that both goal counts are above zero. The probability on each row comes from a model trained on completed matches for this market, blended with the engine's Poisson goal model, which prices each side's chance of scoring from its attacking and defensive record.",
    "A high number here says both defences are expected to be breached, not that the bet is good value. A price already reflects how likely a market thinks the outcome is, so the question worth asking of any row is whether the engine's probability is meaningfully above what the price implies. The track record above is the evidence for whether it usually is.",
  ],
  faqs: [
    {
      q: "What does both teams to score (BTTS) mean?",
      a: "It is a bet that each team scores at least one goal in the match. A 1-1 draw and a 3-2 win both count as yes; a 2-0 win counts as no, however many goals the winner scored.",
    },
    {
      q: "Is BTTS the same as over 2.5 goals?",
      a: "No. Over 2.5 needs three or more goals in total, from either side. BTTS needs both sides to score. A 1-1 draw is BTTS yes but not over 2.5, and a 3-0 win is over 2.5 but not BTTS.",
    },
    {
      q: "What does the percentage beside each pick mean?",
      a: "It is the engine's probability that both teams score. It is a probability, not a guarantee: a 60% pick is expected to miss four times in ten.",
    },
    {
      q: "Do extra time and penalties count?",
      a: "No. The pick is settled on the 90-minute score, including in cup matches.",
    },
    {
      q: "Why are some prices marked with a ≈?",
      a: "No bookmaker price was stored for that pick, so the figure shown is its own fair price: 100 divided by its probability. It carries no bookmaker margin, so it is not a price anyone will pay and should not be read as value against the market.",
    },
    {
      q: "What is the difference between live and reconstructed picks?",
      a: "A live pick was stored before kick-off, so nobody could have known the result. A reconstructed pick was generated after the match from history cut off at kick-off. Both are counted, separately, and the live figure is the stronger evidence.",
    },
  ],
};

export default function BttsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  return <MarketRoute kind="btts" copy={copy} searchParams={searchParams} />;
}
