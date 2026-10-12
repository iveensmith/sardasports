import type { Metadata } from "next";
import { JsonLd } from "@/components/seo/JsonLd";
import { Logo } from "@/components/Logo";
import { NavLinks } from "@/components/NavLinks";
import { SportTabs } from "@/components/sport/SportTabs";
import { organizationLd, websiteLd } from "@/lib/seo";
import { IS_LIVE_SITE, SITE_NAME, SITE_URL } from "@/lib/site";
import { Red_Hat_Display, Red_Hat_Text } from "next/font/google";
import Link from "next/link";
import "./globals.css";
import { ThemeToggle } from "@/components/ThemeToggle";
import { MobileNav } from "@/components/MobileNav";
import { SiteFooter } from "@/components/SiteFooter";

/*
  Replaces Schibsted Grotesk, which turned out to have a broken comma/period
  glyph in its Google Fonts build — visible extra space before every comma
  and full stop, site-wide, confirmed in isolation outside this codebase too
  (a plain test page, several weights, the static and variable instances all
  showed it). Not fixable from here, so a different face, not a config
  change.

  Red Hat Display/Text is an actual display+text pair, not one family
  stretched over both jobs — Red Hat built it for exactly this kind of
  product: dense technical interfaces where numbers are compared against
  each other constantly. Display carries the hero numbers and headlines at
  real weight (its variable axis runs to 900); Text is the workhorse for
  body copy, labels and table cells, with the same tabular figures this
  product already depends on. Deliberately not Inter (the default any
  generated page reaches for) and not Geist (now the default
  `create-next-app` ships, which makes it the new Inter).
*/
const redHatDisplay = Red_Hat_Display({
  subsets: ["latin"],
  variable: "--font-red-hat-display",
  display: "swap",
  // No `weight` array — loads the full variable axis instead of rounding
  // off to static instances.
});
const redHatText = Red_Hat_Text({
  subsets: ["latin"],
  variable: "--font-red-hat-text",
  display: "swap",
});

export const metadata: Metadata = {
  // Every canonical URL and share link on the site resolves against this.
  metadataBase: new URL(SITE_URL),
  title: {
    default: "Best AI Prediction Site: Football, Basketball & Tennis",
    template: `%s | ${SITE_NAME}`,
  },
  description:
    "SARDASPORTS, the best AI prediction site for football: free predictions for today's matches, every pick graded against the final score in public. Basketball and tennis predictions too.",
  applicationName: SITE_NAME,
  category: "sports",
  // Not a ranking factor for Google, which ignores it; kept for the engines
  // that still read it. The words that rank are in titles, headings and copy.
  keywords: [
    // The main phrases
    "football predictions",
    "football predictions today",
    "football prediction site",
    "AI football predictions",
    "AI prediction site",
    "free football predictions",
    "football betting tips",
    "football tips today",
    "soccer predictions",
    // The comparison searches: people looking for the "best" site want criteria
    "best AI prediction site",
    "best football prediction site",
    "best prediction site",
    "most accurate football predictions",
    "football prediction accuracy",
    "football prediction track record",
    // The markets
    "over 2.5 goals predictions",
    "both teams to score predictions",
    "BTTS predictions",
    "correct score predictions",
    "banker tips today",
    "accumulator builder",
    "bet slip generator",
    // The other sports
    "basketball predictions",
    "NBA predictions",
    "tennis predictions",
    "ATP predictions",
    "WTA predictions",
    "AI tennis predictions",
    "AI basketball predictions",
  ],
  openGraph: {
    type: "website",
    siteName: SITE_NAME,
    locale: "en_GB",
    url: "/",
    title: "Best AI Prediction Site: Football, Basketball & Tennis",
    description:
      "The best AI prediction site for football: free predictions for today's matches, with every pick graded against the final score on a public record. Plus basketball and tennis.",
  },
  twitter: { card: "summary_large_image" },
  // Until a real public address is configured this is a local or staging copy
  // and must not be indexed. See lib/site.ts.
  robots: IS_LIVE_SITE
    ? { index: true, follow: true }
    : { index: false, follow: false },
};

// Ordered by what a visitor came for, not by what the product is proudest
// of. Matches first, then the two curated cuts of it, then the record — which
// is the argument for the rest and belongs where someone goes looking for it
// rather than where it can be mistaken for a headline claim.
const NAV = [
  { href: "/", label: "Home" },
  { href: "/matches", label: "Predictions" },
  { href: "/live", label: "Live" },
  { href: "/bankers", label: "Bankers" },
  { href: "/slip", label: "Slip builder" },
  { href: "/leagues", label: "Leagues" },
  { href: "/progress", label: "Track record" },
  { href: "/leaderboard", label: "Models", wideOnly: true },
  { href: "/how-it-works", label: "How it works", wideOnly: true },
  { href: "/contact", label: "Contact" },
];

// Runs before paint, outside React's tree, so the theme is correct on the
// very first frame — a script that ran after hydration would still show one
// frame of the wrong theme. Reads the stored choice; a first-time visitor gets
// the dark theme whatever their system prefers, because dark is the brand's own
// look (black and yellow) and the toggle is there for anyone who wants paper.
// A stored choice always wins.
const THEME_INIT_SCRIPT = `
(function () {
  try {
    var stored = localStorage.getItem("theme");
    var theme = stored === "light" ? "light" : "dark";
    if (theme === "light") {
      document.documentElement.setAttribute("data-theme", "light");
    }
  } catch (e) {}
})();
`;

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      className={`${redHatDisplay.variable} ${redHatText.variable}`}
      suppressHydrationWarning
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
      </head>
      <body className="min-h-dvh antialiased">
        <JsonLd data={[organizationLd(), websiteLd()]} />
        <header className="sticky top-0 z-50 border-b border-[var(--color-line)] bg-[var(--color-base)]/85 backdrop-blur-md">
          <nav className="mx-auto w-full max-w-[1200px] px-4 sm:px-6 lg:px-10 flex h-16 items-center gap-4 lg:gap-8">
            <Link href="/" className="shrink-0" aria-label={SITE_NAME}>
              <Logo priority />
            </Link>
            <NavLinks items={NAV} />
            <div className="ml-auto flex items-center gap-3 lg:ml-0">
              <ThemeToggle />
              <Link
                href="/matches"
                className="hidden rounded-md bg-[var(--color-gold)] px-4 py-2.5 text-[12.5px] font-extrabold tracking-[0.04em] whitespace-nowrap text-[var(--color-ink-on-accent)] uppercase transition-colors hover:bg-[var(--color-gold-bright)] active:scale-[0.97] xl:inline-flex"
              >
                Today&rsquo;s picks
              </Link>
              <MobileNav items={NAV} />
            </div>
          </nav>
          <SportTabs />
        </header>

        <main>{children}</main>

        <SiteFooter />
      </body>
    </html>
  );
}
