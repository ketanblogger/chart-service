"""The book cover is one printed page tall, and what goes on it is not.

A delivered Marathi book had its report-date line ("अहवालाची तारीख") printed ON the gold frame at the foot
of the cover. The cause was not the date line: `.cover` is a fixed-height box (`--page-box`) laid out as a
flex column, a flex item does not shrink below its own content by default, and so ANY cover with more
content than page pushed its footer straight out of the bottom - `margin-top: auto` on the footer
collapsing to nothing - until `overflow: hidden` cut the footer off the page altogether.

What varies, measured on real reports at A5 before the fix:

  * the SCRIPT: the same cover sets 20-30px taller in Devanagari than in Latin (line-height 1.78 for
    hi/mr, and taller line boxes) - a real Marathi book ran 6.9px past the frame where its English twin
    cleared it by 15px;
  * the TITLE, which the model writes and nothing bounds: the longest real one is 92 characters, four
    lines at A5, and that report ran 77.6px past the frame IN ENGLISH;
  * the BIRTH BLOCK: a birth place with a city name adds a coordinates row, and a matching report carries
    two whole blocks - 211px past the frame in Marathi, with the date line gone from the page.

Three different causes, three different sizes of overflow, and only one of them is about Devanagari. That
is why this file measures the box rather than checking that a line moved up: a fixed nudge big enough for
the first is nowhere near the third, and would waste a third of the cover on every ordinary book.

The claim made here is the structural one - the footer is inside the frame and the content block above it
never reaches it - over every language, both page sizes, and the three shapes that made it fail.
"""

import json
from pathlib import Path

import pytest

from app.pdf import browser as pdf_browser
from app.pdf.labels import LANGS
from app.pdf.render import PAGE_SIZES, content_width_px, render_report_html

FIXTURES = Path(__file__).parent / "fixtures"

# Invented people. tests/ is published (tests/test_publication_safety.py), so no customer ever appears here.
SELF_NAME = "अनुष्का देशपांडे"
PARTNER_NAME = "माधवी जोशी"
# The longest cover title seen in production, to the character: the model writes the title and no part of
# the pipeline bounds it, so the cover has to survive one this long.
LONG_TITLE = "The Kundali of a Karka Lagna: Exalted Guru, Steady Mars, and a Mind Sharpened Under Pressure"

# What the cover measures. `.cover-frame::before` is the gold rule; its `inset` is read from the computed
# style rather than copied here, so moving the frame in the stylesheet moves this check with it.
GEOMETRY_JS = """() => {
  const q = s => document.querySelector(s);
  const cover = q('.cover'), frame = q('.cover-frame'), foot = q('.cover-foot'), main = q('.cover-main');
  const facts = q('.cover-facts');
  const inset = parseFloat(getComputedStyle(frame, '::before').top);
  const box = frame.getBoundingClientRect();
  const clipped = el => el ? Math.round(el.scrollHeight - el.clientHeight) : 0;
  return {
    inset,
    frameBottom: box.bottom,
    ruleBottom: box.bottom - inset,
    footBottom: foot.getBoundingClientRect().bottom,
    dateBottom: foot.querySelector('p').getBoundingClientRect().bottom,
    mainBottom: main.getBoundingClientRect().bottom,
    footTop: foot.getBoundingClientRect().top,
    coverClipped: Math.round(cover.scrollHeight - cover.clientHeight),
    mainClipped: clipped(main),
    factsClipped: clipped(facts),
    hasFacts: !!facts,
  };
}"""


def book(language: str) -> dict:
    return json.loads((FIXTURES / f"kundali_book_{language}.json").read_text(encoding="utf-8"))


def with_city(report: dict) -> dict:
    """The fixture chart is given as bare coordinates; a real order carries the city the buyer picked, and
    `blocks.birth_rows` then prints the city AND the coordinates - one more line on the cover."""
    report = json.loads(json.dumps(report))
    report["data"]["chart"]["input"]["city"] = "Miraj, Maharashtra"
    return report


def as_matching(report: dict) -> dict:
    """The fixture bent into the shape `render.build_view` reads for a two-person cover. Only the cover is
    measured here, and the cover reads exactly these four fields per person."""
    report = with_city(report)
    chart = report["data"]["chart"]
    partner = json.loads(json.dumps(chart))
    partner["input"]["city"] = "Navi Mumbai, Maharashtra"  # a longer place: the widest row on that side
    report["data"] = {**report["data"], "matching": {}, "boy_chart": chart, "girl_chart": partner}
    report["data"].pop("chart")  # a real matching report has no single chart, so its cover carries no facts
    report["product"] = "matching-report"
    return report


def with_long_title(report: dict) -> dict:
    report = with_city(report)
    report["title"] = LONG_TITLE
    return report


# (name, how to build it, whether the cover must still hold all of its content, whether it carries the
# three chart facts). The first two are ordinary orders and must lose nothing; the third is the
# 92-character title, where the cover is over budget whatever it does and those three facts are what
# print.css gives up - the book reprints all three on its first content page.
SHAPES = [
    ("delivered", with_city, True, True),
    ("matching", as_matching, True, False),
    ("long-title", with_long_title, False, True),
]


@pytest.fixture(scope="module")
def chromium():
    ok, reason = pdf_browser.chromium_available()
    if not ok:
        pytest.skip(f"headless Chromium cannot launch here: {reason}")


@pytest.fixture(scope="module")
def measure(chromium):
    """One browser for the whole module; each document is laid out in a page's content box under print
    media, which is the layout Chromium prints from (app/pdf/browser.py sets up the real render the
    same way)."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        instance = playwright.chromium.launch(**pdf_browser.launch_options())
        try:
            def run(document: str) -> dict:
                served = {"html": document}
                context = instance.new_context(service_workers="block",
                                               viewport={"width": content_width_px(document), "height": 1000})
                try:
                    context.route("**/*", pdf_browser._serve(served))
                    page = context.new_page()
                    page.emulate_media(media="print")
                    page.goto(f"{pdf_browser.ORIGIN}/report.html", wait_until="load")
                    return page.evaluate(GEOMETRY_JS)
                finally:
                    context.close()

            yield run
        finally:
            instance.close()


@pytest.mark.browser
@pytest.mark.parametrize("shape,build,keeps_everything,has_facts", SHAPES)
@pytest.mark.parametrize("language", LANGS)
@pytest.mark.parametrize("page_size", sorted(PAGE_SIZES))
def test_the_cover_footer_stays_inside_the_frame(measure, page_size, language, shape, build,
                                                keeps_everything, has_facts):
    # There is no Hindi book fixture; the Marathi one is the right shape and script for it, and the cover
    # reads nothing from the fixture that the language switch does not re-label.
    report = build(book(language if language == "en" else "mr"))
    report["language"] = language
    names = {"self": SELF_NAME if language != "en" else "Anushka Deshpande",
             "boy": SELF_NAME if language != "en" else "Anushka Deshpande",
             "girl": PARTNER_NAME if language != "en" else "Madhavi Joshi"}
    document = render_report_html(report, names=names, page_size=page_size)
    where = f"{shape} / {language} / {page_size}"

    box = measure(document)
    assert box["inset"] > 0, "the cover frame rule should be an inset pseudo-element"

    # The defect, stated as geometry: the report-date line, and the footer it sits in, are inside the rule.
    assert box["dateBottom"] <= box["ruleBottom"] + 0.5, (
        f"{where}: the report-date line is {box['dateBottom'] - box['ruleBottom']:.1f}px past the cover frame")
    assert box["footBottom"] <= box["ruleBottom"] + 0.5, (
        f"{where}: the cover footer is {box['footBottom'] - box['ruleBottom']:.1f}px past the cover frame")

    # ... and it is inside it because the block above it never reaches it, not because something was nudged.
    assert box["mainBottom"] <= box["footTop"] + 0.5, (
        f"{where}: the cover content runs {box['mainBottom'] - box['footTop']:.1f}px into the footer")

    # Nothing may be pushed off the page box either: that is how the date line used to disappear entirely.
    assert box["coverClipped"] == 0, f"{where}: {box['coverClipped']}px of the cover is off the page"

    assert box["hasFacts"] is has_facts, f"{where}: the cover should{'' if has_facts else ' not'} carry chart facts"
    if keeps_everything:
        assert (box["mainClipped"], box["factsClipped"]) == (0, 0), (
            f"{where}: an ordinary cover lost content - {box['mainClipped']}px of the block and "
            f"{box['factsClipped']}px of the facts. The cover has to HOLD these, not clip them")
    else:
        # The over-budget cover gives up the facts and nothing else: no arbitrary slice of the block.
        assert box["mainClipped"] == 0, (
            f"{where}: the cover block itself was clipped ({box['mainClipped']}px). Only the facts may give")
