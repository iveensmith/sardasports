import type { Metadata } from "next";
import { Archivo } from "next/font/google";
import Link from "next/link";
import "./globals.css";

/*
  One family, doing both jobs. Archivo is a grotesque with real tabular
  figures and a wide weight range, which is what this product needs: nearly
  every piece of content here is a number set beside another number.
  Deliberately not Inter — it is the default any generated page reaches for,
  and it would make this read as templated regardless of the palette.
*/
const archivo = Archivo({
  subsets: ["latin"],
  variable: "--font-archivo",
  display: "swap",
  // No `weight` array on purpose: listing weights loads *static* instances,
  // and the body then snaps 420 down to 400. Omitting it loads Archivo's
  // variable axis, so intermediate weights are real rather than rounded.
  axes: [],
});

export const metadata: Metadata = {
  title: "UniquePredict — calibrated sports predictions",
  description:
    "Football, basketball and tennis predictions from a model that reports its own confidence, and says so when it cannot price a market.",
};

const NAV = [
  { href: "/predictions", label: "Today" },
  { href: "/matches", label: "Matches" },
  { href: "/leaderboard", label: "Leaderboard" },
  { href: "/analytics", label: "Model" },
];

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={archivo.variable}>
      <body className="min-h-dvh antialiased">
        <header className="sticky top-0 z-50 border-b border-[var(--color-line)] bg-[var(--color-base)]/85 backdrop-blur-md">
          <nav className="mx-auto flex h-16 max-w-6xl items-center gap-8 px-4">
            <Link
              href="/"
              className="text-[17px] font-bold tracking-[-0.02em] whitespace-nowrap"
            >
              Unique<span className="text-[var(--color-gold)]">Predict</span>
            </Link>
            <div className="flex items-center gap-6 text-[14px]">
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
          </nav>
        </header>

        <main>{children}</main>

        <footer className="mt-24 border-t border-[var(--color-line)]">
          <div className="mx-auto max-w-6xl px-4 py-10 text-[13px] leading-relaxed text-[var(--color-text-faint)]">
            <p className="max-w-[68ch]">
              Every number on this site is computed by the prediction engine
              from ingested match data. Where a market cannot be priced, it is
              shown as unavailable rather than estimated. Predictions describe
              probability, not certainty.
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}
