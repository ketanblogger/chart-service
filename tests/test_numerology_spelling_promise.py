"""What the site promises about name spellings: alternatives, never a number of them.

THE DECISION (6 Nov 2026): say "spelling alternatives for your name" everywhere, and promise no
count. The writer's brief in app/ai/products.py asks for alternatives without fixing how many, so a
page that said "3 spelling options" would be claiming something the report does not guarantee - a
lie on the one card that asks for money.

The phrase was also said four different ways in English alone ("alternative spellings of your own
name", "spelling alternatives for your own name", "Alternative spellings of your name"), which is
how a reader ends up unsure whether two pages are describing the same thing.
"""
import re

import pytest

from app.ai.products import PRODUCTS
from app.numerology.copy import CARD, REPORT

LANGS = ("en", "hi", "mr")

#: One phrase per language, used by every sentence that promises the thing.
STANDARD = {"en": "spelling alternatives for your name",
            "hi": "आपके नाम की वर्तनी के विकल्प",
            "mr": "तुमच्या नावाच्या स्पेलिंगचे पर्याय"}

#: Wordings this replaced. Any of them coming back means the copy has drifted apart again.
RETIRED = ("alternative spellings", "spelling alternatives for your own name",
           "वैकल्पिक वर्तनी", "पर्यायी स्पेलिंग", "नावाची पर्यायी")


def _copy(lang: str) -> str:
    return f"{REPORT[lang]}{CARD[lang]}"


@pytest.mark.parametrize("lang", LANGS)
def test_no_number_of_spellings_is_ever_promised(lang):
    """THE RULE. app/ai/products.py asks the writer for alternatives and does not fix how many, so
    nothing may claim a count - not "3 options", not "a few", not "several"."""
    blob = _copy(lang)
    # a number sitting next to the word for spelling, in any of the three languages
    near = re.findall(r"(?:\b(?:one|two|three|four|five|\d+)\b)[^.।]{0,20}"
                      r"(?:spellings?|वर्तनी|स्पेलिंग)", blob, re.IGNORECASE)
    # "one thing they do not do: spelling alternatives ..." counts nothing; it is not about how many
    near = [m for m in near if "thing" not in m.lower()]
    assert not near, f"{lang} promises a number of spellings: {near}"


@pytest.mark.parametrize("lang", LANGS)
def test_one_phrase_is_used_everywhere(lang):
    blob = _copy(lang)
    assert STANDARD[lang] in blob
    for retired in RETIRED:
        assert retired not in blob, f"{lang} still says {retired!r}"


@pytest.mark.parametrize("lang", LANGS)
def test_every_place_that_promises_it_uses_the_phrase(lang):
    """meta, lead, the report's own section description, the CTA body and the personalised teaser.
    The section HEADING stays a short heading ("Name spelling"), which is a label and not a promise."""
    promises = [REPORT[lang]["meta"], REPORT[lang]["lead"], REPORT[lang]["sections"][3][1],
                REPORT[lang]["cta_from_result_body"], CARD[lang]["tail"]]
    for text in promises:
        if any(w in text for w in ("spelling", "वर्तनी", "स्पेलिंग")):
            assert STANDARD[lang] in text, f"{lang}: {text[:90]!r}"


def test_the_writers_brief_still_does_not_fix_a_count():
    """If the brief ever DID promise three, the copy could too - this is the fact the rule rests on,
    so it is asserted rather than remembered."""
    section = dict(PRODUCTS["numerology-report"].sections)["name_spelling"]
    assert not re.search(r"\b(one|two|three|four|five|\d+)\b\s+\w*\s*spellings?", section, re.I), section
    assert "OFFERED, never prescribed" in section


def test_the_page_a_reader_sees_says_it_once_and_the_same_way(client=None):
    """End to end, because the copy is assembled at render time and this is what it looks like."""
    from fastapi.testclient import TestClient

    from app.main import app
    from app.web import i18n

    with TestClient(app) as c:
        for lang in LANGS:
            body = c.post(i18n.url_for("numerology", lang),
                          content="name=Asha&day=29&month=3&year=1988",
                          headers={"content-type": "application/x-www-form-urlencoded"}).text
            card = re.search(r'<section class="report-card".*?</section>', body, re.S).group(0)
            assert STANDARD[lang] in card, lang
            for retired in RETIRED:
                assert retired not in card, f"{lang} card still says {retired!r}"
