"""Cover ornaments, drawn as inline SVG - no raster art, no external file, nothing to load.

Everything here is geometry computed in Python and emitted as `<path>` / `<circle>` with class names;
the colours live in templates/print.css. That keeps the cover print-sharp at any size, keeps the page
offline (app/pdf/browser.py aborts every request but the document and the bundled fonts), and keeps it
inside the site CSP.

The motif is a twelve-petal rosette - the twelve rashis - around an eight-pointed star, with a ring of
small dots for the nakshatras. It is used large on the cover and small as a divider and as a part-title
ornament. Nothing here is astrology: it is decoration only, so no chart data comes in.
"""

import math

TAU = math.tau


def _pt(cx: float, cy: float, angle: float, radius: float) -> tuple[float, float]:
    return cx + radius * math.cos(angle), cy + radius * math.sin(angle)


def _n(value: float) -> str:
    """Short, stable number: 12.0 -> '12', 12.3456 -> '12.35'."""
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return text if text not in ("-0", "") else "0"


def _petal(cx: float, cy: float, angle: float, inner: float, outer: float, spread: float) -> str:
    base_x, base_y = _pt(cx, cy, angle, inner)
    tip_x, tip_y = _pt(cx, cy, angle, outer)
    mid = (inner + outer) / 2
    c1_x, c1_y = _pt(cx, cy, angle - spread, mid)
    c2_x, c2_y = _pt(cx, cy, angle + spread, mid)
    return (f"M{_n(base_x)} {_n(base_y)}Q{_n(c1_x)} {_n(c1_y)} {_n(tip_x)} {_n(tip_y)}"
            f"Q{_n(c2_x)} {_n(c2_y)} {_n(base_x)} {_n(base_y)}Z")


def _star(cx: float, cy: float, points: int, inner: float, outer: float, offset: float = 0.0) -> str:
    coords = []
    for index in range(points * 2):
        angle = offset + index * TAU / (points * 2)
        x, y = _pt(cx, cy, angle, outer if index % 2 == 0 else inner)
        coords.append(f"{_n(x)} {_n(y)}")
    return "M" + "L".join(coords) + "Z"


def rosette(size: float = 200.0, *, petals: int = 12, dots: int = 27, cls: str = "rosette") -> str:
    """The full motif, drawn in a `size` x `size` viewBox. Used big on the cover."""
    c = size / 2
    unit = size / 200  # the numbers below are tuned for a 200-unit box
    parts = [f'<svg class="{cls}" viewBox="0 0 {_n(size)} {_n(size)}" xmlns="http://www.w3.org/2000/svg" '
             f'role="presentation" aria-hidden="true">']
    parts.append(f'<g class="{cls}__petals">')
    for index in range(petals):  # the twelve rashis
        parts.append(f'<path d="{_petal(c, c, index * TAU / petals, 34 * unit, 92 * unit, 0.16)}"/>')
    parts.append("</g>")
    parts.append(f'<g class="{cls}__petals-inner">')
    for index in range(petals):  # a half-step rotated inner ring
        parts.append(f'<path d="{_petal(c, c, (index + 0.5) * TAU / petals, 22 * unit, 58 * unit, 0.2)}"/>')
    parts.append("</g>")
    parts.append(f'<g class="{cls}__rings">'
                 f'<circle cx="{_n(c)}" cy="{_n(c)}" r="{_n(97 * unit)}"/>'
                 f'<circle cx="{_n(c)}" cy="{_n(c)}" r="{_n(92 * unit)}"/>'
                 f'<circle cx="{_n(c)}" cy="{_n(c)}" r="{_n(34 * unit)}"/></g>')
    dot_group = [f'<g class="{cls}__dots">']
    for index in range(dots):  # the twenty-seven nakshatras
        x, y = _pt(c, c, index * TAU / dots - TAU / 4, 82 * unit)
        dot_group.append(f'<circle cx="{_n(x)}" cy="{_n(y)}" r="{_n(1.6 * unit)}"/>')
    dot_group.append("</g>")
    parts += dot_group
    parts.append(f'<path class="{cls}__star" d="{_star(c, c, 8, 11 * unit, 28 * unit, -TAU / 4)}"/>')
    parts.append(f'<circle class="{cls}__core" cx="{_n(c)}" cy="{_n(c)}" r="{_n(7 * unit)}"/>')
    parts.append("</svg>")
    return "".join(parts)


def divider(width: float = 120.0, cls: str = "divider") -> str:
    """A rule with a small eight-pointed star in the middle - between the cover blocks and under part titles."""
    height = 14.0
    mid, gap = width / 2, 11.0
    return (f'<svg class="{cls}" viewBox="0 0 {_n(width)} {_n(height)}" xmlns="http://www.w3.org/2000/svg" '
            f'role="presentation" aria-hidden="true">'
            f'<path class="{cls}__rule" d="M0 {_n(height / 2)}H{_n(mid - gap)}M{_n(mid + gap)} {_n(height / 2)}H{_n(width)}"/>'
            f'<path class="{cls}__star" d="{_star(mid, height / 2, 8, 2.2, 6.5, -TAU / 4)}"/>'
            f'<circle class="{cls}__dot" cx="{_n(mid)}" cy="{_n(height / 2)}" r="1.4"/></svg>')


def corner(size: float = 26.0, cls: str = "corner") -> str:
    """One corner flourish of the cover frame; the template rotates it for the other three."""
    return (f'<svg class="{cls}" viewBox="0 0 {_n(size)} {_n(size)}" xmlns="http://www.w3.org/2000/svg" '
            f'role="presentation" aria-hidden="true">'
            f'<path class="{cls}__line" d="M0 {_n(size)}V{_n(size * 0.42)}Q0 0 {_n(size * 0.42)} 0H{_n(size)}"/>'
            f'<path class="{cls}__line2" d="M{_n(size * 0.18)} {_n(size)}V{_n(size * 0.5)}'
            f'Q{_n(size * 0.18)} {_n(size * 0.18)} {_n(size * 0.5)} {_n(size * 0.18)}H{_n(size)}"/>'
            f'<path class="{cls}__star" d="{_star(size * 0.42, size * 0.42, 4, 1.8, 5.5, -TAU / 4)}"/></svg>')
