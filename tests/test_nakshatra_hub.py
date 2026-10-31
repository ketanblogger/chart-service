"""The front door for the 27 nakshatra pages.

"nakshatras" is 50,000 searches a month and there was nowhere to send them: twenty-seven pages and no
index. It is also why the blog's link map could not use the word - a term needs one page to point at,
and "nakshatra" had twenty-seven or none.

THE LINES ARE NOT NEW COPY. Each row carries the first sentence of the meaning already written and
reviewed for that nakshatra's own page, so the hub cannot drift from what the page it links to says.

Invented people only; `tests/` is published.
"""

import pytest
from fastapi.testclient import TestClient

from app.blog import links
from app.main import app
from app.web import i18n
from app.web.nakshatra_data import NAKSHATRAS
from app.web.nakshatra_pages import HUB, hub_rows

client = TestClient(app)


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_the_hub_exists_in_every_tree(lang):
    response = client.get(i18n.url_for("nakshatra-hub", lang))
    assert response.status_code == 200
    assert HUB[lang]["h1"] in response.text


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_it_lists_all_twenty_seven_and_links_each_one(lang):
    html = client.get(i18n.url_for("nakshatra-hub", lang)).text
    for nakshatra in NAKSHATRAS:
        href = i18n.url_for("nakshatra", lang, nakshatra=nakshatra.key)
        assert f'href="{href}"' in html, (lang, nakshatra.key)


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_every_row_carries_one_sentence_not_a_paragraph(lang):
    """THE DANDA COUNTS. । ends a sentence in Hindi and Marathi, and splitting on "." alone returned
    the whole paragraph for all 54 Devanagari entries - 27 rows of wall-to-wall text instead of an
    index."""
    for row in hub_rows(lang):
        assert row["line"], row["name"]
        assert len(row["line"]) <= 220, (lang, row["name"], len(row["line"]))
        assert row["line"].rstrip()[-1] in ".।॥", (lang, row["name"], row["line"][-30:])


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_the_line_is_the_page_s_own_first_sentence(lang):
    """One source, so the hub and the page cannot disagree about what a nakshatra is."""
    from app.web.nakshatra_pages import _meaning

    for row in hub_rows(lang)[:5]:
        assert _meaning(row["key"], lang).startswith(row["line"][:40])


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_it_points_at_the_free_chart_rather_than_asking_for_anything(lang):
    html = client.get(i18n.url_for("nakshatra-hub", lang)).text
    assert i18n.url_for("kundali", lang) in html
    assert "₹" not in html.split("<main", 1)[-1].split("</main>", 1)[0]


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_the_blog_can_now_link_the_word(lang):
    """The term that had nowhere to point is in the map, and it resolves."""
    terms = links.TERMS[lang]
    word = {"en": "nakshatra", "hi": "नक्षत्र", "mr": "नक्षत्र"}[lang]
    assert word in terms
    key, params = terms[word]
    assert i18n.url_for(key, lang, **params) == i18n.url_for("nakshatra-hub", lang)


def test_the_individual_pages_still_work():
    """The hub was added to the same module that builds them; a route clash would 404 all 27."""
    for nakshatra in NAKSHATRAS[:5]:
        path = i18n.url_for("nakshatra", "en", nakshatra=nakshatra.key)
        assert client.get(path).status_code == 200, path


def test_the_hub_and_a_nakshatra_page_are_different_urls():
    assert i18n.url_for("nakshatra-hub", "en") != i18n.url_for("nakshatra", "en",
                                                               nakshatra=NAKSHATRAS[0].key)
