"""The numerology calculator page: a form, the numbers, and the method shown beside them.

"numerology calculator" and "name numerology calculator" are 500,000 searches a month each - the
largest single term this site has gone after.

THE RESULT IS A POST, NOT A GET. A GET would make the result linkable and would also put somebody's
name and date of birth in our access log, in their browser history, and in the Referer header of
every link they clicked afterwards. The rest of this site keeps birth details out of URLs and this
page does the same.

Invented people only; `tests/` is published.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.numerology.copy import PAGE
from app.web import i18n

client = TestClient(app)
FORM = {"content-type": "application/x-www-form-urlencoded"}


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_the_page_serves_in_every_tree(lang):
    response = client.get(i18n.url_for("numerology", lang))
    assert response.status_code == 200
    assert PAGE[lang]["h1"] in response.text


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_a_submitted_name_and_date_come_back_as_numbers(lang):
    response = client.post(i18n.url_for("numerology", lang),
                           data={"name": "Keshav", "day": "3", "month": "4", "year": "1991"}, headers=FORM)
    assert response.status_code == 200
    body = response.text
    # mulank 3, bhagyank 9, name number 4 - worked by hand in tests/test_numerology_core.py
    assert ">3<" in body and ">9<" in body and ">4<" in body


def test_the_working_is_shown_not_just_the_answer():
    """A reader can check the arithmetic rather than trust it, which is the only honest way to
    publish a calculation whose school other sites disagree with."""
    body = client.post(i18n.url_for("numerology", "en"),
                       data={"name": "Keshav", "day": "3", "month": "4", "year": "1991"}, headers=FORM).text
    for pair in ("K=2", "E=5", "S=3", "H=5", "A=1", "V=6"):
        assert pair in body, pair
    assert "22" in body


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_the_method_and_the_chaldean_table_are_on_the_page(lang):
    html = client.get(i18n.url_for("numerology", lang)).text
    assert PAGE[lang]["method_heading"] in html
    assert "AIJQY" in html.replace(" ", ""), "the Chaldean table itself"


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_the_page_says_which_lo_shu_convention_it_uses(lang):
    """Schools differ on whether the mulank and bhagyank go into the grid. A page that does not say
    which it uses is one a reader cannot check against any other."""
    html = client.get(i18n.url_for("numerology", lang)).text
    method = " ".join(PAGE[lang]["method"])
    assert method.split(". ")[-1][:30] in html or PAGE[lang]["method"][-1][:30] in html


def test_a_name_in_devanagari_is_explained_rather_than_scored():
    """The Chaldean table is for the Latin alphabet. Printing a 0 would be a wrong answer."""
    body = client.post(i18n.url_for("numerology", "hi"),
                       data={"name": "केशव", "day": "3", "month": "4", "year": "1991"}, headers=FORM).text
    assert PAGE["hi"]["unusable_name"][:30] in body


def test_a_missing_or_impossible_date_re_renders_the_form_rather_than_erroring():
    for parts in ({}, {"day": "31", "month": "2", "year": "1991"}, {"day": "x"},
                  {"day": "3", "month": "13", "year": "1991"}):
        response = client.post(i18n.url_for("numerology", "en"),
                               data={"name": "Keshav", **parts}, headers=FORM)
        assert response.status_code == 200, parts
        assert PAGE["en"]["submit"] in response.text


def test_the_name_is_kept_in_the_form_after_a_submission():
    """Re-typing a name because the date was wrong is the kind of small rudeness that loses people."""
    body = client.post(i18n.url_for("numerology", "en"),
                       data={"name": "Keshav"}, headers=FORM).text
    assert 'value="Keshav"' in body


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_every_result_carries_the_disclaimer(lang):
    body = client.post(i18n.url_for("numerology", lang),
                       data={"name": "Keshav", "day": "3", "month": "4", "year": "1991"}, headers=FORM).text
    assert PAGE[lang]["disclaimer"][:40] in body


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_no_number_is_called_lucky_or_unlucky_anywhere_on_the_page(lang):
    """A person cannot change their date of birth. The disclaimer says so in as many words."""
    html = client.post(i18n.url_for("numerology", lang),
                       data={"name": "Keshav", "day": "3", "month": "4", "year": "1991"}, headers=FORM).text
    body = html.split("<main", 1)[-1].split("</main>", 1)[0].lower()
    for word in ("unlucky", "अशुभ"):
        # the disclaimer is allowed to say no number IS lucky or unlucky; nothing else may.
        if word in body:
            assert PAGE[lang]["disclaimer"].lower()[:30] in body, word


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_the_page_prose_would_pass_the_site_s_own_checker(lang):
    from app.blog import safety

    prose = [PAGE[lang]["lead"], PAGE[lang]["disclaimer"], *PAGE[lang]["method"]]
    for text in prose:
        assert not safety.blocking_terms(text, lang=lang), text[:120]


def test_the_date_of_birth_never_reaches_a_url():
    """THE REASON THIS IS A POST. A GET would put it in the access log, the browser history and the
    Referer of every link clicked afterwards."""
    import inspect

    from app.numerology import pages as numerology_pages

    source = inspect.getsource(numerology_pages)
    assert 'methods=["POST"]' in source
    assert "RedirectResponse" not in source, "a redirect would put the fields in a query string"


def test_the_page_needs_no_javascript():
    """The arithmetic is addition. A script would mean the page stopped working where script is
    blocked, for no gain a reader could name."""
    html = client.get(i18n.url_for("numerology", "en")).text
    body = html.split("<main", 1)[-1].split("</main>", 1)[0]
    assert "<script" not in body.lower()


def test_the_date_is_three_fields_not_a_native_date_input():
    """A BROWSER RENDERS A NATIVE DATE INPUT IN ITS OWN LOCALE, so 1991-04-03 shows as "04/03/1991"
    and reads as 4 March to somebody in India. Every other form on this site was changed away from
    native date inputs for exactly that reason, with a test that those two dates cannot be confused.
    Putting one back on a new page would undo that fix one page at a time."""
    html = client.get(i18n.url_for("numerology", "en")).text
    assert 'type="date"' not in html
    for field in ('name="day"', 'name="month"', 'name="year"'):
        assert field in html, field


def test_three_april_and_four_march_cannot_be_confused():
    """The same assertion the form batch added site-wide, on this page."""
    third_april = client.post(i18n.url_for("numerology", "en"),
                              data={"name": "Keshav", "day": "3", "month": "4", "year": "1991"},
                              headers=FORM).text
    fourth_march = client.post(i18n.url_for("numerology", "en"),
                               data={"name": "Keshav", "day": "4", "month": "3", "year": "1991"},
                               headers=FORM).text
    # 3 April 1991 gives mulank 3; 4 March 1991 gives mulank 4. Different pages, not the same one.
    assert third_april != fourth_march


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_the_months_are_named_in_the_page_s_own_language(lang):
    """A month NUMBER in a dropdown is the same ambiguity in a different hat."""
    from app.web import pages as web_pages

    html = client.get(i18n.url_for("numerology", lang)).text
    names = web_pages.content(lang).UI["month_names"]
    for name in names:
        assert f">{name}</option>" in html, (lang, name)


# ---- the consultation box ------------------------------------------------------------------------------


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_a_result_offers_the_paid_consultation_with_the_price_on_it(lang):
    """THE CALCULATORS STAY FREE. This is the one paid thing on the page, and a reader should know
    what it costs while deciding whether to want it - not after."""
    from app.numerology.copy import ASK
    from app.web.pages import chat_offer

    html = client.post(i18n.url_for("numerology", lang),
                       data={"name": "Keshav", "day": "3", "month": "4", "year": "1991"},
                       headers=FORM).text
    assert ASK[lang]["heading"] in html
    assert str(chat_offer()["price_inr"]) in html
    assert str(chat_offer()["free_messages"]) in html


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_the_box_offers_four_ready_questions(lang):
    from app.numerology.copy import ASK

    html = client.post(i18n.url_for("numerology", lang),
                       data={"name": "Keshav", "day": "3", "month": "4", "year": "1991"},
                       headers=FORM).text
    # UNESCAPED: Jinja escapes the apostrophe in "partner's" to &#39;, which is correct of it and
    # which a raw substring comparison does not see.
    import html as html_mod

    text = html_mod.unescape(html)
    assert len(ASK[lang]["chips"]) == 4
    for chip in ASK[lang]["chips"]:
        assert chip in text, (lang, chip)


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_the_box_says_the_numbers_come_from_the_calculator_not_the_model(lang):
    """The numbers are ours. The AI explains them and does not change them, and the page says so
    where a reader can see it rather than only in a prompt they cannot."""
    from app.numerology.copy import ASK

    html = client.post(i18n.url_for("numerology", lang),
                       data={"name": "Keshav", "day": "3", "month": "4", "year": "1991"},
                       headers=FORM).text
    assert ASK[lang]["note"][:40] in html


def test_the_box_uses_the_existing_chat_and_adds_no_new_payment_flow():
    from app.numerology import pages as numerology_pages
    import inspect

    source = inspect.getsource(numerology_pages._ask_box)
    assert "chat_offer" in source
    assert "razorpay" not in source.lower() and "order" not in source.lower()


def test_the_box_is_not_shown_before_there_is_a_result():
    """Offering to explain numbers nobody has worked out yet is an advertisement, not an offer."""
    from app.numerology.copy import ASK

    html = client.get(i18n.url_for("numerology", "en")).text
    assert ASK["en"]["heading"] not in html


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_the_box_prose_would_pass_the_site_s_own_checker(lang):
    from app.blog import safety
    from app.numerology.copy import ASK

    for key in ("heading", "cta", "note"):
        assert not safety.blocking_terms(ASK[lang][key], lang=lang), ASK[lang][key]
    for chip in ASK[lang]["chips"]:
        assert not safety.blocking_terms(chip, lang=lang), chip


def test_the_daily_summary_counts_numerology_separately():
    """A number mixed in with every other consultation source cannot answer whether THESE pages
    sell, which is the question that decides whether this batch was worth building."""
    import inspect

    from app.admin import daily

    source = inspect.getsource(daily)
    assert "_numerology_line" in source
    assert '"numerology", "lo-shu", "number-check"' in source
