"use client";

/**
 * Lets a page say which sport it belongs to, for the tabs under the header.
 *
 * The tabs sit in the layout, above every page, and normally work it out from the
 * address (/tennis is tennis). A match page lives at /match/..., whatever the
 * sport, so it has to say. Render `<ActiveSport sport="tennis" />` on such a page;
 * it tells the tabs on mount and clears itself when the page goes away.
 */

import { useEffect, useSyncExternalStore } from "react";
import type { SportKey } from "@/lib/sports";

let override: SportKey | null = null;
const listeners = new Set<() => void>();

function set(next: SportKey | null) {
  override = next;
  listeners.forEach((listener) => listener());
}

/** The sport a page has claimed, or null to fall back on the address. */
export function useSportOverride(): SportKey | null {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => override,
    () => null,
  );
}

export function ActiveSport({ sport }: { sport: SportKey }) {
  useEffect(() => {
    set(sport);
    return () => set(null);
  }, [sport]);
  return null;
}
