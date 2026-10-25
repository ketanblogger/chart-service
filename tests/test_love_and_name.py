"""Love rashifal and rashi-from-a-name.

TWO THINGS THESE PAGES MUST NOT DO. The love pages must not trigger a second AI call - they show the
relationships section the reading already contains, which is why they cost nothing extra. And the name
page must not let anybody mistake the namakshar method for a birth chart: it answers what a NAME gives,
and most names were chosen for some other reason entirely.
"""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.web import i18n
from app.web.love_and_name import LOVE_COPY, NAME_COPY, name_view

client = TestClient(app)
LANGS = ("en", "hi", "mr")


@pytest.mark.parametrize("lang", LANGS)
def test_the_name_page_says_it_is_about_the_name_above_the_form(lang):
    """Somebody who types their name should read that this is not their chart BEFORE they type it."""
    path = i18n.url_for("rashi-by-name", lang)
    html = client.get(path).text
    main = html.split("<main", 1)[1]
    assert NAME_COPY[lang]["honest"] in main
    assert main.index(NAME_COPY[lang]["honest"]) < main.index("<form"), f"{lang}: caveat after the form"


@pytest.mark.parametrize("lang", LANGS)
def test_a_name_resolves_to_a_syllable_nakshatra_pada_and_rashi(lang):
    found = name_view("Rohan", lang)
    assert found and found["syllable"] and found["nakshatra"] and found["rashi"]
    assert 1 <= found["pada"] <= 4


@pytest.mark.parametrize("lang", LANGS)
def test_an_unreadable_name_is_an_answer_not_an_error(lang):
    path = i18n.url_for("rashi-by-name", lang)
    response = client.post(path, data={"name": "!!!"})
    assert response.status_code == 200
    assert 'id="result"' not in response.text


@pytest.mark.parametrize("lang", LANGS)
def test_the_name_result_is_in_the_pages_language(lang):
    found = name_view("मीरा", lang)
    assert found
    if lang in ("hi", "mr"):
        assert not re.search(r"[A-Za-z]{3,}", found["rashi"]), found["rashi"]
    else:
        assert re.search(r"[A-Za-z]", found["rashi"]), found["rashi"]


@pytest.mark.parametrize("lang", LANGS)
def test_every_love_page_serves_for_every_rashi(lang):
    for rashi in i18n.RASHI_KEYS:
        path = i18n.url_for("love-rashifal", lang, rashi=rashi)
        assert client.get(path).status_code == 200, path


@pytest.mark.parametrize("lang", LANGS)
def test_a_love_page_makes_no_ai_call(lang, monkeypatch):
    """THE COST GUARANTEE. These reuse the relationships section the reading already has; a second call
    here would be about Rs 79 a month for a daily refresh, spent by accident."""
    import app.ai.client as ai_client

    def explode(*args, **kwargs):
        raise AssertionError("a love rashifal page made an AI call")

    monkeypatch.setattr(ai_client, "complete_json", explode, raising=False)
    monkeypatch.setattr(ai_client, "complete", explode, raising=False)
    assert client.get(i18n.url_for("love-rashifal", lang, rashi="tula")).status_code == 200


@pytest.mark.parametrize("lang", LANGS)
def test_the_love_page_links_to_the_full_reading_and_the_astrologer(lang):
    html = client.get(i18n.url_for("love-rashifal", lang, rashi="tula")).text
    assert f'href="{i18n.url_for("rashifal-reading", lang, rashi="tula", period="today")}"' in html
    assert f'{i18n.url_for("consultation", lang)}?topic=relationships' in html


def test_the_copy_is_complete_in_every_language():
    for copy in (NAME_COPY, LOVE_COPY):
        keys = {lang: set(words) for lang, words in copy.items()}
        assert keys["en"] == keys["hi"] == keys["mr"]
        for lang, words in copy.items():
            assert all(str(v).strip() for v in words.values()), lang
