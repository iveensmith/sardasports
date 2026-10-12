/**
 * The home page's line icons, drawn once and shared.
 *
 * Plain outlined shapes at one stroke weight, coloured by `currentColor`, so the
 * page's yellow (or any other colour) is set where they are used and not in here.
 * Drawn rather than taken from an icon set because there are only a dozen and the
 * site has no icon dependency to carry for them.
 */

type IconProps = { size?: number; className?: string };

function Svg({
  size = 22,
  className,
  children,
}: IconProps & { children: React.ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      focusable="false"
      className={className}
    >
      {children}
    </svg>
  );
}

export function ArrowRight(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M4 12h15M13 6l6 6-6 6" />
    </Svg>
  );
}

export function Trophy(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M8 4h8v5a4 4 0 0 1-8 0V4z" />
      <path d="M8 6H5v2a3 3 0 0 0 3 3M16 6h3v2a3 3 0 0 1-3 3" />
      <path d="M12 13v4M8.5 20h7M10 17h4v3h-4z" />
    </Svg>
  );
}

export function Target(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="12" r="8" />
      <circle cx="12" cy="12" r="4" />
      <path d="M12 12l6-6M16.5 4.5V7.5H19.5" />
    </Svg>
  );
}

export function BarsUp(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M5 20v-6M10 20v-9M15 20v-4M20 20V8" />
      <path d="M4 10l5-4 4 3 6-5M15 4h4v4" />
    </Svg>
  );
}

export function Pulse(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7v5l3.2 2" />
    </Svg>
  );
}

export function Medal(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="14" r="5" />
      <path d="M9 3l3 5 3-5M9.5 14l1.8 1.8 3.2-3.4" />
    </Svg>
  );
}

export function ShieldCheck(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M12 3l7 3v5.5c0 4.2-2.9 7.4-7 9-4.1-1.6-7-4.8-7-9V6l7-3z" />
      <path d="M8.8 12.2l2.2 2.2 4.2-4.6" />
    </Svg>
  );
}

export function Check(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M5 12.5l4.5 4.5L19 7" />
    </Svg>
  );
}

export function Cross(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M6 6l12 12M18 6L6 18" />
    </Svg>
  );
}

export function Dots(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="6" cy="12" r="1.2" fill="currentColor" />
      <circle cx="12" cy="12" r="1.2" fill="currentColor" />
      <circle cx="18" cy="12" r="1.2" fill="currentColor" />
    </Svg>
  );
}

export function Clock(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.5V12l3 2" />
    </Svg>
  );
}

export function Lock(props: IconProps) {
  return (
    <Svg {...props}>
      <rect x="5" y="11" width="14" height="9" rx="2" />
      <path d="M8 11V8a4 4 0 0 1 8 0v3" />
    </Svg>
  );
}
