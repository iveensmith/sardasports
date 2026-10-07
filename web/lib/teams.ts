/**
 * A team's own page: form, recent results, what is next, and its table.
 *
 * Everything is read from matches on record. There is no squad, no player list
 * and no market value, because none of those are ingested — see
 * `app/services/team_page_service.py`.
 */

import type { Badge } from "./board";
import type { SeasonStats, TeamFormSummary } from "./types";

export type FormLetter = "W" | "D" | "L";

export interface TeamRecentMatch {
  match_id: number;
  slug: string;
  match_date: string;
  competition: string;
  home_team: string;
  away_team: string;
  home_score: number | null;
  away_score: number | null;
  is_home: boolean;
  result: FormLetter | null;
}

export interface TeamUpcoming {
  match_id: number;
  slug: string;
  match_date: string;
  competition: string;
  short_name: string;
  home_team: string;
  away_team: string;
  is_home: boolean;
}

export interface TeamStanding {
  competition: string;
  short_name: string;
  /** The competition's own page, under /leagues. */
  slug: string;
  season: string | null;
  position: number;
  of: number;
  row: {
    team: string;
    played: number;
    won: number;
    drawn: number;
    lost: number;
    goals_for: number;
    goals_against: number;
    goal_difference: number;
    points: number;
  };
}

export interface TeamPageData {
  team: {
    id: number;
    name: string;
    slug: string;
    elo_rating: number;
    badge: Badge;
    country: string | null;
    /** A national side, whose "country" is only its competition's. */
    is_national: boolean;
  };
  /** Days since the newest result on record. Null with no results at all. */
  last_match_age_days: number | null;
  /** Newest first. */
  form_letters: FormLetter[];
  form_last5: TeamFormSummary;
  form_last10: TeamFormSummary;
  season_stats: SeasonStats | null;
  recent_matches: TeamRecentMatch[];
  upcoming: TeamUpcoming[];
  /** Null for a national side, or any team with no tiered league on record. */
  standing: TeamStanding | null;
}

/**
 * "Bayern München" -> "bayern-munchen".
 *
 * Mirrors `slugify` in app/services/board_service.py: accents are folded, not
 * stripped, and anything non-alphanumeric collapses to one hyphen. If the two
 * disagree, a team link the site builds stops opening.
 */
export function teamSlug(name: string): string {
  return name
    .normalize("NFKD")
    .replace(/[^\x00-\x7f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
}
