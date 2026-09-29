/**
 * The date strip: a few days back and forward.
 *
 * Backwards matters more than forwards. Yesterday's card is where the picks
 * are already settled, so it is the only page a reader can use to decide
 * whether to believe today's — and it is the page prediction sites most
 * often quietly omit.
 *
 * Days with no fixtures are shown disabled rather than hidden, so the strip
 * keeps a stable shape and nobody clicks through to an empty page.
 */

import Link from "next/link";
import type { BoardDay } from "@/lib/board";

export function DateStrip({
  days,
  active,
  basePath = "/matches",
}: {
  days: BoardDay[];
  active: string;
  basePath?: string;
}) {
  return (
    <nav
      aria-label="Choose a day"
      className="flex flex-wrap items-center justify-center gap-1"
    >
      {days.map((day) => {
        const isActive = day.date === active;
        const empty = day.fixtures === 0;
        const className =
          "rounded-[var(--radius-md)] px-3 py-1.5 text-[13px] transition-colors";

        if (empty && !isActive) {
          return (
            <span
              key={day.date}
              aria-disabled
              title="No fixtures on this day"
              className={`${className} text-[var(--color-unknown)]`}
            >
              {day.label}
            </span>
          );
        }

        return (
          <Link
            key={day.date}
            href={`${basePath}?date=${day.date}`}
            aria-current={isActive ? "date" : undefined}
            className={className}
            style={
              isActive
                ? { background: "var(--color-gold)", color: "#131313", fontWeight: 600 }
                : { color: "var(--color-text-dim)" }
            }
          >
            {day.label}
            {!isActive && day.fixtures > 0 && (
              <span className="ml-1.5 text-[11px] text-[var(--color-text-faint)]">
                {day.fixtures}
              </span>
            )}
          </Link>
        );
      })}
    </nav>
  );
}
