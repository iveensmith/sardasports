/**
 * The one page container.
 *
 * Every page, the nav and the footer share this, which is the whole point.
 * Before it there were three widths in use — `max-w-5xl` on the slip builder,
 * `max-w-6xl` on most pages and the nav, `max-w-7xl` on the home page and the
 * board — so the content jumped width as you moved between pages and never
 * lined up with the nav above it. On a 1280px screen the widest of those is
 * 1280px, which meant `max-w-7xl` did nothing at all and the only thing
 * holding text off the edge of the glass was `px-4`: sixteen pixels.
 *
 * So: one measurement, defined here, and nothing else sets a page width.
 *
 * 1200px is chosen for the board rather than for prose. The fixtures table
 * carries ten columns — time, fixture, three prices, three market picks, best
 * tip, confidence — and narrowing the page to a comfortable reading measure
 * would squeeze them until the numbers ran together. Prose is kept readable
 * the other way round, with `max-w-[70ch]` on the paragraphs themselves, so a
 * wide container costs nothing on a text-heavy page.
 *
 * The gutter grows with the viewport instead of staying at 16px, because a
 * fixed gutter is either cramped on a laptop or pointless on a monitor.
 */

import type { ReactNode } from "react";

/** Matches the nav and footer. Nothing else should set a page width. */
export const CONTAINER = "mx-auto w-full max-w-[1200px] px-4 sm:px-6 lg:px-10";

export function Container({
  children,
  className = "",
  as: Tag = "div",
}: {
  children: ReactNode;
  className?: string;
  /** `main`, `header`, `section` where the landmark matters. */
  as?: "div" | "main" | "header" | "section";
}) {
  return <Tag className={`${CONTAINER} ${className}`.trim()}>{children}</Tag>;
}
