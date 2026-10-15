/**
 * The sitemap: every page worth ranking, with a real last-modified date.
 *
 * Two parts. The fixed pages are listed here. The pages that come from data (one
 * per league, per active team, per recent match) come from the engine's
 * `/seo/urls`, which only lists pages with real content and dates each by its
 * own latest match. If the engine cannot be reached, the fixed pages are still
 * served rather than an empty sitemap, and the data pages return on the next
 * rebuild.
 *
 * Left out on purpose: the legacy prediction board and the model analytics view
 * (noindex), and date or country filter variants of the matches page, which are
 * the same content re-sliced.
 */

import type { MetadataRoute } from "next";
import { getSeoUrls } from "@/lib/api";
import type { Post } from "@/lib/content";
import { engineCall } from "@/lib/session";
import { absoluteUrl } from "@/lib/site";

// Rendered per request, not cached as a whole. The league, team and match lists
// are cached for an hour where they are fetched, so a normal request is cheap;
// but if the engine is briefly unreachable, the short fallback below is served
// for that one request and the next one retries. Caching the whole route would
// pin a stunted sitemap for an hour, and a sitemap that suddenly shrinks from
// a thousand pages to eleven reads to a crawler as the site losing its content.
export const dynamic = "force-dynamic";

type Entry = MetadataRoute.Sitemap[number];

const FIXED: Array<{
  path: string;
  changeFrequency: Entry["changeFrequency"];
  priority: number;
}> = [
  { path: "/", changeFrequency: "hourly", priority: 1 },
  { path: "/matches", changeFrequency: "hourly", priority: 0.9 },
  { path: "/bankers", changeFrequency: "hourly", priority: 0.8 },
  {
    path: "/over-2-5-goals-predictions-today",
    changeFrequency: "hourly",
    priority: 0.8,
  },
  {
    path: "/both-teams-to-score-predictions-today",
    changeFrequency: "hourly",
    priority: 0.8,
  },
  {
    path: "/correct-score-predictions-today",
    changeFrequency: "hourly",
    priority: 0.7,
  },
  { path: "/basketball", changeFrequency: "daily", priority: 0.7 },
  { path: "/tennis", changeFrequency: "daily", priority: 0.7 },
  { path: "/slip", changeFrequency: "daily", priority: 0.7 },
  { path: "/leagues", changeFrequency: "daily", priority: 0.7 },
  { path: "/progress", changeFrequency: "daily", priority: 0.7 },
  { path: "/how-it-works", changeFrequency: "monthly", priority: 0.5 },
  {
    path: "/best-football-prediction-site",
    changeFrequency: "monthly",
    priority: 0.7,
  },
  { path: "/blog", changeFrequency: "daily", priority: 0.6 },
  { path: "/picks", changeFrequency: "daily", priority: 0.6 },
  { path: "/premium", changeFrequency: "monthly", priority: 0.4 },
  { path: "/leaderboard", changeFrequency: "weekly", priority: 0.4 },
  { path: "/about", changeFrequency: "monthly", priority: 0.4 },
  { path: "/contact", changeFrequency: "yearly", priority: 0.3 },
  { path: "/privacy", changeFrequency: "yearly", priority: 0.2 },
  { path: "/terms", changeFrequency: "yearly", priority: 0.2 },
];

function dated(lastmod: string | null): Pick<Entry, "lastModified"> {
  return lastmod ? { lastModified: new Date(lastmod) } : {};
}

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const fixed: MetadataRoute.Sitemap = FIXED.map((page) => ({
    url: absoluteUrl(page.path),
    changeFrequency: page.changeFrequency,
    priority: page.priority,
  }));

  // Published posts, each dated by when it was published or last changed.
  const posts = await engineCall<{ posts: Post[] }>("/content/posts?limit=100");
  const postEntries: MetadataRoute.Sitemap = (posts.data?.posts ?? []).map(
    (post): Entry => ({
      url: absoluteUrl(`/blog/${post.slug}`),
      changeFrequency: "monthly",
      priority: 0.6,
      ...dated(post.updated_at ?? post.published_at),
    }),
  );

  let urls;
  try {
    urls = await getSeoUrls();
  } catch {
    return [...fixed, ...postEntries];
  }

  return [
    ...fixed,
    ...postEntries,
    ...urls.leagues.map((entry): Entry => ({
      url: absoluteUrl(`/leagues/${entry.slug}`),
      changeFrequency: "daily",
      priority: 0.8,
      ...dated(entry.lastmod),
    })),
    ...urls.teams.map((entry): Entry => ({
      url: absoluteUrl(`/teams/${entry.slug}`),
      changeFrequency: "daily",
      priority: 0.6,
      ...dated(entry.lastmod),
    })),
    ...urls.matches.map((entry): Entry => ({
      url: absoluteUrl(`/match/${entry.slug}`),
      changeFrequency: "daily",
      priority: 0.6,
      ...dated(entry.lastmod),
    })),
  ];
}
