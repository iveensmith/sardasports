/**
 * Timestamps from the engine are UTC but carry no zone marker ("2026-10-12T18:30:00"), and
 * `new Date()` reads a string like that as the *reader's own* local time. So a 18:30 UTC
 * kick-off was shown as 18:30 to someone in Lagos, an hour early, with nothing to say so.
 * Anything that turns one of these into a `Date` goes through here.
 */

const HAS_ZONE = /(?:Z|[+-]\d{2}:?\d{2})$/i;

/** The same instant with an explicit UTC marker, unless it already has a zone. */
export function asUtc(iso: string): string {
  return HAS_ZONE.test(iso) ? iso : `${iso}Z`;
}

export function utcDate(iso: string): Date {
  return new Date(asUtc(iso));
}
