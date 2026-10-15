/**
 * The day in a basketball or tennis address (`/basketball?date=2026-10-15`).
 *
 * Those addresses are rewritten to `/basketball/d/2026-10-15` inside the site (see
 * next.config.ts), so the page for a day is an ordinary cacheable route instead of one that reads
 * the query string on every request. The visitor's address does not change.
 *
 * Only days near today are served. A cached page costs disk and an engine call per distinct day,
 * and the boards hold nothing useful far outside this window, so an address outside it simply goes
 * to today's page rather than being rendered (and cached) for a date nobody needs.
 */

export const DAYS_BACK = 45;
export const DAYS_AHEAD = 14;

const MS_PER_DAY = 86_400_000;

/** The day as `YYYY-MM-DD` if it is a real date within the window, otherwise null. */
export function validSportDay(value: string, now: Date = new Date()): string | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const parsed = new Date(`${value}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) return null;
  // `2026-02-31` parses in some engines to March 3rd; only an exact round trip is a real day.
  if (parsed.toISOString().slice(0, 10) !== value) return null;
  const today = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
  const offset = Math.round((parsed.getTime() - today) / MS_PER_DAY);
  if (offset < -DAYS_BACK || offset > DAYS_AHEAD) return null;
  return value;
}
