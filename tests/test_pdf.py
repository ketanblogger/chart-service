"""Phase 4 tests: the report JSON is printed as a book (app/pdf).

Most of it needs no browser - HTML is checked as text. The `browser`-marked tests at the bottom print
real PDFs with headless Chromium: that is where the two-pass table of contents, the page size, the
embedded Devanagari fonts and the "nothing is wider than the page" rule are proved.
"""

import contextlib
import datetime as dt
import html
import io
import json
import re
import sys
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.ai import report as report_module
from app.ai.products import PRODUCTS
from app.ai.prompts import DISCLAIMERS
from app.ai.report import Birth, build_data, generate_report
from app.main import app
from app.pdf import blocks, browser, heading_ids, render_report_html, service
from app.pdf.chart_svg import chart_svg
from app.pdf.labels import PART_IDS, PRODUCT_NAMES, SECTION_LABELS, T, Labels, fmt_num
from app.pdf.render import PAGE_SIZES, FONTS_DIR, build_view, content_width_px, page_size_name
from app.web import STATIC_DIR
from tests import reference_charts
from tests.reference_charts import PRIMARY
from tests.test_ai_report import FakeClient, content_for

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures"
AS_OF = reference_charts.AS_OF.date()
def _birth(reference) -> Birth:
    request = reference.request()
    return Birth(dt.date.fromisoformat(request["date"]), dt.time.fromisoformat(request["time"]),
                 reference.lat, reference.lon, reference.tz, reference.place)


# Published charts, not anyone's private data (tests/reference_charts.py). PRIMARY is the feature-rich one
# the fixtures are built from; the second is the matching partner.
MIRAJ = _birth(PRIMARY)          # the single-person chart every report test uses
PUNE = _birth(reference_charts.NEHRU)   # the other half of a matching report
SECTION_PRODUCTS = [slug for slug, product in PRODUCTS.items() if not product.book]
REBUILD = "book fixture drifted - run: .venv/bin/python scripts/build_book_fixture.py"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("PDFS_DIR", str(tmp_path / "pdfs"))
    monkeypatch.delenv("REPORTS_UNLOCKED", raising=False)
    monkeypatch.delenv("PDF_MAX_VARIANTS", raising=False)
    monkeypatch.delenv("PDF_PAGE_SIZE", raising=False)


def book(language: str) -> dict:
    """The long book fixture: real engine data, placeholder prose (scripts/build_book_fixture.py)."""
    return json.loads((FIXTURES / f"kundali_book_{language}.json").read_text(encoding="utf-8"))


def make_report(slug: str, language: str) -> dict:
    """A real report (real engine data, canned text) for a section product, through the real generator."""
    births = [MIRAJ, PUNE] if PRODUCTS[slug].kind == "pair" else [MIRAJ]
    return generate_report(slug, language, births, as_of=AS_OF, client=FakeClient(content_for(slug)))


def flat(text: str) -> str:
    """Dates carry non-breaking spaces (they must never wrap); compare them as ordinary spaces."""
    return text.replace("\u00a0", " ")


def visible_text(document: str) -> str:
    body = re.sub(r"<style>.*?</style>", " ", document, flags=re.S)
    return flat(html.unescape(re.sub(r"<[^>]+>", " ", body)))


def all_chapters(report: dict):
    for part in report["parts"]:
        yield from part["chapters"]


# ---- the book fixture is the contract app/ai actually produces --------------------------------------


def test_book_fixture_is_the_shape_ai_layer_produces():
    """The fixture is built from app/ai/book.py + app/ai/engine_facts.py, so if either changes shape this
    fails and says to rebuild it - the PDF is never tested against a contract nobody produces any more."""
    from app.ai import book_report

    report = book("mr")
    assert report["meta"]["model"] == "fixture" and "FIXTURE" in report["meta"]["note"]
    assert report["product"] == "kundali-report" and PRODUCTS["kundali-report"].book

    _data, _prompt, plan = book_report.build_book_data(build_data(PRODUCTS["kundali-report"], [MIRAJ], AS_OF)[0]["chart"]
                                                      if False else _chart_for(MIRAJ), "mr", AS_OF)
    assert [part["id"] for part in report["parts"]] == [part.id for part in plan], REBUILD
    for part, planned in zip(report["parts"], plan):
        assert [c["id"] for c in part["chapters"]] == [c.id for c in planned.chapters], REBUILD
    assert [part["id"] for part in report["parts"]] == [pid for pid in PART_IDS if pid in
                                                        {p["id"] for p in report["parts"]}]


def _chart_for(birth: Birth) -> dict:
    from app.ai.report import _chart

    return _chart(birth, AS_OF)


def test_book_fixture_is_long_and_dated_by_the_engine():
    report = book("en")
    windows = [w for chapter in all_chapters(report) for w in chapter["windows"]]
    assert len(windows) >= 30, "the timeline is the heart of the book; the fixture must exercise its length"
    for window in windows:
        assert window["start"] and window["end"] and window["window_id"]  # engine dates, not model prose
    words = sum(len(p.split()) for chapter in all_chapters(report) for p in chapter["paragraphs"])
    words += sum(len(p.split()) for chapter in all_chapters(report) for w in chapter["windows"] for p in w["paragraphs"])
    assert words > 8000, "a 30-60 page book, not a leaflet"


def test_marathi_book_is_marathi_and_has_the_shaping_torture_words():
    text = json.dumps(book("mr"), ensure_ascii=False)
    for word in ["पूर्वाषाढा", "वृश्चिक", "ज्येष्ठा", "क्ष", "त्र", "ज्ञ", "महाराष्ट्र", "व्यक्तिमत्त्व"]:
        assert word in text, word


# ---- chart: same drawing as the web page ---------------------------------------------------------


def _svg_texts(svg: str) -> list[tuple]:
    return re.findall(r'<text class="([^"]+)" x="([^"]+)" y="([^"]+)">([^<]*)', svg)


@pytest.mark.parametrize("script", ["en", "deva"])
def test_chart_svg_matches_render_js(script):
    mini_racer = pytest.importorskip("py_mini_racer")
    ctx = mini_racer.MiniRacer()
    ctx.eval((STATIC_DIR / "js" / "render.js").read_text(encoding="utf-8"))
    for birth in (MIRAJ, PUNE):
        chart = build_data(PRODUCTS["mangal-dosha-remedy"], [birth], AS_OF)[0]["chart"]
        web = ctx.eval(f"AstroRender.chartSvg({json.dumps(chart, ensure_ascii=False)}, {json.dumps(script)})")
        ours = chart_svg(chart, script)
        assert _svg_texts(ours) == _svg_texts(web)  # every label, class and coordinate
        assert re.search(r'<path class="kundali__lines" d="([^"]+)"', ours).group(1) == \
            re.search(r'<path class="kundali__lines" d="([^"]+)"', web).group(1)
        assert ours.count("kundali__retro") == web.count("kundali__retro")


def test_chart_has_lagna_in_house_one_and_devanagari_labels():
    chart = book("mr")["data"]["chart"]
    svg = chart_svg(chart, "deva")
    # the lagna marker sits in house 1; its x moves when a graha shares the house, so match the element
    assert re.search(r'<text class="kundali__graha kundali__graha--lagna" x="[\d.]+" y="[\d.]+">ल</text>', svg)
    lagna_sign = str(chart["lagna"]["sign"]["index"])
    assert f'<text class="kundali__sign" x="200" y="178">{lagna_sign}</text>' in svg  # house 1 carries it
    from app.pdf.labels import GRAHA_ABBR
    for key in chart["houses"][0]["grahas"]:
        assert f">{GRAHA_ABBR['deva'][key]}<" in svg, key


def test_navamsa_is_drawn_as_a_second_chart_and_only_when_the_engine_gives_one():
    report = book("mr")
    assert report["data"]["navamsa"]["houses"], "the fixture should carry the engine's D9"
    document = render_report_html(report)
    assert document.count("<svg class=\"kundali") == 2  # D1 and D9
    assert T["mr"]["navamsa_note"] in visible_text(document)

    without = json.loads(json.dumps(report))
    without["data"].pop("navamsa")
    document = render_report_html(without)
    assert document.count("<svg class=\"kundali") == 1  # no D9 data -> no D9 page, no empty frame
    assert T["mr"]["navamsa_note"] not in visible_text(document)


# ---- the book: parts, chapters, dates -------------------------------------------------------------


@pytest.mark.parametrize("language", ["en", "mr"])
def test_book_prints_every_part_chapter_and_window(language):
    report = book(language)
    document = render_report_html(report, names={"self": "Keshav"})
    text = visible_text(document)
    L = Labels(language)

    assert f'<html lang="{language}">' in document
    for index, part in enumerate(report["parts"]):
        assert f"{L['part']} {L.part_letter(index)}" in text
        assert part["heading"] in text
    for chapter in all_chapters(report):
        assert chapter["heading"] in text
        for paragraph in chapter["paragraphs"]:
            assert paragraph in text
        for window in chapter["windows"]:
            assert flat(L.label(window)) in text  # the engine's own label for that window, verbatim
            assert window["paragraphs"][0] in text
    assert DISCLAIMERS[language] in text and report["id"] in text
    assert T[language]["contents"] in text  # the table of contents exists
    assert not re.findall(r'(?:src|href)="(?!#)[^"]*"', document) and "<script" not in document
    assert 'url("fonts/NotoSansDevanagari-Regular.ttf")' in document and 'url("fonts/NotoSans-Regular.ttf")' in document


def test_the_book_never_formats_a_date_range_itself():
    """One date-range format everywhere in the book, and the engine owns it: every
    window carries its own label in all three languages, and anything else goes through the engine's
    `format_range`. This checks the book prints those strings and never invents one of its own."""
    from app.engine import format_range

    for language in ("en", "mr"):
        L = Labels(language)
        report = book(language)
        text = visible_text(render_report_html(report))
        labels = [window["label"] for chapter in all_chapters(report) for window in chapter["windows"]]
        assert len(labels) > 30
        for label in labels:
            assert flat(label) in text, label      # printed exactly as the engine wrote it
        # a range the engine did not label is still formatted by the engine, and `end` is exclusive:
        # a period ending on 1 Oct is labelled "Sep", never "Oct"
        assert L.range("2026-09-01", "2026-10-01") == L.range("2026-09-01", "2026-09-30")
        maha = report["data"]["chart"]["dasha"]["current"]["mahadasha"]
        first, last = dt.date.fromisoformat(maha["start"]), dt.date.fromisoformat(maha["end"])
        assert flat(L.range(maha["start"], maha["end"])) == \
            format_range(first, last - dt.timedelta(days=1), language, "month")
        assert flat(L.range(maha["start"], maha["end"])) in text   # the running mahadasha, in the book


def test_a_dated_chapter_heading_is_split_into_a_span_and_a_theme():
    """`app/ai/book_report.compose_heading` heads a year or five-year chapter with the ENGINE's range
    label plus the model's theme. Printed as one line it would sit directly above the first window's own
    range - two date lines in a row - so the opener sets the span above the title as a quiet kicker.
    The contents page still prints the whole composed string, which is where the dates are useful."""
    from app.pdf.book import timeline_headings

    report = book("mr")
    L = Labels("mr")
    spans = timeline_headings(report["data"], "mr")
    assert spans, "the engine timeline should label its years and blocks"

    view = build_view(report)
    timeline = next(part for part in view["parts"] if part["id"] == "timeline")
    dated = [chapter for chapter in timeline["chapters"] if chapter["kicker"]]
    assert len(dated) >= 4
    for chapter in dated:
        span = spans[chapter["id"]]
        assert chapter["kicker"] == span                       # the engine's label, ours to typeset
        assert span.replace("\u00a0", " ") not in chapter["title"]   # the dates are not printed twice
        assert chapter["title"] and chapter["title"] in chapter["heading"]
        assert chapter["heading"].replace("\u00a0", " ").startswith(span.replace("\u00a0", " "))

    document = render_report_html(report)
    for chapter in dated:                                      # the contents line keeps both halves
        assert flat(chapter["heading"]) in visible_text(document)
        assert f'<p class="chapter-kicker">{chapter["kicker"]}</p>' in document

    undated = [chapter for chapter in timeline["chapters"] if not chapter["kicker"]]
    assert undated and all(chapter["title"] == chapter["heading"] for chapter in undated)


def test_a_window_the_engine_cannot_date_is_not_printed():
    report = book("en")
    chapter = next(c for c in all_chapters(report) if c["windows"])
    kept = chapter["windows"][0]["paragraphs"][0]
    chapter["windows"].append({"window_id": "made-up", "headline": "Invented", "paragraphs": ["INVENTED WINDOW"],
                               "areas": []})
    text = visible_text(render_report_html(report))
    assert kept in text and "INVENTED WINDOW" not in text


def _first_window(report: dict) -> dict:
    return next(c["windows"][0] for part in report["parts"] for c in part["chapters"] if c.get("windows"))


def test_life_area_lines_render_from_every_shape_a_stored_report_carries():
    """The shape that crashed the render of every paid report, and the one the fixtures happen to carry.

    A generated report holds the published contract, [{area, text}], which app/ai/schema.py `pair_areas`
    builds from the model's parallel `areas` / `area_lines`. Both book fixtures hold plain strings. So
    `L.area()` was handed a dict, used it as a key into AREA_LABELS, and raised `unhashable type: dict` -
    on the server var/pdfs stayed empty through every paid order while the whole suite passed here. That
    is the gap this closes: the shapes production writes are exercised, not only the fixture's.

    The sentences have to reach the page as well. Only the tag row was ever rendered, so the per-area line
    the model writes was being discarded, along with the `areas_heading` label kept for it in three
    languages."""
    from app.pdf.labels import AREA_LABELS

    contract = book("en")
    _first_window(contract)["areas"] = [{"area": "career", "text": "CONTRACT LINE ONE."},
                                        {"area": "health", "text": "CONTRACT LINE TWO."}]
    text = visible_text(render_report_html(contract))
    assert "CONTRACT LINE ONE." in text and "CONTRACT LINE TWO." in text
    assert T["en"]["areas_heading"] in text
    assert AREA_LABELS["career"][0] in text and AREA_LABELS["health"][0] in text

    legacy = book("en")
    _first_window(legacy)["areas"] = ["career", "money"]
    assert AREA_LABELS["money"][0] in visible_text(render_report_html(legacy))

    # whatever the model returns, the book still prints: a paid PDF may not be lost to a shape
    junk = book("en")
    _first_window(junk)["areas"] = [{"no_area_key": 1}, None, 42, ["career", "PAIR LINE."], {"area": "", "text": "x"}]
    assert "PAIR LINE." in visible_text(render_report_html(junk))


def test_the_book_reads_exactly_the_shape_the_generator_writes():
    """The seam the two modules drifted across: `pair_areas` writes it, `_area_items` reads it."""
    from app.ai.schema import pair_areas
    from app.pdf.book import _area_items

    stored = pair_areas({"areas": ["career", "money"], "area_lines": ["A sentence.", "Another one."]})
    assert stored == [{"area": "career", "text": "A sentence."}, {"area": "money", "text": "Another one."}]
    tags, lines = _area_items(Labels("en"), stored)
    assert tags == [] and [item["text"] for item in lines] == ["A sentence.", "Another one."]


def test_engine_blocks_are_printed_even_when_the_writer_skipped_the_chapter():
    """A part the model never wrote still prints its engine data: the chart, the graha table, the dasha."""
    report = book("en")
    report["parts"] = [part for part in report["parts"] if part["id"] not in ("chart_basics", "timeline")]
    text = visible_text(render_report_html(report))
    chart = report["data"]["chart"]
    assert T["en"]["col_nakshatra"] in text and chart["janma_nakshatra"]["name"] in text   # the graha table
    assert T["en"]["full_dasha"] in text and T["en"]["current_maha"] in text


def test_the_combust_column_follows_the_engine_and_says_nothing_it_was_not_told():
    """The engine publishes combustion twice - as `combust` on every graha and inside `dignity` - and
    leaves it **null** for Surya, Rahu and Ketu, where the rule does not apply. Null must print as a dash,
    never as "No", and a chart with no combustion verdict at all gets no column."""
    report = book("en")
    assert report["data"].get("dignity"), "the fixture should carry the engine's dignity block"
    text = visible_text(render_report_html(report))
    assert T["en"]["col_combust"] in text and T["en"]["combust_note"] in text

    document = render_report_html(report)
    table = document[document.index('<table class="t-grahas"'):]
    table = table[:table.index("</table>")]
    rows = {cells[0]: cells[-1] for cells in
            (re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row, re.S) for row in re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S))
            if cells}
    for graha in ("Surya (Sun)", "Rahu", "Ketu"):   # the rule does not apply to these three
        assert rows[graha].strip() == "\u2013", (graha, rows[graha])
    assert rows["Shani (Saturn)"].strip() in (T["en"]["yes"], T["en"]["no"])

    stripped = json.loads(json.dumps(report))     # neither source says anything: no column at all
    stripped["data"].pop("dignity")
    for position in stripped["data"]["chart"]["grahas"].values():
        position.pop("combust", None)
    assert T["en"]["col_combust"] not in visible_text(render_report_html(stripped))


def test_gemstone_table_is_localised_and_prints_no_weight_or_price():
    report = book("mr")
    text = visible_text(render_report_html(report))
    stones = (report["data"]["gemstone"] or {}).get("recommended") or []
    assert stones, "the fixture should carry the engine's gemstone table"
    for entry in stones:
        assert entry["stone"] in text
    assert "रविवार" in text or "गुरुवार" in text  # weekday translated, not "Sunday"
    assert "ratti" not in text and "carat" not in text.lower()  # never a weight, never a purchase instruction
    assert (report["data"]["gemstone"] or {}).get("presentation", "x") not in text  # model-facing text stays out


def test_part_a_prints_the_engine_verdict_with_the_writers_line_for_every_highlight():
    """Part A, items 1-7. The writer fills the report's top-level `highlights` object
    (app/ai/schema.py); the engine's own verdict for mangal dosha, sade sati and the running dasha is
    printed with it, and an item the writer skipped still prints that verdict."""
    report = book("mr")
    report["highlights"] = {
        "mangal": {"verdict": "मंगळ दोष आहे पण सौम्य.", "remedy": "मंगळवारी हनुमान चालीसा."},
        "sade_sati": {"verdict": "सध्या साडेसाती नाही.", "guidance": "पुढील चक्रासाठी बचत करा."},
        "dasha": {"mood": "राहू महादशा: वेग आणि अस्वस्थता."},
        "strengths": ["शनी स्वराशीत", "चंद्र पंचमात", "गुरूची दृष्टी"],
        "cautions": ["घाईचे निर्णय", "रात्रीचे काम", "अतिविश्वास"],
        "yogas": [{"name": "शश योग", "text": "स्थैर्य देतो."}],
    }
    L = Labels("mr")
    text = visible_text(render_report_html(report))
    for line in ("मंगळवारी हनुमान चालीसा", "पुढील चक्रासाठी बचत करा", "राहू महादशा: वेग आणि अस्वस्थता.",
                 "शनी स्वराशीत", "घाईचे निर्णय", "शश योग"):
        assert line in text, line
    assert f"{L['hl_remedy']}: मंगळवारी" in text and f"{L['hl_guidance']}: पुढील" in text
    assert L.mangal_status(report["data"]["chart"]["mangal_dosha"]) in text      # the engine's verdict
    assert L["current_maha"] in text and L.chapter("cautions") in text

    report["highlights"] = {}  # the writer's Part A call failed: the engine verdicts still get their page
    text = visible_text(render_report_html(report))
    assert L.mangal_status(report["data"]["chart"]["mangal_dosha"]) in text and L["current_maha"] in text


def test_the_gemstone_card_falls_back_to_the_writers_own_when_the_engine_has_no_table():
    written = {"stone": "माणिक्य", "finger": "अनामिका", "day": "रविवार", "metal": "सोने",
               "avoid": "नीलम", "note": "हे पूर्णपणे ऐच्छिक आहे."}
    report = book("mr")
    report["gemstone"] = written
    text = visible_text(render_report_html(report))
    assert written["note"] in text                      # the writer's note is printed beside the engine table
    assert (report["data"]["gemstone"]["recommended"][0]["stone"]) in text

    report["data"].pop("gemstone")                      # no engine table: the writer's card carries the part
    text = visible_text(render_report_html(report))
    for value in ("माणिक्य", "अनामिका", "रविवार", "सोने", "नीलम", written["note"]):
        assert value in text, value


def test_yoga_table_uses_the_engines_classification_in_the_report_language():
    report = book("mr")
    text = visible_text(render_report_html(report))
    for yoga in report["data"]["yogas"]:
        assert (yoga.get("devanagari") or yoga["name"]) in text
        assert yoga["rule"] not in text  # the engine's English rule text is model-facing
    assert T["mr"]["col_strength"] in text


# ---- the three section products still print as books ------------------------------------------------


@pytest.mark.parametrize("language", ["en", "hi", "mr"])
@pytest.mark.parametrize("slug", SECTION_PRODUCTS)
def test_html_for_every_section_product_and_language(slug, language):
    report = make_report(slug, language)
    document = render_report_html(report, names={"self": "Keshav", "boy": "Keshav", "girl": "Asha"})
    text = visible_text(document)
    L = Labels(language)

    assert f'<html lang="{language}">' in document
    assert DISCLAIMERS[language] in text and T[language]["disclaimer"] in text
    assert PRODUCT_NAMES[slug][language] in text
    data = report["data"]
    born = (data.get("chart") or data.get("boy_chart"))["input"]
    # the reference charts are given as coordinates, not as one of the 124 cities, so the book prints those
    assert "Keshav" in text and flat(L.date(born["date"])) in text
    assert (born.get("city") or blocks.coords(born)) in text
    assert T[language]["remedies"] in text and report["id"] in text
    assert document.count("<svg class=\"kundali") == (2 if slug == "matching-report" else 1)
    assert ('class="kundali kundali--deva"' in document) == (language != "en")
    for section in report["sections"]:
        assert section["paragraphs"][0] in text

    if slug == "matching-report":
        matching = data["matching"]
        assert "Asha" in text and reference_charts.NEHRU.place.split(" (")[0].split(",")[0] in text
        assert T[language]["guna_heading"] in text and f"{L.koota('nadi')[0]}" in text
        assert f"{fmt_num(matching['total'])} / {fmt_num(matching['max_total'])}" in text  # engine, not AI text
        for koota in matching["kootas"]:                       # every value as the engine computed it
            assert L.koota_value(koota["koota"], koota["boy"]) in text, koota["koota"]
        assert T[language]["mangal_compare"] in text and T[language]["bhakoot_dosha"] in text
    else:
        chart = data["chart"]
        assert chart["lagna"]["degree_dms"] in text and L.sign(chart["moon_rashi"]) in text
        assert L.nakshatra(chart["janma_nakshatra"]) in text
        assert T[language]["grahas_heading"] in text and chart["grahas"]["Jupiter"]["degree_dms"] in text
    if slug == "mangal-dosha-remedy":
        assert L.mangal_status(data["chart"]["mangal_dosha"]) in text
        assert L.house(12) in text and T[language]["cancellations"] in text
    if slug == "sade-sati-guide":
        assert L.sade_status("inactive") in text and L.phase("peak")[0] in text


def test_marathi_labels_are_marathi_not_hindi():
    text = visible_text(render_report_html(book("mr")))
    for word in ["मंगळ", "गुरू", "शनी", "राहू", "केतू", "तूळ", "ग्रहस्थिती", "जन्मतारीख", "सध्याची महादशा", "स्थान"]:
        assert word in text, word
    # whole words only: "भाव" is Hindi for house, but it is also the tail of the Marathi "स्वभाव"
    for hindi in ["मंगल", "शनि", "तुला", "भाव", "वर्तमान", "पृष्ठ" if False else "नहीं"]:
        assert not re.search(rf"(?<![\u0900-\u097F])({hindi})(?![\u0900-\u097F])", text), hindi


def test_every_language_has_every_label():
    assert set(T["en"]) == set(T["hi"]) == set(T["mr"])
    from app.pdf.labels import AREA_LABELS, CHAPTER_LABELS, GEM_ROLES, GEM_TERMS, PART_LABELS, YOGA_TERMS

    for table in (PART_LABELS, CHAPTER_LABELS, AREA_LABELS, GEM_TERMS, GEM_ROLES, YOGA_TERMS):
        assert all(len(triple) == 3 and all(triple) for triple in table.values())
    for part_id in PART_IDS:
        assert part_id in PART_LABELS
    for slug, product in PRODUCTS.items():
        if not product.book:  # a book product has no flat section list
            assert set(SECTION_LABELS[slug]) == {section_id for section_id, _ in product.sections}
        assert set(PRODUCT_NAMES[slug]) == {"en", "hi", "mr"}


def test_blank_headings_fall_back_to_our_own_labels():
    report = book("mr")
    report["parts"][1]["heading"] = ""              # what the Phase 3 redactor leaves behind
    report["parts"][1]["chapters"][0]["heading"] = "   "
    document = render_report_html(report)
    L = Labels("mr")
    assert L.part(1, "chart_basics") in visible_text(document)
    assert L.chapter("what_your_chart_looks_like") in visible_text(document)
    assert "<h1 class=\"part-title\" id=\"hd-3\"></h1>" not in document


@pytest.mark.parametrize("language", ["en", "hi", "mr"])
def test_disclaimer_is_always_printed(language):
    report = make_report("sade-sati-guide", language)
    for broken in ("", None):
        report["disclaimer"] = broken
        assert DISCLAIMERS[language] in visible_text(render_report_html(report))
    del report["disclaimer"]
    assert DISCLAIMERS[language] in visible_text(render_report_html(report))


def test_redacted_shapes_render():
    """Empty chapters, empty windows, a table emptied by redaction, no remedies at all."""
    report = book("en")
    for chapter in all_chapters(report):
        chapter["bullets"] = []
    report["parts"][2]["chapters"][0]["paragraphs"] = []
    table_chapter = next(c for c in all_chapters(report) if c["table"])
    table_chapter["table"] = {"columns": ["A"], "rows": []}
    report["remedies"] = []
    document = render_report_html(report)
    assert "<table class=\"t-ai\"" not in document and "<li></li>" not in document
    assert DISCLAIMERS["en"] in visible_text(document)


def test_all_text_is_escaped_and_uncovered_symbols_are_replaced():
    report = book("en")
    report["title"] = 'Hi <script>alert("x")</script>'
    chapter = report["parts"][2]["chapters"][0]
    chapter["paragraphs"][0] = "<img src=x onerror=alert(1)> Guru → Simha ✓"
    report["remedies"][0]["title"] = "</style><b>bold</b>"
    document = render_report_html(report, names={"self": '<i>K</i>\n\x00"; }'})
    body = document.split("</style>", 1)[1]
    assert "<script" not in document and "<img" not in body and "<b>bold" not in body and "<i>" not in body
    assert "&lt;img src=x onerror=alert(1)&gt; Guru – Simha" in body
    assert "→" not in body and "✓" not in body


def test_bundled_fonts_cover_every_character_we_print():
    """No character may fall through to a system font: check template labels + fixtures against the font cmaps."""
    ttlib = pytest.importorskip("fontTools.ttLib")
    covered = set()
    for name in ("NotoSans-Regular", "NotoSans-Bold", "NotoSansDevanagari-Regular", "NotoSansDevanagari-Bold"):
        assert (FONTS_DIR / f"{name}.ttf").is_file()
        covered |= set(ttlib.TTFont(FONTS_DIR / f"{name}.ttf").getBestCmap())
    assert "SIL Open Font License" in (FONTS_DIR / "OFL.txt").read_text(encoding="utf-8")
    documents = [render_report_html(book("mr"), names={"self": "केशव"}), render_report_html(book("en"))]
    documents += [render_report_html(make_report(slug, lang)) for slug in SECTION_PRODUCTS for lang in ("hi", "mr")]
    missing = {ch for document in documents for ch in visible_text(document) if not ch.isspace() and ord(ch) not in covered}
    assert missing == set()


# ---- the two-pass contents page (no browser) ---------------------------------------------------------


def test_every_heading_has_an_id_in_document_order():
    document = render_report_html(book("mr"))
    ids = heading_ids(document)
    assert ids == [f"hd-{n}" for n in range(1, len(ids) + 1)]  # sequential: the outline zip depends on it
    assert len(ids) > 40


def test_filling_the_contents_page_cannot_change_the_layout():
    """The whole two-pass trick rests on this: the second render differs only in the digits printed."""
    report = book("mr")
    first = render_report_html(report)
    anchors = heading_ids(first)
    filled = render_report_html(report, toc_pages={anchor: 7 + index for index, anchor in enumerate(anchors)})
    assert heading_ids(filled) == anchors
    assert len(first) != len(filled) or first == filled
    strip = lambda doc: re.sub(r'(<span class="toc-page[^"]*">)[^<]*<', r"\1<", doc)  # noqa: E731
    assert strip(first) == strip(filled)  # nothing but the page numbers moved
    first_entry = build_view(report)["toc"]["entries"][0]["anchor"]
    view = build_view(report, toc_pages={first_entry: 3})
    assert view["toc"]["entries"][0]["page"] == "3"
    assert [entry["page"] for entry in build_view(report)["toc"]["entries"]] == ["00"] * len(view["toc"]["entries"])


def test_a_missing_page_number_is_left_blank_rather_than_guessed():
    report = book("en")
    view = build_view(report, toc_pages={})
    assert {entry["page"] for entry in view["toc"]["entries"]} == {""}


def test_page_size_is_a5_by_default_and_a4_on_request(monkeypatch):
    assert page_size_name() == "a5" and page_size_name("A4") == "a4" and page_size_name("letter") == "a5"
    monkeypatch.setenv("PDF_PAGE_SIZE", "a4")
    assert page_size_name() == "a4" and page_size_name("a5") == "a5"
    for size, (css, *_rest) in PAGE_SIZES.items():
        document = render_report_html(book("en"), page_size=size)
        assert f"size: {css};" in document and f'<body class="size-{size}">' in document
        assert content_width_px(document) == {"a5": 461, "a4": 658}[size]


def test_the_cover_carries_the_chart_identity(monkeypatch):
    document = render_report_html(book("mr"), names={"self": "केशव"})
    cover = document.split('<section class="contents">')[0]
    text = visible_text(cover)
    L = Labels("mr")
    chart = book("mr")["data"]["chart"]
    for expected in ("केशव", flat(L.date(chart["input"]["date"])),
                     chart["input"].get("city") or blocks.coords(chart["input"]), L["site_name"],
                     L.sign(chart["lagna"]["sign"]), L.sign(chart["moon_rashi"]), L.nakshatra(chart["janma_nakshatra"])):
        assert expected in text, expected
    assert "<svg" in cover and "rosette" in cover  # the ornament is vector, drawn by app/pdf/cover.py
    assert "@page cover" in document


# ---- API ---------------------------------------------------------------------------------------------


def _cache(report: dict) -> str:
    report_module._save_report(report)
    return report["id"]


@pytest.fixture
def fake_chromium(monkeypatch):
    calls = []

    def fake(build_html, **kwargs):
        document = build_html(None)
        calls.append(document)
        return b"%PDF-1.7 fake " + str(len(calls)).encode()

    monkeypatch.setattr(service, "render_book", fake)
    return calls


def test_pdf_route_is_gated_like_the_json_report(fake_chromium):
    rid = _cache(book("mr"))
    response = TestClient(app).get(f"/api/report/{rid}/pdf")
    assert response.status_code == 402
    assert response.json()["detail"]["error"] == "payment_required"
    assert response.json()["detail"]["product"] == "kundali-report"
    assert fake_chromium == [] and not list(service.pdfs_dir().glob("*"))  # nothing rendered for a non-payer


def test_pdf_route_unknown_and_malformed_ids(monkeypatch, fake_chromium):
    monkeypatch.setenv("REPORTS_UNLOCKED", "1")
    client = TestClient(app)
    assert client.get(f"/api/report/{'0' * 32}/pdf").status_code == 404
    assert client.get("/api/report/..%2F..%2Fetc%2Fpasswd/pdf").status_code == 404
    assert fake_chromium == []


def test_pdf_route_serves_attachment_and_caches(monkeypatch, fake_chromium):
    monkeypatch.setenv("REPORTS_UNLOCKED", "1")
    rid = _cache(book("mr"))
    client = TestClient(app)
    first = client.get(f"/api/report/{rid}/pdf")
    assert first.status_code == 200 and first.headers["content-type"] == "application/pdf"
    born = book("mr")["data"]["chart"]["input"]["date"]
    assert first.headers["content-disposition"] == f'attachment; filename="kundali-report-{born}-mr.pdf"'
    assert first.content.startswith(b"%PDF")
    assert client.get(f"/api/report/{rid}/pdf").content == first.content
    assert len(fake_chromium) == 1  # second download came from var/pdfs

    named = client.get(f"/api/report/{rid}/pdf", params={"name": "केशव"})
    assert named.status_code == 200 and len(fake_chromium) == 2 and "केशव" in fake_chromium[1]
    assert client.get(f"/api/report/{rid}/pdf", params={"name": "  केशव "}).content == named.content
    assert len(fake_chromium) == 2
    assert client.get(f"/api/report/{rid}/pdf", params={"name": "x" * 61}).status_code == 422

    monkeypatch.setenv("PDF_MAX_VARIANTS", "2")
    assert client.get(f"/api/report/{rid}/pdf", params={"name": "B"}).status_code == 200
    assert client.get(f"/api/report/{rid}/pdf", params={"name": "C"}).status_code == 429  # disk-filling guard
    assert client.get(f"/api/report/{rid}/pdf").status_code == 200  # the plain PDF is always available


def test_the_cached_pdf_is_per_page_size(monkeypatch, fake_chromium):
    monkeypatch.setenv("REPORTS_UNLOCKED", "1")
    rid = _cache(book("en"))
    client = TestClient(app)
    assert client.get(f"/api/report/{rid}/pdf").status_code == 200
    names = {path.name for path in service.pdfs_dir().glob("*.pdf")}
    assert names == {f"{rid}-v{service.TEMPLATE_VERSION}-a5-plain.pdf"}
    monkeypatch.setenv("PDF_PAGE_SIZE", "a4")
    assert client.get(f"/api/report/{rid}/pdf").status_code == 200
    assert len(fake_chromium) == 2 and 'class="size-a4"' in fake_chromium[1]
    assert len(list(service.pdfs_dir().glob("*.pdf"))) == 2  # the A5 one is still there, still valid


def test_pdf_route_reports_browser_failure_as_503(monkeypatch):
    monkeypatch.setenv("REPORTS_UNLOCKED", "1")
    rid = _cache(book("en"))

    def boom(build_html, **kwargs):
        raise browser.PdfError("no chromium here")

    monkeypatch.setattr(service, "render_book", boom)
    response = TestClient(app).get(f"/api/report/{rid}/pdf")
    assert response.status_code == 503 and response.json()["detail"]["error"] == "pdf_unavailable"
    assert "chromium" not in response.text.lower()  # details go to the log, not to the customer
    assert not list(service.pdfs_dir().glob("*.pdf"))


def test_report_json_carries_pdf_url(monkeypatch):
    monkeypatch.setenv("REPORTS_UNLOCKED", "1")
    monkeypatch.setattr(report_module, "ClaudeClient", lambda settings: FakeClient(content_for("sade-sati-guide")))
    client = TestClient(app)
    body = {"product": "sade-sati-guide", "language": "mr", "as_of": "2026-09-21",
            "birth": PRIMARY.request()}
    created = client.post("/api/report", json=body).json()
    assert created["pdf_url"] == f"/api/report/{created['id']}/pdf"
    assert client.get(f"/api/report/{created['id']}").json()["pdf_url"] == created["pdf_url"]
    assert "pdf_url" not in json.loads((report_module._cache_path(created["id"])).read_text(encoding="utf-8"))


def test_launch_options_follow_the_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("PDF_CHROMIUM_EXECUTABLE", "/usr/bin/chromium")
    monkeypatch.setenv("PDF_CHROMIUM_LD_LIBRARY_PATH", "/opt/libs")
    monkeypatch.setenv("PDF_CHROMIUM_ARGS", "--disable-gpu --foo='a b'")
    monkeypatch.setenv("LD_LIBRARY_PATH", "/already")
    options = browser.launch_options()
    assert options["executable_path"] == "/usr/bin/chromium" and options["args"] == ["--disable-gpu", "--foo=a b"]
    assert options["env"]["LD_LIBRARY_PATH"] == "/opt/libs:/already"
    monkeypatch.delenv("PDF_CHROMIUM_EXECUTABLE")
    monkeypatch.delenv("PDF_CHROMIUM_ARGS")
    monkeypatch.setenv("PDF_CHROMIUM_LD_LIBRARY_PATH", "")  # explicit empty = a normal server: leave the env alone
    assert browser.launch_options() == {"headless": True}


# ---- the real thing ----------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def chromium():
    ok, reason = browser.chromium_available()
    if not ok:
        pytest.skip(f"headless Chromium cannot launch here: {reason}")


def _render(report: dict, *, names=None, page_size=None):
    """The real two-pass book render; returns (pdf bytes, the documents of each pass)."""
    passes = []

    def build(toc_pages):
        document = render_report_html(report, names=names, page_size=page_size, toc_pages=toc_pages)
        passes.append((toc_pages, document))
        return document

    return browser.render_book(build), passes


@pytest.mark.browser
def test_the_marathi_book_prints_true_page_numbers_on_its_contents_page(chromium):
    """The two-pass render, end to end: every number on the contents page is the page that heading is on."""
    pypdf = pytest.importorskip("pypdf")
    report = book("mr")
    pdf, passes = _render(report, names={"self": "केशव"})
    assert pdf.startswith(b"%PDF-") and b"%%EOF" in pdf[-1024:]
    assert len(passes) == 2, "one pass to measure, one to print the numbers"

    reader = pypdf.PdfReader(io.BytesIO(pdf))
    assert 25 <= len(reader.pages) <= 90, f"a book, not a leaflet or a phone directory: {len(reader.pages)} pages"
    assert reader.metadata.title == report["title"]

    printed = passes[-1][0]
    landed = dict(zip(heading_ids(passes[-1][1]), browser.outline_pages(pdf)))
    assert printed and len(landed) == len(printed)
    assert {anchor: page for anchor, page in printed.items() if landed[anchor] != page} == {}
    assert max(printed.values()) == len(reader.pages) or max(printed.values()) <= len(reader.pages)


@pytest.mark.browser
def test_the_book_pdf_uses_only_the_bundled_fonts_and_is_a5(chromium):
    pypdf = pytest.importorskip("pypdf")
    pdf, _passes = _render(book("mr"), names={"self": "केशव"})
    reader = pypdf.PdfReader(io.BytesIO(pdf))
    width, height = reader.pages[1].mediabox.width, reader.pages[1].mediabox.height
    assert round(width) == 420 and round(height) == 595, "A5 portrait (420 x 595 pt)"

    fonts = browser.embedded_fonts(pdf)
    assert {"NotoSansDevanagari-Regular", "NotoSansDevanagari-Bold", "NotoSans-Regular"} <= fonts
    assert browser.fallback_fonts(pdf) == set(), "some character fell back to a system font"
    for page in reader.pages:  # the fonts are embedded (subset), not merely referenced
        for font in page["/Resources"]["/Font"].values():
            font = font.get_object()
            descriptor = (font["/DescendantFonts"][0].get_object() if "/DescendantFonts" in font else font)["/FontDescriptor"]
            assert any(key in descriptor.get_object() for key in ("/FontFile", "/FontFile2", "/FontFile3"))

    # Extraction loses some matras / conjunct glyphs (normal for Indic PDFs), so look for words that survive.
    text = re.sub(r"\s+", "", "".join(page.extract_text() for page in reader.pages))
    # Only words that survive extraction: Chromium drops the Unicode mapping of some conjuncts, so a sign
    # like वृश्चिक (श्च) may not come back even though it is printed correctly. Latin digits always do.
    chart = book("mr")["data"]["chart"]
    for word in ["जन्मतारीख", "महादशा", "केशव", chart["input"]["date"][:4]]:
        assert word in text, word
    from app.web import site

    # the running head and the page number come from the @page margin boxes; the cover carries none
    assert re.search(r"पृष्ठ\d+/\d+", text) and "पृष्ठ1/" not in text
    assert site.SITE_NAME.replace(" ", "") in text
    assert book("mr")["id"] in text  # also proves ligatures are off for the id ("ff" must not become U+FB00)


@pytest.mark.browser
@pytest.mark.parametrize("page_size", ["a5", "a4"])
def test_nothing_in_the_book_is_wider_than_the_page(chromium, page_size, caplog):
    """Chromium lays every page out in the first page's content box and silently shrinks the WHOLE document
    to fit anything wider - which would change every type size in the book. browser.py warns; this fails."""
    import logging

    with caplog.at_level(logging.WARNING, logger="app.pdf.browser"):
        _render(book("mr"), page_size=page_size)
    overflow = [record.getMessage() for record in caplog.records if "overflow" in record.getMessage()]
    assert overflow == []


@pytest.mark.browser
def test_the_longest_composed_heading_still_lays_out(chromium):
    """A timeline chapter heading is the engine's range label plus a theme of up to 64 characters, and the
    contents page has to hold the whole composed string beside its leader dots and page number."""
    report = book("mr")
    theme = "जबाबदारी, प्रवास आणि शिक्षण यांचा समतोल राखण्याचा काळ"[:64]
    longest = 0
    for part in report["parts"]:
        for chapter in part["chapters"]:
            span = chapter["heading"].split(" \u2014 ")[0] if " \u2014 " in chapter["heading"] else ""
            if span:
                chapter["heading"] = f"{span} \u2014 {theme}"
                longest = max(longest, len(chapter["heading"]))
    assert longest > 75, "the fixture should carry a worst-case heading"

    import logging

    with caplog_at_warning() as records:
        pdf, passes = _render(report)
    assert [message for message in records if "overflow" in message] == []
    printed = passes[-1][0]
    landed = dict(zip(heading_ids(passes[-1][1]), browser.outline_pages(pdf)))
    assert printed and all(landed[anchor] == page for anchor, page in printed.items())
    assert logging  # noqa: B018


@contextlib.contextmanager
def caplog_at_warning():
    """The renderer warns through the logging module; collect those messages for the duration."""
    import logging

    messages: list[str] = []

    class Collect(logging.Handler):
        def emit(self, record):
            messages.append(record.getMessage())

    logger = logging.getLogger("app.pdf.browser")
    handler = Collect()
    logger.addHandler(handler)
    try:
        yield messages
    finally:
        logger.removeHandler(handler)


@pytest.mark.browser
def test_a_section_product_still_prints_as_a_book(chromium):
    pypdf = pytest.importorskip("pypdf")
    pdf, passes = _render(make_report("matching-report", "hi"), names={"boy": "Keshav", "girl": "Asha"})
    reader = pypdf.PdfReader(io.BytesIO(pdf))
    assert len(reader.pages) > 3 and browser.fallback_fonts(pdf) == set()
    printed = passes[-1][0]
    landed = dict(zip(heading_ids(passes[-1][1]), browser.outline_pages(pdf)))
    assert printed and all(landed[anchor] == page for anchor, page in printed.items())


@pytest.mark.browser
def test_pdf_over_http_end_to_end(chromium, monkeypatch):
    monkeypatch.setenv("REPORTS_UNLOCKED", "1")
    rid = _cache(book("en"))
    response = TestClient(app).get(f"/api/report/{rid}/pdf", params={"name": "Keshav"})
    assert response.status_code == 200 and response.content.startswith(b"%PDF-")
    assert browser.fallback_fonts(response.content) == set()
    assert (service.pdfs_dir() / service.pdf_path(rid, {"self": "Keshav"}).name).is_file()


# ---- the cover name comes from a query parameter --------------------------------------------------------


HOSTILE_NAMES = [
    "A" * 200,                                   # far over the limit
    "केशव" * 30,                                   # over the limit, and wider per character
    "اسم عربي طويل جدا",                          # right-to-left
    "Keshav‮Override‭",                  # bidi override: would re-order the whole header line
    '"; } body { display: none } .x { content: "',  # an attempt to close the CSS string in the @page rule
    "<b>x</b><script>alert(1)</script>",
    "Keshav  ﻿\u0000",              # line / paragraph separators, BOM, NUL
]


@pytest.mark.parametrize("name", HOSTILE_NAMES)
def test_a_hostile_name_cannot_escape_the_cover_or_the_running_head(name):
    from app.pdf.render import MAX_HEADER_LENGTH, MAX_NAME_LENGTH, clean_name, running_head

    cleaned = clean_name(name)
    assert len(cleaned) <= MAX_NAME_LENGTH
    assert all(ch.isprintable() for ch in cleaned)      # no bidi overrides, no separators, no NUL
    head = running_head(cleaned, "Title")
    assert len(head) <= MAX_HEADER_LENGTH               # it shares one line with "Kundali Report"

    document = render_report_html(book("mr"), names={"self": name})
    style = document[:document.index("</style>")]
    body = document.split("</style>", 1)[1]
    assert "<script" not in document                       # nothing from the name became an element
    assert "<b>x</b>" not in body and "&lt;b&gt;x&lt;/b&gt;" in body if "<b>x" in name else True
    # The @page rules are still exactly the three we wrote, and every margin box is ONE closed CSS string:
    # whatever the name contains is inside it, escaped, where it cannot start a declaration or a rule.
    assert len(re.findall(r"(?m)^@page\b[^{]*\{", style)) == 3
    strings = re.findall(r"content: (\"(?:[^\"\\\\]|\\\\.)*\")", style)
    assert len(strings) >= 6                      # head, title, site name, page number, cover blanks, contents
    for literal in strings:
        assert literal.count('"') == 2, literal   # nothing in the name closed the string early
    if '"' in cleaned or "}" in cleaned:
        assert "\\22 " in style or "\\7d " in style, "quotes and braces from a name must be escaped"
    assert cleaned in visible_text(document) or not cleaned  # the cover still prints it


@pytest.mark.browser
def test_the_longest_name_still_fits_the_running_head(chromium, caplog):
    """A 60-character Devanagari name is the widest thing the header can be asked to carry."""
    import logging

    with caplog.at_level(logging.WARNING, logger="app.pdf.browser"):
        pdf, _passes = _render(book("mr"), names={"self": "केशव" * 30})
    assert [record.getMessage() for record in caplog.records if "overflow" in record.getMessage()] == []
    assert browser.fallback_fonts(pdf) == set()


# ---- one book at a time, on the whole machine ------------------------------------------------------------


def test_the_render_limit_is_machine_wide_not_per_process(tmp_path, monkeypatch):
    """A book render peaks near 400 MB, so `--workers 2` must not mean two at once. The limit is a file
    lock: a second PROCESS has to wait for the first, not just a second thread."""
    import multiprocessing
    import textwrap

    lock = tmp_path / "pdf-render.lock"
    script = textwrap.dedent(f"""
        import os, sys, time
        sys.path.insert(0, {str(ROOT)!r})
        os.environ["PDF_MAX_CONCURRENT"] = "1"
        os.environ["PDF_RENDER_LOCK"] = {str(lock)!r}
        from app.pdf import browser
        started = time.time()
        with browser._slots():
            print("in", round(time.time() - started, 2), flush=True)
            time.sleep(float(sys.argv[1]))
    """)
    runner = tmp_path / "hold.py"
    runner.write_text(script, encoding="utf-8")

    import subprocess

    first = subprocess.Popen([sys.executable, str(runner), "1.5"], stdout=subprocess.PIPE, text=True)
    assert first.stdout.readline().startswith("in")          # it holds the only slot
    started = time.time()
    second = subprocess.run([sys.executable, str(runner), "0"], capture_output=True, text=True, timeout=60)
    waited = time.time() - started
    first.wait(timeout=30)
    assert second.returncode == 0, second.stderr
    assert waited > 0.5, f"the second process did not wait for the first ({waited:.2f}s)"
    assert multiprocessing  # noqa: B018 - imported for the reader: this is about processes, not threads


def test_the_config_check_warns_when_the_box_cannot_hold_a_render(monkeypatch):
    from app import hardening

    monkeypatch.setattr(hardening, "total_ram_mb", lambda: 900)
    monkeypatch.setenv("PDF_MAX_CONCURRENT", "1")
    fatal, warnings = hardening._pdf_memory_problem()
    assert not fatal and warnings and "900 MB RAM" in warnings[0] and "PDF_MAX_CONCURRENT" in warnings[0]

    monkeypatch.setenv("PDF_MAX_CONCURRENT", "3")   # asking for more than the box can hold is fatal
    fatal, warnings = hardening._pdf_memory_problem()
    assert fatal and not warnings

    monkeypatch.setattr(hardening, "total_ram_mb", lambda: 8000)
    assert hardening._pdf_memory_problem() == ([], [])


# ---- the FREE Basic Chart PDF -----------------------------------------------------------------------
#
# Three things are being defended here, in order of how expensive they would be to get wrong:
#   1. it must never call the AI (that is the product);
#   2. it must never print AI text even if some future edit hands it some (that is the back door);
#   3. it must not quietly become the paid book (that is the business).

from app.engine import compute_chart                                  # noqa: E402
from app.pdf.basic import build_basic_view, render_basic_html         # noqa: E402
from app.pdf.labels import ERA_NAMES, EXCLUDED_ITEMS                  # noqa: E402

BASIC_LANGS = ["en", "hi", "mr"]
# A birth in Chennai in 1890 was recorded on Madras time, which the engine flags as a non-standard clock;
# this Prayagraj minute in 2000 puts the lagna ~95 km from a sign boundary, which it flags as sensitive.
MADRAS_1890 = (dt.date(1890, 3, 4), dt.time(6, 30), "Chennai")
CUSP_2000 = (dt.date(2000, 1, 1), dt.time(7, 44), "Prayagraj")


def basic_chart(birth=None, *, city: str | None = None) -> dict:
    """An engine chart exactly as POST /api/chart/pdf computes one: `detail="basic"`, nothing else."""
    date, time, place = birth or (MIRAJ.date, MIRAJ.time, "Miraj")
    from app import engine

    found = engine.find_city(city or place)
    chart = compute_chart(date, time, found["lat"], found["lon"], found["tz"], as_of=AS_OF_DT, detail="basic")
    chart["input"]["city"] = found["name"]
    return chart


AS_OF_DT = dt.datetime.combine(AS_OF, dt.time(12, 0))


def test_the_free_chart_prints_every_promised_block_and_no_others():
    """The brief, item by item: both charts, the graha table with its six columns, mangal dosha,
    sade sati, the running dasha - and the "what this does not include" note."""
    chart = basic_chart()
    document = render_basic_html(chart, language="en")
    text = visible_text(document)
    L = Labels("en")

    assert document.count('class="kundali kundali--') == 2, "the D1 lagna chart and the D9 navamsa chart"
    assert L["chart_heading"] in text and L["navamsa_heading"] in text
    for column in ("col_sign", "col_degree", "col_nakshatra", "col_pada", "col_house", "col_retro"):
        assert L[column] in text, column
    assert L["col_combust"] in text, "the engine gives a combustion verdict on a basic chart; print it"
    for heading in ("mangal_heading", "sade_heading", "dasha_heading"):
        assert L[heading] in text, heading
    assert L["current_maha"] in text and L["current_antar"] in text
    current = chart["dasha"]["current"]
    for period in ("mahadasha", "antardasha"):
        dates = L.label(current[period], fallback_start=current[period]["start"],
                        fallback_end=current[period]["end"])
        assert dates and flat(dates) in flat(text), f"a current {period} without its dates is useless"
    assert L["excluded_heading"] in text and L["excluded_note"] in text
    assert all(item in text for item in L.excluded())
    assert DISCLAIMERS["en"] in text


def test_the_free_chart_leaves_the_paid_tiers_something_to_sell():
    """The product rule: the ₹49 and ₹249 tiers' extra value has to be obviously distinct. So the free sheet
    carries the CURRENT dasha and no more - not the complete Vimshottari table, which is the book's -
    and it says so in as many words instead of leaving the reader to discover the gap."""
    document = render_basic_html(basic_chart(), language="en")
    text = visible_text(document)
    L = Labels("en")
    assert L["full_dasha"] not in text and 'class="dasha-grid"' not in document
    assert L["maha_timeline"] not in text, "the mahadasha timeline is part of what is being sold"
    # by markup, not by wording: "Remedies, gemstone guidance ..." is what the excluded note SAYS
    assert 'class="remedy"' not in document and 'class="t-gems"' not in document
    assert 'class="window"' not in document and L["timeline_heading"] not in text
    # and the note that says all of that out loud, without ever naming a price (a PDF outlives a price list)
    assert L["excluded_heading"] in text
    assert not re.search(r"(?<![\d,])\d{2,4}\s*(?:rupees|INR|₹)|₹\s*\d", text), "no price in a PDF people keep"


AI_BLOCK_TYPES = ("prose", "bullets", "subsections", "windows", "remedies", "highlights", "dasha_grid",
                  "columns", "score")


def test_the_free_chart_template_has_no_macro_that_could_print_ai_text():
    """The structural half of the guarantee. templates/report.html draws the writer's prose through these
    block types; templates/basic.html must not know any of them, so that handing the free sheet AI text
    produces nothing at all rather than a leak."""
    basic = (ROOT / "app/pdf/templates/basic.html").read_text(encoding="utf-8")
    book = (ROOT / "app/pdf/templates/report.html").read_text(encoding="utf-8")
    body = basic.split("#}", 1)[1]  # the header comment names them in prose; the template must not
    for block_type in AI_BLOCK_TYPES:
        assert f'== "{block_type}"' in book, f"{block_type} should still be a book block - has it moved?"
        assert f'== "{block_type}"' not in body, f"basic.html grew a macro branch for {block_type}"


def test_the_free_chart_cannot_print_ai_text_even_when_it_is_handed_some():
    """The behavioural half. Every AI-written field of a real generated book is stapled onto the chart
    dict under every name the book reads it by; none of it may reach the page."""
    report = book("en")
    written = [report["summary"], report["title"], *(r["title"] for r in report["remedies"])]
    for chapter in all_chapters(report):
        written += chapter["paragraphs"] + chapter["bullets"]
        written += [w["headline"] for w in chapter["windows"] if w.get("headline")]
    written = [line for line in written if line and len(line.split()) > 3]
    assert len(written) > 50, "the fixture should carry plenty of AI prose to try to smuggle in"

    chart = basic_chart()
    polluted = {**chart, "parts": report["parts"], "sections": report.get("sections"),
                "summary": report["summary"], "remedies": report["remedies"], "title": report["title"],
                "highlights": report["parts"][0], "prose": written, "paragraphs": written,
                "bullets": written, "windows": written, "report": {"parts": report["parts"]}}
    text = visible_text(render_basic_html(polluted, language="en"))
    leaked = [line for line in written if line in text]
    assert leaked == [], f"the free chart printed writer's text: {leaked[:2]}"


def test_the_free_chart_says_it_has_no_ai_and_never_names_ai_without_the_engine():
    """The trust rules, and the one the brief calls out by name: AI is never mentioned without
    Swiss Ephemeris nearby in the same section. For the free sheet that means saying outright that there
    is no AI in it - the reader arrives from pages that do talk about AI."""
    for language in BASIC_LANGS:
        L = Labels(language)
        document = render_basic_html(basic_chart(), language=language)
        text = visible_text(document)
        assert L["trust_heading_chart"] in text and L["trust_calc"] in text
        assert L["trust_no_ai"] in text
        assert L["trust_ai"] not in text, "the free sheet must not claim an AI explained anything"
        engine_name = "Swiss Ephemeris" if language == "en" else "स्विस एफेमेरिस"
        for section in re.findall(r'<section class="trust">(.*?)</section>', document, flags=re.S):
            assert "AI" in section and engine_name in section


@pytest.mark.parametrize("language", BASIC_LANGS)
def test_every_pdf_carries_the_trust_box_before_anything_it_explains(language):
    """The trust rules want it on the cover or the FIRST page - of every PDF, not only the
    free one. The book's cover is full, so it opens the front-matter page, which is the first page the
    reader reads through and comes before the contents rather than behind forty chapters of them."""
    L = Labels(language)
    document = render_report_html(make_report("sade-sati-guide", language))
    text = visible_text(document)
    assert L["trust_heading"] in text and L["trust_calc"] in text and L["trust_ai"] in text
    front = document.index('class="frontmatter"')
    assert front < document.index('class="contents"'), "front matter comes before the table of contents"
    assert document.index('class="trust"') < document.index('class="contents"')
    for section in re.findall(r'<section class="trust">(.*?)</section>', document, flags=re.S):
        assert "AI" in section and ("Swiss Ephemeris" in section or "स्विस एफेमेरिस" in section)


def test_the_trust_box_does_not_add_a_heading_the_contents_page_would_have_to_number():
    """The two-pass contents page zips heading ids against the PDF outline. Front matter carries no
    heading element, so the zip is exactly what it was before it existed."""
    report = book("mr")
    ids = heading_ids(render_report_html(report))
    assert ids == [f"hd-{n}" for n in range(1, len(ids) + 1)]
    document = render_report_html(report)
    front = document[document.index('class="frontmatter"'):document.index('class="contents"')]
    assert not re.search(r"<h[1-6]\b", front), "front matter must not introduce a heading"


@pytest.mark.parametrize("language", BASIC_LANGS)
def test_the_accuracy_caveats_are_printed_exactly_when_the_engine_flags_them(language):
    """Word for word what app/static/js/render.js prints on the chart page - a customer who reads the
    page and then the PDF is told the same thing twice, not two different things once. And nothing at
    all on the ~94% of charts the engine flags neither way."""
    L = Labels(language)
    quiet = basic_chart()
    assert not quiet["accuracy"]["lagna_boundary"]["sensitive"]
    assert not quiet["accuracy"]["clock"]["non_standard"]
    assert L["acc_heading"] not in visible_text(render_basic_html(quiet, language=language))

    clock = basic_chart(MADRAS_1890)
    assert clock["accuracy"]["clock"]["non_standard"] and clock["accuracy"]["clock"]["era"] == "madras_time"
    text = flat(visible_text(render_basic_html(clock, language=language)))
    assert L["acc_heading"] in text
    assert L.era({"era": "madras_time"}) in text
    assert "9" in text and L["acc_behind"] in text

    place = basic_chart(CUSP_2000)
    assert place["accuracy"]["lagna_boundary"]["sensitive"]
    text = flat(visible_text(render_basic_html(place, language=language)))
    boundary = place["accuracy"]["lagna_boundary"]
    assert L["acc_heading"] in text and L["acc_km"] in text
    assert str(round(boundary["km_to_change_sign"])) in text
    assert L.sign(boundary["adjacent_sign"], short=True) in text
    assert "Prayagraj" in text, "the caveat names the city, so a reader can judge it"


def test_the_book_prints_the_same_caveats_the_free_chart_does():
    """A paid reader is not told less than a free one. Same block, same words, on the front-matter page."""
    report = book("en")
    report["data"]["chart"]["accuracy"] = basic_chart(MADRAS_1890)["accuracy"]
    text = visible_text(render_report_html(report))
    assert Labels("en")["acc_heading"] in text and "Madras time" in text


def test_every_language_has_every_free_chart_label():
    for table in (EXCLUDED_ITEMS, tuple(ERA_NAMES.values())):
        assert all(len(triple) == 3 and all(triple) for triple in table)
    assert len(EXCLUDED_ITEMS) == 4
    for language in BASIC_LANGS:
        view = build_basic_view(basic_chart(), language=language)
        assert view["lang"] == language and view["title"] and view["disclaimer"]


def test_the_free_chart_escapes_a_hostile_name_like_the_book_does():
    document = render_basic_html(basic_chart(), language="mr", name='<b>x</b>‮" ; }')
    style, body = document[:document.index("</style>")], document.split("</style>", 1)[1]
    assert "<script" not in document and "<b>x</b>" not in body
    for literal in re.findall(r"content: (\"(?:[^\"\\\\]|\\\\.)*\")", style):
        assert literal.count('"') == 2, literal


# ---- the brand palette -------------------------------------------------------------------------------
#
# site.css calls its ten --color-* tokens "the contract with the PDF report", so the two sheets are
# compared here token by token, and the two colour rules are measured with the SAME parser the web sheet
# is measured with (tests/test_brand_css.py) rather than with a second opinion about what gold is.

from tests import test_brand_css as brand                              # noqa: E402

PRINT_CSS = ROOT / "app/pdf/templates/print.css"
SHARED_TOKENS = ("--color-primary", "--color-accent", "--color-saffron", "--color-ink", "--color-muted",
                 "--color-bg", "--color-card", "--color-tint", "--color-success", "--color-warning",
                 "--color-success-ink", "--color-success-bg", "--color-warning-bg", "--color-surface",
                 "--color-line", "--color-on-dark", "--color-meta-dark")


def print_css_rules():
    return brand._rules(PRINT_CSS.read_text(encoding="utf-8"))


def print_css_tokens():
    return {name: value for selector, decls in print_css_rules() if selector == ":root"
            for name, value in decls.items() if name.startswith("--")}


@pytest.fixture
def print_palette(monkeypatch):
    """Point the web sheet's colour parser at print.css instead, so `_rgb` resolves OUR var() names."""
    monkeypatch.setattr(brand, "ROOT_TOKENS", print_css_tokens())
    return print_css_tokens()


def test_the_pdf_and_the_web_share_one_palette(print_palette):
    """The two stylesheets cannot be edited apart: same names, same values."""
    for token in SHARED_TOKENS:
        assert token in print_palette, f"{token} is missing from print.css"
        assert token in brand.ROOT_TOKENS or True
        web = brand._rules(brand.CSS)
        web_tokens = {name: value for selector, decls in web if selector == ":root"
                      for name, value in decls.items() if name.startswith("--")}
        assert print_palette[token].strip().lower() == web_tokens[token].strip().lower(), (
            f"{token}: print.css says {print_palette[token]}, site.css says {web_tokens[token]}")


def test_the_pdf_palette_is_the_one_in_the_guidelines(print_palette):
    for token, value in (("--color-primary", "#241b54"), ("--color-accent", "#e0a526"),
                         ("--color-saffron", "#d2691e"), ("--color-ink", "#1e1b2e"),
                         ("--color-muted", "#5c5875"), ("--color-bg", "#fbf8f1"),
                         ("--color-card", "#2e2660"), ("--color-tint", "#f3effa"),
                         ("--color-success", "#2e9e5b"), ("--color-warning", "#a13d2b")):
        assert print_palette[token].strip().lower() == value, token


def test_no_rule_in_the_print_sheet_puts_light_text_on_gold(print_palette):
    """Brand section 2's most-made mistake, measured rather than grepped: every rule that paints gold
    must say what colour its text is, and the pair must clear 4.5:1."""
    gold_compounds, failures = set(), []
    for selector_list, decls in print_css_rules():
        background = brand._background(decls)
        if not brand._is_gold(background):
            continue
        gold_compounds |= {brand._compound(s) for s in brand._selectors(selector_list)}
        colour = decls.get("color")
        if colour is None:
            failures.append(f"{selector_list}: paints gold but never says what colour its text is")
            continue
        text, gold = brand._rgb(colour), brand._rgb(background)
        if text is None or brand.contrast(text, gold) < brand.AA:
            failures.append(f"{selector_list}: {colour} on gold is unreadable")
    assert gold_compounds, "no gold surface in the print sheet at all - has the palette moved?"
    assert failures == []


def test_success_and_saffron_are_never_text_in_the_print_sheet(print_palette):
    """Neither clears AA on Cream (3.22:1 and 3.43:1). They are fills, rules and marks here; the words
    are --color-success-ink and Ink. This is the finding the guidelines' own contrast table misses."""
    unreadable = {brand._hex(brand._rgb(print_palette[token])) for token in ("--color-success", "--color-saffron")}
    offenders = []
    for selector, decls in print_css_rules():
        rgb = brand._rgb(decls["color"]) if "color" in decls else None
        if rgb is not None and brand._hex(rgb) in unreadable:
            offenders.append(selector)
        fill = brand._rgb(decls["fill"]) if "fill" in decls else None   # the SVG chart sets `fill`, not `color`
        if fill is not None and brand._hex(fill) in unreadable and "kundali" in selector:
            offenders.append(selector)
    assert offenders == [], f"{offenders} set text in a colour that fails AA on cream"
    page = brand._rgb(print_palette["--color-bg"])
    assert brand.contrast(brand._rgb(print_palette["--color-success-ink"]), page) >= brand.AA
    assert brand.contrast(brand._rgb(print_palette["--color-warning"]), page) >= brand.AA


def test_every_declared_colour_pair_in_the_print_sheet_clears_aa(print_palette):
    """The general form of the gold rule. Every rule that paints a surface AND sets its text colour is
    measured, whatever the two colours are - so a status colour dropped onto an indigo table head, or a
    new tint that nobody checked, fails here rather than in somebody's hands.

    Neither status colour works on an indigo ground: Warning on Card is 2.06:1 and --color-success-ink
    is 2.06:1. Nothing in either document does that today (the only indigo surfaces are the cover, the
    free sheet's head band and `thead th`, and every status colour sits on its own tint or on Cream),
    and this test is what keeps it that way. If one is ever needed there, the status has to be carried
    by --color-on-dark plus a mark or a gold rule, not by hue."""
    failures, unparsed = [], []
    for selector, decls in print_css_rules():
        background = brand._background(decls)
        if "color" not in decls or background is None:
            continue
        text, ground = brand._rgb(decls["color"]), brand._rgb(background)
        if text is None or ground is None:
            unparsed.append(f"{selector}: {decls['color']!r} on {background!r}")
            continue
        ratio = brand.contrast(text, ground)
        if ratio < brand.AA:
            failures.append(f"{selector}: {brand._hex(text)} on {brand._hex(ground)} is {ratio:.2f}:1")
    assert unparsed == [], f"a colour this test could not read is a colour nobody checked: {unparsed}"
    assert failures == []
    assert len([1 for selector, decls in print_css_rules()
                if "color" in decls and brand._background(decls)]) >= 8, "did the sheet stop painting?"


WARNING_SURFACES = (".banner--warn", ".caveats", ".caveats-title", "tr.is-flagged td:last-child")


def test_warning_is_the_only_caution_colour_and_carries_only_cautions(print_palette):
    """Brand section 5: Warning is for an active mangal dosha, an active sade sati and caution windows -
    never Saffron, never a plain red. Checked in the sheet and in what the renderer actually emits."""
    warning = brand._hex(brand._rgb(print_palette["--color-warning"]))
    assert warning == "#a13d2b"
    painted = set()
    for selector_list, decls in print_css_rules():
        for prop in ("color", "background", "background-color", "border-left-color", "border-color"):
            rgb = brand._rgb(decls[prop]) if prop in decls else None
            if rgb and brand._hex(rgb) == warning:
                painted |= set(brand._selectors(selector_list))
    assert painted, "nothing uses Warning at all"
    for selector in painted:
        assert any(surface in selector for surface in WARNING_SURFACES), (
            f"{selector} paints Warning but is not a dosha, a sade sati or a caution note")

    L = Labels("en")
    chart = basic_chart()
    assert chart["mangal_dosha"]["present"], "the reference chart should have mangal dosha to colour"
    # a dosha a classical exception cancels is information, not a caution, and stays neutral - so the
    # tone under test here is the uncancelled one
    chart = {**chart, "mangal_dosha": {**chart["mangal_dosha"], "cancellation_applies": False}}
    document = render_basic_html(chart, language="en")
    banner = re.search(r'<div class="banner banner--(\w+)"><p class="banner-title">([^<]*)', document)
    assert banner.group(1) == "warn" and L.mangal_status(chart["mangal_dosha"]) in banner.group(2)


def test_an_active_sade_sati_is_a_caution_and_an_absent_one_is_not():
    """The renderer's own mapping, which Brand section 5 spells out. The engine's verdict is forced here
    rather than hunted for, because what is under test is the tone the sheet gives each verdict."""
    chart = basic_chart()
    assert not chart["sade_sati"]["active"]
    tones = re.findall(r'banner banner--(\w+)"><p class="banner-title">([^<]*)', render_basic_html(chart))
    assert ("ok", Labels("en").sade_status("inactive")) in [(tone, title.strip()) for tone, title in tones]

    running = {**chart, "sade_sati": {**chart["sade_sati"], "active": True, "phase": "rising",
                                      "cycle": {**(chart["sade_sati"].get("cycle") or {}), "which": "current"}}}
    tones = dict((title.strip(), tone) for tone, title in
                 re.findall(r'banner banner--(\w+)"><p class="banner-title">([^<]*)', render_basic_html(running)))
    active = [title for title in tones if Labels("en").sade_status("active") in title]
    assert active and tones[active[0]] == "warn", "an active sade sati is a caution period (Brand section 5)"


# ---- POST /api/chart/pdf: free, ungated, and never an AI call -----------------------------------------


BASIC_BODY = {"date": "1931-10-15", "time": "06:30", "city": "Miraj", "language": "en"}


@pytest.fixture
def no_ai(monkeypatch):
    """Any attempt to build an AI client anywhere fails loudly for the duration of the test."""
    import app.ai.chat as chat_module
    import app.ai.client as client_module
    import app.ai.report as report_module_

    def forbidden(*args, **kwargs):
        raise AssertionError("the free chart PDF built an AI client")

    for module in (client_module, chat_module, report_module_):
        if hasattr(module, "ClaudeClient"):
            monkeypatch.setattr(module, "ClaudeClient", forbidden)
    monkeypatch.setattr(report_module_, "generate_report", forbidden)


@pytest.fixture
def fake_basic_chromium(monkeypatch):
    """html_to_pdf without a browser: returns the document it was given, so the route can be exercised."""
    seen = []

    def fake(html, **kwargs):
        seen.append(html)
        return b"%PDF-1.4 fake\n%%EOF"

    monkeypatch.setattr(service, "html_to_pdf", fake)
    return seen


def test_the_free_chart_pdf_route_is_not_gated_and_never_calls_the_ai(no_ai, fake_basic_chromium):
    """No entitlement, no cookie, no order - and no model client built anywhere on the path."""
    response = TestClient(app).post("/api/chart/pdf", json=BASIC_BODY)
    assert response.status_code == 200, response.text
    assert response.content.startswith(b"%PDF")
    assert response.headers["content-disposition"].startswith("attachment")
    assert "basic-chart-1931-10-15-en.pdf" in response.headers["content-disposition"]
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-robots-tag"] == "noindex"
    document = fake_basic_chromium[0]
    assert 'class="trust"' in document and document.count('class="kundali kundali--') == 2


def test_the_free_chart_pdf_route_computes_the_chart_itself(no_ai, fake_basic_chromium):
    """A chart sent BY the caller would be attacker-controlled text inside a PDF we put our name on, so
    the route takes birth details only - and anything else in the body is simply not a field."""
    client = TestClient(app)
    hostile = {**BASIC_BODY, "chart": {"grahas": {}}, "summary": "BUY MY COURSE",
               "parts": [{"heading": "BUY MY COURSE"}], "name": "Keshav"}
    response = client.post("/api/chart/pdf", json=hostile)
    assert response.status_code == 200
    assert "BUY MY COURSE" not in fake_basic_chromium[-1]
    assert "Keshav" in fake_basic_chromium[-1], "the one string a caller may put on the sheet"

    assert client.post("/api/chart/pdf", json={**BASIC_BODY, "city": "Atlantis"}).status_code == 422
    assert client.post("/api/chart/pdf", json={**BASIC_BODY, "language": "fr"}).status_code == 422


def test_the_free_chart_pdf_is_cached_by_its_own_rendered_html(no_ai, fake_basic_chromium):
    client = TestClient(app)
    assert client.post("/api/chart/pdf", json=BASIC_BODY).status_code == 200
    files = sorted(service.basic_dir().glob("*.pdf"))
    assert len(files) == 1 and files[0].name.startswith("chart-")

    assert client.post("/api/chart/pdf", json=BASIC_BODY).status_code == 200
    assert len(fake_basic_chromium) == 1, "the second download came from the cache"
    assert client.post("/api/chart/pdf", json={**BASIC_BODY, "language": "mr"}).status_code == 200
    assert len(fake_basic_chromium) == 2 and len(sorted(service.basic_dir().glob("*.pdf"))) == 2


def test_the_free_chart_cache_has_a_ceiling(monkeypatch, no_ai, fake_basic_chromium):
    """It is a free endpoint: the cache cannot be allowed to grow with however many charts arrive."""
    monkeypatch.setenv("PDF_BASIC_CACHE_MAX", "3")
    monkeypatch.setenv("BASIC_PDF_HOURLY_LIMIT", "50")
    client = TestClient(app)
    for minute in range(6):
        body = {**BASIC_BODY, "time": f"06:{minute:02d}"}
        assert client.post("/api/chart/pdf", json=body).status_code == 200
    assert len(sorted(service.basic_dir().glob("*.pdf"))) == 3


def test_the_free_chart_pdf_route_is_rate_limited(monkeypatch, no_ai, fake_basic_chromium):
    """A Chromium render is the most expensive thing this server does, and this is the only route that
    runs one for somebody who has not paid."""
    monkeypatch.setenv("BASIC_PDF_HOURLY_LIMIT", "2")
    client = TestClient(app)
    for minute in range(2):
        assert client.post("/api/chart/pdf", json={**BASIC_BODY, "time": f"06:{minute:02d}"}).status_code == 200
    response = client.post("/api/chart/pdf", json={**BASIC_BODY, "time": "06:59"})
    assert response.status_code == 429
    assert response.json()["detail"]["error"] == "rate_limited"
    assert int(response.headers["retry-after"]) > 0


def test_the_rate_limit_counts_renders_not_downloads(monkeypatch, no_ai, fake_basic_chromium):
    """The limit rations Chromium, so a CACHE HIT COSTS NOTHING. This is what makes the limit survivable
    behind CGNAT: a whole carrier NAT pool shares one public IPv4, and re-downloading a sheet somebody has
    already generated must not spend the pool's budget on a render that does not happen."""
    monkeypatch.setenv("BASIC_PDF_HOURLY_LIMIT", "1")
    client = TestClient(app)
    for _ in range(5):
        assert client.post("/api/chart/pdf", json=BASIC_BODY).status_code == 200
    assert len(fake_basic_chromium) == 1, "one render for five downloads"
    # a DIFFERENT chart is a real render, and that is what the budget is for
    assert client.post("/api/chart/pdf", json={**BASIC_BODY, "time": "07:15"}).status_code == 429


def test_the_free_sheet_queues_for_a_bounded_time_then_gives_up(monkeypatch, no_ai):
    """Both PDF routes are sync, so they run in FastAPI's threadpool; a free download that queued
    indefinitely for the machine-wide render slot would hold one of those threads for the whole render,
    and enough of them starve every route on the site. So it waits a BOUNDED time and then refuses."""
    asked = {}

    def busy(html, **kwargs):
        asked.update(kwargs)
        raise browser.PdfBusy("every render slot on this machine is busy")

    monkeypatch.setattr(service, "html_to_pdf", busy)
    response = TestClient(app).post("/api/chart/pdf", json=BASIC_BODY)
    wait = asked.get("wait")
    assert wait is not True and isinstance(wait, (int, float)) and 0 <= wait <= 10, (
        f"the free sheet must ask for a BOUNDED wait, not {wait!r}")
    assert wait == service.free_wait_seconds()
    # and when it runs out it refuses - it must never fall through into a render
    assert response.status_code == 503 and response.json()["detail"]["error"] == "pdf_busy"
    assert response.headers["retry-after"] == "10"


def test_the_route_refuses_against_a_REAL_held_slot_rather_than_blocking(tmp_path, monkeypatch, no_ai):
    """The seam between the two tests around it.

    `test_the_free_sheet_queues_for_a_bounded_time_then_gives_up` fakes the render and checks the route's
    half; `test_a_bounded_waiter_picks_the_slot_up_when_the_holder_lets_go` uses a real slot but not the
    route. Neither would notice if the two stopped being wired together - if `wait` were dropped on the
    way down, the route would block for the whole render instead of refusing, and both would still pass.
    So this one holds the machine-wide slot for real and goes in through HTTP.

    No browser is launched: `_slots` raises before Chromium is ever started, which is the point."""
    monkeypatch.setenv("PDF_RENDER_LOCK", str(tmp_path / "render.lock"))
    monkeypatch.setenv("PDF_MAX_CONCURRENT", "1")
    monkeypatch.setenv("PDF_FREE_WAIT_SECONDS", "0.4")
    monkeypatch.setattr(browser, "_semaphore", None)

    launched = []
    monkeypatch.setattr(browser, "launch_options", lambda: launched.append(True) or {})

    holding = threading.Event()
    release = threading.Event()

    def hold():
        with browser._slots():
            holding.set()
            release.wait(timeout=20)

    holder = threading.Thread(target=hold)
    holder.start()
    assert holding.wait(timeout=10), "the holder never took the slot"
    try:
        started = time.monotonic()
        response = TestClient(app).post("/api/chart/pdf", json=BASIC_BODY)
        waited = time.monotonic() - started
    finally:
        release.set()
        holder.join(timeout=20)

    assert response.status_code == 503, response.text
    assert response.json()["detail"]["error"] == "pdf_busy"
    assert response.headers["retry-after"] == "10"
    assert waited >= 0.35, f"it refused without honouring the bound ({waited:.2f}s)"
    assert waited < 10, f"it blocked instead of refusing ({waited:.2f}s)"
    assert launched == [], "no browser may be started when the slot was never free"


def test_the_bounded_wait_is_configurable_and_survives_nonsense(monkeypatch):
    assert service.free_wait_seconds() == service.DEFAULT_FREE_WAIT_SECONDS == 2.0
    monkeypatch.setenv("PDF_FREE_WAIT_SECONDS", "0")
    assert service.free_wait_seconds() == 0.0        # refuse instantly, the old behaviour
    monkeypatch.setenv("PDF_FREE_WAIT_SECONDS", "not a number")
    assert service.free_wait_seconds() == service.DEFAULT_FREE_WAIT_SECONDS


def test_a_paid_book_still_waits_its_turn_and_the_free_sheet_does_not(tmp_path, monkeypatch):
    """The free sheet refuses to queue - a queued request holds a threadpool thread, and this is the
    route an anonymous visitor can fire at will - while a paid book is QUEUED rather than refused.

    The render slot is machine-wide state that every other renderer shares, so this test gets its own
    lock file and its own semaphore rather than borrowing the real ones - otherwise it is a race against
    whatever else on the box is printing, which is exactly how it first failed."""
    import inspect

    assert inspect.signature(browser._slots).parameters["wait"].default is True
    assert "wait" not in inspect.signature(browser.render_book).parameters, "a book never refuses to queue"
    assert inspect.signature(browser.html_to_pdf).parameters["wait"].default is True

    monkeypatch.setenv("PDF_RENDER_LOCK", str(tmp_path / "render.lock"))
    monkeypatch.setenv("PDF_MAX_CONCURRENT", "1")
    monkeypatch.setattr(browser, "_semaphore", None)  # rebuilt from the env above, restored afterwards

    with browser._slots():                                    # something is already printing
        with pytest.raises(browser.PdfBusy):
            with browser._slots(wait=False):                  # wait=False still refuses at once
                pass
        started = time.monotonic()
        with pytest.raises(browser.PdfBusy):
            with browser._slots(wait=0.3):                    # a bounded waiter gives up ON TIME ...
                pass
        waited = time.monotonic() - started
        assert 0.25 <= waited < 3, f"the bound must actually bound: waited {waited:.2f}s for 0.3s"
    with browser._slots(wait=False):                          # and takes its turn once the slot is free
        pass


def test_a_bounded_waiter_picks_the_slot_up_when_the_holder_lets_go(tmp_path, monkeypatch):
    """The point of the bound is that most collisions are SHORTER than it, so the download succeeds a
    moment late instead of failing. Its own lock file again, for the reason above."""
    monkeypatch.setenv("PDF_RENDER_LOCK", str(tmp_path / "render.lock"))
    monkeypatch.setenv("PDF_MAX_CONCURRENT", "1")
    monkeypatch.setattr(browser, "_semaphore", None)

    released = threading.Event()

    def hold():
        with browser._slots():
            time.sleep(0.4)
        released.set()

    holder = threading.Thread(target=hold)
    holder.start()
    time.sleep(0.1)
    started = time.monotonic()
    with browser._slots(wait=5.0):                            # generous: this asserts rescue, not timing
        waited = time.monotonic() - started
    holder.join(timeout=10)
    assert released.is_set()
    assert waited >= 0.2, f"it cannot have been free all along ({waited:.2f}s)"


def test_the_free_chart_pdf_route_reports_browser_failure_as_503(monkeypatch, no_ai):
    def boom(html, **kwargs):
        raise browser.PdfError("chromium is not installed")

    monkeypatch.setattr(service, "html_to_pdf", boom)
    response = TestClient(app).post("/api/chart/pdf", json=BASIC_BODY)
    assert response.status_code == 503 and response.json()["detail"]["error"] == "pdf_unavailable"


# ---- the gold rule, measured on the printed pixels ----------------------------------------------------
#
# The stylesheet test above reads declarations. This one reads the PDF. They catch different things: a
# `color` inherited from an ancestor, an SVG `fill`, a gold surface painted by a rule the parser did not
# join up. The detector looks for a LIGHT pixel with gold in all four directions within a few pixels -
# which is what a white glyph on a gold badge looks like and what a gold rule beside cream does not.

GOLD_RGB = (224, 165, 38)
GOLD_TOLERANCE = 34
LIGHT_FLOOR = 238     # white is 255; Cream #FBF8F1 is 241; the warm Saffron tint #FAEEE3 is 227
REACH = 15            # px at RASTER_SCALE (about 2mm): far enough to cross a glyph, not a page gutter
THICK = 5             # a gold SURFACE is gold at least this many px across, which a thin rule is not
RASTER_SCALE = 2.0


def _channel_mask(image, test):
    from PIL import ImageChops

    mask = None
    for index, band in enumerate(image.split()[:3]):
        band_mask = band.point(lambda value, i=index: 255 if test(value, i) else 0, mode="1")
        mask = band_mask if mask is None else ImageChops.logical_and(mask, band_mask)
    return mask


def gold_surfaces(image):
    """Gold that is a SURFACE, not a rule: the gold mask eroded by THICK px, so a 1mm divider or a gold
    left border erodes to nothing while a badge or a table-header strip keeps a solid core. Brand
    section 2 is about gold-BACKGROUND components; a hairline beside cream is not one."""
    from PIL import ImageFilter

    gold = _channel_mask(image, lambda value, i: abs(value - GOLD_RGB[i]) <= GOLD_TOLERANCE)
    return gold.convert("L").filter(ImageFilter.MinFilter(THICK)).point(lambda v: 255 if v > 127 else 0, mode="1")


def ink_on_surface(image, ink, surface) -> int:
    """Pixels of `ink` that have a `surface` SURFACE within REACH px in all four directions - which is
    what a glyph sitting on that surface looks like, and what a glyph merely beside a rule does not."""
    from PIL import Image, ImageChops

    enclosed = None
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        found = Image.new("1", image.size, 0)
        for step in range(1, REACH + 1):
            found = ImageChops.logical_or(found, ImageChops.offset(surface, -step * dx, -step * dy))
        enclosed = found if enclosed is None else ImageChops.logical_and(enclosed, found)
    return ImageChops.logical_and(ink, enclosed).convert("L").histogram()[255]


def light_on_gold(image) -> int:
    """Brand section 2, on the paper: a light glyph on a gold surface."""
    light = _channel_mask(image, lambda value, i: value >= LIGHT_FLOOR)
    return ink_on_surface(image, light, gold_surfaces(image))


# The two indigo grounds and the two status inks. Neither ink is legible on either ground (2.06:1), so
# a status that ever has to appear on indigo has to be carried by --color-on-dark plus a mark.
INDIGO_RGB = ((46, 38, 96), (36, 27, 84))           # --color-card, --color-primary
STATUS_RGB = ((161, 61, 43), (31, 110, 63))         # --color-warning, --color-success-ink


def status_on_indigo(image) -> int:
    from PIL import ImageChops, ImageFilter

    ground = None
    for rgb in INDIGO_RGB:
        mask = _channel_mask(image, lambda value, i, rgb=rgb: abs(value - rgb[i]) <= 22)
        ground = mask if ground is None else ImageChops.logical_or(ground, mask)
    ground = ground.convert("L").filter(ImageFilter.MinFilter(THICK)).point(lambda v: 255 if v > 127 else 0, mode="1")

    ink = None
    for rgb in STATUS_RGB:
        mask = _channel_mask(image, lambda value, i, rgb=rgb: abs(value - rgb[i]) <= 30)
        ink = mask if ink is None else ImageChops.logical_or(ink, mask)
    return ink_on_surface(image, ink, ground)


def _pages(pdf: bytes, scale: float = RASTER_SCALE):
    pypdfium2 = pytest.importorskip("pypdfium2")
    pytest.importorskip("PIL")
    document = pypdfium2.PdfDocument(io.BytesIO(pdf))
    for index in range(len(document)):
        yield index + 1, document[index].render(scale=scale).to_pil().convert("RGB")


SWATCH = ("<!DOCTYPE html><html><head><style>%s\n@page { size: A5 portrait; margin: 10mm; }"
          ".sw { background: %s; font-size: 9pt; font-weight: 700; padding: 4mm; }"
          "</style></head><body><p class='sw' style='color: %s'>%s</p></body></html>")
SWATCH_WORDS = "Mangal dosha is present Sade sati Shukra Guru " * 3


def _swatch(surface: str, colour: str) -> bytes:
    return browser.html_to_pdf(SWATCH % (PRINT_CSS.read_text(encoding="utf-8"), surface, colour, SWATCH_WORDS))


@pytest.mark.browser
@pytest.mark.parametrize("detector, surface, good, bad", [
    (lambda image: light_on_gold(image), "var(--color-accent)",
     "var(--color-ink)", "#fff"),
    (lambda image: status_on_indigo(image), "var(--color-card)",
     "var(--color-on-dark)", "var(--color-warning)"),
    (lambda image: status_on_indigo(image), "var(--color-card)",
     "var(--color-on-dark)", "var(--color-success-ink)"),
])
def test_each_pixel_detector_is_proved_on_a_control_before_it_is_trusted(chromium, detector, surface, good, bad):
    """Controls, so that a green result on a real page means "no violation" rather than "the detector is
    broken". Each pair is built from the sheet's own tokens: the correct pairing, then the bug."""
    assert sum(detector(image) for _page, image in _pages(_swatch(surface, good))) == 0
    assert sum(detector(image) for _page, image in _pages(_swatch(surface, bad))) > 50, \
        "the detector cannot see the bug it exists to catch"


@pytest.mark.browser
def test_no_light_text_sits_on_gold_in_either_printed_document(chromium):
    """Brand section 2, on the paper. Every page of the free chart sheet and of the book."""
    free = browser.html_to_pdf(render_basic_html(basic_chart(MADRAS_1890), language="mr", name="केशव"))
    paid, _passes = _render(book("mr"), names={"self": "केशव"})
    offenders = [(name, number, count) for name, pdf in (("free", free), ("book", paid))
                 for number, image in _pages(pdf) if (count := light_on_gold(image))]
    assert offenders == [], f"light text on a gold surface: {offenders}"


@pytest.mark.browser
def test_the_free_chart_pdf_prints_with_only_the_bundled_fonts(chromium):
    pypdf = pytest.importorskip("pypdf")
    for language, name in (("mr", "केशव"), ("hi", "केशव"), ("en", "Keshav")):
        pdf = browser.html_to_pdf(render_basic_html(basic_chart(MADRAS_1890), language=language, name=name))
        assert pdf.startswith(b"%PDF-") and browser.fallback_fonts(pdf) == set()
        reader = pypdf.PdfReader(io.BytesIO(pdf))
        assert 3 <= len(reader.pages) <= 10, f"a few sheets, not a book: {len(reader.pages)}"
        assert round(reader.pages[0].mediabox.width) == 420, "A5 portrait"
        first = reader.pages[0].extract_text()
        # the trust box has to be on the FIRST page (a trust requirement). Devanagari conjuncts do
        # not always survive extraction, so look for the Latin "AI" that every language's wording carries.
        assert "AI" in first or "Swiss" in first
        assert "Madras" in first or "मद्रास" in first or "AI" in first


@pytest.mark.browser
def test_nothing_in_the_free_chart_is_wider_than_the_page(chromium):
    """Chromium shrinks the WHOLE document to fit anything wider than the first page's content box."""
    with caplog_at_warning() as records:
        browser.html_to_pdf(render_basic_html(basic_chart(MADRAS_1890), language="mr", name="केशव" * 15))
    assert [message for message in records if "overflow" in message] == []


@pytest.mark.browser
def test_the_free_chart_pdf_over_http_end_to_end(chromium):
    """`pdf_busy` is a legitimate answer - the route refuses to queue for the machine-wide render slot -
    and another test on this box may hold it, so retry on exactly that. Any OTHER 503 is a real failure
    and fails immediately rather than being retried into a pass."""
    client = TestClient(app)
    for attempt in range(6):
        response = client.post("/api/chart/pdf", json={**BASIC_BODY, "language": "mr", "name": "केशव"})
        if response.status_code != 503:
            break
        detail = response.json()["detail"]
        assert detail["error"] == "pdf_busy", detail
        time.sleep(0.5 * (attempt + 1))
    assert response.status_code == 200, response.text
    assert response.content.startswith(b"%PDF-")
    assert browser.fallback_fonts(response.content) == set()
    assert len(sorted(service.basic_dir().glob("*.pdf"))) == 1


@pytest.mark.browser
def test_no_status_colour_sits_on_an_indigo_ground(chromium):
    """Warning `#A13D2B` and `--color-success-ink` are both 2.06:1 on Card `#2E2660` - unreadable. The
    declaration test above says no RULE does that; this says no PIXEL does, which also covers a status
    colour inherited onto an indigo surface by a rule that never mentions a background."""
    free = browser.html_to_pdf(render_basic_html(basic_chart(MADRAS_1890), language="mr", name="केशव"))
    paid, _passes = _render(book("mr"), names={"self": "केशव"})
    offenders = [(name, number, count) for name, pdf in (("free", free), ("book", paid))
                 for number, image in _pages(pdf) if (count := status_on_indigo(image))]
    assert offenders == [], f"a status colour on an indigo ground: {offenders}"


# ---- an approximate birth time ---------------------------------------------------------------------
#
# The form offers tap-to-select time presets up to three hours wide for people who do not know their
# birth time. The numbers in these tests come from a sweep of 150 random births compared across a
# three-hour bucket (the method is in `blocks.accuracy_block`'s docstring); they are what the caveat
# claims, so a change in either has to move the other.


def test_an_approximate_time_is_caveated_and_an_exact_one_is_not():
    chart = basic_chart()
    assert not chart["accuracy"]["lagna_boundary"]["sensitive"]   # nothing else would raise a caveat
    assert not chart["accuracy"]["clock"]["non_standard"]
    L = Labels("en")

    exact = visible_text(render_basic_html(chart, language="en"))
    assert L["acc_heading"] not in exact and L["acc_approx_time"] not in exact

    approx = visible_text(render_basic_html(chart, language="en", approximate_time=True))
    assert L["acc_heading"] in approx and L["acc_approx_time"] in approx
    assert L["acc_approx_dasha"] in approx, "the dated section repeats it where the dates are read"


@pytest.mark.parametrize("language", BASIC_LANGS)
def test_the_approximate_time_caveat_comes_first_and_is_in_every_language(language):
    """It dominates the other two: a three-hour bucket moves the lagna every single time, where a
    near-cusp birthplace moves it rarely. So it is the first thing in the box, not the last."""
    L = Labels(language)
    document = render_basic_html(basic_chart(CUSP_2000), language=language, approximate_time=True)
    box = re.search(r'<section class="caveats">(.*?)</section>', document, flags=re.S).group(1)
    assert L["acc_approx_time"] in box and L["acc_place"].split("{")[0].strip() in box, "both caveats print"
    assert box.index(L["acc_approx_time"]) < box.index(L["acc_km"]), "the guessed time comes first"


# What the caveat CLAIMS, as a proportion, and the band each claim has to land in. The copy states these
# in words ("about one chart in seven"); this is the same statement as a number, so the two cannot drift.
# Bands are wide enough for sampling noise at BUCKET_SAMPLE and narrow enough to fail a wrong claim: "one
# in eight" and "one in five" do not both fit through any of them, which is the mistake this exists for.
BUCKET_SAMPLE = 1200
CLAIMED = {                    # key: (low %, high %, what the copy says)
    "lagna":  (68.0,  82.0, "about three charts in four"),
    "mangal": ( 6.0,  14.0, "about one chart in ten"),
    "lord":   ( 4.0,  10.0, "about one chart in fifteen"),
    "nak":    ( 4.0,  10.0, "about one chart in fifteen"),
    "moon":   ( 1.2,   5.0, "one in forty"),
    # An UPPER bound in the copy ("fewer than one in two hundred"), so zero satisfies it. At this sample
    # size the true rate of ~0.4% gives about five hits and a real chance of drawing none, so the band
    # cannot demand one. `test_the_caveat_never_claims_anything_is_immune_to_the_birth_time` is what
    # stops the wording sliding back to "does not depend on the birth time" while this band allows zero.
    "sade":   ( 0.0,   1.5, "fewer than one in two hundred"),
}
# The Moon covers at most ~0.95 deg of a 13.33 deg nakshatra in ninety minutes, and the longest mahadasha
# is Venus at 20 years, so a dasha boundary cannot move more than 1.44 years. A measurement past that is
# arithmetic, not astrology - which is how a 21-hour "three-hour" bucket was caught in this sweep. The
# observed maximum sits ON this bound (1.44 measured against 1.44 derived), not merely inside it.
PHYSICAL_MAX_SHIFT_YEARS = 1.5


def _bucket_sweep(n=BUCKET_SAMPLE, seed=20260923):
    """Random births, each compared against the same birth CAVEAT_WINDOW_HOURS later - the worst a reader
    can be out, given the form's presets. Seeded, so a failure is a real change rather than a bad draw.

    The later time is built with `timedelta`, NOT `time(hour % 24)`: the modulo version silently turns a
    bucket starting at 21:00 into a 21-hour comparison against 00:00 the same morning, which inflated
    every figure in this file by about half before it was caught."""
    import random

    from app import engine as engine_module

    random.seed(seed)
    cities = [engine_module.find_city(name) for name in
              ("Miraj", "Delhi", "Chennai", "Kolkata", "Prayagraj", "Pune", "Jaipur", "Kochi")]
    hits = dict.fromkeys(CLAIMED, 0)
    shifts = []
    for _ in range(n):
        city = random.choice(cities)
        day = dt.date(random.randint(1950, 2008), random.randint(1, 12), random.randint(1, 28))
        start = dt.datetime.combine(day, dt.time(random.randrange(24), random.randrange(60)))
        later = start + dt.timedelta(hours=CAVEAT_WINDOW_HOURS)
        early, late = [engine_module.compute_chart(when.date(), when.time(), city["lat"], city["lon"],
                                                   city["tz"], as_of=AS_OF_DT, detail="basic")
                       for when in (start, later)]
        hits["lagna"]  += early["lagna"]["sign"]["name"] != late["lagna"]["sign"]["name"]
        hits["moon"]   += early["moon_rashi"]["name"] != late["moon_rashi"]["name"]
        hits["nak"]    += early["janma_nakshatra"]["name"] != late["janma_nakshatra"]["name"]
        hits["mangal"] += early["mangal_dosha"]["present"] != late["mangal_dosha"]["present"]
        hits["sade"]   += early["sade_sati"]["active"] != late["sade_sati"]["active"]
        one, two = early["dasha"]["current"]["mahadasha"], late["dasha"]["current"]["mahadasha"]
        if one["lord"]["name"] != two["lord"]["name"]:
            hits["lord"] += 1
        else:
            shifts.append(abs((dt.date.fromisoformat(one["start"]) - dt.date.fromisoformat(two["start"])).days))
    return {key: 100 * value / n for key, value in hits.items()}, sorted(shifts)


def test_every_proportion_the_caveat_states_still_holds():
    """The caveat puts numbers in a printed document, so the numbers are measured rather than trusted.

    This exists because they were wrong twice over. Three separate 150-to-600-birth samples put the
    mahadasha lord at one in seven, one in nine and one in five; it is one in eight. Two of them put sade
    sati at exactly zero, and a draft of this caveat therefore told readers it "does not depend on the
    birth time at all" - it follows the Moon sign and flips for about one chart in a hundred.
    """
    measured, shifts = _bucket_sweep()
    wrong = [f"{key}: {measured[key]:.1f}% is outside {low}-{high}% (copy says {claim!r})"
             for key, (low, high, claim) in CLAIMED.items() if not low <= measured[key] <= high]
    assert wrong == [], "the caveat's wording no longer matches the engine:\n  " + "\n  ".join(wrong)


def test_the_dasha_shift_matches_the_spread_the_copy_quotes():
    """The copy gives a SPREAD rather than a single typical value, because two careful sweeps disagreed
    about the median while agreeing closely on the tails. A distributional claim needs a distributional
    check: a one-birth assertion that the dates "move" would pass with the wording saying five years.

    The upper end is not a measurement at all but a derivation, which is why the copy says the dates can
    NEVER move more than about a year and a half rather than that they rarely do."""
    measured, shifts = _bucket_sweep()
    years = [days / 365.25 for days in shifts]
    over_one = sum(value > 1 for value in years) / len(years)
    over_two = sum(value > 2 for value in years) / len(years)
    assert 0.30 <= over_one <= 0.58, f"copy says two charts in five exceed a year; measured {over_one:.0%}"
    assert over_two == 0, (
        f"{over_two:.1%} of charts moved more than two years, which the copy says CANNOT happen - and it "
        "cannot: ninety minutes of Moon travel over the 20-year Venus period is 1.44 years at most")

    # and the sanity bound that caught the bad sweep: nothing may exceed what the Moon can do in 3 hours
    assert max(years) <= PHYSICAL_MAX_SHIFT_YEARS, (
        f"a dasha boundary moved {max(years):.2f} years in three hours, which the Moon cannot do - "
        "the sweep is measuring something other than a three-hour bucket")

    # An internal coherence check, which catches a different class of error from the bound above. If the
    # whole dasha sequence slides by `mean` years, the chance that `as_of` crosses a period boundary is
    # about mean / (average mahadasha length), and 120 years of Vimshottari over nine lords is 13.33.
    # So the shift distribution and the lord-change rate are two views of one quantity: a sweep where
    # they disagree is measuring the two inconsistently, however tight either number looks on its own.
    mean_years = sum(years) / len(years)
    predicted = 100 * mean_years / (120 / 9)
    assert abs(predicted - measured["lord"]) < 4.0, (
        f"a mean shift of {mean_years:.2f} y predicts {predicted:.1f}% lord changes, but "
        f"{measured['lord']:.1f}% were measured - the sweep is not internally coherent")


def test_the_caveat_never_claims_anything_is_immune_to_the_birth_time():
    """The specific error the sweep above caught: an absolute claim about the safest-looking quantity.
    Nothing in this document is independent of the birth time, and the copy may not say otherwise."""
    for language in BASIC_LANGS:
        text = Labels(language)["acc_approx_time"]
        for absolute in ("does not depend on the birth time at all", "बिल्कुल निर्भर नहीं",
                         "मुळीच अवलंबून नाही", "एकमेव गोष्ट", "एकमात्र ऐसी बात"):
            assert absolute not in text, f"{language}: absolute claim {absolute!r} is not true of any of it"


def test_an_approximate_time_changes_nothing_about_the_calculation():
    """The flag is a caveat, not an input. The chart printed is the chart computed from the time given -
    the same graha table, the same charts, the same dates - so nobody can read the caveat as an
    adjustment we applied on their behalf."""
    chart = basic_chart()
    plain = render_basic_html(chart, language="en")
    flagged = render_basic_html(chart, language="en", approximate_time=True)
    L = Labels("en")
    strip = lambda doc: doc.replace(L["acc_approx_time"], "").replace(L["acc_approx_dasha"], "")  # noqa: E731
    for table in ("t-grahas", "kundali kundali--"):
        assert plain.count(table) == flagged.count(table)
    # every graha row is identical, character for character
    rows = lambda doc: re.findall(r'<tr class="[^"]*"><th scope="row">.*?</tr>', strip(doc), flags=re.S)  # noqa: E731
    assert rows(plain) == rows(flagged) and rows(plain)


def test_the_route_takes_the_flag_and_the_cache_separates_the_two(no_ai, fake_basic_chromium):
    client = TestClient(app)
    assert client.post("/api/chart/pdf", json=BASIC_BODY).status_code == 200
    assert client.post("/api/chart/pdf", json={**BASIC_BODY, "approximate_time": True}).status_code == 200
    assert len(fake_basic_chromium) == 2, "a caveated sheet is a different document, so a different file"
    assert Labels("en")["acc_approx_time"] not in fake_basic_chromium[0]
    assert Labels("en")["acc_approx_time"] in fake_basic_chromium[1]
    assert len(sorted(service.basic_dir().glob("*.pdf"))) == 2


# ---- the closing philosophy line -------------------------------------------------------------------


VERSE_FIELDS = ("verse", "verse_gloss", "verse_ours")


@pytest.mark.parametrize("language", BASIC_LANGS)
def test_the_verse_and_our_application_of_it_are_never_one_string(language):
    """Bhagavad Gita 2.47 is about action and its fruits. It says nothing about astrology.

    So our sentence may sit beside the verse but never inside it: run together they read as a
    translation, which is a false and checkable claim of scriptural sourcing - the same one
    app/web/policies.py already rules out for the Bhrigu Samhita. The guarantee is structural: three
    separate label fields rendered into three separate elements, so collapsing them takes a deliberate
    edit to both files rather than a careless one to either.
    """
    L = Labels(language)
    verse, gloss, ours = (L[key] for key in VERSE_FIELDS)
    assert verse and gloss and ours
    assert verse not in ours and ours not in gloss, "our application must not be inside the quotation"
    assert "2.47" in gloss, "the gloss cites the verse it is translating"
    # the gloss translates the VERSE, so it may not mention astrology; the application is where we do
    for word in ("astrology", "ज्योतिष"):
        assert word not in gloss, f"the gloss claims the verse says {word!r}; it does not"
    assert any(word in ours for word in ("astrology", "ज्योतिष")), "our line is the one about astrology"


@pytest.mark.parametrize("language", BASIC_LANGS)
def test_both_documents_print_the_verse_beside_the_disclaimer_not_instead_of_it(language):
    """The disclaimer is the compliance statement and the verse is brand voice. Two lines, and the
    compliance one survives intact - a test, because "we also added a nice line" is exactly the kind of
    edit that quietly replaces something load-bearing."""
    L = Labels(language)
    for document in (render_basic_html(basic_chart(), language=language),
                     render_report_html(make_report("sade-sati-guide", language))):
        text = visible_text(document)
        assert DISCLAIMERS[language] in text, "the disclaimer must survive"
        for key in VERSE_FIELDS:
            assert L[key] in text
        # three elements, not one: the structural half of the guarantee above
        for css_class in ("philosophy__verse", "philosophy__gloss", "philosophy__ours"):
            assert f'class="{css_class}"' in document
        assert document.index("philosophy__verse") < document.index("philosophy__ours")
        assert document.index('class="disclaimer"') < document.index('class="philosophy"')


def test_the_english_document_carries_the_devanagari_verse_and_can_render_it():
    """The verse is the first and only Devanagari in an otherwise Latin document, so the English book is
    where a missing font would show up. The glyph coverage is checked here; the embedded-font list of a
    real English PDF is checked in test_the_english_pdf_embeds_a_devanagari_face_for_the_verse."""
    ttlib = pytest.importorskip("fontTools.ttLib")
    covered = set()
    for name in ("NotoSans-Regular", "NotoSans-Bold", "NotoSansDevanagari-Regular", "NotoSansDevanagari-Bold"):
        covered |= set(ttlib.TTFont(FONTS_DIR / f"{name}.ttf").getBestCmap())
    document = render_basic_html(basic_chart(), language="en")
    assert Labels("en")["verse"] in visible_text(document)
    missing = {ch for ch in Labels("en")["verse"] if ord(ch) not in covered}
    assert missing == set(), f"the bundled fonts cannot draw the verse: {missing}"


def test_the_unused_footer_line_label_is_still_unused():
    """`footer_line` exists in labels.py for all three languages and is rendered by neither template.
    Flagged upstream rather than deleted, because it is a compliance-flavoured string and removing one
    of those quietly is worse than carrying it. This fails if it is ever wired up, so that whoever does
    it has to decide consciously whether it duplicates the disclaimer already printed."""
    for language in BASIC_LANGS:
        line = Labels(language)["footer_line"]
        assert line
        for document in (render_basic_html(basic_chart(), language=language),
                         render_report_html(make_report("sade-sati-guide", language))):
            assert line not in visible_text(document), "footer_line is now printed - is it a duplicate?"


@pytest.mark.browser
def test_the_english_pdf_embeds_a_devanagari_face_for_the_verse(chromium):
    """The check the verse most needs: an English document that now contains one Devanagari line. If the
    Devanagari face were not embedded, Chromium would reach for a system font (or print tofu on a bare
    server) for the one line nobody proofreads."""
    pdf = browser.html_to_pdf(render_basic_html(basic_chart(), language="en", name="Keshav"))
    fonts = browser.embedded_fonts(pdf)
    assert browser.fallback_fonts(pdf) == set(), f"the English sheet fell back to a system font: {fonts}"
    assert any("Devanagari" in name for name in fonts), (
        f"the English sheet prints the verse but embeds no Devanagari face: {sorted(fonts)}")


@pytest.mark.browser
@pytest.mark.parametrize("language", BASIC_LANGS)
def test_the_verse_lands_on_the_closing_page_not_a_page_of_its_own(chromium, language):
    """It closes the document, so it belongs under the disclaimer rather than alone on a trailing page.

    Getting there needed `break-inside: avoid` on the whole `.closing` section - it is 89-105mm in the
    three languages, so it always fits one page. `break-before: avoid` on the philosophy block does NOT
    work: Chromium largely ignores it, and the English sheet put the verse on a page by itself with it
    in place. That is why this test renders rather than reading the stylesheet.
    """
    pypdf = pytest.importorskip("pypdf")
    pdf = browser.html_to_pdf(render_basic_html(basic_chart(), language=language, name="Keshav"))
    pages = [page.extract_text() for page in pypdf.PdfReader(io.BytesIO(pdf)).pages]
    # Latin markers only: Devanagari conjuncts do not survive extraction reliably
    verse_page = next((n for n, text in enumerate(pages, 1) if "2.47" in text), None)
    calc_page = next((n for n, text in enumerate(pages, 1) if "22.90" in text), None)
    assert verse_page and calc_page, f"verse on {verse_page}, calculation note on {calc_page}"
    assert verse_page == calc_page, (
        f"the verse is alone on page {verse_page}; the closing it belongs to is on page {calc_page}")


# ---- the caveat's window is a fact about the FORM, not a constant we chose ---------------------------

# The worst a reader's birth time can be out, given the presets the form offers, in hours. The caveat is
# written against this number, so it is derived from the form rather than restated here: if the preset
# list changes, the copy's premise changes with it and this is what says so.
CAVEAT_WINDOW_HOURS = 1.5
PRESET_TEMPLATE = ROOT / "app/web/templates/_person_fields.html"


def _worst_preset_error_hours() -> float:
    """Read the form's time presets and return the largest error a nearest-preset choice can produce.

    A birth between two presets is at worst half the gap from the nearer one, so the answer is half the
    widest gap - including the gap that wraps around midnight."""
    source = PRESET_TEMPLATE.read_text(encoding="utf-8")
    block = source[source.index("TIME_PRESETS"):source.index("%}", source.index("TIME_PRESETS"))]
    times = sorted(int(h) * 60 + int(m) for h, m in re.findall(r'"(\d{2}):(\d{2})"', block))
    assert len(times) >= 2, f"could not read the presets out of {PRESET_TEMPLATE.name}: {times}"
    gaps = [later - earlier for earlier, later in zip(times, times[1:])]
    gaps.append(times[0] + 24 * 60 - times[-1])        # the wrap around midnight
    return max(gaps) / 2 / 60


def test_the_caveats_window_still_matches_the_form_the_reader_used():
    """The premise of the whole caveat - "across a three-hour range" and every proportion under it - is a
    fact about the preset list, not a number we picked. One entry added or removed changes it.

    This is the handoff, and it has already fired once. The presets used to run 00, 06, 09, 12, 15, 18,
    21 - a six-hour jump from midnight to six, so the worst nearest-preset error was three hours and the
    caveat was written for that. Adding 03:00 halved it to ninety minutes: the lagna went from changing
    in every chart to about three in four, every other rate roughly halved, and the "more than two years"
    clause became IMPOSSIBLE rather than rarer, because the Moon moves at most 0.95 degrees in ninety
    minutes - 0.071 of a nakshatra, which over the 20-year Venus period is 1.44 years. That is why the
    copy now says the dates can never move further, rather than that they seldom do.
    """
    worst = _worst_preset_error_hours()
    assert worst == CAVEAT_WINDOW_HOURS, (
        f"the form's presets now allow a worst error of {worst:g} h, but the PDF caveat is written for "
        f"{CAVEAT_WINDOW_HOURS:g} h. FOUR places state that premise and all of them move together:\n"
        f"  1. app/pdf/labels.py   acc_approx_time and acc_approx_dasha, all three languages\n"
        f"  2. this file           CAVEAT_WINDOW_HOURS, the CLAIMED bands, PHYSICAL_MAX_SHIFT_YEARS\n"
        f"  3. app/pdf/blocks.py   the measured table in accuracy_block's docstring\n"
        f"  4. docs/API.md         the proportions table under POST /api/chart/pdf\n"
        f"Only 1 and 2 are enforced by tests; 3 and 4 are prose and will drift silently if you skip them.")

    # and the window the copy actually states, in the language it states it in
    english = Labels("en")["acc_approx_time"]
    assert "ninety minutes" in english, f"the copy no longer says ninety minutes: {english[:90]}"
