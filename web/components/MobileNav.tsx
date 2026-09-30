"use client";

/**
 * The nav, collapsed for a phone-width header.
 *
 * Six links plus the theme toggle never fit a phone's width beside the
 * wordmark — the previous header just let them wrap, which pushed the
 * theme toggle and half the links off the visible edge instead of onto a
 * second line anyone could see. A hamburger is the plain, expected answer
 * at this width; the desktop row stays exactly as it was above the
 * breakpoint (see layout.tsx).
 *
 * Full-width overlay rather than a corner dropdown: a phone screen is
 * narrow enough that a small anchored panel and a full-width sheet cost
 * about the same tap-target the reader has to reconsider a menu, so the
 * simpler markup wins.
 */

import Link from "next/link";
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

function MenuIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      width={20}
      height={20}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      aria-hidden
    >
      <path d="M3.5 6.5h17M3.5 12h17M3.5 17.5h17" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      width={20}
      height={20}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      aria-hidden
    >
      <path d="M5 5l14 14M19 5L5 19" />
    </svg>
  );
}

export function MobileNav({
  items,
}: {
  items: { href: string; label: string }[];
}) {
  const [open, setOpen] = useState(false);
  // A portal target isn't available during SSR or the first client render
  // (no document yet in one case, and matching the server markup in the
  // other), so the panel itself waits one tick rather than risk rendering
  // into `document.body` before hydration settles.
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setMounted(true);
  }, []);

  // Closing on route change (a link tap) rather than requiring a second tap
  // on the link itself — Link already navigates on the same tap that should
  // dismiss the sheet.
  useEffect(() => {
    if (!open) return;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  const panel = open && mounted && (
    <div
      // Portaled to <body> rather than left where the button lives: the
      // header has `backdrop-blur-md`, and a `backdrop-filter` on an
      // ancestor makes it the containing block for any `position: fixed`
      // descendant — this panel's top/bottom would resolve against the
      // header's own 64px box instead of the viewport, collapsing it to
      // zero height. Escaping to `document.body` sidesteps that entirely.
      className="fixed inset-x-0 top-16 bottom-0 z-40 overflow-y-auto bg-[var(--color-base)]"
      role="dialog"
      aria-modal="true"
    >
      <nav className="flex flex-col px-4 py-2 sm:px-6">
        {items.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            onClick={() => setOpen(false)}
            className="border-b border-[var(--color-line)] py-4 text-[16px] text-[var(--color-text)]"
          >
            {item.label}
          </Link>
        ))}
      </nav>
    </div>
  );

  return (
    <div className="lg:hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label={open ? "Close menu" : "Open menu"}
        aria-expanded={open}
        className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-[var(--color-line)] text-[var(--color-text-dim)] transition-colors hover:border-[var(--color-line-strong)] hover:text-[var(--color-text)]"
      >
        {open ? <CloseIcon /> : <MenuIcon />}
      </button>

      {mounted && panel && createPortal(panel, document.body)}
    </div>
  );
}
