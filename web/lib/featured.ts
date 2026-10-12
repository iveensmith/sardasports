/**
 * Which picks the home page puts up front.
 *
 * Chosen by the one thing that can be compared across sports: how likely the engine
 * says the pick is. Football takes two cards (from different competitions, so the
 * row is not two matches from one league), and basketball and tennis one each. A
 * sport with nothing priced and still to play simply has no card: the row is shorter,
 * it is never filled with a made-up fixture.
 *
 * Only matches that have not been played are considered, so a card never shows a
 * result as a pick.
 */

import type { Badge, BoardRow, DayBoard } from "@/lib/board";
import { allRows } from "@/lib/board";
import { matchPath } from "@/lib/seo";
import type { SportBoard } from "@/lib/sports";

export interface FeaturedCard {
  sport: "football" | "basketball" | "tennis";
  /** "Premier League", "NBA", "ATP Tour". */
  competition: string;
  countryCode: string | null;
  home: string;
  away: string;
  homeBadge: Badge;
  awayBadge: Badge;
  /** ISO timestamp, UTC. */
  kickoff: string;
  /** What is being picked, in words: "Home or draw", "Lakers to win". */
  tip: string;
  /** Null where no price exists (basketball and tennis have no odds feed). */
  odds: number | null;
  oddsEstimated: boolean;
  /** Percent. */
  probability: number;
  href: string;
}

function initials(name: string): string {
  const words = name.replace(/[.\-]/g, " ").split(/\s+/).filter(Boolean);
  if (words.length >= 2) return (words[0][0] + words[1][0]).toUpperCase();
  return (words[0] ?? "?").slice(0, 2).toUpperCase();
}

function monogram(name: string): Badge {
  return { kind: "monogram", code: null, initials: initials(name), logo: null };
}

function footballCards(boards: Array<DayBoard | null>, take: number): FeaturedCard[] {
  const seen = new Set<string>();
  const candidates: BoardRow[] = [];
  for (const board of boards) {
    if (!board) continue;
    for (const row of allRows(board)) {
      if (row.score || row.live || !row.best_tip) continue;
      candidates.push(row);
    }
    // Today first: tomorrow only fills what today could not.
    if (candidates.length >= take * 3) break;
  }
  candidates.sort(
    (a, b) => (b.best_tip?.probability ?? 0) - (a.best_tip?.probability ?? 0),
  );
  const cards: FeaturedCard[] = [];
  for (const row of candidates) {
    if (cards.length >= take) break;
    if (seen.has(row.competition.name)) continue;
    seen.add(row.competition.name);
    const tip = row.best_tip!;
    cards.push({
      sport: "football",
      competition: row.competition.short_name || row.competition.name,
      countryCode: row.competition.country_code,
      home: row.home_team,
      away: row.away_team,
      homeBadge: row.home_badge ?? monogram(row.home_team),
      awayBadge: row.away_badge ?? monogram(row.away_team),
      kickoff: row.match_date,
      tip: tip.label,
      odds: tip.odds,
      oddsEstimated: tip.odds_is_estimated,
      probability: tip.probability,
      href: `/match/${row.slug}`,
    });
  }
  return cards;
}

function sportCard(
  sport: "basketball" | "tennis",
  boards: Array<SportBoard | null>,
): FeaturedCard | null {
  let best: FeaturedCard | null = null;
  for (const board of boards) {
    if (!board) continue;
    for (const competition of board.competitions) {
      for (const match of competition.matches) {
        if (
          !match.pick ||
          match.status === "completed" ||
          match.in_play ||
          match.overdue
        ) {
          continue;
        }
        if (best && match.pick.probability <= best.probability) continue;
        best = {
          sport,
          competition:
            sport === "tennis" && competition.tour
              ? `${competition.tour} · ${competition.name}`
              : competition.name,
          countryCode: competition.country_code,
          home: match.home,
          away: match.away,
          homeBadge: monogram(match.home),
          awayBadge: monogram(match.away),
          kickoff: match.kickoff,
          tip: `${match.pick.name} to win`,
          odds: null,
          oddsEstimated: false,
          probability: match.pick.probability,
          href: matchPath(match.home, match.away, match.match_id),
        };
      }
    }
    // Today's best is enough; tomorrow is only consulted when today had nothing.
    if (best) break;
  }
  return best;
}

export function pickFeatured(input: {
  footballToday: DayBoard | null;
  footballTomorrow: DayBoard | null;
  basketball: Array<SportBoard | null>;
  tennis: Array<SportBoard | null>;
}): FeaturedCard[] {
  const football = footballCards(
    [input.footballToday, input.footballTomorrow],
    2,
  );
  const basketball = sportCard("basketball", input.basketball);
  const tennis = sportCard("tennis", input.tennis);
  // Reading order: football, basketball, tennis, then football's second pick.
  return [football[0], basketball, tennis, football[1]].filter(
    (card): card is FeaturedCard => Boolean(card),
  );
}
