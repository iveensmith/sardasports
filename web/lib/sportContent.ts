/**
 * The words on the basketball and tennis pages.
 *
 * Every factual statement here is something the engine's own records support (the
 * data source, the seasons covered, the markets it prices, what the measured edge
 * is). Figures that change are not written here; the page reads them from the
 * engine and the FAQ below is built from them, so the copy cannot drift from the
 * numbers.
 */

import type { OtherSportKey, SportModelRow, SportOverview } from "./sports";
import { edgeVerdict, shortDate } from "./sports";

export interface SportCopy {
  path: string;
  /** The page's own keyword-led title and description. */
  metaTitle: string;
  metaDescription: string;
  h1: string;
  intro: string;
  /** What the engine prices for this sport, as plain definitions. */
  markets: Array<{ name: string; body: string }>;
  /** How the predictions are made, in a few honest paragraphs. */
  method: string[];
  /** Where the data comes from, and what it does not include. */
  source: string;
  /** Singular and plural words for the thing being rated. */
  competitor: { singular: string; plural: string };
  /** One line for the home page card. */
  cardLine: string;
  keywords: string[];
}

export const SPORT_COPY: Record<OtherSportKey, SportCopy> = {
  tennis: {
    path: "/tennis",
    metaTitle: "Tennis Predictions Today: ATP and WTA Match Tips",
    metaDescription:
      "AI tennis predictions for every ATP and WTA match: win probabilities and total games by surface, stored before the match and graded, with each model's record.",
    h1: "Tennis predictions for every ATP and WTA match",
    intro:
      "Match-winner probabilities and total-games lines for ATP and WTA matches, qualifying included, from ratings kept separately for hard, clay and grass. Predictions are stored before the match and graded afterwards, and each model is shown beside the simplest rule it has to beat. Where it adds nothing, this page says so.",
    markets: [
      {
        name: "Match winner",
        body: "The probability that each player wins the match. Tennis has no draw, so the two figures always add to 100%.",
      },
      {
        name: "Total games",
        body: "The chance that the two players play more or fewer games than a line such as 21.5. It depends on how evenly matched they are and on the format: WTA matches and most ATP matches are best of three sets, Grand Slam men's matches best of five.",
      },
    ],
    method: [
      "Each player has an Elo-style rating, and a second rating for each surface. Clay ability is not grass ability, so where the overall and surface ratings disagree, the surface rating is the better guide and the engine uses both. Where a tournament's surface is not known the overall rating is used rather than a guessed surface.",
      "On top of the ratings the model reads recent form, the share of matches won on the surface, average games won and lost, head-to-head and the match format, then blends its own estimate with the rating baseline. A player with fewer than five recent matches on record is not priced, because a default rating is not evidence.",
      "Match outcome in tennis is close to fully described by the gap between two ratings, which is why the winner model is measured against a rule that always picks the higher-rated player. The total-games lines are where the model has more to add, because a rating says who is better and nothing about how long the match lasts.",
    ],
    source:
      "History comes from tennis-data.co.uk (ATP and WTA main-tour results from 2010, with set scores). Fixtures and results for the tournaments in progress come from ESPN's public scoreboard, which is not a licensed data product and could change without notice. Together they cover the ATP and WTA tours, qualifying included. Challenger and ITF events and doubles are not covered.",
    competitor: { singular: "player", plural: "players" },
    cardLine: "Every ATP and WTA match: winners and total games",
    keywords: [
      "tennis predictions",
      "tennis predictions today",
      "ATP predictions",
      "WTA predictions",
      "tennis betting tips",
      "AI tennis predictions",
      "tennis match predictions",
    ],
  },
  basketball: {
    path: "/basketball",
    metaTitle: "Basketball Predictions Today: NBA, EuroLeague and More",
    metaDescription:
      "AI basketball predictions for the NBA, EuroLeague and dozens of leagues worldwide: win probabilities and total points, stored before tip-off and graded.",
    h1: "Basketball predictions for the NBA, EuroLeague and every league we cover",
    intro:
      "Win probabilities and total-points lines for games across the NBA, the EuroLeague, the Spanish, Italian, German, Turkish, Chinese, Australian, Japanese and Korean leagues and dozens more, women's competitions included. Predictions are stored before tip-off and graded afterwards, and each model is shown beside the baseline it has to beat.",
    markets: [
      {
        name: "Game winner",
        body: "The probability that each team wins. Basketball has no draws (overtime settles every game), so the two figures always add to 100%.",
      },
      {
        name: "Total points",
        body: "The chance that both teams combined score more or fewer points than a line such as 225.5. Leagues score very differently (about 227 a game in the NBA, about 160 in the EuroLeague), so each league gets lines near its own average; the NBA uses trained models and every other league uses a statistical estimate, and the table below shows how each measures.",
      },
    ],
    method: [
      "Each team has an Elo-style rating that moves with every result, weighted by the margin. Ratings are kept per sport, so a basketball side is never mixed up with a football club that shares its name.",
      "The winner model reads each side's scoring and conceding averages, win rate, days of rest, whether it is playing a second game in two nights, and head-to-head, then blends its estimate with the rating baseline. One model covers every league, and its accuracy is reported for the NBA and for the rest separately.",
      "Totals outside the NBA are priced from a normal distribution around the expected total (what each side scores blended with what the other concedes) with that league's own spread. It was checked against games it never saw, and the table shows the result. A team with fewer than six prior games, or none for over a year, is not priced: a default rating is not evidence.",
    ],
    source:
      "Results come from API-Basketball. History runs from 2022 to 2025 for the leagues loaded so far (more are added every day within the plan's request limit), and fixtures and results since arrive through a daily feed covering every league the provider lists. A league's ratings are only as good as the seasons loaded for it, and a match with too little history behind it is left off the board rather than shown without a pick.",
    competitor: { singular: "team", plural: "teams" },
    cardLine: "NBA, EuroLeague and dozens more leagues: winners and totals",
    keywords: [
      "basketball predictions",
      "NBA predictions",
      "NBA predictions today",
      "EuroLeague predictions",
      "basketball betting tips",
      "AI basketball predictions",
      "NBA over under predictions",
    ],
  },
};

function pct(value: number | null): string {
  return value === null ? "n/a" : `${value.toFixed(1)}%`;
}

function describe(model: SportModelRow): string {
  const verdict = edgeVerdict(model);
  const base = `${pct(model.accuracy)} on ${model.test_matches?.toLocaleString("en-GB") ?? "an unrecorded number of"} held-out matches`;
  if (model.baseline === null || model.edge === null) return base;
  const against = `${pct(model.baseline)} for the baseline (${model.baseline_kind?.toLowerCase()})`;
  const gap =
    verdict === "clear"
      ? `a real edge of ${model.edge.toFixed(1)} points`
      : `a gap of ${model.edge.toFixed(1)} points, which is within what chance alone produces`;
  return `${base}, against ${against}: ${gap}`;
}

/** The questions a reader asks, answered from the engine's own figures. */
export function sportFaqs(
  sport: OtherSportKey,
  data: SportOverview,
): Array<{ q: string; a: string }> {
  const copy = SPORT_COPY[sport];
  const winner = data.models[0];
  const totals = data.models.slice(1);
  const best = [...totals]
    .filter((m) => edgeVerdict(m) === "clear")
    .sort((a, b) => (b.edge ?? 0) - (a.edge ?? 0))[0];
  const label = sport === "tennis" ? "tennis" : "basketball";

  const faqs: Array<{ q: string; a: string }> = [];

  if (winner) {
    faqs.push({
      q: `How accurate are the ${label} predictions?`,
      a: `The ${winner.label.toLowerCase()} model scored ${describe(winner)}. ${
        edgeVerdict(winner) === "clear"
          ? "That is a measurable improvement on the simple rule."
          : "So on this market the model is no better than the simple rule, and the page says so rather than quote the headline figure."
      }${
        best
          ? ` The strongest total is ${best.label.toLowerCase()}, at ${pct(best.accuracy)} against ${pct(best.baseline)}.`
          : ""
      } These are measured on matches the model was not trained on; they are not a record of picks published in advance.`,
    });
  }

  faqs.push({
    q: `Are there ${label} predictions for today?`,
    a:
      data.upcoming.length > 0
        ? `Yes. The board on this page lists every ${label} match loaded for the day, grouped by ${sport === "tennis" ? "tournament" : "league"}, and you can step back or forward a few days. Each prediction says whether it was stored before the match or calculated afterwards. The newest result in the data is from ${shortDate(data.last_result_date)}.`
        : `Not at the moment. The data behind this page runs to ${shortDate(data.last_result_date)} and no upcoming matches are loaded, so there is no list of today's matches to price. Rather than show an empty board as if it were current, the page shows what the engine says about the latest matches on record, labelled as reconstructed.`,
  });

  faqs.push({
    q: `Where does the ${label} data come from?`,
    a: copy.source,
  });

  faqs.push({
    q: `Do the ${label} predictions come with a public record like the football ones?`,
    a: "It has started. Predictions for upcoming matches are stored before they begin and graded against the result, and the record section on this page counts them, apart from anything reconstructed afterwards. It is young, so the sample is small, and it is kept separate from the football record rather than blended with it. Until it is larger, the table of held-out results is the better guide to how each model performs.",
  });

  faqs.push({
    q: `Are ${label} predictions a guarantee?`,
    a: "No. A prediction is a probability: a side given 70% is expected to lose three times in ten. Nothing on this site is betting advice or a promise of winnings, and it never links to a bookmaker. You must be 18 or over to bet, and you should never stake money you cannot afford to lose.",
  });

  return faqs;
}
