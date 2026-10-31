"""The biodata designs: three free, the rest behind the ninety-nine rupee unlock.

A DESIGN IS DATA, NOT A TEMPLATE. Twenty templates would be twenty places to fix a layout bug, so
there is one sheet template (app/pdf/templates/biodata.html) and a design is a set of CSS custom
properties plus a named ornament. That keeps every design the same document with the same fields in
the same order, which is what a family comparing two printouts actually wants.

NO ART THAT IS NOT OURS. Every ornament here is geometry this repository draws - CSS borders and
inline SVG paths written by hand. There is no traced motif, no stock flourish and no stock photo
(the repository is public and AGPL; see docs/CREDITS.md).

AND NO IMAGE OF A DEITY. Several of these are the "Ganesh" designs that marriage biodatas in
Maharashtra and the north conventionally open with, and what they carry is the WRITTEN INVOCATION -
॥ श्री गणेशाय नमः ॥ - set as type, above a geometric ornament. That is what is printed on the real
sheets, it is what the keyword is asking for, and it needs no picture of Ganapati: this project does
not generate or ship images of deities. A family that wants a figure on the sheet can paste one into
the .docx, which is their choice to make and not ours to make for them.
"""
from __future__ import annotations

# THE ONLY TWO FACES THIS REPOSITORY SHIPS, named exactly as app/pdf/templates/print.css declares
# them. Devanagari comes first and is restricted to its unicode-range by that @font-face, so Latin
# falls through to Report Sans; naming any other family here is how Devanagari becomes tofu, which
# this project has already shipped once.
#
# SO THERE IS NO SERIF / SANS DISTINCTION BETWEEN DESIGNS. A serif design would mean shipping a
# third face - a licence to check, a credits entry, two more files in every PDF - or rendering a
# font the headless browser may not have, and the fallback for Devanagari is a row of boxes on a
# document somebody is about to hand to a prospective family. The twenty designs differ by colour,
# ornament, weight and spacing, which is where a biodata's character actually lives.
# UNQUOTED ON PURPOSE. These land inside a <style> block in a Jinja template, and Jinja autoescapes
# - which is right for HTML and ruinous here: the quoted form arrived in the document as
# `&#34;Report Devanagari&#34;`, the declaration was invalid, Chromium fell back to DejaVu, and every
# Devanagari character printed as a box on a sheet whose whole point is being handed to a family.
# A multi-word family name needs no quotes in CSS, and an unquoted one has nothing left to escape.
HEAD_FONT = "Report Devanagari, Report Sans"
BODY_FONT = "Report Devanagari, Report Sans"

# Ornaments, each drawn by app/pdf/templates/biodata.html from geometry in this repository.
ORNAMENTS = ("none", "rule", "double-rule", "corner-brackets", "woven-border", "arch", "lotus-rule",
             "diamond-row", "scallop")

INVOCATIONS = {
    "ganesh": "॥ श्री गणेशाय नमः ॥",
    "swastik": "॥ ॐ ॥",
    "none": "",
}

# (key, free, invocation, ornament, tokens) - tokens are the CSS custom properties the sheet reads.
_DESIGNS = (
    # ---- the three free ones. Deliberately the three most asked for, not three leftovers: a plain
    # printable sheet, a traditional one with the invocation, and a modern one.
    ("classic", True, "none", "double-rule",
     {"ink": "#1a1a1a", "accent": "#7a5c1e", "paper": "#ffffff", "band": "#f6f1e6",
      "head": HEAD_FONT, "body": BODY_FONT}),
    ("traditional", True, "ganesh", "woven-border",
     {"ink": "#2b1a08", "accent": "#a8321e", "paper": "#fffdf7", "band": "#fdf0dd",
      "head": HEAD_FONT, "body": BODY_FONT}),
    ("modern", True, "none", "rule",
     {"ink": "#14181f", "accent": "#1f5f8b", "paper": "#ffffff", "band": "#eef4f8",
      "head": HEAD_FONT, "body": BODY_FONT}),
    # ---- premium
    ("ganesh-saffron", False, "ganesh", "arch",
     {"ink": "#2a1505", "accent": "#c2651b", "paper": "#fffaf2", "band": "#fdeedb",
      "head": HEAD_FONT, "body": BODY_FONT}),
    ("ganesh-maroon", False, "ganesh", "woven-border",
     {"ink": "#23110f", "accent": "#7d1f2b", "paper": "#fffaf9", "band": "#f8e6e6",
      "head": HEAD_FONT, "body": BODY_FONT}),
    ("ganesh-gold", False, "ganesh", "diamond-row",
     {"ink": "#241c08", "accent": "#9a7b16", "paper": "#fffdf4", "band": "#faf3dc",
      "head": HEAD_FONT, "body": BODY_FONT}),
    ("swastik-cream", False, "swastik", "corner-brackets",
     {"ink": "#2a2214", "accent": "#8a6a22", "paper": "#fffcf3", "band": "#f8f2e1",
      "head": HEAD_FONT, "body": BODY_FONT}),
    ("temple-arch", False, "ganesh", "arch",
     {"ink": "#1d1410", "accent": "#8c4a1f", "paper": "#fffaf5", "band": "#f7ebe0",
      "head": HEAD_FONT, "body": BODY_FONT}),
    ("lotus-rose", False, "none", "lotus-rule",
     {"ink": "#2a1620", "accent": "#a93b63", "paper": "#fffafc", "band": "#fbe9f0",
      "head": HEAD_FONT, "body": BODY_FONT}),
    ("peacock-teal", False, "none", "scallop",
     {"ink": "#10211f", "accent": "#126b67", "paper": "#f8fffe", "band": "#e2f3f1",
      "head": HEAD_FONT, "body": BODY_FONT}),
    ("marathi-kesari", False, "ganesh", "double-rule",
     {"ink": "#2b1a06", "accent": "#b5651d", "paper": "#fffdf6", "band": "#fcf0de",
      "head": HEAD_FONT, "body": BODY_FONT}),
    ("minimal-slate", False, "none", "none",
     {"ink": "#16181c", "accent": "#4a5663", "paper": "#ffffff", "band": "#f2f4f6",
      "head": HEAD_FONT, "body": BODY_FONT}),
    ("minimal-ivory", False, "none", "rule",
     {"ink": "#1d1b16", "accent": "#7c6f55", "paper": "#fffef9", "band": "#f6f3ea",
      "head": HEAD_FONT, "body": BODY_FONT}),
    ("minimal-mono", False, "none", "none",
     {"ink": "#000000", "accent": "#000000", "paper": "#ffffff", "band": "#f2f2f2",
      "head": HEAD_FONT, "body": BODY_FONT}),
    ("royal-indigo", False, "swastik", "corner-brackets",
     {"ink": "#121630", "accent": "#2f3a86", "paper": "#fcfdff", "band": "#e8ebfa",
      "head": HEAD_FONT, "body": BODY_FONT}),
    ("emerald-leaf", False, "none", "lotus-rule",
     {"ink": "#121d13", "accent": "#1f6b3a", "paper": "#fafffb", "band": "#e5f4ea",
      "head": HEAD_FONT, "body": BODY_FONT}),
    ("sandal-beige", False, "ganesh", "scallop",
     {"ink": "#241e14", "accent": "#8d6f3a", "paper": "#fffdf7", "band": "#f6efe1",
      "head": HEAD_FONT, "body": BODY_FONT}),
    ("rangoli-border", False, "swastik", "woven-border",
     {"ink": "#221414", "accent": "#a33a2a", "paper": "#fffcfa", "band": "#fae8e3",
      "head": HEAD_FONT, "body": BODY_FONT}),
    ("pearl-grey", False, "none", "double-rule",
     {"ink": "#1a1c1e", "accent": "#5d6b76", "paper": "#ffffff", "band": "#eff2f4",
      "head": HEAD_FONT, "body": BODY_FONT}),
    ("sunrise-amber", False, "none", "diamond-row",
     {"ink": "#2a1d08", "accent": "#c08418", "paper": "#fffdf4", "band": "#fdf2d9",
      "head": HEAD_FONT, "body": BODY_FONT}),
)

NAMES = {
    "classic": {"en": "Classic", "hi": "क्लासिक", "mr": "क्लासिक"},
    "traditional": {"en": "Traditional", "hi": "पारंपरिक", "mr": "पारंपरिक"},
    "modern": {"en": "Modern", "hi": "आधुनिक", "mr": "आधुनिक"},
    "ganesh-saffron": {"en": "Ganesh saffron", "hi": "गणेश केसरी", "mr": "गणेश केशरी"},
    "ganesh-maroon": {"en": "Ganesh maroon", "hi": "गणेश मैरून", "mr": "गणेश मरून"},
    "ganesh-gold": {"en": "Ganesh gold", "hi": "गणेश सुनहरा", "mr": "गणेश सुवर्ण"},
    "swastik-cream": {"en": "Swastik cream", "hi": "स्वस्तिक क्रीम", "mr": "स्वस्तिक क्रीम"},
    "temple-arch": {"en": "Temple arch", "hi": "मंदिर कमान", "mr": "मंदिर कमान"},
    "lotus-rose": {"en": "Lotus rose", "hi": "कमल गुलाबी", "mr": "कमळ गुलाबी"},
    "peacock-teal": {"en": "Peacock teal", "hi": "मोरपंखी", "mr": "मोरपंखी"},
    "marathi-kesari": {"en": "Marathi kesari", "hi": "मराठी केसरी", "mr": "मराठी केशरी"},
    "minimal-slate": {"en": "Minimal slate", "hi": "मिनिमल स्लेट", "mr": "मिनिमल स्लेट"},
    "minimal-ivory": {"en": "Minimal ivory", "hi": "मिनिमल आइवरी", "mr": "मिनिमल आयव्हरी"},
    "minimal-mono": {"en": "Minimal mono", "hi": "मिनिमल मोनो", "mr": "मिनिमल मोनो"},
    "royal-indigo": {"en": "Royal indigo", "hi": "रॉयल इंडिगो", "mr": "रॉयल इंडिगो"},
    "emerald-leaf": {"en": "Emerald leaf", "hi": "एमराल्ड पत्ती", "mr": "एमराल्ड पान"},
    "sandal-beige": {"en": "Sandal beige", "hi": "चंदन बेज", "mr": "चंदन बेज"},
    "rangoli-border": {"en": "Rangoli border", "hi": "रंगोली किनार", "mr": "रांगोळी किनार"},
    "pearl-grey": {"en": "Pearl grey", "hi": "पर्ल ग्रे", "mr": "पर्ल ग्रे"},
    "sunrise-amber": {"en": "Sunrise amber", "hi": "सनराइज़ अम्बर", "mr": "सनराइज अंबर"},
}

DESIGNS = {
    key: {"key": key, "free": free, "invocation": INVOCATIONS[invocation],
          "invocation_key": invocation, "ornament": ornament, "tokens": tokens,
          "names": NAMES[key]}
    for key, free, invocation, ornament, tokens in _DESIGNS
}
FREE = tuple(key for key, design in DESIGNS.items() if design["free"])
PREMIUM = tuple(key for key, design in DESIGNS.items() if not design["free"])
DEFAULT = "classic"

# Printed on a free sheet, small, at the foot. Not a watermark across the page: a biodata is shown to
# a prospective family and a bar across the middle of it would make the tool an embarrassment rather
# than a credit. The premium sheet carries nothing.
MADE_ON = {"en": "Made on RashiKundli.com", "hi": "RashiKundli.com पर बनाया गया",
           "mr": "RashiKundli.com वर तयार केले"}

# Photo frames, premium only. Shapes, not pictures.
FRAMES = ("square", "rounded", "oval", "arch", "ring")
FRAME_NAMES = {
    "square": {"en": "Square", "hi": "वर्ग", "mr": "चौरस"},
    "rounded": {"en": "Rounded", "hi": "गोल कोने", "mr": "गोल कोपरे"},
    "oval": {"en": "Oval", "hi": "अंडाकार", "mr": "अंडाकृती"},
    "arch": {"en": "Arch", "hi": "कमान", "mr": "कमान"},
    "ring": {"en": "Ring", "hi": "वलय", "mr": "वलय"},
}


def design(key: str | None, *, paid: bool = False) -> dict:
    """The design to render with. An unknown key, or a premium one without payment, falls back to
    the default rather than erroring: the sheet is the point, and a 400 here would lose typing."""
    found = DESIGNS.get(key or DEFAULT)
    if found is None or (not found["free"] and not paid):
        found = DESIGNS[DEFAULT]
    return found


def choices(*, language: str, paid: bool = False) -> list[dict]:
    """Every design, in order, with whether this visitor can use it - so the page can show the
    premium ones as something to unlock rather than hiding what the ninety-nine rupees buys."""
    return [{"key": key, "name": d["names"][language], "free": d["free"],
             "usable": d["free"] or paid, "ornament": d["ornament"],
             "tokens": d["tokens"], "invocation": d["invocation"]}
            for key, d in DESIGNS.items()]
