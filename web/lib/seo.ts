/**
 * Page metadata and structured data, built in one place.
 *
 * Every page asks for its title, description and address here instead of
 * hand-writing a metadata object, so canonical URLs, social-share cards and the
 * staging safeguard (see `lib/site.ts`) are identical everywhere and a new page
 * cannot forget one.
 *
 * Titles name what the page is about in the words people search for, and stay
 * short enough to show whole in a result (around 60 characters including the
 * brand). Descriptions say what the visitor will find, in plain terms, inside
 * about 155 characters. Neither claims accuracy, wins or "sure" anything: the
 * site's argument is that every pick is graded in public, and a claim it cannot
 * back would be both untrue and, for a gambling-adjacent site, a quick way to be
 * treated as spam.
 *
 * Structured data describes only what is on the page. A FAQ block marks up the
 * questions the page actually shows, a breadcrumb the trail the visitor could
 * follow, and so on; markup for content that is not visible is the other way to
 * be treated as spam.
 */

import type { Metadata } from "next";
import { teamSlug } from "@/lib/teams";
import { absoluteUrl, IS_LIVE_SITE, SITE_NAME } from "@/lib/site";

const SHARE_IMAGE = {
  url: "/opengraph-image",
  width: 1200,
  height: 630,
  alt: `${SITE_NAME}: football predictions, every one graded`,
};

/** Search results cut a title at roughly 60 characters and a description at 155. */
const TITLE_BUDGET = 62;
const DESCRIPTION_BUDGET = 155;

/** Trim to a word boundary, with an ellipsis, rather than let a result cut it mid-word. */
function fit(text: string, budget: number): string {
  if (text.length <= budget) return text;
  const cut = text.slice(0, budget - 1);
  return `${cut.slice(0, cut.lastIndexOf(" ")).replace(/[,;:\s]+$/, "")}…`;
}

export function pageMetadata({
  title,
  description,
  path,
  absoluteTitle = false,
  noindex = false,
}: {
  title: string;
  description: string;
  /** The page's own path, e.g. "/bankers" or "/leagues/english-premier-league". */
  path: string;
  /** Use the title as written, without appending the brand. */
  absoluteTitle?: boolean;
  noindex?: boolean;
}): Metadata {
  const branded = `${title} | ${SITE_NAME}`;
  // A long title (two long team names, say) drops the brand rather than be cut
  // off: the words people searched for matter more than the site name.
  const useBrand = !absoluteTitle && branded.length <= TITLE_BUDGET;
  const full = useBrand ? branded : title;
  const summary = fit(description, DESCRIPTION_BUDGET);
  return {
    title: useBrand ? title : { absolute: title },
    description: summary,
    alternates: { canonical: path },
    openGraph: {
      type: "website",
      title: full,
      description: summary,
      url: path,
      siteName: SITE_NAME,
      locale: "en_GB",
      images: [SHARE_IMAGE],
    },
    twitter: {
      card: "summary_large_image",
      title: full,
      description: summary,
      images: [SHARE_IMAGE.url],
    },
    // Left unset on indexable pages so the site-wide rule in the root layout
    // (noindex until a real address is configured) is what applies.
    ...(noindex ? { robots: { index: false, follow: true } } : {}),
  };
}

/**
 * The one readable address for a fixture, whichever of /match/144414 or the long
 * form a visitor arrived on. Mirrors `match_slug` in app/services/board_service.py,
 * so the canonical is the same URL the boards link to.
 */
export function matchPath(home: string, away: string, id: number): string {
  return `/match/${teamSlug(home)}-vs-${teamSlug(away)}-prediction-${id}`;
}

// --- structured data -------------------------------------------------------

type JsonLdNode = Record<string, unknown>;

export function organizationLd(): JsonLdNode {
  return {
    "@context": "https://schema.org",
    "@type": "Organization",
    "@id": absoluteUrl("/#organization"),
    name: SITE_NAME,
    url: absoluteUrl("/"),
    description:
      "A football prediction engine that grades every pick against the final score and publishes the full record, wins and losses.",
  };
}

export function websiteLd(): JsonLdNode {
  return {
    "@context": "https://schema.org",
    "@type": "WebSite",
    "@id": absoluteUrl("/#website"),
    name: SITE_NAME,
    url: absoluteUrl("/"),
    inLanguage: "en",
    publisher: { "@id": absoluteUrl("/#organization") },
  };
}

export function faqLd(items: Array<{ q: string; a: string }>): JsonLdNode {
  return {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: items.map((item) => ({
      "@type": "Question",
      name: item.q,
      acceptedAnswer: { "@type": "Answer", text: item.a },
    })),
  };
}

export function breadcrumbLd(
  trail: Array<{ name: string; path: string }>,
): JsonLdNode {
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: trail.map((crumb, index) => ({
      "@type": "ListItem",
      position: index + 1,
      name: crumb.name,
      item: absoluteUrl(crumb.path),
    })),
  };
}

/**
 * A fixture. Only facts the site holds: the two sides, the kick-off, the
 * competition and whether it has been played. No venue, because none is stored,
 * and no prediction, because a forecast is not an attribute of the event.
 */
export function sportsEventLd(event: {
  name: string;
  path: string;
  startDate: string;
  homeTeam: string;
  awayTeam: string;
  competition: string;
  played: boolean;
}): JsonLdNode {
  return {
    "@context": "https://schema.org",
    "@type": "SportsEvent",
    name: event.name,
    url: absoluteUrl(event.path),
    startDate: event.startDate,
    sport: "Association football",
    eventStatus: event.played
      ? "https://schema.org/EventCompleted"
      : "https://schema.org/EventScheduled",
    homeTeam: { "@type": "SportsTeam", name: event.homeTeam },
    awayTeam: { "@type": "SportsTeam", name: event.awayTeam },
    superEvent: { "@type": "SportsEvent", name: event.competition },
  };
}

/** The public track record as a downloadable dataset, which Google Dataset
 * Search can list. Describes the two CSV files the site really serves. */
export function recordDatasetLd(): JsonLdNode {
  return {
    "@context": "https://schema.org",
    "@type": "Dataset",
    name: `${SITE_NAME} graded football predictions`,
    description:
      "Every prediction the engine has made, graded against the final score as won, lost or void, with the competition, both teams and whether the pick was stored before kick-off or reconstructed afterwards. Includes a daily summary.",
    url: absoluteUrl("/progress"),
    isAccessibleForFree: true,
    creator: { "@id": absoluteUrl("/#organization") },
    keywords: [
      "football predictions",
      "prediction accuracy",
      "graded predictions",
      "betting tips record",
    ],
    distribution: [
      {
        "@type": "DataDownload",
        name: "Graded matches",
        encodingFormat: "text/csv",
        contentUrl: absoluteUrl("/progress/matches.csv"),
      },
      {
        "@type": "DataDownload",
        name: "Daily record",
        encodingFormat: "text/csv",
        contentUrl: absoluteUrl("/progress/daily.csv"),
      },
    ],
  };
}
