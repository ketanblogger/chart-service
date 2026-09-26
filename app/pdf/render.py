"""Report JSON (docs/API.md, "Paid AI reports") -> print-ready HTML for the book. No browser needed here.

The pieces: app/pdf/book.py builds the parts and chapters, app/pdf/blocks.py builds what is inside them,
app/pdf/cover.py draws the cover ornaments, templates/report.html + print.css lay the pages out.

Two sources, never mixed:
- charts, graha / dasha / koota / dosha tables come from `report["data"]` (engine output);
- prose comes from the AI - plain text, escaped by Jinja autoescape, never trusted as HTML.

Page size: A5 portrait by default (`PDF_PAGE_SIZE=a4` for A4). A5 is the booklet format this product is
print-and-bind for: it is what a print shop folds 2-up out of A4, and it is the one that stays readable on
a phone, which is how most buyers will actually read a Rs 249 book.

Table of contents: `render_report_html(..., toc_pages=None)` lays the TOC out with fixed-width placeholders;
`heading_ids()` then gives the ids of every heading in the finished HTML, in document order, which
app/pdf/browser.py zips against the outline of the first-pass PDF and hands back as `toc_pages` for the
second pass. Filling in real digits cannot reflow the book, so the numbers stay true.
"""

import os
import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

from app.ai.prompts import DISCLAIMERS

from . import cover as cover_art
from .blocks import accuracy_block, birth_rows, key_facts, trust_block
from .book import Anchors, build_parts, build_toc
from .labels import LANGS, Labels

PDF_DIR = Path(__file__).resolve().parent
FONTS_DIR = PDF_DIR / "fonts"
TEMPLATE_VERSION = 3  # bump when the look changes; it is part of the PDF cache file name

# name -> (@page size, top, side, bottom margin). Generous margins: this is a book, not a form.
# print.css carries the printable height of one page (--page-box = paper height - top - bottom); keep both in step.
PAGE_SIZES = {
    "a5": ("A5 portrait", "14mm", "13mm", "16mm"),
    "a4": ("A4 portrait", "20mm", "18mm", "22mm"),
}
PAPER_WIDTH_MM = {"a5": 148, "a4": 210}
_BODY_SIZE = re.compile(r'<body class="size-([a-z0-9]+)"')
DEFAULT_PAGE_SIZE = "a5"

# Symbols an author might type that the bundled Noto fonts do not contain. Left alone, Chromium would take
# them from whatever system font has them (or print tofu on a bare server), so swap them for covered ones.
_SYMBOLS = str.maketrans({
    "\u2192": "\u2013", "\u2190": "\u2013", "\u2194": "\u2013", "\u21d2": "\u2013", "\u2794": "\u2013", "\u279c": "\u2013",
    "\u2713": "", "\u2714": "", "\u25cf": "\u2022", "\u25aa": "\u2022", "\u25a0": "\u2022", "\u25c6": "\u2022",
    "\u2605": "*", "\u2606": "*", "\u2726": "*", "\u2248": "~", "\u2264": "<=", "\u2265": ">=",
    "\ufe0f": "",
})

_HEADING_ID = re.compile(r"<h[1-6]\b[^>]*\bid=\"([^\"]+)\"", re.I)
_HEADING_ANY = re.compile(r"<h[1-6]\b", re.I)


def _finalize(value):
    """Runs on every value the template prints (before autoescaping)."""
    return value.translate(_SYMBOLS) if isinstance(value, str) and not isinstance(value, Markup) else value


_env = Environment(loader=FileSystemLoader(PDF_DIR / "templates"), autoescape=select_autoescape(["html"]),
                   trim_blocks=True, lstrip_blocks=True, finalize=_finalize)


def env() -> Environment:
    """The one Jinja environment both documents are rendered through - autoescaping, and `_finalize` on
    every value printed. app/pdf/basic.py renders the free chart sheet through this same environment, so
    a symbol we have no glyph for cannot slip into one document by being rendered through another."""
    return _env

MAX_NAME_LENGTH = 60      # what a customer may put on the cover
MAX_HEADER_LENGTH = 32    # what fits beside "Kundali Report" in the running head of every page


def clean_name(name: str | None) -> str:
    """A customer's name for the cover: printable text only, one line, bounded length."""
    if not name:
        return ""
    text = " ".join("".join(ch for ch in str(name) if ch.isprintable()).split())
    return text[:MAX_NAME_LENGTH].strip()


def running_head(name: str, title: str) -> str:
    """The left half of the running head. The name comes from a query parameter, so it is already stripped
    of anything unprintable by `clean_name`; here it is also kept SHORT, because the running head shares one
    line with "Kundali Report" on the right and a 60-character name (or a 60-character Devanagari one, which
    is wider) would run into it. `css_string` escapes whatever is left."""
    text = (name or title or "").strip()
    return text if len(text) <= MAX_HEADER_LENGTH else text[:MAX_HEADER_LENGTH - 1].rstrip() + "\u2026"


def css_string(text: str) -> str:
    """A CSS string literal (used for the @page margin boxes). Escapes everything that could end the
    string or the <style>."""
    out = []
    for ch in text:
        if ch in '"\\<>&\'' or ord(ch) < 0x20:
            out.append(f"\\{ord(ch):x} ")
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


def page_size_name(page_size: str | None = None) -> str:
    name = (page_size or os.getenv("PDF_PAGE_SIZE") or DEFAULT_PAGE_SIZE).strip().lower()
    return name if name in PAGE_SIZES else DEFAULT_PAGE_SIZE


def heading_ids(html: str) -> list[str]:
    """The id of every heading in a rendered document, in document order - the list Chromium's PDF outline
    is zipped against. A heading without an id would silently shift that zip, so it is an error here."""
    ids = _HEADING_ID.findall(html)
    total = len(_HEADING_ANY.findall(html))
    if total != len(ids):
        raise ValueError(f"{total - len(ids)} of {total} headings have no id: the book template must give every one")
    return ids


def content_width_px(html: str) -> int:
    """How wide one printed page's content box is, in CSS pixels, for the size class this document carries.

    The browser lays the book out in a viewport of exactly this width (app/pdf/browser.py), which is what
    Chromium itself does when it prints - so anything that sticks out can be found and reported instead of
    silently shrinking the whole document."""
    match = _BODY_SIZE.search(html)
    size = match.group(1) if match and match.group(1) in PAGE_SIZES else DEFAULT_PAGE_SIZE
    side = float(PAGE_SIZES[size][2].removesuffix("mm"))
    return round((PAPER_WIDTH_MM[size] - 2 * side) / 25.4 * 96)


def page_css(L: Labels, page_size: str, running: str, *, title: str | None = None) -> Markup:
    """The @page rules: size, margins and the margin boxes (running head, page number, footer).

    Chromium supports @page margin boxes and named pages, so the cover carries no furniture, the contents
    page carries its own head, and every other page gets the running head and the page number.

    `title` is the right half of the running head, and defaults to the book's. The free chart sheet
    (app/pdf/basic.py) passes its own, so a reader never has a page that says "Kundali Report" on a
    document that is not one."""
    size, top, side, bottom = PAGE_SIZES[page_size]
    fonts = '"Report Devanagari", "Report Sans"'
    head = f"font-family: {fonts}; font-size: 7.5pt; color: #6a6f7d; letter-spacing: .02em;"
    return Markup(f"""
@page {{
  size: {size};
  margin: {top} {side} {bottom};
  @top-left {{ content: {css_string(running)}; {head} vertical-align: bottom; padding-bottom: 3mm; }}
  @top-right {{ content: {css_string(title or L["running_title"])}; {head} vertical-align: bottom; padding-bottom: 3mm; }}
  @bottom-left {{ content: {css_string(L["site_name"])}; {head} vertical-align: top; padding-top: 3.5mm; }}
  @bottom-right {{ content: {css_string(L["page"] + " ")} counter(page) {css_string(" " + L["of"] + " ")} counter(pages);
                   {head} vertical-align: top; padding-top: 3.5mm; white-space: nowrap; }}
}}
@page cover {{
  @top-left {{ content: ""; }} @top-right {{ content: ""; }}
  @bottom-left {{ content: ""; }} @bottom-right {{ content: ""; }}
}}
@page contents {{
  @top-left {{ content: {css_string(L["contents"])}; {head} vertical-align: bottom; padding-bottom: 3mm; }}
}}
""")


def _cover(L: Labels, report: dict, people: list[dict], names: dict) -> dict:
    """The front cover: brand, title, who it is for, the three facts that identify the chart, ornaments."""
    data = report.get("data") or {}
    chart = data.get("chart") or {}
    facts = key_facts(L, chart)["items"] if chart else []
    meta = report.get("meta") or {}
    return {
        "site": L["site_name"], "tagline": L["cover_tagline"], "note": L["cover_note"],
        "title": (report.get("title") or "").strip() or L.product(report.get("product", ""), report.get("product_name", "")),
        "product_name": L.product(report.get("product", ""), report.get("product_name", "")),
        "prepared_for": L["prepared_for"], "name": names.get("self") or names.get("boy") or "",
        "people": people, "facts": [(label, value) for label, value, _ in facts],
        "report_date": f"{L['report_date']}: {L.date(meta.get('as_of'))}",
        "rosette": Markup(cover_art.rosette(200)), "divider": Markup(cover_art.divider()),
        "corner": Markup(cover_art.corner()),
    }


def build_view(report: dict, *, names: dict | None = None, chart_script: str | None = None,
               page_size: str | None = None, toc_pages: dict[str, int] | None = None) -> dict:
    """Everything the template needs. names: {"self" | "boy" | "girl": str}. chart_script: "en" | "deva".
    toc_pages: heading anchor -> printed page number (second pass), or None (first pass)."""
    lang = report.get("language") if report.get("language") in LANGS else "en"
    L = Labels(lang)
    product, data = report.get("product", ""), report.get("data") or {}
    names = {key: clean_name(value) for key, value in (names or {}).items()}
    script = chart_script if chart_script in ("en", "deva") else ("en" if lang == "en" else "deva")
    size = page_size_name(page_size)

    people: list[dict] = []
    calc_meta = None
    if "matching" in data:
        for who in ("boy", "girl"):
            chart = data[f"{who}_chart"]
            calc_meta = calc_meta or chart.get("meta")
            nak = chart["janma_nakshatra"]
            people.append({"title": f"{L[who]}{': ' + names[who] if names.get(who) else ''}",
                           "rows": birth_rows(L, chart.get("input") or {}) + [
                (L["lagna"], L.sign(chart["lagna"]["sign"])), (L["rashi"], L.sign(chart["moon_rashi"])),
                (L["nakshatra"], f"{L.nakshatra(nak)}, {L['pada']} {nak.get('pada', '')}")]})
    elif "chart" in data:
        calc_meta = data["chart"].get("meta")
        people.append({"title": "", "rows": birth_rows(L, data["chart"].get("input") or {})})

    # The front-matter page, between the cover and the contents: what this report is, in one
    # paragraph, and how it was made. The trust rules want the trust box on
    # "the cover or first page", and the cover is full - so it opens the first page the reader reads
    # through, ahead of the contents rather than buried behind forty chapters of them. The engine's
    # accuracy caveats sit with it: they are facts about the whole report, not about one chapter.
    single = data.get("chart") if isinstance(data.get("chart"), dict) else None
    front = {"trust": trust_block(L, ai=True),
             "caveats": accuracy_block(L, single) if single else None}

    anchors = Anchors()
    cover = _cover(L, report, people, names)
    cover["anchor"] = anchors.next()  # the cover title is the first heading in the document
    contents_anchor = anchors.next()
    parts = build_parts(report, L, script, names, anchors)
    closing = {"anchor": anchors.next(), "heading": L["disclaimer"]}

    ayanamsa = ((calc_meta or {}).get("ayanamsa") or {}).get("degrees")
    running = running_head(cover["name"], cover["title"])
    return {
        "lang": lang, "L": L.t, "page_size": size,
        "product_name": cover["product_name"], "title": cover["title"],
        "summary": (report.get("summary") or "").strip(),
        "cover": cover, "contents_anchor": contents_anchor, "closing": closing, "front": front,
        "toc": build_toc(L, parts, toc_pages, closing=closing), "parts": parts,
        "report_id": report.get("id", ""),
        "disclaimer": (report.get("disclaimer") or "").strip() or DISCLAIMERS[lang],  # never print a report without it
        "calc_note": L["calc_note"].format(ayanamsa=f"{ayanamsa:.4f}°" if isinstance(ayanamsa, (int, float)) else ""),
        "page_css": page_css(L, size, running),
        "divider": Markup(cover_art.divider()),
    }


def render_report_html(report: dict, *, names: dict | None = None, chart_script: str | None = None,
                       page_size: str | None = None, toc_pages: dict[str, int] | None = None) -> str:
    """The complete HTML document. Fonts are referenced as `fonts/<file>.ttf`, relative to the document URL
    (app/pdf/browser.py serves them from FONTS_DIR)."""
    view = build_view(report, names=names, chart_script=chart_script, page_size=page_size, toc_pages=toc_pages)
    css = Markup((PDF_DIR / "templates" / "print.css").read_text(encoding="utf-8"))
    return _env.get_template("report.html").render(css=css, **view)
