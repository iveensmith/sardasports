# ruff: noqa: E501 (the SVG templates below are long lines of markup)
"""Build the SARDASPORTS logo SVGs in web/public.

The wordmark is converted from Arial Black to outlines (so the SVG needs no font),
sheared into the italic of the official logo. The emblem (S inside a gold orbit, four
sport balls) is drawn by hand. Run:  .venv/Scripts/python.exe scripts/build_logo_svg.py

Outputs
  web/public/sardasports-logo.svg             full stacked logo (emblem above wordmark)
  web/public/sardasports-logo-horizontal.svg  compact lockup for the site header/footer
  web/app/icon.svg                            the browser-tab icon: the emblem on a dark tile
                                              (web/scripts/build-favicons.mjs makes the .ico and
                                              the touch icon from it)
"""

from pathlib import Path

from matplotlib.font_manager import FontProperties
from matplotlib.path import Path as MPath
from matplotlib.textpath import TextPath

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "web" / "public"
APP = ROOT / "web" / "app"
FONT = FontProperties(fname="C:/Windows/Fonts/ariblk.ttf")
SHEAR = 0.24  # italic slant, x shift per unit of height

GOLD_LIGHT, GOLD, GOLD_DARK = "#fff0a8", "#e3bc45", "#a8780f"
INK = "#0b0b0b"


def text_outline(text, size, tracking=0.0):
    """Return (svg path d, width, ascent) for `text` laid out in y-down SVG space,
    origin at the left of the baseline, sheared for italic."""
    parts, x = [], 0.0
    for ch in text:
        tp = TextPath((0, 0), ch, size=size, prop=FONT)
        if ch == " ":
            advance = size * 0.3
        else:
            advance = (
                TextPath((0, 0), ch + ch, size=size, prop=FONT).get_extents().x1
                - tp.get_extents().x1
            )
        verts, codes = tp.vertices.copy(), tp.codes
        d, i = [], 0
        while i < len(codes):
            c = codes[i]

            def pt(j):
                vx, vy = verts[j]
                return f"{x + vx + SHEAR * vy:.2f} {-vy:.2f}"

            if c == MPath.MOVETO:
                d.append(f"M{pt(i)}")
                i += 1
            elif c == MPath.LINETO:
                d.append(f"L{pt(i)}")
                i += 1
            elif c == MPath.CURVE3:
                d.append(f"Q{pt(i)} {pt(i + 1)}")
                i += 2
            elif c == MPath.CURVE4:
                d.append(f"C{pt(i)} {pt(i + 1)} {pt(i + 2)}")
                i += 3
            elif c == MPath.CLOSEPOLY:
                d.append("Z")
                i += 1
            else:
                i += 1
        parts.append("".join(d))
        x += advance + tracking
    ascent = TextPath((0, 0), "H", size=size, prop=FONT).get_extents().y1
    return "".join(parts), x - tracking + SHEAR * ascent, ascent


def wordmark(prefix, size, x, baseline, tracking=0.0):
    """SARDA (white) + SPORTS (gold) as one outlined group; returns (svg, total width)."""
    sarda, w1, asc = text_outline("SARDA", size, tracking)
    sports, w2, _ = text_outline("SPORTS", size, tracking)
    gap = size * 0.04
    stroke = max(2.0, size * 0.1)
    total = w1 + gap + w2
    svg = f"""
  <defs>
    <linearGradient id="{prefix}-wg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="{GOLD_LIGHT}"/>
      <stop offset="0.45" stop-color="{GOLD}"/>
      <stop offset="1" stop-color="{GOLD_DARK}"/>
    </linearGradient>
    <linearGradient id="{prefix}-ww" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#ffffff"/>
      <stop offset="1" stop-color="#d9d9d9"/>
    </linearGradient>
  </defs>
  <g transform="translate({x:.2f} {baseline:.2f})" stroke-linejoin="round">
    <path d="{sarda}" fill="url(#{prefix}-ww)" stroke="{INK}" stroke-width="{stroke:.2f}" paint-order="stroke"/>
    <path d="{sports}" transform="translate({w1 + gap:.2f} 0)" fill="url(#{prefix}-wg)" stroke="{INK}" stroke-width="{stroke:.2f}" paint-order="stroke"/>
  </g>"""
    return svg, total, asc


def _pentagon(cx, cy, r, rot):
    import math

    return [
        (
            cx + r * math.cos(math.radians(rot + 72 * i)),
            cy + r * math.sin(math.radians(rot + 72 * i)),
        )
        for i in range(5)
    ]


def _poly(points):
    return "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in points) + " Z"


_CENTRE = _pentagon(0, 0, 14, -90)
_EDGE = [
    _pentagon(
        46 * __import__("math").cos(__import__("math").radians(-90 + 72 * k)),
        46 * __import__("math").sin(__import__("math").radians(-90 + 72 * k)),
        15,
        90 + 72 * k,
    )
    for k in range(5)
]
SOCCER_PATCHES = _poly(_CENTRE) + "".join(_poly(e) for e in _EDGE)
SOCCER_SEAMS = "".join(
    f"M{_CENTRE[k][0]:.1f} {_CENTRE[k][1]:.1f} L{_EDGE[k][(k + 2) % 5][0]:.1f} {_EDGE[k][(k + 2) % 5][1]:.1f}"
    for k in range(5)
)


def balls(prefix, cx, cy, s):
    """The cluster of four balls; (cx, cy) is its centre, s its overall scale (~radius of one ball = s)."""
    return f"""
  <g transform="translate({cx:.2f} {cy:.2f}) scale({s:.4f})">
    <!-- American football, behind -->
    <g transform="translate(58 18) rotate(-32)">
      <ellipse rx="52" ry="31" fill="#7a4020" stroke="{INK}" stroke-width="5"/>
      <ellipse rx="52" ry="31" fill="url(#{prefix}-fb)"/>
      <path d="M-30 -27 C-34 -9 -34 9 -30 27 M-22 -29 C-26 -9 -26 9 -22 29" fill="none" stroke="#fff" stroke-width="5"/>
      <path d="M-9 0 H22 M-3 -7 V7 M5 -7 V7 M13 -7 V7" stroke="#fff" stroke-width="3.2" stroke-linecap="round"/>
    </g>
    <!-- basketball, behind -->
    <g transform="translate(-18 -52)">
      <circle r="38" fill="url(#{prefix}-bb)" stroke="{INK}" stroke-width="5"/>
      <g fill="none" stroke="{INK}" stroke-width="3.2" clip-path="url(#{prefix}-bbclip)">
        <path d="M-38 0 H38 M0 -38 V38"/>
        <path d="M-27 -27 C-10 -10 -10 10 -27 27 M27 -27 C10 -10 10 10 27 27"/>
      </g>
    </g>
    <!-- tennis ball -->
    <g transform="translate(62 -34)">
      <circle r="26" fill="url(#{prefix}-tb)" stroke="{INK}" stroke-width="4.5"/>
      <g fill="none" stroke="#fff" stroke-width="3" clip-path="url(#{prefix}-tbclip)">
        <path d="M-22 -22 C-4 -8 -4 8 -22 22"/>
        <path d="M22 -22 C4 -8 4 8 22 22"/>
      </g>
    </g>
    <!-- soccer ball, front -->
    <g transform="translate(12 20)">
      <circle r="42" fill="#fff" stroke="{INK}" stroke-width="5"/>
      <g clip-path="url(#{prefix}-sbclip)">
        <path d="{SOCCER_PATCHES}" fill="{INK}"/>
        <path d="{SOCCER_SEAMS}" fill="none" stroke="{INK}" stroke-width="2.2" stroke-linecap="round"/>
      </g>
    </g>
  </g>
  <defs>
    <radialGradient id="{prefix}-bb" cx="0.35" cy="0.3" r="0.8">
      <stop offset="0" stop-color="#ffa24d"/><stop offset="1" stop-color="#d9631a"/>
    </radialGradient>
    <radialGradient id="{prefix}-tb" cx="0.35" cy="0.3" r="0.8">
      <stop offset="0" stop-color="#e8ff6a"/><stop offset="1" stop-color="#9fcf1e"/>
    </radialGradient>
    <radialGradient id="{prefix}-fb" cx="0.35" cy="0.3" r="0.9">
      <stop offset="0" stop-color="#b26a38" stop-opacity="0.9"/><stop offset="1" stop-color="#5a2b12" stop-opacity="0"/>
    </radialGradient>
    <clipPath id="{prefix}-bbclip"><circle r="38"/></clipPath>
    <clipPath id="{prefix}-tbclip"><circle r="26"/></clipPath>
    <clipPath id="{prefix}-sbclip"><circle r="42"/></clipPath>
  </defs>"""


def ring_path(rx, ry, steps=72):
    """A closed swoosh: an ellipse ring whose thickness is greatest at the lower left
    and tapers to a hairline at the upper right, like the orbit in the official logo."""
    import math

    outer, inner = [], []
    for k in range(steps):
        t = 2 * math.pi * k / steps
        thick = 0.045 + 0.2 * (1 + math.cos(t - math.radians(150))) / 2
        outer.append((rx * math.cos(t), ry * math.sin(t)))
        inner.append((rx * (1 - thick) * math.cos(t), ry * (1 - thick * 1.5) * math.sin(t)))

    def poly(points):
        return "M" + " L".join(f"{x:.2f} {y:.2f}" for x, y in points) + " Z"

    return poly(outer) + poly(inner[::-1])


def emblem(prefix, cx, cy, s, s_scale=0.62):
    """Italic S inside a tilted gold orbit swoosh; (cx, cy) centre, s scale.
    `s_scale` is the letter's size against the orbit (the favicon makes it bigger)."""
    s_path, sw, asc = text_outline("S", 240)
    ox, oy = -sw / 2, asc / 2
    ring = ring_path(170, 62)
    return f"""
  <defs>
    <linearGradient id="{prefix}-sg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#ffffff"/>
      <stop offset="0.3" stop-color="{GOLD_LIGHT}"/>
      <stop offset="0.65" stop-color="{GOLD}"/>
      <stop offset="1" stop-color="{GOLD_DARK}"/>
    </linearGradient>
    <linearGradient id="{prefix}-og" x1="0" y1="1" x2="1" y2="0">
      <stop offset="0" stop-color="{GOLD_DARK}"/>
      <stop offset="0.5" stop-color="{GOLD}"/>
      <stop offset="1" stop-color="{GOLD_LIGHT}"/>
    </linearGradient>
    <clipPath id="{prefix}-front"><rect x="-200" y="0" width="400" height="120"/></clipPath>
  </defs>
  <g transform="translate({cx:.2f} {cy:.2f}) scale({s:.4f})" stroke-linejoin="round">
    <g transform="rotate(-24)">
      <path d="{ring}" fill="url(#{prefix}-og)" fill-rule="evenodd" stroke="{INK}" stroke-width="5"/>
      <ellipse rx="150" ry="53" fill="none" stroke="#fff" stroke-width="3.5" stroke-dasharray="300 700" stroke-dashoffset="-150" stroke-linecap="round"/>
    </g>
    <g transform="translate({ox * s_scale:.2f} {oy * s_scale:.2f}) scale({s_scale})">
      <path d="{s_path}" fill="url(#{prefix}-sg)" stroke="{INK}" stroke-width="14" paint-order="stroke"/>
    </g>
    <g transform="rotate(-24)" clip-path="url(#{prefix}-front)">
      <path d="{ring}" fill="url(#{prefix}-og)" fill-rule="evenodd" stroke="{INK}" stroke-width="5"/>
    </g>
  </g>"""


def svg_doc(view_w, view_h, body, label):
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {view_w} {view_h}" role="img" aria-label="{label}">
  <title>{label}</title>{body}
</svg>
"""


def build_stacked():
    width, height = 666, 459
    _, w100, _ = wordmark("m", 100, 0, 0, tracking=-1)
    size = 100 * (width - 44) / w100
    word, _, _ = wordmark("stw", size, 22, height - 34, tracking=-1)
    em = emblem("st", 190, 150, 1.0)
    bl = balls("st", 505, 150, 1.45)
    return svg_doc(width, height, em + bl + word, "SARDASPORTS")


def build_horizontal():
    height = 150
    em = emblem("hz", 84, height / 2, 0.5)
    bl = balls("hz", 222, height / 2 + 4, 0.6)
    size = 90
    word, word_w, asc = wordmark("hzw", size, 300, height / 2 + 90 * 0.36, tracking=-1)
    width = int(300 + word_w + 12)
    return svg_doc(width, height, em + bl + word, "SARDASPORTS")


def build_favicon():
    """The emblem alone, big, on a dark rounded tile: the stacked logo's balls and wordmark
    are unreadable at 16 px, the S and its gold orbit are not."""
    size = 512
    em = emblem("fv", size / 2, size / 2 + 4, 1.22, s_scale=1.02)
    body = f'  <rect width="{size}" height="{size}" rx="104" fill="{INK}"/>' + em
    return svg_doc(size, size, body, "SARDASPORTS")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "sardasports-logo.svg").write_text(build_stacked(), encoding="utf-8")
    (OUT / "sardasports-logo-horizontal.svg").write_text(build_horizontal(), encoding="utf-8")
    (APP / "icon.svg").write_text(build_favicon(), encoding="utf-8")
    print("wrote", APP / "icon.svg")
    print("wrote", OUT / "sardasports-logo.svg")
    print("wrote", OUT / "sardasports-logo-horizontal.svg")
