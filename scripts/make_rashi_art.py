#!/usr/bin/env python3
"""Display-size rashi symbols, built from the line glyphs this repository already owns.

NOTHING NEW IS DRAWN. app/static/img/glyphs.svg already holds twelve original rashi symbols, drawn here
from primitives on a 24x24 grid - circles, arcs, crosses and arrows, the shapes these symbols have
always had. Redrawing them larger by hand would give the site two sets that drift apart; this reads
those exact paths and sets each one inside the brand mark's own geometry.

THE STYLE IS THE LOGO'S, because it is the logo's shapes: favicon.svg is a gold ring with a filled disc
inside it and a small disc on the orbit. Each card here is that ring, with the rashi's own line symbol
where the disc sits, and the small accent disc kept so the family reads as one set.

No stock art, nothing traced, no figurative depiction of anything - which is also why these are symbols
rather than illustrations of animals or people.
"""
from __future__ import annotations

import re
from pathlib import Path

# Derived from this file's location, never written out: an absolute path from somebody's laptop is
# both useless to anybody else and a detail a public repository should not carry.
ROOT = Path(__file__).resolve().parents[1]
GLYPHS = ROOT / "app/static/img/glyphs.svg"
GOLD = "#E0A526"

RASHIS = ("mesha", "vrishabha", "mithuna", "karka", "simha", "kanya",
          "tula", "vrishchika", "dhanu", "makara", "kumbha", "meena")


def paths_for(slug: str) -> str:
    """The <path> elements of one rashi symbol, exactly as glyphs.svg draws them."""
    source = GLYPHS.read_text(encoding="utf-8")
    match = re.search(rf'<symbol id="r-{slug}"[^>]*>(.*?)</symbol>', source, re.S)
    if not match:
        raise SystemExit(f"no symbol for {slug} in {GLYPHS}")
    return match.group(1).strip()


def card(slug: str) -> str:
    """One 96x96 card: the brand's ring, the rashi's symbol inside it, the orbit's accent disc.

    The symbol is drawn on a 24x24 grid, so it is translated and scaled to sit in the middle at about
    half the card - large enough to read at 48px on a phone, small enough that the ring still frames it.
    Stroke width is scaled with it so the line weight matches the ring rather than thinning.
    """
    inner = paths_for(slug)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96" width="96" height="96"
     role="img" aria-labelledby="t-{slug}" fill="none">
  <title id="t-{slug}">{slug}</title>
  <!-- The orbit, at the logo's proportion: favicon.svg is r=13 of 32, which is r=39 of 96. -->
  <circle cx="48" cy="48" r="39" stroke="{GOLD}" stroke-width="2.6"/>
  <!-- The small disc on the orbit, kept so these read as one family with the mark. -->
  <circle cx="79.5" cy="27.6" r="5.1" fill="{GOLD}"/>
  <!-- The rashi's own symbol, from glyphs.svg, scaled 24 -> 44 and centred. -->
  <g transform="translate(26 26) scale(1.8333)" stroke="{GOLD}" stroke-width="1.6"
     stroke-linecap="round" stroke-linejoin="round">
    {inner}
  </g>
</svg>
'''


def main() -> int:
    out = ROOT / "app/static/img/rashi"
    out.mkdir(exist_ok=True)
    for slug in RASHIS:
        (out / f"{slug}.svg").write_text(card(slug), encoding="utf-8")
    print(f"  {len(RASHIS)} cards -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
