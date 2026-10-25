"""A date the calendar does not have must say so, on every form that takes one.

31 February produced NOTHING on the live site: the page re-rendered with the fields still filled, no
result and no message, so the only thing a reader could conclude is that the button was broken. The
API has always answered 422 for it - this was a UI gap, not a validation one.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.numerology.copy import ERRORS

FORM = {"content-type": "application/x-www-form-urlencoded"}
PATHS = {
    "en": ("/numerology-calculator", "/lo-shu-grid-calculator", "/mobile-number-numerology",
           "/numerology-report"),
    "hi": ("/hi/ank-jyotish", "/hi/lo-shu-grid", "/hi/mobile-number-numerology",
           "/hi/numerology-report"),
    "mr": ("/mr/ank-jyotish", "/mr/lo-shu-grid", "/mr/mobile-number-numerology",
           "/mr/numerology-report"),
}


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def _error(response) -> str:
    import re

    found = re.search(r'class="num-error"[^>]*>(.*?)</p>', response.text, re.S)
    return " ".join(found.group(1).split()) if found else ""


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
@pytest.mark.parametrize("index", [0, 1, 3])      # calculator, lo shu, report - the date is required
def test_an_impossible_date_is_named_in_the_readers_language(client, lang, index):
    path = PATHS[lang][index]
    response = client.post(path, content="name=Asha&number=9876543210&day=31&month=2&year=1988",
                           headers=FORM)
    assert response.status_code == 200
    assert _error(response) == ERRORS[lang]["bad_date"], path


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_the_number_checker_keeps_its_own_words_for_an_unusable_number(client, lang):
    """IT ALREADY HAD A BETTER MESSAGE than anything added here - "there were no digits in that",
    in all three languages, with its own test. My first version of this work replaced it with a
    generic error and blanked the result, which took the better message away. `num-error` on this
    form is only ever about the date."""
    path = PATHS[lang][2]
    response = client.post(path, content="number=&day=&month=&year=", headers=FORM)
    assert response.status_code == 200
    assert _error(response) == "", "the generic error is back, hiding the page's own explanation"


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_the_number_checker_still_names_an_impossible_date(client, lang):
    """With a usable number and 31 February, the fit section would otherwise just vanish."""
    path = PATHS[lang][2]
    response = client.post(path, content="number=9876543210&day=31&month=2&year=1988", headers=FORM)
    assert _error(response) == ERRORS[lang]["bad_date"]


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
@pytest.mark.parametrize("index", [0, 1, 3])
def test_a_partly_typed_date_asks_for_the_rest(client, lang, index):
    response = client.post(PATHS[lang][index], content="name=Asha&day=11&month=&year=",
                           headers=FORM)
    assert _error(response) == ERRORS[lang]["no_date"]


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
@pytest.mark.parametrize("index", [0, 1, 3])
def test_an_untouched_form_says_nothing(client, lang, index):
    """A FRESH PAGE IS NOT AN ERROR. Showing "enter a day, a month and a year" to somebody who has
    just arrived tells them they have made a mistake they have not made."""
    response = client.post(PATHS[lang][index], content="name=&day=&month=&year=", headers=FORM)
    assert _error(response) == ""
    assert client.get(PATHS[lang][index]).status_code == 200
    assert _error(client.get(PATHS[lang][index])) == ""


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_a_real_date_still_produces_a_result_and_no_error(client, lang):
    response = client.post(PATHS[lang][0], content="name=Asha&day=11&month=3&year=1988",
                           headers=FORM)
    assert response.status_code == 200
    assert _error(response) == ""
    assert "2" in response.text          # the mulank for that date


def test_every_language_has_every_message():
    for lang in ("en", "hi", "mr"):
        assert set(ERRORS[lang]) == {"bad_date", "no_date", "bad_number"}
        for key, text in ERRORS[lang].items():
            assert text.strip() and len(text) > 15, (lang, key)
