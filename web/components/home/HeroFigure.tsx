/**
 * The figure behind the hero headline.
 *
 * An original silhouette, drawn here rather than loaded. The reference site
 * uses a photographic player from its CDN; that is their asset and not ours
 * to take. At the scale a hero figure actually reads at — veiled, behind
 * type, mostly shoulders and light — a drawn one does the same work, weighs
 * about two kilobytes, needs no second file for phones, and recolours with a
 * token.
 *
 * **It is lit from behind, and that is the whole trick.** The first attempt
 * drew a dark body on a dark page and it disappeared: a #1b2734 silhouette on
 * a #090d12 background is a ten-percent contrast step, and it vanished
 * completely once the veil went over it. What makes the reference image read
 * is not the body at all, it is the glow the body is standing in front of.
 * So the light is the subject here: a broad radial bloom, with the figure
 * punched out of it as an occluder.
 *
 * Opacity is baked into the gradients rather than applied to the whole
 * element, so the glow can stay bright while the body stays dark. A single
 * `opacity` on the parent would flatten both towards the background and
 * bring back the problem it was meant to solve.
 *
 * Read from the back, standing, arms at rest: someone waiting for kick-off,
 * not celebrating. This is a product about calibrated uncertainty and a
 * graded record, and a figure mid-victory-slide would promise something the
 * engine does not.
 */

export function HeroFigure({ className = "" }: { className?: string }) {
  return (
    <svg
      viewBox="70 0 260 620"
      preserveAspectRatio="xMidYMax meet"
      aria-hidden="true"
      focusable="false"
      className={className}
    >
      <defs>
        {/* A tight core right behind the head. The broad bloom lives in the
            hero as a CSS gradient so it can run the full width of the
            viewport; this one has to travel with the figure, because it is
            what gives the shoulders an edge to be seen against. */}
        <radialGradient id="hf-core" cx="50%" cy="15%" r="42%">
          <stop offset="0%" stopColor="#f0d98a" stopOpacity="0.30" />
          <stop offset="55%" stopColor="#e3bc45" stopOpacity="0.07" />
          <stop offset="100%" stopColor="#e3bc45" stopOpacity="0" />
        </radialGradient>

        {/* The body occludes the light, so it is darker than the page rather
            than lighter — a shape cut out of the bloom. */}
        <linearGradient id="hf-body" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#05080c" stopOpacity="0.96" />
          <stop offset="55%" stopColor="#05080c" stopOpacity="0.88" />
          <stop offset="100%" stopColor="#05080c" stopOpacity="0.9" />
        </linearGradient>

        {/* The floor light. The body only reads as a shape against light, and
            the bloom behind the head stops well above the legs, so without
            this the lower half is dark on dark and disappears. A pool of light
            on the ground puts the legs and boots in silhouette. */}
        <radialGradient id="hf-floor" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#f0d98a" stopOpacity="0.34" />
          <stop offset="45%" stopColor="#e3bc45" stopOpacity="0.12" />
          <stop offset="100%" stopColor="#e3bc45" stopOpacity="0" />
        </radialGradient>

        {/* A light touch at the very foot only: the legs stay visible all the way
            down to the boots. */}
        <linearGradient id="hf-fade" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#fff" stopOpacity="1" />
          <stop offset="90%" stopColor="#fff" stopOpacity="1" />
          <stop offset="100%" stopColor="#fff" stopOpacity="0.85" />
        </linearGradient>
        <mask id="hf-mask">
          <rect x="70" y="0" width="260" height="620" fill="url(#hf-fade)" />
        </mask>
      </defs>

      {/* Light first, figure on top of it. */}
      <rect x="70" y="0" width="260" height="620" fill="url(#hf-core)" />
      <ellipse cx="200" cy="585" rx="118" ry="150" fill="url(#hf-floor)" />

      <g mask="url(#hf-mask)" fill="url(#hf-body)">
        {/* Head and neck. */}
        <ellipse cx="200" cy="86" rx="38" ry="44" />
        <path d="M182 122h36v26h-36z" />

        {/* Shoulders and torso, tapering to the waist. */}
        <path d="M200 136c-26 0-48 6-62 16-11 8-16 20-18 34l-6 44c-1 8 4 13 11 12l9-1 6 76c1 9 7 14 16 14h88c9 0 15-5 16-14l6-76 9 1c7 1 12-4 11-12l-6-44c-2-14-7-26-18-34-14-10-36-16-62-16z" />

        {/* Arms, with a little daylight at the elbow so the torso reads. */}
        <path d="M122 188c-8 3-12 10-14 19l-14 68c-2 9 2 15 9 16 7 1 12-3 14-12l17-71z" />
        <path d="M278 188c8 3 12 10 14 19l14 68c2 9-2 15-9 16-7 1-12-3-14-12l-17-71z" />

        {/* Shorts. */}
        <path d="M156 338h88l7 62c1 8-4 13-12 13h-26c-7 0-11-4-12-11l-1-30-1 30c-1 7-5 11-12 11h-26c-8 0-13-5-12-13z" />

        {/* Legs, feet a little apart. */}
        <path d="M166 410h30l-4 96-4 90h-24l3-90z" />
        <path d="M234 410h-30l4 96 4 90h24l-3-90z" />

        {/* Boots, so the legs end somewhere. */}
        <path d="M160 592h31l3 9c1 6-3 9-8 9h-22c-7 0-9-6-5-11z" />
        <path d="M240 592h-31l-3 9c-1 6 3 9 8 9h22c7 0 9-6 5-11z" />
      </g>
    </svg>
  );
}
