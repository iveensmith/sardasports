/**
 * The five promises under the banner, each with its icon.
 *
 * Every line says something the site actually does, and the same claims are made at
 * length further down the page (the record, the markets, the live scores), so none of
 * these is a slogan that the rest of the page has to quietly live up to.
 */

import Link from "next/link";
import {
  BarsUp,
  Medal,
  Pulse,
  ShieldCheck,
  Target,
} from "@/components/home/icons";

const ITEMS = [
  {
    icon: Target,
    title: "Calibrated predictions",
    text: "Probabilities checked against results",
    href: "/how-it-works",
  },
  {
    icon: BarsUp,
    title: "In-depth analysis",
    text: "Seven markets for every match",
    href: "/matches",
  },
  {
    icon: Pulse,
    title: "Live scores",
    text: "Football, updated through the day",
    href: "/matches",
  },
  {
    icon: Medal,
    title: "Proven results",
    text: "Every pick graded, win or lose",
    href: "/progress",
  },
  {
    icon: ShieldCheck,
    title: "Free to use",
    text: "No account, no sign-up",
    href: "/about",
  },
];

export function FeatureStrip() {
  return (
    <section
      aria-label="What you get"
      className="border-b border-[var(--color-line)] bg-[var(--color-surface)]"
    >
      <ul className="mx-auto grid w-full max-w-[1200px] grid-cols-2 px-4 sm:px-6 lg:grid-cols-5 lg:px-10">
        {ITEMS.map((item, index) => (
          <li
            key={item.title}
            className={`border-[var(--color-line)] ${
              index > 0 ? "lg:border-l" : ""
            } ${index === ITEMS.length - 1 ? "col-span-2 lg:col-span-1" : ""} ${
              index % 2 === 1 ? "border-l lg:border-l" : ""
            }`}
          >
            <Link
              href={item.href}
              className="group flex items-center gap-3.5 px-3 py-5 transition-colors hover:bg-[var(--color-surface-raised)] lg:px-5"
            >
              <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-[var(--color-gold)]/40 text-[var(--color-gold-bright)] transition-colors group-hover:border-[var(--color-gold)]">
                <item.icon size={22} />
              </span>
              <span className="min-w-0">
                <span className="block text-[14px] leading-tight font-bold">
                  {item.title}
                </span>
                <span className="mt-0.5 block text-[12.5px] leading-snug text-[var(--color-text-dim)]">
                  {item.text}
                </span>
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
