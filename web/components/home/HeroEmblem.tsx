/**
 * The mark behind the hero headline: the SARDASPORTS logo, large and lit.
 *
 * Replaces the standing silhouette this slot used to hold. A grey figure said
 * nothing about the product; the site's own mark, with a burst of rays behind
 * it, says whose picks these are before a word is read. It is the same artwork
 * as the header's (`public/sardasports-logo.svg`, built by
 * `scripts/build_logo_svg.py`), so there is nothing to license and it cannot
 * drift from the brand.
 *
 * It arrives with one soft flash on load and then holds still; the motion and
 * the per-theme opacities live in `.hero-emblem` in globals.css, where
 * reduced-motion readers get it without the flash. The hero's veil sits over
 * it and closes behind the headline, so the type keeps its contrast.
 */

import Image from "next/image";

export function HeroEmblem() {
  return (
    <div aria-hidden className="hero-emblem">
      <span className="hero-emblem__rays" />
      {/* Fixed intrinsic size (the logo's viewBox, 666 x 459) so nothing shifts as it loads. */}
      <Image
        src="/sardasports-logo.svg"
        alt=""
        width={666}
        height={459}
        priority
        unoptimized
        className="hero-emblem__logo"
      />
    </div>
  );
}
