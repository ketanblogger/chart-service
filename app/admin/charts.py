"""Inline SVG charts. No library, no script, no request to anybody.

WHY SVG BUILT HERE. The CSP in app/hardening.py allows scripts only from self and Razorpay's checkout, and
the admin pages add no asset of their own - so a charting library would mean a new CSP host or a new bundled
file, for four small charts. Inline SVG needs neither: it is markup in the page the server already renders,
it prints, and it degrades to the table beside it. Hover is native `<title>` elements, which browsers show
as tooltips with no JavaScript at all.

COLOURS. The brand palette in app/static/css/site.css is a palette for a page, not for a chart, and it does
not survive the checks a categorical series set has to pass: deep indigo reads gray at chart size, and
Celestial Gold against Saffron separates by only 14.7 (normal vision, OKLab x100) - below the floor of 15,
which means a full-colour reader cannot reliably tell two adjacent stack segments apart. So the four series
slots below are re-stepped from the same hue families and validated: worst adjacent pair 16.9 (protan),
13.9 (tritan), 24.4 (normal vision); every slot inside the lightness band and above the chroma floor. Gold
is below 3:1 against white, which is why **every chart here ships with a legend AND the same numbers as a
table beside it** - that is the required relief, not a nice-to-have.

Light only, deliberately: the rest of this site has one theme, and an admin page that alone flipped with the
operating system's setting would be the only surface here whose colours are not the ones the brand tests
check.

ONE AXIS PER CHART. Revenue and order count are two scales, so they are two charts (`sparkline` twice),
never one with two y-axes. A stacked bar is one scale by construction, which is what makes it legal here.
"""

from html import escape

# Validated categorical slots, in fixed order. NEVER cycled: a fifth series folds into "other" instead.
SERIES = ("#5B4BC4", "#0D9488", "#E0A526", "#C0468E")
INK = "#1E1B2E"        # text on a chart: a text token, never a series colour
MUTED = "#5C5875"
GRID = "#E3DEF0"
SURFACE = "#FFFFFF"
GOOD = "#1F6E3F"       # status, reserved: never used as a series
BAD = "#A13D2B"
BAR_GAP = 2            # the surface gap between adjacent bars and stacked segments


def _num(value) -> float:
    return 0.0 if value is None else float(value)


def _title(text: str) -> str:
    return f"<title>{escape(str(text))}</title>"


def sparkline(values, labels=None, *, width: int = 520, height: int = 72, colour: str = SERIES[0],
              fmt="{:.0f}", unit: str = "") -> str:
    """A line over a daily series. `None` in `values` is a gap, not a zero - a day with no data is not a
    day with a value of nothing, and drawing it as zero invents a crash.

    The last point is the only labelled one. A number on every point is unreadable at 30 days and is the
    thing the table below the chart is for."""
    points = [None if value is None else float(value) for value in values]
    labels = list(labels or [""] * len(points))
    if not points:
        return ""
    real = [value for value in points if value is not None]
    top = max(real) if real else 1.0
    top = top if top > 0 else 1.0
    left, right, bottom = 4, 46, 6
    span = max(1, len(points) - 1)
    plot_width = width - left - right

    def x(index: int) -> float:
        return left + plot_width * index / span

    def y(value: float) -> float:
        return height - bottom - (height - bottom - 8) * (value / top)

    segments, current = [], []
    for index, value in enumerate(points):
        if value is None:
            if len(current) > 1:
                segments.append(current)
            current = []
        else:
            current.append((x(index), y(value)))
    if len(current) > 1:
        segments.append(current)

    parts = [f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" role="img" '
             f'class="chart" preserveAspectRatio="none">',
             f'<line x1="{left}" y1="{height - bottom}" x2="{width - right}" y2="{height - bottom}" '
             f'stroke="{GRID}" stroke-width="1"/>']
    for segment in segments:
        path = " ".join(f"{'M' if index == 0 else 'L'}{px:.1f},{py:.1f}" for index, (px, py) in enumerate(segment))
        parts.append(f'<path d="{path}" fill="none" stroke="{colour}" stroke-width="2" '
                     f'stroke-linejoin="round" stroke-linecap="round"/>')
    # One marker per point, >= 8px across, each carrying its own native tooltip. A 2px surface ring keeps
    # overlapping markers legible where a weekend of equal values stacks them.
    for index, value in enumerate(points):
        if value is None:
            continue
        parts.append(f'<circle cx="{x(index):.1f}" cy="{y(value):.1f}" r="4" fill="{colour}" '
                     f'stroke="{SURFACE}" stroke-width="2">'
                     f'{_title(f"{labels[index]}: {fmt.format(value)}{unit}")}</circle>')
    last = next((index for index in range(len(points) - 1, -1, -1) if points[index] is not None), None)
    if last is not None:
        parts.append(f'<text x="{x(last) + 8:.1f}" y="{y(points[last]) + 4:.1f}" fill="{INK}" '
                     f'font-size="12" font-weight="600">{escape(fmt.format(points[last]) + unit)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def stacked_bars(rows, series, *, width: int = 640, height: int = 150, fmt="{:.2f}", unit: str = "Rs ") -> str:
    """One bar per day, split into `series` = [(label, key), ...] read out of each row's `spend` dict.

    Segments are separated by a 2px surface gap and the top of each bar is rounded, so the stack reads as
    parts of one day rather than as a solid block. A segment of zero draws nothing - a hairline for a day
    with no rashifal run would be a run that did not happen."""
    rows = list(rows)
    if not rows:
        return ""
    totals = [sum(_num((row.get("spend") or {}).get(key)) for _, key in series) for row in rows]
    top = max(totals) if totals else 0.0
    top = top if top > 0 else 1.0
    left, bottom, top_pad = 4, 18, 8
    plot_height = height - bottom - top_pad
    step = (width - left * 2) / len(rows)
    bar = max(3.0, min(26.0, step - 3))
    parts = [f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" role="img" class="chart">',
             f'<line x1="{left}" y1="{height - bottom}" x2="{width - left}" y2="{height - bottom}" '
             f'stroke="{GRID}" stroke-width="1"/>']
    for index, row in enumerate(rows):
        centre = left + step * (index + 0.5)
        cursor = height - bottom
        spend = row.get("spend") or {}
        detail = ", ".join(f"{label} {unit}{_num(spend.get(key)):.2f}" for label, key in series)
        for slot, (label, key) in enumerate(series):
            value = _num(spend.get(key))
            if value <= 0:
                continue
            segment = plot_height * value / top
            if segment < 1:
                continue
            cursor -= segment
            parts.append(f'<rect x="{centre - bar / 2:.1f}" y="{cursor:.1f}" width="{bar:.1f}" '
                         f'height="{max(1.0, segment - BAR_GAP):.1f}" rx="2" '
                         f'fill="{SERIES[slot % len(SERIES)]}">'
                         f'{_title(str(row.get("day", "")) + ": " + detail)}</rect>')
            cursor -= BAR_GAP
    # Only the first and last day are labelled: thirty date labels at this width overlap into a gray band.
    parts.append(f'<text x="{left}" y="{height - 4}" fill="{MUTED}" font-size="11">'
                 f'{escape(str(rows[0].get("day", "")))}</text>')
    parts.append(f'<text x="{width - left}" y="{height - 4}" fill="{MUTED}" font-size="11" '
                 f'text-anchor="end">{escape(str(rows[-1].get("day", "")))}</text>')
    parts.append("</svg>")
    return "".join(parts)


def bar_row(value, top, label: str = "", *, colour: str = SERIES[0], width: int = 120, height: int = 10) -> str:
    """One horizontal bar for a table cell (a duration, a share). Anchored at the left, rounded right end."""
    top = float(top) if top else 1.0
    length = max(0.0, min(1.0, _num(value) / top)) * width
    return (f'<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" class="chart-bar">'
            f'<rect x="0" y="1" width="{max(1.0, length):.1f}" height="{height - 2}" rx="2" fill="{colour}">'
            f'{_title(label)}</rect></svg>')


def legend(series) -> str:
    """Always rendered for two or more series: identity is never colour alone."""
    items = "".join(
        f'<span class="legend__item"><span class="legend__swatch" style="background:{SERIES[index % len(SERIES)]}">'
        f'</span>{escape(str(label))}</span>' for index, (label, _key) in enumerate(series))
    return f'<div class="legend">{items}</div>'
