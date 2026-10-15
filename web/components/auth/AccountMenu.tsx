"use client";

/**
 * The header's account controls: "Log in" and "Sign up" when signed out, "Account" when in.
 *
 * It asks `/api/auth/me` from the browser after the page has loaded, rather than reading the
 * session cookie on the server, so reading it never turns a cached, shared page into one
 * rendered per visitor. Until the answer arrives (and when signed out) it shows "Log in".
 *
 * Sizing follows the two icon buttons beside it (theme and menu, 32px circles): below `sm`
 * the sign-in control is the same 32px circle, so the right-hand cluster stays narrow enough
 * for a 320px phone. From `sm` it becomes a labelled button, and `xl` adds "Sign up".
 */

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/clientApi";
import type { Session } from "@/lib/session";

function PersonIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      width={18}
      height={18}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      aria-hidden
    >
      <circle cx="12" cy="8.5" r="3.6" />
      <path d="M4.5 20c.9-3.6 3.9-5.5 7.5-5.5s6.6 1.9 7.5 5.5" />
    </svg>
  );
}

export function AccountMenu() {
  const [session, setSession] = useState<Session | null | undefined>(undefined);

  useEffect(() => {
    let alive = true;
    api<Session>("/api/auth/me").then((result) => {
      if (alive) setSession(result.ok ? result.data : null);
    });
    return () => {
      alive = false;
    };
  }, []);

  if (session === undefined) {
    // Same footprint as the final control, so the header does not jump when the answer arrives.
    return <span className="inline-block h-8 w-8 sm:h-9 sm:w-[88px] lg:max-xl:h-8 lg:max-xl:w-8" aria-hidden />;
  }

  if (!session) {
    return (
      <span className="flex items-center gap-2">
        <Link
          href="/login"
          aria-label="Log in"
          className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-[var(--color-gold)] text-[var(--color-gold-bright)] transition-[transform,background-color] duration-150 hover:bg-[var(--color-gold)]/10 active:scale-[0.96] sm:h-9 sm:w-auto sm:gap-2 sm:rounded-md sm:px-3 sm:text-[13px] sm:font-bold sm:tracking-[0.02em] sm:whitespace-nowrap lg:max-xl:h-8 lg:max-xl:w-8 lg:max-xl:rounded-full lg:max-xl:px-0"
        >
          <PersonIcon />
          <span className="hidden sm:inline lg:max-xl:hidden">Log in</span>
        </Link>
        <Link
          href="/signup"
          className="hidden h-9 items-center rounded-md bg-[var(--color-gold)] px-3 text-[13px] font-extrabold tracking-[0.02em] whitespace-nowrap text-[var(--color-ink-on-accent)] transition-[transform,background-color] duration-150 hover:bg-[var(--color-gold-bright)] active:scale-[0.96] xl:inline-flex"
        >
          Sign up
        </Link>
      </span>
    );
  }

  return (
    <span className="flex items-center gap-2">
      {session.user.role === "admin" && (
        <Link
          href="/admin"
          className="hidden h-9 items-center rounded-md px-3 text-[13px] font-bold text-[var(--color-gold-bright)] transition-colors hover:bg-[var(--color-surface-raised)] sm:inline-flex"
        >
          Admin
        </Link>
      )}
      <Link
        href="/account"
        aria-label="Your account"
        className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-[var(--color-line-strong)] text-[var(--color-text)] transition-[transform,background-color] duration-150 hover:bg-[var(--color-surface-raised)] active:scale-[0.96] sm:h-9 sm:w-auto sm:gap-2 sm:rounded-md sm:px-3 sm:text-[13px] sm:font-bold sm:whitespace-nowrap lg:max-xl:h-8 lg:max-xl:w-8 lg:max-xl:rounded-full lg:max-xl:px-0"
      >
        <PersonIcon />
        <span className="hidden sm:inline lg:max-xl:hidden">Account</span>
        {session.entitlement.premium && (
          <span className="hidden rounded bg-[var(--color-gold)] px-1.5 py-0.5 text-[10px] font-extrabold tracking-wider text-[var(--color-ink-on-accent)] uppercase sm:inline lg:max-xl:hidden">
            Premium
          </span>
        )}
      </Link>
    </span>
  );
}
