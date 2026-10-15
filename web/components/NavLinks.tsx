"use client";

/**
 * The header's desktop links, with the page you are on marked.
 *
 * The current section is a solid yellow pill, as in the banner's navigation: the
 * one place on the page that says where you are. A section counts as current for
 * its own address and anything beneath it (`/leagues/premier-league` keeps
 * "Leagues" lit), and "Home" only for the front page itself so it is not lit
 * everywhere.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";

export interface NavItem {
  href: string;
  label: string;
  /** Hidden below the widest breakpoint, where the row runs out of room. */
  wideOnly?: boolean;
  /** Hidden between lg and xl, where the account controls take the room. */
  xlOnly?: boolean;
}

function isCurrent(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function NavLinks({ items }: { items: NavItem[] }) {
  const pathname = usePathname() ?? "/";
  return (
    <div className="hidden flex-1 items-center gap-1 text-[13.5px] lg:flex">
      {items.map((item) => {
        const current = isCurrent(pathname, item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={current ? "page" : undefined}
            className={`rounded-md px-2.5 py-2 font-semibold whitespace-nowrap transition-colors ${
              item.wideOnly
                ? "hidden min-[1680px]:block"
                : item.xlOnly
                  ? "hidden xl:block"
                  : ""
            } ${
              current
                ? "bg-[var(--color-gold)] text-[var(--color-ink-on-accent)]"
                : "text-[var(--color-text-dim)] hover:bg-[var(--color-surface-raised)] hover:text-[var(--color-text)]"
            }`}
          >
            {item.label}
          </Link>
        );
      })}
    </div>
  );
}
