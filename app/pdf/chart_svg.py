"""North Indian (diamond) kundali as inline SVG, drawn from the engine's chart dict.

A line-for-line port of `chartSvg()` in app/static/js/render.js - same 400x400 geometry, same house
layout, same abbreviations, same class names - so the PDF chart and the web chart always agree.
tests/test_pdf.py runs both against the same chart and compares every text element and coordinate.
If you change one, change the other.

Input: chart["houses"] (house -> sign + graha keys), chart["grahas"][key]["retrograde"], chart["lagna"].
Nothing is calculated here.
"""

from html import escape

from .labels import GRAHA_ABBR

GRAHA_KEYS = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu"]

# House 1 is the top-centre diamond, houses run anticlockwise. c = centre for graha text,
# n = position of the sign number, per = grahas per text line (side triangles are narrow).
HOUSE_LAYOUT = [
    {"c": (200, 95), "n": (200, 178), "per": 3},   # 1
    {"c": (100, 38), "n": (100, 84), "per": 3},    # 2
    {"c": (40, 100), "n": (84, 105), "per": 2},    # 3
    {"c": (100, 200), "n": (178, 205), "per": 3},  # 4
    {"c": (40, 300), "n": (84, 305), "per": 2},    # 5
    {"c": (100, 366), "n": (100, 326), "per": 3},  # 6
    {"c": (200, 305), "n": (200, 232), "per": 3},  # 7
    {"c": (300, 366), "n": (300, 326), "per": 3},  # 8
    {"c": (360, 300), "n": (316, 305), "per": 2},  # 9
    {"c": (300, 200), "n": (222, 205), "per": 3},  # 10
    {"c": (360, 100), "n": (316, 105), "per": 2},  # 11
    {"c": (300, 38), "n": (300, 84), "per": 3},    # 12
]
LINE_HEIGHT = 19


def _num(value: float) -> str:
    """Format like JavaScript does: 185.5 -> '185.5', 200.0 -> '200'."""
    return str(int(value)) if float(value).is_integer() else repr(float(value))


def chart_svg(chart: dict, script: str = "en", label: str = "") -> str:
    """script: "en" (Su, Mo ...) or "deva" (सू, चं ...). Returns an <svg> string, fully escaped."""
    script = "deva" if script == "deva" else "en"
    abbr = GRAHA_ABBR[script]
    step = 27 if script == "deva" else 29
    lagna_sign = (chart.get("lagna") or {}).get("sign") or {}
    aria = label or f"North Indian kundali chart. Lagna {lagna_sign.get('name', '')}."
    parts = [
        f'<svg class="kundali kundali--{script}" viewBox="0 0 400 400" role="img" '
        f'xmlns="http://www.w3.org/2000/svg" aria-label="{escape(aria, quote=True)}">'
        '<rect class="kundali__frame" x="1.5" y="1.5" width="397" height="397"/>'
        '<path class="kundali__lines" d="M1.5 1.5 398.5 398.5M398.5 1.5 1.5 398.5M200 1.5 398.5 200 200 398.5 1.5 200Z"/>'
    ]
    grahas = chart.get("grahas") or {}
    for house in chart.get("houses") or []:
        number = house.get("house")
        if not isinstance(number, int) or not 1 <= number <= 12:
            continue
        layout = HOUSE_LAYOUT[number - 1]
        parts.append(f'<text class="kundali__sign" x="{layout["n"][0]}" y="{layout["n"][1]}">'
                     f'{escape(str(house["sign"]["index"]))}</text>')

        items = [("Lagna", True, False)] if number == 1 else []
        for key in house.get("grahas") or []:
            # Rahu/Ketu are always retrograde (mean node), so the marker would only add clutter.
            retro = bool((grahas.get(key) or {}).get("retrograde")) and key not in ("Rahu", "Ketu")
            items.append((key, False, retro))

        per = layout["per"]
        lines = [items[i:i + per] for i in range(0, len(items), per)]
        y0 = layout["c"][1] - ((len(lines) - 1) * LINE_HEIGHT) / 2 + 5
        for row, line in enumerate(lines):
            x0 = layout["c"][0] - ((len(line) - 1) * step) / 2
            for col, (key, is_lagna, retro) in enumerate(line):
                cls = "kundali__graha kundali__graha--lagna" if is_lagna else "kundali__graha"
                marker = '<tspan class="kundali__retro" dy="-6">R</tspan>' if retro else ""
                parts.append(f'<text class="{cls}" x="{_num(x0 + col * step)}" y="{_num(y0 + row * LINE_HEIGHT)}">'
                             f'{escape(abbr.get(key, key))}{marker}</text>')
    parts.append("</svg>")
    return "".join(parts)


def chart_legend(script: str, names: dict[str, str]) -> list[tuple[str, str]]:
    """[(abbreviation, full name)] for Lagna + the nine grahas. `names` maps key -> display name."""
    abbr = GRAHA_ABBR["deva" if script == "deva" else "en"]
    return [(abbr[key], names.get(key, key)) for key in ["Lagna", *GRAHA_KEYS]]
