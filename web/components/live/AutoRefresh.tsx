"use client";

/**
 * Re-reads the page's data every so often, so a goal shows up without anyone pressing
 * reload.
 *
 * `router.refresh()` re-runs the server render and swaps in the new result without losing
 * scroll position or the rest of the page's state. It pauses while the tab is hidden: a
 * background tab polling the engine every 20 seconds is load that nobody is looking at.
 */

import { useRouter } from "next/navigation";
import { useEffect } from "react";

export function AutoRefresh({ seconds = 20 }: { seconds?: number }) {
  const router = useRouter();
  useEffect(() => {
    const tick = () => {
      if (document.visibilityState === "visible") router.refresh();
    };
    const timer = window.setInterval(tick, seconds * 1000);
    document.addEventListener("visibilitychange", tick);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", tick);
    };
  }, [router, seconds]);
  return null;
}
