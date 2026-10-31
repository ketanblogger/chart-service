"""The PDF landing page and the competitor comparison.

THE COMPARISON PAGE NAMES REAL COMPANIES, which makes it the easiest page on this site to get wrong.
The tests below enforce the rules it was written under: it is dated, it concedes where competitors are
better, it makes no accuracy claim it has not measured, and it uses no logos or implied affiliation.
"""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.payments import catalogue
from app.web import i18n
from app.web.compare_page import CHECKED_ON, COPY as COMPARE, SOURCES
from app.web.kundli_pdf_page import COPY as PDF

client = TestClient(app)
LANGS = ("en", "hi", "mr")
COMPETITORS = ("AstroSage", "Drik Panchang", "Prokerala")


# ---- the comparison --------------------------------------------------------------------------------

@pytest.mark.parametrize("lang", LANGS)
def test_the_comparison_is_dated_on_the_page(lang):
    """These are live products. An undated comparison is a claim that silently becomes false."""
    html = client.get(i18n.url_for("compare", lang)).text
    assert str(CHECKED_ON.year) in html
    assert 'id="checked"' in html


@pytest.mark.parametrize("lang", LANGS)
def test_every_competitor_gets_a_row_saying_where_they_are_better(lang):
    """A comparison that finds the author best at everything is an advertisement, and readers can tell."""
    rows = dict(COMPARE[lang]["rows"])
    for name in COMPETITORS:
        assert name in rows, f"{lang}: {name} has no row"
        assert len(rows[name].split()) >= 25, f"{lang}: {name}'s row is a token mention"
    ours = rows["RashiKundli"]
    assert ours, "we need a row too"


@pytest.mark.parametrize("lang", LANGS)
def test_the_page_states_what_it_does_not_claim(lang):
    """We have not measured their accuracy, so the page says so rather than implying we have."""
    fair = " ".join(COMPARE[lang]["fair"])
    assert len(fair.split()) >= 40
    html = client.get(i18n.url_for("compare", lang)).text
    assert 'id="fair"' in html


@pytest.mark.parametrize("lang", LANGS)
def test_no_logos_and_no_implied_affiliation(lang):
    html = client.get(i18n.url_for("compare", lang)).text
    main = html.split("<main", 1)[1].split("</main>", 1)[0]
    assert "<img" not in main, f"{lang}: the comparison page carries an image"
    for word in ("partner", "official", "endorsed", "साझेदार", "अधिकृत", "भागीदार"):
        assert word.lower() not in main.lower(), f"{lang}: implies affiliation with {word!r}"


@pytest.mark.parametrize("lang", LANGS)
def test_outbound_links_are_nofollow_and_cite_their_own_pages(lang):
    html = client.get(i18n.url_for("compare", lang)).text
    for name, url in SOURCES:
        assert url in html, f"{lang}: {name} is not cited"
    for match in re.finditer(r'<a href="(https?://[^"]+)"([^>]*)>', html):
        if "rashikundli" in match.group(1):
            continue
        assert "nofollow" in match.group(2), match.group(1)


def test_the_sunrise_difference_is_described_as_a_convention_not_an_error():
    """We publish a four-minute difference with Drik. Saying "they are wrong" would be false - it is a
    convention difference, and this site uses the other one."""
    row = dict(COMPARE["en"]["rows"])["Drik Panchang"]
    assert "neither is wrong" in row.lower()
    assert "refraction" in row.lower()


# ---- the PDF landing page --------------------------------------------------------------------------

@pytest.mark.parametrize("lang", LANGS)
def test_the_pdf_page_shows_both_options_and_the_real_price(lang):
    html = client.get(i18n.url_for("kundli-pdf", lang)).text
    assert 'id="free"' in html and 'id="paid"' in html
    assert str(catalogue._REPORT_PRICES_INR["kundali-report"]) in html


@pytest.mark.parametrize("lang", LANGS)
def test_the_page_says_the_free_pdf_is_the_whole_calculation(lang):
    """A landing page that implies the free thing is crippled to sell the paid one is the pattern that
    makes people distrust every other claim on the site."""
    html = client.get(i18n.url_for("kundli-pdf", lang)).text
    assert 'id="honest"' in html
    assert PDF[lang]["honest"] in html


@pytest.mark.parametrize("lang", LANGS)
def test_both_lists_are_specific(lang):
    words = PDF[lang]
    assert len(words["free_points"]) >= 5 and len(words["paid_points"]) >= 5
    for point in words["free_points"] + words["paid_points"]:
        assert len(point.split()) >= 4, point


def test_the_copy_is_complete_in_every_language():
    for copy in (PDF, COMPARE):
        keys = {lang: set(words) for lang, words in copy.items()}
        assert keys["en"] == keys["hi"] == keys["mr"]
