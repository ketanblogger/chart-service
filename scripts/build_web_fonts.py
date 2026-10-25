"""Build the self-hosted Devanagari web fonts from the TTFs the PDF renderer already bundles.

    uv pip install brotli          # once: fontTools needs it to write woff2
    .venv/bin/python scripts/build_web_fonts.py            # writes app/static/fonts/*.woff2
    .venv/bin/python scripts/build_web_fonts.py --check    # fails if the built files are out of date

WHY SELF-HOST AT ALL. `--font` in site.css is a SYSTEM stack: it NAMES "Noto Sans Devanagari" and hopes the
device has it. Most phones in India do; a desktop with a thin font set does not, and then two of the three
language trees render as boxes - which is exactly what happened to a screenshot browser on this machine and
would happen to a real reader on such a device. The Latin tree is unaffected and stays on system fonts.

WHAT IS IN THE SUBSET, and it is not a judgement call: the same unicode ranges `app/pdf/templates/print.css`
already declares for its Devanagari face, read out of that file rather than written again here. If the PDF's
coverage changes, this changes with it. Latin, digits and punctuation are deliberately NOT included - the
@font-face carries the same `unicode-range`, so Latin text never even requests this file and keeps using the
system font it already used.

The TTFs are the four in app/pdf/fonts, under the SIL Open Font License (OFL.txt beside them), which permits
subsetting and redistribution - the licence file is copied next to the built fonts so it travels with them.
"""

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SOURCE = ROOT / "app" / "pdf" / "fonts"
OUT = ROOT / "app" / "static" / "fonts"
PRINT_CSS = ROOT / "app" / "pdf" / "templates" / "print.css"
# Regular and Bold are the two STATIC faces that exist. The brief asked for 400 and 600; there is no 600 face
# to build one from, and a browser asked for 600 with 400 and 700 available picks 700, which is what the
# headings on this site want anyway. Synthesising a 600 would mean shipping a fake weight.
FACES = {"NotoSansDevanagari-Regular.ttf": 400, "NotoSansDevanagari-Bold.ttf": 700}


def unicode_ranges() -> str:
    """The Devanagari coverage print.css declares, as fontTools wants it (`U+0900-097F` -> `0900-097F`)."""
    css = PRINT_CSS.read_text(encoding="utf-8")
    found = re.search(r"unicode-range:\s*([^;]+);", css)
    if not found:
        raise SystemExit("print.css no longer declares a unicode-range; this script reads it from there")
    return ",".join(part.strip().removeprefix("U+") for part in found.group(1).split(","))


def build(check: bool) -> int:
    from fontTools import subset

    ranges = unicode_ranges()
    OUT.mkdir(parents=True, exist_ok=True)
    stale = []
    for name, weight in FACES.items():
        source = SOURCE / name
        target = OUT / (source.stem + ".subset.woff2")
        before = target.read_bytes() if target.is_file() else None
        options = subset.Options(flavor="woff2", layout_features="*", desubroutinize=True,
                                 drop_tables=["DSIG"], notdef_outline=True, recalc_bounds=True)
        font = subset.load_font(str(source), options)
        subsetter = subset.Subsetter(options=options)
        subsetter.populate(unicodes=subset.parse_unicodes(ranges))
        subsetter.subset(font)
        subset.save_font(font, str(target), options)
        font.close()
        after = target.read_bytes()
        print(f"  {target.name:44} {len(after) / 1024:6.1f} KB  (from {source.stat().st_size / 1024:.0f} KB "
              f"TTF, weight {weight})")
        if check and before != after:
            stale.append(target.name)
            if before is None:
                target.unlink()
            else:
                target.write_bytes(before)
    licence = OUT / "OFL.txt"
    if not licence.is_file():
        licence.write_bytes((SOURCE / "OFL.txt").read_bytes())
        print(f"  {licence.name:44} copied beside the fonts it covers")
    if stale:
        print("\nOUT OF DATE: " + ", ".join(stale) + " - run this script without --check and commit the result.")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Subset the Devanagari fonts for the web.")
    parser.add_argument("--check", action="store_true", help="fail if the committed files are out of date")
    args = parser.parse_args(argv)
    print(f"subsetting to {unicode_ranges()}")
    return build(args.check)


if __name__ == "__main__":
    raise SystemExit(main())
