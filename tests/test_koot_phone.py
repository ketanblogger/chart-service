"""The two 36-guna tables on a phone: koota and points on one line, the rest underneath.

THE ONE COLUMN THAT MATTERED WAS THE ONE OFF THE SCREEN. Both tables are read for their POINTS - the
static "36 gun milan" table that is its own search term, and the Ashtakoota breakdown in a result -
and at 390px the points column sat past the right edge inside a scrolling wrapper.

NOTHING WAS BROKEN, which is why no guard fired: the wrapper scrolls, the page never widened, and the
sideways-scroll check in scripts/design_shots.py was quiet and correct. It was a judgement about one
table rather than a defect, and the proprietor made it.

Invented people only; `tests/` is published.
"""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.web import STATIC_DIR, i18n

client = TestClient(app)
SITE_CSS = (Path("app/static/css/site.css")).read_text(encoding="utf-8")
RENDER_JS = (STATIC_DIR / "js" / "render.js").read_text(encoding="utf-8")
# THE BLOCK THIS FILE IS ABOUT, found by its own marker. There are three `max-width: 640px` blocks in
# site.css, and anchoring on the first one made these assertions read a stylesheet section that has
# nothing to do with tables - two of them failed against rules they were never written for.
_MARKER = "---------- the 36-guna tables on a phone"
PHONE_RULES = SITE_CSS[SITE_CSS.index(_MARKER):]


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_every_cell_of_the_static_table_carries_its_column_name(lang):
    """With the header row hidden, a value with no label is a number nobody can read."""
    html = client.get(i18n.url_for("matching", lang)).text
    table = html[html.index('<table class="koot-table"'):]
    table = table[:table.index("</table>")]
    rows = table[table.index("<tbody>"):]
    # An EMPTY cell needs no label - the total row has one, and the CSS hides it on a phone rather
    # than printing a column name in front of nothing.
    cells = re.findall(r"<(t[hd])([^>]*)>(.*?)</\1>", rows, re.S)
    unlabelled = [c for c in cells if c[2].strip() and "data-label=" not in c[1]]
    assert not unlabelled, f"{len(unlabelled)} unlabelled non-empty cell(s) in {lang}: {unlabelled[:2]}"


def test_the_result_table_labels_its_cells_too():
    """The result's table is built in render.js, so the label goes on in the builder."""
    builder = RENDER_JS[RENDER_JS.index("function table(headers, rows, className)"):]
    builder = builder[:builder.index("\n  }")]
    assert "data-label=" in builder
    assert "headers[i]" in builder, "the label must be the column's own header, not a guess"


def test_the_labels_are_escaped():
    """A header is copy, and copy goes into an attribute."""
    builder = RENDER_JS[RENDER_JS.index("function table(headers, rows, className)"):]
    builder = builder[:builder.index("\n  }")]
    assert "esc(String(headers[i]" in builder


def test_the_header_row_is_hidden_only_on_a_phone():
    """It is STYLED above the breakpoint and hidden below it - the cells carry their own labels there."""
    assert ".koot-table thead" in PHONE_RULES and "display: none" in PHONE_RULES
    above = SITE_CSS[:SITE_CSS.index(_MARKER)]
    header_rules = [line for line in above.splitlines() if ".koot-table thead" in line]
    assert header_rules, "the wide-screen header styling has gone"
    assert not any("display: none" in line for line in header_rules), header_rules


def test_the_points_sit_beside_the_koota_rather_than_below_it():
    """THE WHOLE FIX. Points on the first line, where the eye already is."""
    assert "grid-template-columns: 1fr auto" in PHONE_RULES
    assert "grid-column: 2; grid-row: 1" in PHONE_RULES


def test_nothing_is_hidden_or_truncated_only_stacked():
    """A phone layout that drops a column is a worse answer than a swipe."""
    assert "grid-column: 1 / -1" in PHONE_RULES, "the other cells must span the row, not vanish"
    for bad in ("text-overflow: ellipsis", "visibility: hidden"):
        assert bad not in PHONE_RULES, bad
    # Two, and only two: the header row (whose labels now live on the cells) and a cell that is
    # genuinely empty.
    assert PHONE_RULES.count("display: none") == 2, PHONE_RULES.count("display: none")


def test_above_the_breakpoint_both_tables_are_what_they_were():
    """The promise: one media query, and nothing outside it changed."""
    assert PHONE_RULES.strip().endswith("}")
    above = SITE_CSS[:SITE_CSS.index("@media (max-width: 640px)")]
    assert ".table--kootas tr" not in above


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_the_table_still_adds_to_36(lang):
    """Unchanged by the layout, and worth asserting beside it: a table of the 36 gunas that does not
    add to 36 is worse than no table."""
    from app.web import pages as web_pages

    rows = web_pages.content(lang).KOOT_TABLE
    assert sum(points for _, points, _ in rows) == 36
