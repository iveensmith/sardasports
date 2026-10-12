"use client";

/**
 * A kick-off time, shown in the reader's own time zone.
 *
 * The server renders in UTC (the engine stores every kick-off as UTC), and a reader an hour
 * ahead who sees "19:00" on a page and "19:36" on their own clock concludes the match has
 * started when it has not: that is what happened with a board of nine unstarted matches
 * reported as "live but not showing live". So the time is converted in the browser, after the
 * page loads, and the UTC reading is kept in the tooltip.
 *
 * Before the conversion runs (and for anything that cannot run it) the text is the UTC time,
 * so the server's output and the first browser render agree and nothing flickers into the
 * wrong hour. `utcSuffix` puts " UTC" on that first reading, for places with room for it.
 */

import { useSyncExternalStore } from "react";
import { utcDate } from "@/lib/time";

function clock(iso: string, timeZone?: string): string {
  return utcDate(iso).toLocaleTimeString("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone,
  });
}

function dayAndClock(iso: string, timeZone?: string): string {
  const at = utcDate(iso);
  const date = at.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone,
  });
  return `${date} · ${clock(iso, timeZone)}`;
}

const subscribeNever = () => () => {};

function browserZone(): string | null {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone;
  } catch {
    return null;
  }
}

export function LocalTime({
  iso,
  withDate = false,
  utcSuffix = false,
  className,
}: {
  /** ISO timestamp, UTC. */
  iso: string;
  /** "12 Oct 2026 · 20:00" instead of "20:00". */
  withDate?: boolean;
  /** Label the server-rendered reading "UTC" (the converted one is the reader's own). */
  utcSuffix?: boolean;
  className?: string;
}) {
  const render = withDate ? dayAndClock : clock;
  const initial = `${render(iso, "UTC")}${utcSuffix ? " UTC" : ""}`;
  // `useSyncExternalStore` is the hydration-safe way to read something only the browser
  // knows: the server (and the first browser render) get `initial`, and the browser then
  // switches to the reader's own time without a mismatch warning.
  const text = useSyncExternalStore(
    subscribeNever,
    () => render(iso),
    () => initial,
  );
  const zone = useSyncExternalStore(subscribeNever, browserZone, () => null);

  return (
    <time
      dateTime={iso}
      className={className}
      title={`${zone ? `Your time (${zone})` : "Your time"}. ${clock(iso, "UTC")} UTC.`}
    >
      {text}
    </time>
  );
}
