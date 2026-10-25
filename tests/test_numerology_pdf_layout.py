"""The numerology PDF's own shape: its grid, its one title, and no part machinery.

Four things the proprietor found in the first real one. The grid was described in words and never
drawn; the cover printed the product's name twice, in two different spellings of the same words
("अंक ज्योतिष अहवाल" over "अंकज्योतिष अहवाल"); and a six-page document carried "भाग A" and "भाग B"
title pages - the first of them headed "कुंडल्या आणि ग्रह", charts and grahas, on a report that
casts no chart.
"""
import datetime as dt

import pytest

from app.ai.prompts import NUMEROLOGY_DISCLAIMERS
from app.numerology import core
from app.pdf import blocks as B
from app.pdf.labels import Labels

LANGS = ("en", "hi", "mr")
BORN, NAME = dt.date(1988, 3, 29), "Asha Vernekar"


def _facts():
    return core.for_report(BORN, NAME)


def _report(lang="mr", title=None):
    return {
        "id": "c" * 32, "product": "numerology-report", "language": lang, "as_of": "2026-11-06",
        "title": title if title is not None else "अंकज्योतिष अहवाल",
        "product_name": "Numerology Report", "summary": "Mulank 2.",
        "data": {"numerology": _facts()},
        "sections": [{"id": "your_numbers", "heading": "Your numbers", "paragraphs": ["Mulank 2."]},
                     {"id": "name_spelling", "heading": "Name spelling", "paragraphs": ["Below."]}],
        "disclaimer": NUMEROLOGY_DISCLAIMERS[lang], "meta": {"model": "fixture"},
    }


# ---- 3. the grid is drawn ------------------------------------------------------------------------

def test_the_report_facts_carry_the_grid():
    rows = _facts()["lo_shu_grid"]
    assert len(rows) == 3 and all(len(row) == 3 for row in rows)
    assert {cell["number"] for row in rows for cell in row} == set(range(1, 10))


@pytest.mark.parametrize("lang", LANGS)
def test_the_grid_block_repeats_a_repeated_digit(lang):
    """A cell holding 9 twice prints "99" - which is how the grid is read, and the whole reason for
    looking at one."""
    block = B.lo_shu_block(Labels(lang), _facts())
    assert block and block["type"] == "lo_shu"
    cells = [cell for row in block["rows"] for cell in row]
    repeated = [c for c in cells if len(c["filled"]) > 1]
    assert repeated, "this fixture has repeated digits; none were doubled"
    for cell in repeated:
        assert cell["filled"] == str(cell["number"]) * len(cell["filled"])
    assert any(c["empty"] for c in cells), "an absent number must read as an empty cell"


def test_the_grid_matches_the_one_the_site_draws():
    """One implementation: the PDF and the page cannot disagree about somebody's grid."""
    site = core.lo_shu(BORN)["rows"]
    block = B.lo_shu_block(Labels("en"), _facts())
    for site_row, pdf_row in zip(site, block["rows"]):
        for site_cell, pdf_cell in zip(site_row, pdf_row):
            assert pdf_cell["number"] == site_cell["number"]
            assert pdf_cell["filled"] == str(site_cell["number"]) * site_cell["count"]


def test_the_grid_is_not_zebra_striped_like_a_data_table():
    """The generic tbody striping tinted the middle row, so a cell holding a 3 looked empty."""
    import pathlib

    css = (pathlib.Path(__file__).resolve().parents[1]
           / "app/pdf/templates/print.css").read_text(encoding="utf-8")
    assert ".lo-shu-grid tbody tr:nth-child(even) { background: transparent; }" in css


# ---- 4. one title, no part machinery -------------------------------------------------------------

def test_a_title_that_is_only_the_product_name_again_is_dropped():
    from app.pdf.render import _cover_title

    L = Labels("en")
    product = L.product("numerology-report", "Numerology Report")
    assert _cover_title(L, _report("en", title=product)) == ""
    assert _cover_title(L, _report("en", title=product.replace(" ", ""))) == "", "spacing only"
    assert _cover_title(L, _report("en", title=product.upper())) == "", "case only"
    assert _cover_title(L, _report("en", title="What your numbers say")) == "What your numbers say"


def test_the_numerology_report_is_one_untitled_part():
    """Six pages do not need "भाग A" and "भाग B" title pages, and the first of them was headed
    "charts and grahas" on a report that casts no chart."""
    from app.pdf.book import Anchors, build_parts

    parts = build_parts(_report(), Labels("mr"), "deva", {"self": NAME}, Anchors())
    assert len(parts) == 1
    assert parts[0]["untitled"] is True
    assert parts[0]["id"] == "numerology"
    assert "chart_basics" not in [p["id"] for p in parts]


def test_the_contents_does_not_list_an_untitled_part():
    """A contents line pointing at a page that does not announce itself is a line nobody can
    follow. Its chapters still appear."""
    from app.pdf.book import Anchors, build_parts, build_toc

    L = Labels("mr")
    parts = build_parts(_report(), L, "deva", {"self": NAME}, Anchors())
    toc = build_toc(L, parts, None)
    assert all(entry["level"] != 1 for entry in toc["entries"]), toc["entries"]
    assert toc["entries"], "the chapters must still be listed"


def test_the_part_title_page_is_skipped_in_the_template():
    import pathlib

    html = (pathlib.Path(__file__).resolve().parents[1]
            / "app/pdf/templates/report.html").read_text(encoding="utf-8")
    assert "{% if part.untitled %}" in html
    assert 'id="{{ part.anchor }}"' in html, "the anchor must survive; the contents links to it"
