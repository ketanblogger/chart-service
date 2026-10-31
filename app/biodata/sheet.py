"""Build the biodata's HTML - the one document the PDF, the .docx and the on-page preview come from.

THE PHOTO IS NEVER WRITTEN TO DISK. It arrives on the POST, is checked, is base64'd into the HTML as
a data URI, and goes out of scope when the response does. There is no file to serve, so there is no
URL that can be guessed, no directory that can be listed and nothing to forget to delete. That costs
a little memory per render and buys the only privacy promise worth making about somebody's face.

What is checked before it is embedded: the byte signature (not the filename, which a browser lets
anybody set), the size, and that it is one of the three formats every printer and Word can show. A
file that fails any of those is dropped and the sheet renders without a photo rather than failing -
the typing is the expensive thing on this page, and losing a form because a photo was a HEIC is a
worse outcome than a sheet the person can add a photo to in Word.
"""
from __future__ import annotations

import base64

from markupsafe import Markup

from . import core, designs, model

# `app.pdf.render` IS IMPORTED INSIDE build(), NOT HERE. At module level it closes a cycle:
# app.pdf -> basic -> blocks -> chart_svg -> labels -> app.web.site -> app.web -> routes, which
# registers this package's routes at import time -> app.biodata.pages -> this module -> back into
# app.pdf.render while app.pdf.blocks is still half-initialised. The failure is an ImportError for
# a name that plainly exists, raised only when something imports app.pdf FIRST - so the whole
# application worked and one test module could not be collected. app/blog/admin.py defers an import
# for the same reason and says so.

MAX_PHOTO_BYTES = 6 * 1024 * 1024

# Byte signatures, because the browser's content-type and the filename are both caller-controlled.
_SIGNATURES = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"RIFF", "image/webp"),        # ...with "WEBP" at offset 8, checked below
)

HEADINGS = {"en": "Marriage biodata", "hi": "विवाह बायोडाटा", "mr": "विवाह बायोडाटा"}
# Said under the kundli block when the birth time was not given, so the open rows are explained
# rather than just looking unfinished.
NO_TIME_NOTE = {
    "en": "Rows marked in italics depend on the birth time, which was not given. Add it and these "
          "fill in exactly.",
    "hi": "तिरछे अक्षरों वाली पंक्तियाँ जन्म समय पर निर्भर हैं, जो नहीं दिया गया। समय जोड़ने पर ये "
          "पूरी भर जाएँगी।",
    "mr": "तिरक्या अक्षरांतील ओळी जन्मवेळेवर अवलंबून आहेत, जी दिलेली नाही. वेळ दिल्यास त्या नेमक्या "
          "भरतील.",
}


def photo_data_uri(raw: bytes | None) -> str | None:
    """A data URI for a photo we are willing to print, or None. Never touches the filesystem."""
    if not raw or len(raw) > MAX_PHOTO_BYTES:
        return None
    kind = None
    for signature, mime in _SIGNATURES:
        if raw.startswith(signature):
            kind = mime
            break
    if kind == "image/webp" and raw[8:12] != b"WEBP":
        return None
    if kind is None:
        return None
    return f"data:{kind};base64," + base64.b64encode(raw).decode("ascii")


def build(fields: dict, *, language: str = "en", design_key: str | None = None,
          paid: bool = False, photo: bytes | None = None, frame: str = "square",
          kundli: dict | None = None, qr: dict | None = None) -> str:
    """The complete sheet. `kundli` is app/biodata/core.from_birth's answer, or None."""
    if language not in HEADINGS:
        language = "en"
    chosen = designs.design(design_key, paid=paid)
    sections = model.filled_sections(fields, language=language)

    rows = []
    if kundli:
        rows = [{"label": kundli["labels"][key], "text": kundli["rows"][key]["text"],
                 "known": kundli["rows"][key]["known"]}
                for key in core.ROWS]
        # Devak and gotra are free text, not computed - they sit with the kundli rows because that is
        # where a family looks for them, but they come from the form.
        for key in ("devak", "gotra"):
            if fields.get(key):
                rows.append({"label": kundli["labels"][key], "text": fields[key], "known": True})

    from app.pdf.render import PDF_DIR, env

    css = Markup((PDF_DIR.parent / "biodata" / "sheet.css").read_text(encoding="utf-8"))
    return env(language).get_template("biodata.html").render(
        css=css,
        lang=language,
        title=HEADINGS[language],
        heading=fields.get("full_name") or HEADINGS[language],
        subheading=HEADINGS[language] if fields.get("full_name") else "",
        design=chosen,
        frame=frame if frame in designs.FRAMES and paid else "square",
        photo=photo_data_uri(photo) if paid else None,
        sections=sections,
        kundli=bool(rows),
        kundli_rows=rows,
        kundli_title=model.SECTION_TITLES["kundli"][language],
        kundli_note=(NO_TIME_NOTE[language] if kundli and not kundli["from_time"] else ""),
        qr=qr,
        made_on=("" if paid else designs.MADE_ON[language]),
    )
