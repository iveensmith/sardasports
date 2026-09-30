"use client";

/**
 * The light/dark switch.
 *
 * Dark is the site's default identity — the brief pins it, and the landing
 * hero stays dark regardless (see globals.css) — so this is an opt into
 * light, not a coin flip between two equal states. The choice persists in
 * localStorage and otherwise follows the system preference, read once by
 * the inline script in the root layout before paint so there is no flash
 * of the wrong theme on load.
 *
 * Sun and moon rather than a generic switch: the icon shown is the theme
 * a click would move *to*, matching how the reference site's own toggle
 * reads, so the control never asks a reader to infer which state they're
 * currently in.
 */

import { useEffect, useState } from "react";

function SunIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      width={16}
      height={16}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      aria-hidden
    >
      <circle cx="12" cy="12" r="4.2" />
      <path d="M12 2.5v2.4M12 19.1v2.4M4.9 4.9l1.7 1.7M17.4 17.4l1.7 1.7M2.5 12h2.4M19.1 12h2.4M4.9 19.1l1.7-1.7M17.4 6.6l1.7-1.7" />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      width={16}
      height={16}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M20 14.2A8.2 8.2 0 1 1 9.8 4a6.4 6.4 0 0 0 10.2 10.2Z" />
    </svg>
  );
}

export function ThemeToggle() {
  // Starts null so the server-rendered and first-client-render markup
  // match exactly (the real theme lives in a pre-hydration inline script
  // reading localStorage, which the server cannot see) — the icon fills in
  // a frame later rather than risk a hydration mismatch warning.
  const [theme, setTheme] = useState<"light" | "dark" | null>(null);

  useEffect(() => {
    // Reads a value the pre-hydration script already set on the real DOM,
    // not React state — there is no earlier render this could have run in.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setTheme(
      document.documentElement.getAttribute("data-theme") === "light"
        ? "light"
        : "dark",
    );
  }, []);

  function toggle() {
    const next = theme === "light" ? "dark" : "light";
    setTheme(next);
    document.documentElement.setAttribute("data-theme", next);
    try {
      localStorage.setItem("theme", next);
    } catch {
      // Private browsing or a blocked store — the toggle still works for
      // this page view, it just won't be remembered for the next one.
    }
  }

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={
        theme === "light" ? "Switch to dark theme" : "Switch to light theme"
      }
      title={
        theme === "light" ? "Switch to dark theme" : "Switch to light theme"
      }
      className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-[var(--color-line)] text-[var(--color-text-dim)] transition-colors hover:border-[var(--color-line-strong)] hover:text-[var(--color-text)]"
    >
      {theme === "light" ? <MoonIcon /> : <SunIcon />}
    </button>
  );
}
