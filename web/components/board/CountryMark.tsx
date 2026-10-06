/**
 * A country's flag, or a globe where the grouping is not a single nation.
 *
 * Shared by the board's country sidebar and the leagues pages. International
 * competitions group under their confederation (Europe, Africa, World), and
 * there is no flag for "World" — reaching for a nearby one would be a factual
 * claim about geography this mark isn't making.
 */

function flagSrc(code: string) {
  return `https://flagcdn.com/w20/${code.toLowerCase()}.png`;
}

/** Plain shapes, not a licensed icon set — this is the one mark on the page
 * that isn't a flag, so it only has to read as "not a single nation". */
export function GlobeMark() {
  return (
    <svg
      viewBox="0 0 24 24"
      width={13}
      height={13}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      className="shrink-0"
    >
      <circle cx="12" cy="12" r="9" />
      <path d="M3.2 12h17.6" />
      <path d="M12 3c2.6 2.7 2.6 15.3 0 18" />
      <path d="M12 3c-2.6 2.7-2.6 15.3 0 18" />
    </svg>
  );
}

export function CountryMark({ code }: { code: string | null }) {
  if (!code) {
    return (
      <span className="inline-flex h-[14px] w-5 shrink-0 items-center justify-center text-[var(--color-text-faint)]">
        <GlobeMark />
      </span>
    );
  }
  return (
    <img
      src={flagSrc(code)}
      alt=""
      width={20}
      height={14}
      loading="lazy"
      decoding="async"
      className="h-[14px] w-5 shrink-0 rounded-[2px] object-cover"
    />
  );
}
