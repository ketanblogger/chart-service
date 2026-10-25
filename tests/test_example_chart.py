"""The labelled example chart on the chart tools, and the twelve rashi symbols.

TWO RULES HOLD THIS TOGETHER. The example is drawn by the same function that draws a reader's own
chart, so the diagram teaching somebody to read a kundli cannot drift from the kundli they get. And it
is INLINE, because an SVG behind `<img>` is sandboxed away from the site's webfont and renders
Devanagari as boxes on any device without a face of its own - which is how the first version of this
came out, on this machine.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.web import pages
from app.web.example_chart import EXAMPLE_BIRTH, example_chart

client = TestClient(app)
PARTIAL = Path("app/web/templates/_example_chart.html").read_text(encoding="utf-8")
CHART_PAGES = {"en": "/birth-chart", "hi": "/hi/kundli", "mr": "/mr/kundali"}
RASHIS = ("mesha", "vrishabha", "mithuna", "karka", "simha", "kanya",
          "tula", "vrishchika", "dhanu", "makara", "kumbha", "meena")


@pytest.mark.parametrize("lang,path", CHART_PAGES.items())
def test_the_example_chart_is_on_every_chart_tool(lang, path):
    html = client.get(path).text
    assert "example-chart" in html, path
    assert pages.ui(lang)["example_chart_heading"] in html, path
    for note in pages.ui(lang)["example_chart_notes"]:
        assert note in html, (path, note[:30])


def test_it_is_not_on_tools_whose_result_is_not_a_chart():
    """A matching page's answer is a score, and a Sade Sati page's is a date range. A chart panel on
    either would be explaining an output they do not produce."""
    for path in ("/horoscope-matching", "/sade-sati", "/mangal-dosha"):
        assert "example-chart" not in client.get(path).text, path


def test_it_is_drawn_by_the_same_function_as_a_readers_own_chart():
    """NOT A SECOND DRAWING OF THE SAME DIAGRAM. The first time the real chart changed, a hand-built
    copy would quietly carry on teaching the old one."""
    from app.engine.chart import compute_chart
    from app.pdf.chart_svg import chart_svg

    expected = chart_svg(compute_chart(**EXAMPLE_BIRTH), script="deva",
                         label=pages.ui("hi")["example_chart_aria"])
    assert str(example_chart("hi")) == expected


def test_the_diagram_is_inline_and_not_an_image_file():
    """An SVG loaded through <img> cannot reach the site's webfont; its text is drawn with whatever
    face the DEVICE has. Every Devanagari glyph in the first version of this was a box."""
    # The template's own comment EXPLAINS why there is no <img>, so the comment is stripped before
    # looking - the first version of this test failed on its own explanation.
    markup = re.sub(r"\{#.*?#\}", "", PARTIAL, flags=re.S)
    assert "<img" not in markup, "an <img> here cannot render Devanagari reliably"
    html = client.get("/mr/kundali").text
    panel = html.split('class="card example-chart"', 1)[1].split("</section>", 1)[0]
    assert "<svg" in panel, "the chart is not inline"
    # The Devanagari abbreviations really are in the page, which is the thing <img> could not do.
    assert "सू" in panel and "ल" in panel


def test_the_example_says_it_is_an_example_in_every_language():
    """Nobody may mistake an invented chart for their own."""
    for lang, path in CHART_PAGES.items():
        from markupsafe import escape

        note = str(escape(pages.ui(lang)["example_chart_note"]))
        assert note in client.get(path).text, path


def test_the_birth_behind_it_is_invented():
    """No real birth data anywhere in this repository, fixtures included."""
    assert EXAMPLE_BIRTH["birth_date"].year == 1991 and EXAMPLE_BIRTH["tz"] == "Asia/Kolkata"


def test_every_rashi_has_a_symbol_and_they_are_all_different():
    """Twelve files, twelve distinct drawings. A copy-paste slip would give two signs one symbol, and
    nothing on the page would say so."""
    art = Path("app/static/img/rashi")
    bodies = {}
    for key in RASHIS:
        f = art / f"{key}.svg"
        assert f.is_file(), f"no symbol for {key}"
        assert f.stat().st_size < 4096, f"{key}.svg is larger than a symbol needs to be"
        bodies[key] = f.read_text(encoding="utf-8")
    assert len(set(bodies.values())) == 12, "two signs share a drawing"


def test_the_symbol_sits_on_the_rashi_hub_with_alt_text_in_that_language():
    for lang, path in (("en", "/horoscope/libra"), ("hi", "/hi/rashifal/tula"),
                       ("mr", "/mr/rashi-bhavishya/tula")):
        html = client.get(path).text
        assert "/static/img/rashi/tula.svg" in html, path
        alt = pages.ui(lang)["rashi_symbol_alt"].split("{")[0].strip()
        assert re.search(r'alt="[^"]*' + re.escape(alt[:6]), html) or alt == "", path
        assert 'width="88" height="88"' in html, f"{path} reserves no space for the symbol"


def test_the_example_chart_is_outside_the_holder_the_readers_own_chart_goes_into():
    """TWO CHARTS ON ONE PAGE NOW. render.js writes the reader's own into #chart-holder, and the
    example sits in its own panel - a browser test asking for "svg.kundali" on this page matched both
    and failed in strict mode, which is the polite version of this problem.

    The impolite version is anything that reaches for the chart by class and silently gets the
    example: a screenshot, a PDF, a test asserting the reader's own chart appeared. So the structural
    separation is asserted here rather than left as a convention.
    """
    html = client.get("/birth-chart").text
    panel = html.split('class="card example-chart"', 1)[1].split("</section>", 1)[0]
    assert "chart-holder" not in panel, "the example sits inside the reader's own chart holder"
    assert "<svg" in panel

    # And the holder the reader's chart lands in is empty until they ask for one.
    holder = html.split('id="chart-holder"', 1)
    if len(holder) > 1:
        assert "<svg" not in holder[1].split("</div>", 1)[0], \
            "something is already drawn in the reader's chart holder"


@pytest.mark.parametrize("script,mark", [("en", "R"), ("deva", "व")])
def test_the_retrograde_mark_follows_the_script(script, mark):
    """THE SITE WAS CHANGING ALPHABET HALFWAY THROUGH ONE IDEA. A Hindi page writes वक्री in its own
    positions table and the sky panel beside it marks a retrograde graha with व - and the chart in the
    middle of the same page put a Latin R on it.

    app/pdf/chart_svg.py and chartSvg() in render.js both carry this table, and tests/test_pdf.py
    compares the two outputs element by element, so a change to one without the other fails there.
    """
    import datetime as dt
    import re

    from app.engine.chart import compute_chart
    from app.pdf.chart_svg import chart_svg

    chart = compute_chart(birth_date=dt.date(1991, 3, 14), birth_time=dt.time(7, 20),
                          lat=18.5204, lon=73.8567, tz="Asia/Kolkata")
    svg = chart_svg(chart, script=script)
    marks = set(re.findall(r'kundali__retro[^>]*>([^<]+)<', svg))
    assert marks, "no retrograde marked at all in a chart that has retrograde grahas"
    assert marks == {mark}, marks


def test_the_chart_and_the_sky_panel_agree_on_the_mark():
    """One idea, one symbol. These are defined in two modules and nothing but this connects them."""
    from app.pdf.chart_svg import RETRO_MARK
    from app.web import design_v2

    for lang, script in (("en", "en"), ("hi", "deva"), ("mr", "deva")):
        assert design_v2.LABELS[lang]["sky_rx"] == RETRO_MARK[script], lang
