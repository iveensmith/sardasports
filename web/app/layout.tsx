import type { Metadata } from "next";
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
  title: "UniquePredict | Calibrated sports predictions",
  description:
    "Football, basketball and tennis predictions from a model that reports its own confidence, and says so when it cannot price a market.",
};

// Ordered by what a visitor came for, not by what the product is proudest
// of. Matches first, then the two curated cuts of it, then the record — which
// is the argument for the rest and belongs where someone goes looking for it
// rather than where it can be mistaken for a headline claim.
const NAV = [
  { href: "/matches", label: "Matches" },
  { href: "/bankers", label: "Bankers" },
  { href: "/slip", label: "Slip builder" },
  { href: "/leagues", label: "Leagues" },
  { href: "/progress", label: "Track record" },
  { href: "/leaderboard", label: "Models" },
  { href: "/how-it-works", label: "How it works" },
];

// Runs before paint, outside React's tree, so the theme is correct on the
// very first frame — a script that ran after hydration would still show one
// frame of the wrong theme. Reads the stored choice, falling back to the
// system preference for a first-time visitor; a stored choice always wins
// over the system, since the toggle exists precisely to let someone
// override it.
const THEME_INIT_SCRIPT = `
(function () {
  try {
    var stored = localStorage.getItem("theme");
    var theme = stored === "light" || stored === "dark"
      ? stored
      : (window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark");
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
        <header className="sticky top-0 z-50 border-b border-[var(--color-line)] bg-[var(--color-base)]/85 backdrop-blur-md">
          <nav className="mx-auto w-full max-w-[1200px] px-4 sm:px-6 lg:px-10 flex h-16 items-center gap-8">
            <Link
              href="/"
              className="text-[17px] font-bold tracking-[-0.02em] whitespace-nowrap"
            >
              Unique<span className="text-[var(--color-gold)]">Predict</span>
            </Link>
            <div className="hidden flex-1 items-center gap-6 text-[14px] lg:flex">
              {NAV.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="text-[var(--color-text-dim)] transition-colors hover:text-[var(--color-text)]"
                >
                  {item.label}
                </Link>
              ))}
            </div>
            <div className="ml-auto flex items-center gap-3 lg:ml-0">
              <ThemeToggle />
              <MobileNav items={NAV} />
            </div>
          </nav>
        </header>

        <main>{children}</main>

        <SiteFooter />
      </body>
    </html>
  );
}
