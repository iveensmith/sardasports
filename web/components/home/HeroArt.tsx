/**
 * The picture on the right of the home hero: a football, a basketball and a tennis
 * ball in front of yellow paint slashes, lit from above.
 *
 * Original artwork, drawn here as vector shapes rather than loaded: no licensed
 * photograph, no second file for phones, and it scales to any width. It stands in for
 * the photographed athletes a sports-betting banner usually has, which this site does
 * not have the rights to and which would also imply an endorsement nobody gave.
 *
 * Each ball is built the same way: a base gradient for its colour, its markings
 * clipped to the circle, then one shading layer (dark towards the rim, a soft highlight
 * top-left) so a flat disc reads as a sphere. The yellow slashes go through a rough-edge
 * filter so they look brushed, not cut. There is no animation: it is a still picture.
 */

const POINTS = (cx: number, cy: number, r: number, start: number) =>
  Array.from({ length: 5 }, (_, k) => {
    const a = ((start + k * 72) * Math.PI) / 180;
    return `${(cx + r * Math.cos(a)).toFixed(1)},${(cy + r * Math.sin(a)).toFixed(1)}`;
  }).join(" ");

function Football({ cx, cy, r }: { cx: number; cy: number; r: number }) {
  const k = r / 120;
  // Five pentagons around the one in the middle, each turned to face it.
  const ring = Array.from({ length: 5 }, (_, i) => -90 + i * 72);
  return (
    <g transform={`translate(${cx} ${cy}) scale(${k})`}>
      <ellipse cx="0" cy="128" rx="104" ry="15" fill="url(#ha-floor)" />
      <circle r="120" fill="url(#ha-football)" />
      <g clipPath="url(#ha-clip-football)">
        <polygon points={POINTS(0, 0, 36, -90)} fill="#0c0e12" />
        {ring.map((angle) => {
          const rad = (angle * Math.PI) / 180;
          const px = 108 * Math.cos(rad);
          const py = 108 * Math.sin(rad);
          return (
            <g key={angle}>
              <line
                x1={36 * Math.cos(rad)}
                y1={36 * Math.sin(rad)}
                x2={px - 30 * Math.cos(rad)}
                y2={py - 30 * Math.sin(rad)}
                stroke="#1b1f27"
                strokeWidth="2.6"
              />
              <polygon
                points={POINTS(px, py, 36, angle + 180 - 90 + 90)}
                fill="#0c0e12"
              />
            </g>
          );
        })}
      </g>
      <circle r="120" fill="url(#ha-shade)" />
      <ellipse cx="-42" cy="-58" rx="34" ry="20" fill="#fff" opacity="0.5" transform="rotate(-32 -42 -58)" />
    </g>
  );
}

function Basketball({ cx, cy, r }: { cx: number; cy: number; r: number }) {
  const k = r / 118;
  return (
    <g transform={`translate(${cx} ${cy}) scale(${k})`}>
      <circle r="118" fill="url(#ha-basketball)" />
      <circle r="118" fill="url(#ha-pebble)" />
      <g
        clipPath="url(#ha-clip-basketball)"
        fill="none"
        stroke="#1a0b03"
        strokeWidth="4.4"
        strokeLinecap="round"
      >
        <path d="M0 -120V120M-120 0H120" />
        <path d="M-84 -86C-34 -42 -34 42 -84 86" />
        <path d="M84 -86C34 -42 34 42 84 86" />
      </g>
      <circle r="118" fill="url(#ha-shade)" />
      <ellipse cx="-40" cy="-56" rx="32" ry="18" fill="#fff" opacity="0.38" transform="rotate(-32 -40 -56)" />
    </g>
  );
}

function TennisBall({ cx, cy, r }: { cx: number; cy: number; r: number }) {
  const k = r / 58;
  return (
    <g transform={`translate(${cx} ${cy}) scale(${k})`}>
      <ellipse cx="0" cy="62" rx="50" ry="8" fill="url(#ha-floor)" />
      <circle r="58" fill="url(#ha-tennis)" />
      <g
        clipPath="url(#ha-clip-tennis)"
        fill="none"
        stroke="#f6fbe0"
        strokeWidth="4.2"
        strokeLinecap="round"
      >
        <path d="M-44 -46C-6 -20 -6 20 -44 46" />
        <path d="M44 -46C6 -20 6 20 44 46" />
      </g>
      <circle r="58" fill="url(#ha-shade)" />
      <ellipse cx="-20" cy="-28" rx="16" ry="9" fill="#fff" opacity="0.5" transform="rotate(-32 -20 -28)" />
    </g>
  );
}

export function HeroArt({ className = "" }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 640 470"
      aria-hidden="true"
      focusable="false"
      className={className}
      preserveAspectRatio="xMidYMid meet"
    >
      <defs>
        <filter id="ha-brush" x="-10%" y="-10%" width="120%" height="120%">
          <feTurbulence type="fractalNoise" baseFrequency="0.028 0.06" numOctaves="2" seed="7" />
          <feDisplacementMap in="SourceGraphic" scale="16" />
        </filter>

        <radialGradient id="ha-glow" cx="50%" cy="50%" r="50%">
          <stop offset="0" stopColor="#ffd43b" stopOpacity="0.34" />
          <stop offset="0.6" stopColor="#f5c000" stopOpacity="0.08" />
          <stop offset="1" stopColor="#f5c000" stopOpacity="0" />
        </radialGradient>

        <linearGradient id="ha-slash" x1="0" y1="1" x2="1" y2="0">
          <stop offset="0" stopColor="#b88a00" />
          <stop offset="0.5" stopColor="#f5c000" />
          <stop offset="1" stopColor="#ffe066" />
        </linearGradient>

        <linearGradient id="ha-streak" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#ffd43b" stopOpacity="0" />
          <stop offset="1" stopColor="#ffffff" stopOpacity="0.85" />
        </linearGradient>

        <radialGradient id="ha-football" cx="38%" cy="32%" r="78%">
          <stop offset="0" stopColor="#ffffff" />
          <stop offset="0.7" stopColor="#e3e7ec" />
          <stop offset="1" stopColor="#aab2bd" />
        </radialGradient>
        <radialGradient id="ha-basketball" cx="38%" cy="30%" r="80%">
          <stop offset="0" stopColor="#ffb25e" />
          <stop offset="0.5" stopColor="#ef7413" />
          <stop offset="1" stopColor="#a63f05" />
        </radialGradient>
        <radialGradient id="ha-tennis" cx="38%" cy="30%" r="80%">
          <stop offset="0" stopColor="#f6ff77" />
          <stop offset="0.55" stopColor="#c8e41c" />
          <stop offset="1" stopColor="#7c9608" />
        </radialGradient>
        {/* Darker towards the rim, whatever the ball: that is what makes it round. */}
        <radialGradient id="ha-shade" cx="40%" cy="34%" r="72%">
          <stop offset="0.45" stopColor="#000" stopOpacity="0" />
          <stop offset="1" stopColor="#000" stopOpacity="0.5" />
        </radialGradient>
        <radialGradient id="ha-floor" cx="50%" cy="50%" r="50%">
          <stop offset="0" stopColor="#000" stopOpacity="0.55" />
          <stop offset="1" stopColor="#000" stopOpacity="0" />
        </radialGradient>

        <pattern id="ha-dots" width="9" height="9" patternUnits="userSpaceOnUse">
          <circle cx="4.5" cy="4.5" r="1.1" fill="#000" opacity="0.18" />
        </pattern>
        <pattern id="ha-pebble" width="9" height="9" patternUnits="userSpaceOnUse">
          <circle cx="4.5" cy="4.5" r="1.1" fill="#000" opacity="0.2" />
        </pattern>

        <clipPath id="ha-clip-football">
          <circle r="120" />
        </clipPath>
        <clipPath id="ha-clip-basketball">
          <circle r="118" />
        </clipPath>
        <clipPath id="ha-clip-tennis">
          <circle r="58" />
        </clipPath>
      </defs>

      {/* Light behind the balls. */}
      <ellipse cx="350" cy="245" rx="310" ry="215" fill="url(#ha-glow)" />

      {/* The slashes, drawn first so the balls sit on them. */}
      <g filter="url(#ha-brush)">
        <polygon points="330,470 540,470 640,250 640,70 600,70" fill="url(#ha-slash)" opacity="0.95" />
        <polygon points="262,470 322,470 556,40 604,40" fill="#f5c000" opacity="0.55" />
        <polygon points="560,470 640,470 640,360" fill="#b88a00" opacity="0.8" />
      </g>

      {/* Speed streaks, so the balls look thrown rather than placed. */}
      <g strokeLinecap="round">
        <rect x="0" y="246" width="80" height="3" rx="1.5" fill="url(#ha-streak)" />
        <rect x="0" y="282" width="62" height="2" rx="1" fill="url(#ha-streak)" opacity="0.7" />
        <rect x="0" y="316" width="70" height="3" rx="1.5" fill="url(#ha-streak)" opacity="0.85" />
      </g>

      <Basketball cx={352} cy={196} r={114} />
      <Football cx={196} cy={292} r={124} />
      <TennisBall cx={392} cy={364} r={56} />

      {/* A few sparks. */}
      <g fill="#ffe066">
        <circle cx="82" cy="130" r="2.4" opacity="0.9" />
        <circle cx="552" cy="150" r="2" opacity="0.8" />
        <circle cx="596" cy="260" r="2.6" opacity="0.9" />
        <circle cx="40" cy="400" r="1.8" opacity="0.7" />
      </g>
    </svg>
  );
}

/** Soft out-of-focus floodlights along the top of the banner: positions are fixed so
 *  the server and the browser agree. */
const BOKEH: Array<[number, number, number, number]> = [
  [6, 14, 7, 0.55],
  [11, 8, 4, 0.4],
  [17, 20, 9, 0.35],
  [24, 6, 5, 0.5],
  [33, 16, 6, 0.3],
  [41, 7, 8, 0.4],
  [52, 12, 4, 0.5],
  [60, 5, 9, 0.35],
  [68, 18, 5, 0.45],
  [76, 8, 7, 0.4],
  [84, 15, 10, 0.3],
  [91, 6, 5, 0.5],
  [96, 19, 7, 0.4],
];

export function HeroBokeh({ className = "" }: { className?: string }) {
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      className={className}
      viewBox="0 0 100 40"
      preserveAspectRatio="none"
    >
      <defs>
        <radialGradient id="hb-dot">
          <stop offset="0" stopColor="#fff6c4" stopOpacity="1" />
          <stop offset="1" stopColor="#ffd43b" stopOpacity="0" />
        </radialGradient>
      </defs>
      {BOKEH.map(([x, y, r, o]) => (
        <ellipse
          key={`${x}-${y}`}
          cx={x}
          cy={y}
          rx={r / 3}
          ry={r / 1.4}
          fill="url(#hb-dot)"
          opacity={o}
        />
      ))}
    </svg>
  );
}
