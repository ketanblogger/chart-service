"""The dosha guides, and the thing they refuse to do.

The oldest commercial pattern in this field is: find a configuration, call it dangerous, sell the
remedy. Pitra dosha and kaal sarp support an entire industry of paid pujas, and the people most likely
to pay are the ones least able to afford it. These pages exist to answer the question without joining
that trade, so the tests below are mostly about what must NOT appear.
"""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.web import i18n
from app.web.dosha_guides import COPY, DOSHAS

client = TestClient(app)
LANG = "hi"


@pytest.mark.parametrize("slug", DOSHAS)
def test_the_page_serves_and_is_not_a_stub(slug):
    response = client.get(i18n.url_for("dosha-guide", LANG, dosha=slug))
    assert response.status_code == 200
    body = re.sub(r"<[^>]+>", " ", response.text.split("<main", 1)[1].split("</main>", 1)[0])
    assert len(body.split()) > 200, f"{slug}: {len(body.split())} words"


@pytest.mark.parametrize("slug", DOSHAS)
def test_nothing_is_for_sale_on_a_dosha_page(slug):
    """THE WHOLE POINT. No product, no price, no checkout - on the three pages where selling a remedy
    would be easiest and worst."""
    html = client.get(i18n.url_for("dosha-guide", LANG, dosha=slug)).text
    main = html.split("<main", 1)[1].split("</main>", 1)[0]
    for forbidden in ("₹", "checkout", "buy", "खरीद", "कीमत", "मूल्य"):
        assert forbidden not in main, f"{slug}: the page offers {forbidden!r}"
    assert "data-product" not in main


@pytest.mark.parametrize("slug", DOSHAS)
def test_the_page_says_where_astrologers_disagree(slug):
    """A guide that states one definition as settled fact is the thing that lets two astrologers give
    opposite answers and both sound certain."""
    words = COPY[LANG][slug]
    how = " ".join(words["how_body"])
    assert "मतभेद" in words["how"] or "मतभेद" in how, f"{slug}: no disagreement is acknowledged"
    assert len(how.split()) > 60


@pytest.mark.parametrize("slug", DOSHAS)
def test_the_remedies_are_the_cheap_traditional_ones_and_the_page_says_so(slug):
    words = COPY[LANG][slug]
    remedies = " ".join(words["remedies_body"])
    assert any(w in remedies for w in ("नि:शुल्क", "महँगा", "महँगी", "डर बेच", "धंधा", "बिचौलिए")), (
        f"{slug}: the remedies section does not warn about what is sold against this dosha")


def test_kaal_sarp_says_it_is_absent_from_the_classical_texts():
    """The single most useful fact about kaal sarp, and the one never mentioned by anyone selling a
    puja against it."""
    body = " ".join(COPY[LANG]["kaal-sarp"]["what_body"])
    assert "शास्त्रीय ग्रंथों में नहीं" in body or "ग्रंथों में नहीं है" in body


def test_mangal_dosha_gives_the_frequency_rather_than_only_the_warning():
    """About one chart in three. Saying so is the difference between information and a scare."""
    body = " ".join(COPY[LANG]["mangal"]["what_body"])
    assert "तीन में से एक" in body or "एक-तिहाई" in body


def test_pitra_dosha_admits_the_definition_is_open():
    body = " ".join(COPY[LANG]["pitra"]["what_body"] + COPY[LANG]["pitra"]["how_body"])
    assert "परिभाषा" in body or "खुली" in body


@pytest.mark.parametrize("slug", DOSHAS)
def test_each_page_links_to_a_free_check_and_to_the_other_guides(slug):
    html = client.get(i18n.url_for("dosha-guide", LANG, dosha=slug)).text
    for other in DOSHAS:
        if other == slug:
            continue
        assert f'href="{i18n.url_for("dosha-guide", LANG, dosha=other)}"' in html
    assert 'class="reading__ask"' in html, f"{slug}: no link to a free check"


def test_the_guides_are_hindi_only_on_purpose():
    """All three target queries are Hindi, and the English tree already answers mangal dosha with a
    calculator. Thin English and Marathi versions to fill a registry would be three more pages with
    nothing to say."""
    assert set(i18n.page_langs("dosha-guide")) == {"hi"}
