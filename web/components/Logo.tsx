/**
 * The SARDASPORTS logo. The artwork is built by `scripts/build_logo_svg.py` (the
 * wordmark is outlined, so no font is needed) into `public/`; re-run that script to
 * change it rather than editing the SVG by hand.
 *
 * The horizontal lockup is the one for chrome (header, footer): the stacked version
 * is for places with room for it. Width and height are fixed so the page does not
 * shift while the image loads.
 */

import Image from "next/image";
import { SITE_NAME } from "@/lib/site";

// Intrinsic size of the horizontal lockup's viewBox (1087 x 150).
const RATIO = 1087 / 150;

export function Logo({
  className = "h-8 sm:h-11",
  priority = false,
}: {
  /** Sets the height; the width follows from the lockup's aspect ratio. */
  className?: string;
  priority?: boolean;
}) {
  return (
    <Image
      src="/sardasports-logo-horizontal.svg"
      alt={SITE_NAME}
      width={Math.round(44 * RATIO)}
      height={44}
      priority={priority}
      unoptimized
      className={`w-auto ${className}`}
    />
  );
}
