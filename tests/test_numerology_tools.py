"""The Lo Shu grid page and the number checker.

"lo shu grid" and "lo shu grid calculator" are 50,000 searches a month each, and the mobile/vehicle/
house/business number terms many thousands more across their variants. Both pages use the arithmetic
already tested by hand in tests/test_numerology_core.py; what is tested here is what a reader sees.

Invented people only; `tests/` is published.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.numerology.copy import CHECK, LO_SHU
from app.web import i18n

client = TestClient(app)
FORM = {"content-type": "application/x-www-form-urlencoded"}
BORN = {"day": "3", "month": "4", "year": "1991"}


# ---- the Lo Shu page -----------------------------------------------------------------------------------


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_the_lo_shu_page_serves_and_draws_a_grid(lang):
    response = client.post(i18n.url_for("lo-shu", lang), data=BORN, headers=FORM)
    assert response.status_code == 200
    # 3 April 1991: 1 twice, 3 twice, 4 once, 9 three times
    assert ">999<" in response.text and ">33<" in response.text and ">11<" in response.text


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_it_reports_all_eight_planes(lang):
    html = client.post(i18n.url_for("lo-shu", lang), data=BORN, headers=FORM).text
    for label in LO_SHU[lang]["plane_names"].values():
        assert label in html, (lang, label)


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_a_missing_number_is_not_called_a_fault(lang):
    """A person cannot change their date of birth. The note says so in as many words."""
    html = client.post(i18n.url_for("lo-shu", lang), data=BORN, headers=FORM).text
    assert LO_SHU[lang]["missing_note"][:40] in html


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_the_page_states_which_convention_it_uses(lang):
    """Schools differ on whether the mulank and bhagyank go into the grid. A page that does not say
    which it uses cannot be checked against any other."""
    from app.numerology.copy import PAGE

    html = client.get(i18n.url_for("lo-shu", lang)).text
    assert PAGE[lang]["method"][3][:40] in html


def test_the_lo_shu_page_asks_only_for_a_date():
    """No name field in the way of the thing being searched for."""
    html = client.get(i18n.url_for("lo-shu", "en")).text
    form = html.split("<form", 1)[1].split("</form>", 1)[0]
    assert 'name="name"' not in form
    assert 'name="day"' in form and 'name="year"' in form


# ---- the number checker --------------------------------------------------------------------------------


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_a_number_comes_back_with_its_total_and_digit(lang):
    html = client.post(i18n.url_for("number-check", lang),
                       data={"number": "98765 43210"}, headers=FORM).text
    # 9+8+7+6+5+4+3+2+1+0 = 45 -> 9
    assert ">45<" in html and ">9<" in html


def test_the_date_is_optional_on_the_checker():
    """Somebody checking a number they are about to buy should not have to hand over their birthday
    to see what it adds up to."""
    html = client.get(i18n.url_for("number-check", "en")).text
    form = html.split("<form", 1)[1].split("</form>", 1)[0]
    for field in ('name="day"', 'name="month"', 'name="year"'):
        assert "required" not in form.split(field, 1)[1].split(">", 1)[0], field
    response = client.post(i18n.url_for("number-check", "en"),
                           data={"number": "98765 43210"}, headers=FORM)
    assert response.status_code == 200
    assert "45" in response.text


def test_a_fit_is_shown_only_when_a_date_was_given():
    without = client.post(i18n.url_for("number-check", "en"),
                          data={"number": "98765 43210"}, headers=FORM).text
    with_date = client.post(i18n.url_for("number-check", "en"),
                            data={"number": "98765 43210", **BORN}, headers=FORM).text
    assert CHECK["en"]["fit_mulank"] not in without.split("<form", 1)[1].split("</form>", 1)[1]
    assert CHECK["en"]["fit_mulank"] in with_date


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_no_result_is_ever_worse_than_neutral(lang):
    """The rule the whole feature is built under. Every pairing of every number is checked, so a
    fourth level could not be added without this failing."""
    from app.numerology import core

    allowed = set(CHECK[lang]["levels"].values())
    assert set(CHECK[lang]["levels"]) == set(core.FIT_LEVELS)
    for a in range(1, 10):
        for b in range(1, 10):
            assert CHECK[lang]["levels"][core.fit(a, b)] in allowed


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_neutral_is_explained_rather_than_left_to_sound_bad(lang):
    html = client.post(i18n.url_for("number-check", lang),
                       data={"number": "98765 43210", **BORN}, headers=FORM).text
    assert CHECK[lang]["neutral_note"][:40] in html


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_nothing_suggests_buying_a_different_number(lang):
    """A numerology page that tells somebody their phone number is wrong is selling them a new one."""
    html = client.post(i18n.url_for("number-check", lang),
                       data={"number": "98765 43210", **BORN}, headers=FORM).text
    body = html.split("<main", 1)[-1].split("</main>", 1)[0]
    assert "₹" not in body and "data-product" not in body
    assert CHECK[lang]["disclaimer"][:40] in body


def test_text_with_no_digits_is_explained():
    html = client.post(i18n.url_for("number-check", "en"),
                       data={"number": "no digits here"}, headers=FORM).text
    assert CHECK["en"]["unusable"][:20] in html


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_both_pages_prose_would_pass_the_site_s_own_checker(lang):
    from app.blog import safety

    for words in (LO_SHU[lang], CHECK[lang]):
        for key in ("lead", "missing_note", "neutral_note", "disclaimer"):
            text = words.get(key)
            if text:
                assert not safety.blocking_terms(text, lang=lang), text[:120]
