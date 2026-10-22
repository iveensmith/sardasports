/**
 * Types for the blog and the editor's picks, as the engine returns them.
 */

export interface Post {
  id: number;
  slug: string;
  title: string;
  excerpt: string;
  /** Empty when `locked`. */
  body: string;
  /** `html` is sanitised on the engine and shown as stored; `markdown` is the older format. */
  body_format: "html" | "markdown";
  category: string | null;
  tags: string[];
  /** The public address of the featured image (`/media/<name>`), if there is one. */
  featured_image: string | null;
  locked: boolean;
  premium_only: boolean;
  status: "draft" | "published";
  created_at: string | null;
  updated_at: string | null;
  published_at: string | null;
}

export interface EditorPick {
  id: number;
  sport: "football" | "basketball" | "tennis";
  competition: string;
  home_team: string;
  away_team: string;
  /** ISO timestamp, UTC (no zone marker). */
  kickoff: string;
  /** Null while `locked`. */
  market: string | null;
  selection: string | null;
  odds: number | null;
  confidence: number | null;
  rationale: string | null;
  premium_only: boolean;
  status: "draft" | "published";
  result: "pending" | "won" | "lost" | "void";
  void_reason: string | null;
  published_at: string | null;
  settled_at: string | null;
  locked: boolean;
}

export interface PicksRecord {
  published: number;
  won: number;
  lost: number;
  void: number;
  pending: number;
  settled: number;
  win_rate: number | null;
}

export interface PlanView {
  code: string;
  name: string;
  description: string;
  price_minor: number;
  currency: string;
  interval: "week" | "month" | "year";
  active: boolean;
}

/** "£9.99" / "₦5,000" from an amount in the smallest unit. */
export function money(minor: number, currency: string): string {
  try {
    // US dollars read as "$10.99" in the US style; in the UK style they read "US$10.99".
    return new Intl.NumberFormat(currency === "USD" ? "en-US" : "en-GB", {
      style: "currency",
      currency,
      maximumFractionDigits: minor % 100 === 0 ? 0 : 2,
    }).format(minor / 100);
  } catch {
    return `${(minor / 100).toFixed(2)} ${currency}`;
  }
}
