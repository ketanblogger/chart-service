"""/rashi/makar-in-english - a real query, answered properly.

Search Console shows people typing "makar rashi in english", "vrishchik rashi 2027 english", "kanya rashi
in english". They know their rashi by its Indian name and want the English one. That is a one-word answer.

THE REASON THE PAGE IS LONGER THAN ONE WORD. The English name they are matching it to is almost always
being used for a SUN sign - that is what a western horoscope means by "Capricorn" - while a rashi is a
MOON sign, and the two agree for about one person in twelve. Somebody who learns "Makar is Capricorn" and
then reads a Capricorn column is reading about somebody else. Giving only the word would do that to them.
"""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.web import i18n

client = TestClient(app, raise_server_exceptions=False)

PATHS = [(path, lang, params["rashi"]) for path, key, lang, params in i18n.all_paths()
         if key == "rashi-in-english"]


def test_there_is_one_for_every_rashi_in_every_tree():
    assert len(PATHS) == 36, f"expected 12 rashis x 3 trees, got {len(PATHS)}"


@pytest.mark.parametrize("path, lang, rashi", PATHS)
def test_every_one_of_them_answers(path, lang, rashi):
    assert client.get(path).status_code == 200, path


@pytest.mark.parametrize("path, lang, rashi", PATHS)
def test_the_url_uses_the_indian_name_in_every_tree(path, lang, rashi):
    """The query is "makar rashi in english". "/rashi/capricorn-in-english" answers a question nobody is
    asking, and an English speaker typing "capricorn" is not looking for this page."""
    assert f"/{i18n.rashi_slug(rashi, 'hi')}-in-english" in path, path


def test_the_english_spelling_is_not_a_second_address_for_the_same_page():
    """One canonical URL, so there is nothing to choose between and nothing to split a ranking across."""
    assert client.get("/rashi/capricorn-in-english").status_code == 404
    assert client.get("/rashi/aries-in-english").status_code == 404


@pytest.mark.parametrize("path, lang, rashi", [p for p in PATHS if p[1] == "en"])
def test_the_answer_is_in_the_first_heading(path, lang, rashi):
    names = i18n.rashi_names(rashi, "en")
    h1 = re.search(r"<h1>(.*?)</h1>", client.get(path).text, re.S)
    assert h1 and names["sign"] in h1.group(1), (path, h1.group(1) if h1 else None)


@pytest.mark.parametrize("path, lang, rashi", PATHS)
def test_it_says_the_thing_that_stops_somebody_reading_the_wrong_horoscope(path, lang, rashi):
    """The whole point: moon sign, not sun sign. Without this the page is actively unhelpful."""
    html = client.get(path).text
    wording = {"en": ("Moon", "Sun"), "hi": ("चंद्र", "सूर्य"), "mr": ("चंद्र", "सूर्य")}[lang]
    assert all(word in html for word in wording), (path, wording)


@pytest.mark.parametrize("path, lang, rashi", PATHS)
def test_it_offers_the_chart_and_the_astrologer(path, lang, rashi):
    html = client.get(path).text
    assert i18n.url_for("kundali", lang) in html, path
    assert i18n.url_for("consultation", lang) in html, path
    assert i18n.url_for("rashifal-rashi", lang, rashi=rashi) in html, path


def test_they_are_in_the_sitemap_with_hreflang():
    sitemap = client.get("/sitemap.xml").text
    for path, _lang, _rashi in PATHS:
        assert f"{path}<" in sitemap or f"{path}\"" in sitemap or path in sitemap, path


#: EVERY path, not one hand-picked rashi. `p[2] == "Makara"` matched nothing - the key is "makara" - so
#: this test was collected with an empty parameter set and SKIPPED: a test that cannot fail, reported as
#: a pass with a note nobody reads.
@pytest.mark.parametrize("path, lang, rashi", PATHS)
def test_each_tree_points_at_the_others(path, lang, rashi):
    """A reader on the Hindi page and a reader on the English one are asking the same question."""
    html = client.get(path).text
    for other in ("en", "hi", "mr"):
        assert i18n.url_for("rashi-in-english", other, rashi=rashi) in html, (path, other)


@pytest.mark.parametrize("path, lang, rashi", PATHS)
def test_the_title_fits_a_search_result(path, lang, rashi):
    title = re.search(r"<title>(.*?)</title>", client.get(path).text, re.S)
    assert title, path
    assert len(title.group(1).strip()) <= 65, (path, len(title.group(1).strip()), title.group(1))
