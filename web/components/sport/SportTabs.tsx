"use client";

/**
 * The sport switcher under the main nav: Football, Basketball, Tennis.
 *
 * It is on every page so the other sports are one tap away from anywhere, which is
 * the point of it: before this the only way to find basketball or tennis was to
 * already know the address. Football is the default, so it is active everywhere
 * that is not a basketball or tennis page.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSportOverride } from "@/components/sport/ActiveSport";
import { SportMark } from "@/components/sport/SportMark";
import { SPORT_LABELS, SPORT_PATHS, type SportKey } from "@/lib/sports";

const ORDER: SportKey[] = ["football", "basketball", "tennis"];

function activeSport(pathname: string): SportKey {
  if (pathname === "/basketball" || pathname.startsWith("/basketball/")) {
    return "basketball";
  }
  if (pathname === "/tennis" || pathname.startsWith("/tennis/")) {
    return "tennis";
  }
  return "football";
}

export function SportTabs() {
  const claimed = useSportOverride();
  const pathname = usePathname() ?? "/";
  const current = claimed ?? activeSport(pathname);
  return (
    <nav aria-label="Sports" className="border-t border-[var(--color-line)]">
      <ul className="mx-auto flex h-10 w-full max-w-[1200px] items-center gap-1 px-3 min-[400px]:gap-1.5 min-[400px]:px-4 sm:px-6 lg:px-10">
        {ORDER.map((sport) => {
          const active = sport === current;
          return (
            <li key={sport}>
              <Link
                href={SPORT_PATHS[sport]}
                aria-current={active ? "page" : undefined}
                className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[13px] min-[400px]:gap-2 min-[400px]:px-3.5 font-medium transition-colors ${
                  active
                    ? "bg-[var(--color-gold)] text-[var(--color-ink-on-accent)]"
                    : "text-[var(--color-text-dim)] hover:bg-[var(--color-surface)] hover:text-[var(--color-text)]"
                }`}
              >
                <SportMark sport={sport} size={14} />
                {SPORT_LABELS[sport]}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
