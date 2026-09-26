"""The FREE Basic Chart PDF: an engine chart printed as a few A5 sheets. **No AI call, ever.**

That is the whole point of this product, so it is worth being blunt about what "no AI call" rests on.
Nothing in this module, in templates/basic.html or on the route that serves it (app/pdf/routes.py,
`POST /api/chart/pdf`) imports `app.ai.client`, loads a report, or touches an entitlement. The input is
one `chart` dict straight out of `engine.compute_chart(..., detail="basic")` plus the D9 that
`engine.navamsa_chart()` derives from it; the output is Chromium's PDF of this template. The marginal
cost of a download is one browser render - about a rupee of a VPS's time, and nothing at all from
Anthropic. tests/test_pdf.py holds that line two ways: it asserts the route never builds an AI client,
and it asserts the rendered HTML contains none of the fields the AI writes.

**Why this is not the paid book with sections suppressed.** A "hide the paid parts" flag is one edit away
from leaking them, and the edit that leaks them does not look dangerous. So this is a separate document
with a separate template, and that template can draw exactly seven block types - facts, table, chart,
banner, note, trust, caveats, excluded - every one of which is engine data or one of our own labels. The
block types that carry the writer's prose in templates/report.html (`prose`, `bullets`, `subsections`,
`windows`, `remedies`, `highlights`) have no macro here at all. Handing this page AI text would not
produce a leak; it would produce nothing.

What is on the sheets, in order - all of it computed, none of it interpreted:

    1. who this is for, the birth details, lagna / rashi / nakshatra
       the "How this chart was made" trust box, and the engine's accuracy caveats if it flagged any
    2. the D1 lagna chart and the D9 navamsa chart
    3. the graha table: sign, degree, nakshatra and pada, house, retrograde, combust
    4. mangal dosha status; sade sati status, with the cycle's dates
    5. the current mahadasha and antardasha, with dates
    6. what this free chart does NOT include, and the disclaimer

`render_basic_html()` returns a complete document; app/pdf/service.py renders and caches it and
app/pdf/routes.py serves it. There is no contents page, so it is a ONE-pass render (`html_to_pdf`),
unlike the book.
"""

from markupsafe import Markup

from app.ai.prompts import DISCLAIMERS  # the same disclaimer text the paid reports carry. No client.
from app.engine import navamsa_chart

from . import blocks as B
from . import cover as cover_art
from .book import Anchors
from .labels import LANGS, Labels
from .render import PDF_DIR, clean_name, env, page_css, page_size_name


def _sections(L: Labels, chart: dict, d9: dict | None, script: str, anchors: Anchors,
              approximate_time: bool = False) -> list[dict]:
    """The body of the sheet: one section per heading, in print order. Every block comes from
    app/pdf/blocks.py and is built from the engine chart - nothing here writes a sentence about it."""
    sections: list[dict] = []

    def section(heading: str, items: list, *, new_page: bool = False) -> None:
        kept = [block for block in items if block]
        if kept:
            # only a section that PRINTS a heading takes an anchor, so the ids stay "hd-1", "hd-2" ...
            # in document order - the same invariant the book's outline zip depends on
            sections.append({"anchor": anchors.next() if heading else "", "heading": heading,
                             "blocks": kept, "new_page": new_page})

    # Both charts are drawn SMALL so that the D1 and the D9 share one page. At full size each figure is
    # taller than half the A5 text box, so they would take a page each and the free sheet would run to
    # seven pages of half-empty paper - which people print at home, at their own cost.
    charts = [B.chart_block(L, chart, script, L["chart_heading"], small=True)]
    if d9:
        charts.append(B.chart_block(L, d9, script, L["navamsa_heading"], small=True,
                                    note_text=L["navamsa_note"]))
    section("", charts, new_page=True)

    # The vargottama note rides with the graha table rather than under the D9 figure: the two charts fill
    # that page exactly, and one trailing line would spill onto a page of its own. It reads just as well
    # here - it is a statement about where grahas fall in both charts, which is what the table shows.
    section(L["grahas_heading"], [B.graha_table(L, chart, title=""),
                                  B.vargottama_note(L, d9) if d9 else None], new_page=True)

    if chart.get("mangal_dosha") and (chart.get("grahas") or {}).get("Mars"):
        section(L["mangal_heading"], B.mangal_blocks(L, chart))

    sade = chart.get("sade_sati")
    if sade:
        # The phase table is printed for a cycle that is RUNNING. The brief is "status, with dates when
        # active", and the fact tiles already name the span of a cycle that has not begun - a seven-row
        # phase breakdown of a sade sati fifteen years away is a page of paper for no reader.
        running = (sade.get("cycle") or {}).get("which") == "current"
        section(L["sade_heading"], [*B.sade_blocks(L, sade),
                                    B.sade_periods(L, sade) if running else None])

    dasha = chart.get("dasha") or {}
    if dasha.get("current"):
        # The dasha section repeats the approximate-time warning in one line. The caveats box on page one
        # is the full statement, but this is the part it most affects - a median shift of about two years -
        # and it is four pages away from anyone who has turned to the dates to read them.
        section(L["dasha_heading"], [B.dasha_now(L, dasha),
                                     B.note(L["acc_approx_dasha"]) if approximate_time else None,
                                     B.note(L["as_of_note"].format(date=L.date(dasha.get("as_of"))))])

    section("", [B.excluded_block(L)])
    return sections


def build_basic_view(chart: dict, *, language: str = "en", name: str | None = None,
                     chart_script: str | None = None, page_size: str | None = None,
                     approximate_time: bool = False) -> dict:
    """Everything templates/basic.html needs, from one engine chart.

    `chart` is `engine.compute_chart(..., detail="basic")` output; the D9 is derived here so there is
    exactly one place the free PDF's navamsa comes from. `name` is a cover name from a query parameter
    and goes through the same `clean_name` the book uses."""
    lang = language if language in LANGS else "en"
    L = Labels(lang)
    script = chart_script if chart_script in ("en", "deva") else ("en" if lang == "en" else "deva")
    size = page_size_name(page_size)
    name = clean_name(name)

    try:
        d9 = navamsa_chart(chart)
    except (KeyError, TypeError, ValueError):  # a chart without the longitudes the D9 needs
        d9 = None

    anchors = Anchors()
    head_anchor = anchors.next()  # the title is the first heading in the document
    # facts, then the caveats, then the trust box - the order app/static/js/render.js uses on the chart
    # page, and the order that keeps all five blocks on page one. A caveat put after the trust box does
    # not fit under it and gets a page of its own, which is a strange thing to hand somebody.
    first = [B.key_facts(L, chart), B.accuracy_block(L, chart, approximate_time=approximate_time),
             B.trust_block(L, ai=False)]
    sections = [{"anchor": "", "heading": "", "blocks": [block for block in first if block],
                 "new_page": False}]
    sections += _sections(L, chart, d9, script, anchors, approximate_time)

    ayanamsa = ((chart.get("meta") or {}).get("ayanamsa") or {}).get("degrees")
    return {
        "lang": lang, "L": L.t, "page_size": size, "title": L["basic_title"],
        "head": {
            "anchor": head_anchor, "site": L["site_name"], "title": L["basic_title"],
            "product_name": L["basic_product"], "tagline": L["basic_tagline"], "note": L["basic_note"],
            "name": name, "rows": B.birth_rows(L, chart.get("input") or {}),
        },
        "sections": sections,
        "closing": {"anchor": anchors.next()},
        "disclaimer": DISCLAIMERS[lang],  # never print a chart without it
        "calc_note": L["calc_note"].format(ayanamsa=f"{ayanamsa:.4f}°" if isinstance(ayanamsa, (int, float)) else ""),
        "page_css": page_css(L, size, name or L["basic_title"], title=L["basic_running_title"]),
        "corner": Markup(cover_art.corner()),
    }


def render_basic_html(chart: dict, *, language: str = "en", name: str | None = None,
                      chart_script: str | None = None, page_size: str | None = None,
                      approximate_time: bool = False) -> str:
    """The complete HTML document for the free chart PDF. Fonts are referenced as `fonts/<file>.ttf`,
    relative to the document URL, exactly as the book's are (app/pdf/browser.py serves them)."""
    view = build_basic_view(chart, language=language, name=name, chart_script=chart_script,
                            page_size=page_size, approximate_time=approximate_time)
    css = Markup((PDF_DIR / "templates" / "print.css").read_text(encoding="utf-8"))
    return env().get_template("basic.html").render(css=css, **view)
