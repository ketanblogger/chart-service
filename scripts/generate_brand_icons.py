"""Regenerate the favicon and app-icon set from the brand sources in app/static/brand.

    .venv/bin/python scripts/generate_brand_icons.py [SOURCE_DIR]

SOURCE_DIR defaults to app/static/brand, which holds the cleaned copies. Point it at the original artwork
only if you know what the originals contain: the files as delivered carried garbage RGB under an alpha of
zero - red and green noise - which is invisible until something resizes or flattens without weighting colour
by alpha, and then it bleeds in as speckle. `clean_alpha` below mattes it away, and the copies in
app/static/brand have already been through it. tests/test_icons.py asserts they stay that way.
"""
import sys
from pathlib import Path

from PIL import Image

SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("app/static/brand")
BRAND = Path("app/static/brand")
ICONS = Path("app/static/icons")
INDIGO = (36, 27, 84)          # --color-primary #241B54

GOLD = (224, 165, 38)

def clean_alpha(im: Image.Image) -> Image.Image:
    """The transparent regions of these sources carry garbage RGB - red and green noise sitting under an
    alpha of zero, left by whatever produced the file.

    It is invisible until something resizes or flattens without weighting RGB by alpha, and then it bleeds
    in as coloured speckle. Pillow's resize does exactly that: it averages RGB and alpha separately, so a
    transparent red pixel contributes its red at full weight to a neighbour's colour.

    Zeroing it is not enough either - that just makes the bleed black instead of red, which shows as a dark
    fringe. So the RGB of every pixel that is not essentially opaque is replaced with the artwork's own gold.
    Any bleed is then gold bleeding into gold, which is invisible at every size. Alpha is untouched, so the
    shape is exactly the artist's."""
    im = im.convert("RGBA")
    r, g, b, a = im.split()
    original = Image.merge("RGB", (r, g, b))
    matte = Image.new("RGB", im.size, GOLD)
    keep = a.point(lambda v: 255 if v >= 200 else 0)
    return Image.merge("RGBA", (*Image.composite(original, matte, keep).split(), a))

def bleed(emblem: Image.Image, size: int, coverage: float) -> Image.Image:
    """Full-bleed indigo square with the emblem centred at `coverage` of the width. No rounded corners:
    iOS and Android apply their own mask, and a baked-in radius shows as slivers inside theirs."""
    out = Image.new("RGBA", (size, size), INDIGO + (255,))
    e = emblem.resize((int(size * coverage),) * 2, Image.LANCZOS)
    off = (size - e.width) // 2
    out.alpha_composite(e, (off, off))
    return out

BRAND.mkdir(parents=True, exist_ok=True); ICONS.mkdir(parents=True, exist_ok=True)

main = clean_alpha(Image.open(SRC / "main-logo.png"))
fav  = clean_alpha(Image.open(SRC / "favicon-source.png"))
app  = Image.open(SRC / "app-icon.png").convert("RGB")
tile = app.crop((42, 41, app.width - 42, app.height - 41))      # drop the white margin

main.save(BRAND / "main-logo.png"); fav.save(BRAND / "favicon-source.png"); app.save(BRAND / "app-icon.png")

# the emblem, lifted off the indigo tile so it can be re-grounded at any coverage
emblem = fav.crop(fav.getchannel("A").getbbox())

for size in (16, 32, 48):
    fav.resize((size, size), Image.LANCZOS).save(ICONS / f"favicon-{size}.png")
ICONS.joinpath("favicon-48.png").unlink()                        # .ico only; no link tag needs 48
# Pillow derives the .ico's sizes from the SOURCE image, so saving from an already-16px one silently
# produces a single 16px entry. Save from a large source and let it build all three.
fav.resize((256, 256), Image.LANCZOS).save(ICONS / "favicon.ico", format="ICO",
                                           sizes=[(16, 16), (32, 32), (48, 48)])

# Apple and Android: full bleed, emblem at 72% (inside the 80% maskable safe zone either way)
for name, size in (("apple-touch-icon-180", 180), ("icon-192", 192), ("icon-512", 512)):
    bleed(emblem, size, 0.72).convert("RGB").save(ICONS / f"{name}.png")
bleed(emblem, 512, 0.62).convert("RGB").save(ICONS / "maskable-icon-512.png")   # tighter: OS crops to a circle

# The header mark, at 3x for a 32px slot. The GRID-LESS emblem, not the full logo: at 32px on a 1x screen
# the kundali lattice inside the planet does not read as a faint chart, it reads as dirt on the gold. The
# full artwork stays for the hero, the reports and anywhere with the pixels to earn its detail.
emblem_96 = emblem.resize((96, 96), Image.LANCZOS)
# re-matte: Pillow zeroes RGB under full transparency on save, so the matte does not survive a resize and
# the saved file would carry black beneath its transparent pixels - invisible in a browser, a dark fringe
# in the next tool that resizes without premultiplying.
r_, g_, b_, a_ = emblem_96.split()
keep_ = a_.point(lambda v: 255 if v >= 200 else 0)
matted_ = Image.composite(Image.merge("RGB", (r_, g_, b_)), Image.new("RGB", emblem_96.size, GOLD), keep_)
Image.merge("RGBA", (*matted_.split(), a_)).save(BRAND / "emblem-96.png")
for p in sorted(list(ICONS.iterdir()) + [BRAND / "emblem-96.png"]):
    im = Image.open(p)
    print(f"  {p.as_posix():44} {im.size[0]}x{im.size[1]} {im.mode} {p.stat().st_size//1024 or 1}KB")
