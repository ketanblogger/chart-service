"""The mulank 1-9 pages: nine numbers, three trees, written once and committed.

"mulank 1" through "mulank 9" and "{n} number in numerology" are 50,000 searches a month each.

THE COPY IS COMMITTED, NOT GENERATED ON A SCHEDULE. scripts/generate_mulank.py wrote it once under
this site's own checker; a mulank's traits have not changed and these pages cost nothing per view.
What is tested here is the shape of that copy and the rules it had to pass, so a future regeneration
that drifts is caught.

Invented people only; `tests/` is published.
"""

import re

import pytest
from fastapi.testclient import TestClient

from app.blog import safety
from app.main import app
from app.numerology.core import RULERS, reduce_to_digit
from app.numerology.mulank_copy import MULANK
from app.web import i18n

client = TestClient(app)
LANGS = ("en", "hi", "mr")
FIELDS = ("intro", "traits", "strengths", "work", "compatible", "lucky", "bhagyank")


def test_all_nine_numbers_in_all_three_trees():
    assert sorted(MULANK, key=int) == [str(n) for n in range(1, 10)]
    for number in MULANK.values():
        assert sorted(number) == sorted(LANGS)


@pytest.mark.parametrize("number", range(1, 10))
@pytest.mark.parametrize("lang", LANGS)
def test_every_page_serves(number, lang):
    response = client.get(i18n.url_for("mulank", lang, number=number))
    assert response.status_code == 200
    assert MULANK[str(number)][lang]["h1"] in response.text


@pytest.mark.parametrize("number", range(1, 10))
@pytest.mark.parametrize("lang", LANGS)
def test_every_section_was_written(number, lang):
    page = MULANK[str(number)][lang]
    for field in FIELDS:
        assert page.get(field, "").strip(), (number, lang, field)


@pytest.mark.parametrize("number", range(1, 10))
@pytest.mark.parametrize("lang", LANGS)
def test_every_title_fits_a_search_result(number, lang):
    assert len(MULANK[str(number)][lang]["title"]) <= 60


@pytest.mark.parametrize("number", range(1, 10))
@pytest.mark.parametrize("lang", ["hi", "mr"])
def test_every_devanagari_title_carries_a_roman_phrase(lang, number):
    """Most Indian readers type these searches in Roman letters even when they read Devanagari, and
    tests/test_pages_i18n.py requires it of every Devanagari title on the site."""
    assert re.search(r"[A-Za-z]{4,}", MULANK[str(number)][lang]["title"])


@pytest.mark.parametrize("number", range(1, 10))
@pytest.mark.parametrize("lang", LANGS)
def test_no_page_would_fail_the_site_s_own_checker(number, lang):
    """THE RULE THE GENERATION RAN UNDER, asserted again here so a future regeneration that drifts
    is caught before it ships. Titles are exempt - a Devanagari title deliberately carries a Roman
    phrase, which is the site's pattern and not a defect."""
    page = MULANK[str(number)][lang]
    for field in FIELDS + ("meta",):
        problems = safety.blocking_terms(page[field], lang=lang)
        assert not problems, (number, lang, field, problems)


@pytest.mark.parametrize("number", range(1, 10))
@pytest.mark.parametrize("lang", LANGS)
def test_no_number_is_ever_called_unlucky(lang, number):
    """Somebody's mulank is the day they were born. Telling them it is unlucky is a charge they can
    do nothing about, which is why this site does not have the word."""
    page = MULANK[str(number)][lang]
    text = " ".join(page[f] for f in FIELDS).lower()
    for word in ("unlucky", "bad number", "weak number", "अशुभ", "दोष"):
        assert word not in text, (number, lang, word)


@pytest.mark.parametrize("number", range(1, 10))
def test_no_page_tells_anybody_to_change_their_name_or_a_number(number):
    text = " ".join(MULANK[str(number)]["en"][f] for f in FIELDS).lower()
    for phrase in ("change your name", "change the spelling", "you must change", "should change your"):
        assert phrase not in text, (number, phrase)


@pytest.mark.parametrize("number", range(1, 10))
def test_the_compatibility_section_uses_only_the_three_levels(number):
    """Strong, good, neutral. There is no fourth, and the generation brief said so."""
    text = MULANK[str(number)]["en"]["compatible"].lower()
    assert "match" in text or "neutral" in text
    for word in ("enemy", "incompatible", "avoid", "clash"):
        assert word not in text, (number, word)


@pytest.mark.parametrize("number", range(1, 10))
def test_the_page_names_the_days_that_give_that_mulank(number):
    """How a reader checks the number is theirs before reading a word about it."""
    html = client.get(i18n.url_for("mulank", "en", number=number)).text
    days = [d for d in range(1, 32) if reduce_to_digit(d) == number]
    for day in days:
        assert str(day) in html, (number, day)


@pytest.mark.parametrize("number", range(1, 10))
def test_the_page_names_the_ruling_planet(number):
    html = client.get(i18n.url_for("mulank", "en", number=number)).text
    assert RULERS[number] in html


def test_the_nine_pages_are_linked_from_the_calculator():
    """Without this they are orphans - the guard that caught three sets of pages this week."""
    html = client.get(i18n.url_for("numerology", "en")).text
    for number in range(1, 10):
        assert f'href="{i18n.url_for("mulank", "en", number=number)}"' in html, number


@pytest.mark.parametrize("number", range(1, 10))
def test_each_page_links_the_other_eight(number):
    html = client.get(i18n.url_for("mulank", "en", number=number)).text
    for other in range(1, 10):
        if other != number:
            assert i18n.url_for("mulank", "en", number=other) in html, (number, other)


@pytest.mark.parametrize("lang", LANGS)
def test_a_mulank_page_offers_the_consultation(lang):
    from app.numerology.copy import ASK

    html = client.get(i18n.url_for("mulank", lang, number=7)).text
    assert ASK[lang]["heading"] in html


def test_the_copy_module_says_it_was_generated_and_how():
    """Somebody opening it should know it came from a script, that it was checked, and that it is
    edited by hand from here on."""
    import app.numerology.mulank_copy as module

    assert "generate_mulank.py" in (module.__doc__ or "")
    assert "safety.py" in (module.__doc__ or "")
