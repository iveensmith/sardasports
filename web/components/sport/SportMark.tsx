/**
 * A small ball for each sport, drawn to match the ones in the logo.
 *
 * Decorative: the sport's name always sits beside it, so it carries no label of its
 * own. Drawn rather than taken from an icon set because the logo already fixes how
 * these balls look on this site, and a mark that disagrees with the logo would look
 * like it came from somewhere else.
 */

import type { SportKey } from "@/lib/sports";

export function SportMark({
  sport,
  size = 16,
  className,
}: {
  sport: SportKey;
  size?: number;
  className?: string;
}) {
  const common = {
    width: size,
    height: size,
    viewBox: "-12 -12 24 24",
    "aria-hidden": true,
    className,
  } as const;

  if (sport === "basketball") {
    return (
      <svg {...common}>
        <circle r="10.5" fill="#e8742a" />
        <g
          fill="none"
          stroke="#1b1208"
          strokeWidth="1.3"
          clipPath="url(#sm-bb)"
        >
          <path d="M-11 0H11M0 -11V11" />
          <path d="M-7.5 -7.5C-3 -3 -3 3 -7.5 7.5M7.5 -7.5C3 -3 3 3 7.5 7.5" />
        </g>
        <defs>
          <clipPath id="sm-bb">
            <circle r="10.5" />
          </clipPath>
        </defs>
      </svg>
    );
  }

  if (sport === "tennis") {
    return (
      <svg {...common}>
        <circle r="10.5" fill="#c6e23b" />
        <g fill="none" stroke="#fff" strokeWidth="1.4" clipPath="url(#sm-tn)">
          <path d="M-9 -9C-2 -3 -2 3 -9 9" />
          <path d="M9 -9C2 -3 2 3 9 9" />
        </g>
        <defs>
          <clipPath id="sm-tn">
            <circle r="10.5" />
          </clipPath>
        </defs>
      </svg>
    );
  }

  return (
    <svg {...common}>
      <circle r="10.5" fill="#fff" stroke="#0b0b0b" strokeWidth="1.2" />
      <path d="M0 -4.2 L4 -1.3 L2.5 3.4 H-2.5 L-4 -1.3 Z" fill="#0b0b0b" />
      <path
        d="M0 -4.2V-9.5M4 -1.3L9 -3M-4 -1.3L-9 -3M2.5 3.4L5.8 8M-2.5 3.4L-5.8 8"
        stroke="#0b0b0b"
        strokeWidth="1.1"
        fill="none"
      />
    </svg>
  );
}
