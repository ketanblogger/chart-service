"""A mulank page has headings and an FAQ, and the FAQ cannot contradict the page it sits on.

Item 10 of the QA round. The page was six paragraphs in a row, so a reader looking for "what work
suits this number" had to read all of it to find out whether the answer was in there. The TEXT is
unchanged - this is about where the headings are.
"""
import json
import re

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.numerology import core
from app.numerology.copy import FAQ, PLANETS, SECTIONS
from app.web import i18n

LANGS = ("en", "hi", "mr")
DANDA = "।"


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _page(client, number, lang):
    return client.get(i18n.url_for("mulank", lang, number=number)).text


# ---- the copy is complete ------------------------------------------------------------------------

def test_every_language_has_every_section_and_question():
    """A missing key renders as an empty heading, which is worse than no heading."""
    for lang in LANGS:
        assert sorted(SECTIONS[lang]) == sorted(SECTIONS["en"]), lang
        assert sorted(FAQ[lang]) == sorted(FAQ["en"]), lang
        assert sorted(PLANETS[lang]) == list(range(1, 10)), lang
        assert all(str(v).strip() for v in SECTIONS[lang].values()), lang


def test_the_hindi_and_marathi_copy_is_not_the_english():
    for lang in ("hi", "mr"):
        assert SECTIONS[lang] != SECTIONS["en"]
        assert PLANETS[lang] != PLANETS["en"]
        for key in FAQ[lang]:
            assert FAQ[lang][key] != FAQ["en"][key], key


def test_the_marathi_copy_ends_sentences_the_way_the_rest_of_the_site_does():
    """The site's Hindi uses the danda and its Marathi uses a full stop - 10 to 0 either way in the
    existing copy. I wrote the Marathi FAQ with dandas, which a Marathi reader would notice."""
    hindi = " ".join(q + a for q, a in FAQ["hi"].values())
    marathi = " ".join(q + a for q, a in FAQ["mr"].values())
    # I wrote this assertion backwards the first time - "no full stop in the Marathi" - which is the
    # opposite of the convention it is meant to protect.
    assert DANDA in hindi, "the Hindi should end sentences with a danda"
    assert "." not in hindi, "the Hindi should not use a full stop"
    assert "." in marathi, "the Marathi should end sentences with a full stop"
    assert DANDA not in marathi, "the Marathi should not use a danda"


# ---- the page ------------------------------------------------------------------------------------

@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("number", range(1, 10))
def test_each_paragraph_sits_under_a_heading(client, number, lang):
    body = _page(client, number, lang)
    headings = [" ".join(h.split()) for h in re.findall(r"<h2[^>]*>(.*?)</h2>", body, re.S)]
    for key in ("personality", "work", "compatible", "lucky", "bhagyank", "faq"):
        assert SECTIONS[lang][key] in headings, (number, lang, key)


@pytest.mark.parametrize("lang", LANGS)
def test_the_planet_is_named_in_the_pages_own_language(client, lang):
    """It printed core.RULERS straight out, so a Hindi reader was told their number is ruled by
    "Moon"."""
    body = _page(client, 2, lang)
    assert PLANETS[lang][2] in body
    if lang != "en":
        assert not re.search(r">\s*Moon\s*<", body), "the English planet name is still on the page"


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("number", range(1, 10))
def test_the_faq_has_every_question_answered(client, number, lang):
    body = _page(client, number, lang)
    questions = [" ".join(q.split()) for q in re.findall(r"<summary>(.*?)</summary>", body, re.S)]
    assert len(questions) == len(FAQ[lang]), (number, lang, questions)
    assert all(q.strip() for q in questions)
    # SCOPED TO THE FAQ, and to the placeholder names. My first version looked for "{" anywhere
    # before </article>, which includes the head - where the JSON-LD is nothing but braces.
    faq_section = re.search(r'<section class="faq".*?</section>', body, re.S)
    assert faq_section, (number, lang)
    for placeholder in ("{number}", "{days}", "{planet}", "{strong}", "{good}", "{neutral}"):
        assert placeholder not in faq_section.group(0), (number, lang, placeholder)


@pytest.mark.parametrize("lang", LANGS)
def test_the_faq_is_in_the_page_schema(client, lang):
    body = _page(client, 5, lang)
    blobs = [json.loads(x) for x in
             re.findall(r'type="application/ld\+json">(.*?)</script>', body, re.S)]
    faq = [b for b in blobs if b.get("@type") == "FAQPage"]
    assert len(faq) == 1, [b.get("@type") for b in blobs]
    assert len(faq[0]["mainEntity"]) == len(FAQ[lang])
    for entry in faq[0]["mainEntity"]:
        assert entry["name"].strip() and entry["acceptedAnswer"]["text"].strip()


# ---- the FAQ cannot contradict the page --------------------------------------------------------

@pytest.mark.parametrize("number", range(1, 10))
def test_the_dates_answer_matches_the_dates_on_the_page(client, number):
    """Both come from the same list, and this is what keeps them from drifting."""
    from app.numerology.pages import _DAYS_FOR

    body = _page(client, number, "en")
    answer = [a for q, a in re.findall(r"<summary>(.*?)</summary>\s*<p>(.*?)</p>", body, re.S)
              if "birth dates" in q][0]
    for day in _DAYS_FOR[number]:
        assert str(day) in answer, (number, day)


@pytest.mark.parametrize("number", range(1, 10))
def test_the_suits_answer_comes_from_the_compatibility_table(client, number):
    """THE SINGLE SOURCE AGAIN. core.fit_groups decides every pairing on this site; an FAQ with its
    own opinion about which numbers suit which would be the same contradiction item 2 fixed, just
    moved further down the page."""
    groups = core.fit_groups(number)
    body = _page(client, number, "en")
    answer = [a for q, a in re.findall(r"<summary>(.*?)</summary>\s*<p>(.*?)</p>", body, re.S)
              if "Which numbers suit" in q][0]
    digits = {int(d) for d in re.findall(r"\b(\d)\b", answer)}
    assert digits == set(groups["strong"]) | set(groups["good"]) | set(groups["neutral"]), (
        number, answer)


def test_the_faq_is_not_generated_at_view_time():
    """No model on this path: the answers are assembled from data, and a page view costs nothing."""
    import inspect

    from app.numerology import pages

    source = inspect.getsource(pages._mulank_faqs)
    for forbidden in ("client", "anthropic", "complete(", "generate("):
        assert forbidden not in source.lower(), forbidden


# ---- item 8 applies to this page too -------------------------------------------------------------

@pytest.mark.parametrize("lang", LANGS)
def test_the_chip_strip_here_is_labelled_as_well(client, lang):
    """The calculator page and this one carry the same strip; fixing one and not the other would
    leave the bare aria-label="1-9" on nine pages in three languages."""
    body = _page(client, 3, lang)
    assert 'aria-labelledby="mulank-chips-label"' in body
    assert 'aria-label="1-9"' not in body
    labelled = re.findall(r'<a href="[^"]*mulank-(\d)"\s+aria-label="([^"]+)"', body)
    assert len(labelled) == 8, labelled  # the nine, less this page's own number
    for number, label in labelled:
        assert label.endswith(f" {number}") and ":" not in label, label
