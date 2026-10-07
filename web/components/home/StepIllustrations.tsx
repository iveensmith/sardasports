/**
 * The three diagrams on the "how it works" cards.
 *
 * Drawn for this engine, not borrowed. The reference's third diagram is a neural
 * network, which would misdescribe a system that blends three differently built
 * estimators, so this one shows what actually happens: three views of a match
 * merge into one probability. The first and second show the same ideas the
 * reference's do (inputs converging on a processor; messy data passing through a
 * filter and coming out clean) with this engine's own inputs.
 *
 * They are decorative (`aria-hidden`): the card's text carries the meaning.
 * Colours come from the theme tokens, so they follow light and dark mode.
 */

const LINE = "var(--color-line-strong)";
const FAINT = "var(--color-text-faint)";
const DIM = "var(--color-text-dim)";
const GOLD = "var(--color-gold-bright)";
const WON = "var(--color-won)";
const LOST = "var(--color-lost)";
const SURFACE = "var(--color-surface)";

const base = {
  viewBox: "0 0 320 180",
  fill: "none",
  "aria-hidden": true,
  className: "h-full w-full",
  preserveAspectRatio: "xMidYMid meet",
} as const;

const dashed = { stroke: LINE, strokeWidth: 1.4, strokeDasharray: "4 4" };

/** Inputs (results, ratings, form, trend) converging on one processor. */
export function DataCollectionDiagram() {
  const rows = [30, 68, 106, 144];
  return (
    <svg {...base}>
      {/* connectors, drawn first so the boxes sit on top */}
      {rows.map((y) => (
        <path
          key={y}
          d={`M112 ${y} H150 V90 H190`}
          stroke={LINE}
          strokeWidth={1.4}
          strokeDasharray="4 4"
        />
      ))}

      {rows.map((y, i) => (
        <g key={`box-${y}`}>
          <rect
            x={20}
            y={y - 14}
            width={92}
            height={28}
            rx={7}
            fill={SURFACE}
            stroke={LINE}
            strokeWidth={1.4}
          />
          <text x={104} y={y - 16} fontSize={7} textAnchor="end" fill={FAINT}>
            {`0${i + 1}`}
          </text>
        </g>
      ))}

      {/* 01 results: bars standing on one baseline */}
      <g fill={GOLD}>
        <rect x={32} y={30} width={5} height={7} rx={1} />
        <rect x={40} y={25} width={5} height={12} rx={1} />
        <rect x={48} y={19} width={5} height={18} rx={1} />
        <rect x={56} y={27} width={5} height={10} rx={1} />
      </g>
      {/* 02 Elo rating: the word */}
      <text x={32} y={73} fontSize={13} fontWeight={700} fill={GOLD}>
        Elo
      </text>
      {/* 03 form: a ring */}
      <circle cx={40} cy={106} r={7} stroke={GOLD} strokeWidth={2} />
      <circle cx={40} cy={106} r={2.4} fill={GOLD} />
      {/* 04 trend: a rising line */}
      <path
        d="M32 150 L42 143 L50 147 L62 136"
        stroke={GOLD}
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx={62} cy={136} r={2.4} fill={GOLD} />

      {/* the processor */}
      <g>
        <circle
          cx={232}
          cy={90}
          r={48}
          stroke={LINE}
          strokeWidth={1}
          strokeDasharray="2 5"
        />
        <rect
          x={196}
          y={54}
          width={72}
          height={72}
          rx={12}
          fill={SURFACE}
          stroke={LINE}
          strokeWidth={1.6}
        />
        {[0, 1, 2, 3].map((i) => (
          <g key={i} stroke={LINE} strokeWidth={1.6} strokeLinecap="round">
            <path d={`M${208 + i * 16} 54 v-7`} />
            <path d={`M${208 + i * 16} 126 v7`} />
            <path d={`M196 ${66 + i * 16} h-7`} />
            <path d={`M268 ${66 + i * 16} h7`} />
          </g>
        ))}
        <circle cx={232} cy={90} r={17} stroke={GOLD} strokeWidth={1.8} />
        <circle cx={232} cy={90} r={4} fill={GOLD} />
        <path
          d="M232 68 v8 M232 104 v8 M210 90 h8 M246 90 h8"
          stroke={GOLD}
          strokeWidth={1.8}
          strokeLinecap="round"
        />
      </g>
    </svg>
  );
}

/** Messy records going through a filter and coming out consistent. */
export function CleaningDiagram() {
  return (
    <svg {...base}>
      {/* raw records, two of them faulty */}
      {[
        { y: 34, w: 70, bad: false },
        { y: 62, w: 52, bad: true },
        { y: 90, w: 76, bad: false },
        { y: 118, w: 46, bad: true },
        { y: 146, w: 64, bad: false },
      ].map((row) => (
        <g key={row.y}>
          <rect
            x={20}
            y={row.y - 4}
            width={row.w}
            height={8}
            rx={4}
            fill={LINE}
          />
          {row.bad && (
            <path
              d={`M${28 + row.w} ${row.y - 4} l8 8 m0 -8 l-8 8`}
              stroke={LOST}
              strokeWidth={1.8}
              strokeLinecap="round"
            />
          )}
        </g>
      ))}

      <path d="M112 90 H128" {...dashed} />

      {/* the filter, as a funnel inside a panel */}
      <rect
        x={128}
        y={34}
        width={64}
        height={112}
        rx={12}
        fill={SURFACE}
        stroke={LINE}
        strokeWidth={1.6}
      />
      <path
        d="M144 62 H176 L164 88 V114 L156 108 V88 Z"
        stroke={GOLD}
        strokeWidth={2}
        strokeLinejoin="round"
        fill="none"
      />
      <path
        d="M160 128 H160"
        stroke={LINE}
        strokeWidth={1.6}
        strokeLinecap="round"
      />

      <path d="M192 90 H208" {...dashed} />

      {/* clean, consistent output */}
      {[54, 78, 102, 126].map((y) => (
        <rect
          key={y}
          x={208}
          y={y - 4}
          width={64}
          height={8}
          rx={4}
          fill={GOLD}
        />
      ))}

      {/* validated */}
      <circle cx={288} cy={36} r={13} stroke={WON} strokeWidth={1.8} />
      <path
        d="M282 36.5 l4.2 4.2 l8 -8.4"
        stroke={WON}
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** Three estimators, each its own view, merging into one probability. */
export function BlendDiagram() {
  const nodes = [
    { y: 44, label: "Elo" },
    { y: 90, label: "Poisson" },
    { y: 136, label: "Boosted" },
  ];
  return (
    <svg {...base}>
      {nodes.map((n) => (
        <path
          key={n.y}
          d={`M96 ${n.y} C 132 ${n.y}, 138 90, 170 90`}
          stroke={LINE}
          strokeWidth={1.4}
          strokeDasharray="4 4"
        />
      ))}

      {nodes.map((n) => (
        <g key={n.label}>
          <rect
            x={22}
            y={n.y - 15}
            width={74}
            height={30}
            rx={8}
            fill={SURFACE}
            stroke={LINE}
            strokeWidth={1.5}
          />
          <text
            x={59}
            y={n.y + 4}
            fontSize={11}
            fontWeight={600}
            textAnchor="middle"
            fill={DIM}
          >
            {n.label}
          </text>
        </g>
      ))}

      {/* the blend */}
      <circle
        cx={190}
        cy={90}
        r={22}
        fill={SURFACE}
        stroke={GOLD}
        strokeWidth={1.8}
      />
      <circle
        cx={190}
        cy={90}
        r={30}
        stroke={LINE}
        strokeWidth={1}
        strokeDasharray="2 5"
      />
      <text
        x={190}
        y={95}
        fontSize={14}
        fontWeight={700}
        textAnchor="middle"
        fill={GOLD}
      >
        %
      </text>

      <path d="M222 90 H246" {...dashed} />

      {/* the pick, graded */}
      <circle cx={274} cy={90} r={22} stroke={WON} strokeWidth={1.8} />
      <path
        d="M263 90.5 l8 8 l14 -15"
        stroke={WON}
        strokeWidth={2.4}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
