"""The offer under the chart: it names the reader's own mahadasha, or it does not appear.

WHAT 3b ASKED FOR was real free facts instead of a teaser. There was no teaser: the free kundli result
already gives the whole chart, every graha's degree, nakshatra and pada, and the full Vimshottari
timeline. What it did NOT have was an offer anybody could connect to their own chart - a generic card at
the foot of a result nearly 8,000 pixels tall, reached by a reader who has already read everything.

So the offer moved up, under the chart, and now says one thing the engine computed for THIS person. It is
not a teaser either: the dates it names are printed in full a few hundred pixels below it. What it sells
is the READING of that period, which is the thing the free page genuinely does not do.

NO FACT, NO OFFER. A birth with no time has no dasha, and "you are in your undefined mahadasha" is worse
than silence. That is pinned below, because it is the case that would ship broken.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

RENDER = Path("app/static/js/render.js").read_text(encoding="utf-8")
RESULT_PARTIAL = Path("app/web/templates/_tool_result.html").read_text(encoding="utf-8")


def test_the_offer_is_built_from_the_chart_and_not_from_a_template():
    """It has to be client-side: the server renders the page before any birth has been entered, so a
    server-rendered offer cannot name anybody's mahadasha."""
    assert "function offerHtml(" in RENDER
    assert "dasha.current" in RENDER or "current.mahadasha" in RENDER


def test_no_mahadasha_means_no_offer():
    """THE CASE THAT WOULD SHIP BROKEN. A birth without a time has no dasha at all; the block must be
    absent rather than naming an empty lord or an undefined date."""
    body = RENDER[RENDER.index("function offerHtml("):]
    body = body[:body.index("\n  function ", 1)]
    guard = body[:body.index("return '<section")]
    assert 'return ""' in guard, "offerHtml does not bail out before rendering"
    for needed in ("current.mahadasha", ".lord", ".end"):
        assert needed in guard, f"the guard does not check {needed}"


def test_the_offer_names_a_graha_in_prose_not_a_table_cell():
    """grahaLabel() returns "Mangal (Mars) मंगल" in English - right for a table column, and three
    different grahas in a sentence."""
    body = RENDER[RENDER.index("function offerHtml("):]
    body = body[:body.index("\n  function ", 1)]
    assert "grahaName(" in body
    assert "grahaLabel(" not in body


def test_every_language_has_the_offer_copy():
    for key in ("offerHeading", "offerBody", "offerCta"):
        assert RENDER.count(key + ":") == 3, f"{key} is not in all three language tables"


def test_the_marathi_heading_does_not_leave_a_postposition_standing_alone():
    """Marathi joins the genitive to the oblique form - मंगळाच्या, not मंगळ च्या - and the oblique differs
    per graha. The sentence is built to need no genitive, which is the fix that works for every name."""
    heading = re.search(r'offerHeading: "(सध्या[^"]*)"', RENDER)
    assert heading, "the Marathi heading is not where this test expects it"
    assert " च्या" not in heading.group(1), "a free-standing च्या after an uninflected name"
    assert "{lord}" in heading.group(1)


def test_the_offer_prefers_the_purchase_block_on_this_page():
    """/birth-chart and /kundli are two different English pages that both carry the buy block, so a
    condition on the page key sent one to the other - a link to the page the reader was already on."""
    assert "function offerHref(" in RENDER
    body = RENDER[RENDER.index("function offerHref("):]
    body = body[:body.index("\n  function ", 1)]
    assert 'getElementById("cta")' in body and '"#cta"' in body
    assert "data-report-href" in body, "no fallback for a tool page with no purchase block"


def test_the_fallback_url_comes_from_the_registry():
    """A path spelled in JavaScript is the one that goes stale when a path moves."""
    assert "data-report-href=\"{{ href('kundali') }}\"" in RESULT_PARTIAL
    body = RENDER[RENDER.index("function offerHref("):]
    body = body[:body.index("\n  function ", 1)]
    assert "/birth-chart" not in body and "/kundli" not in body


@pytest.mark.parametrize("key", ["offerHeading", "offerBody"])
def test_the_offer_claims_nothing_the_page_does_not_show(key):
    """It may name the mahadasha lord and the date it ends - both printed in full further down the same
    page. A claim about what the period MEANS belongs to the paid reading, not to this block."""
    for match in re.finditer(key + r': "([^"]*)"', RENDER):
        text = match.group(1)
        placeholders = set(re.findall(r"\{(\w+)\}", text))
        assert placeholders <= {"lord", "date"}, f"{key} fills {placeholders - {'lord', 'date'}}"


def test_the_offer_survives_an_engine_with_no_dom():
    """THIS FILE RUNS IN TWO PLACES. A browser, and py_mini_racer - a bare JS VM the suite uses to render
    the result HTML and check its shape, where there is no `document` at all. An unguarded
    document.getElementById in the offer's link lookup took out 50 tests in one run, every one of them
    reporting a JSEvalException rather than anything about offers."""
    body = RENDER[RENDER.index("function offerHref("):]
    body = body[:body.index("\n  function ", 1)]
    assert 'typeof document === "undefined"' in body, "no guard for the DOM-less engine"
    guard_at = body.index('typeof document === "undefined"')
    assert guard_at < body.index("document.getElementById"), "the guard comes after the first DOM read"
