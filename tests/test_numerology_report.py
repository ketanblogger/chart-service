"""The paid numerology report, and the proof that no other report's order path moved.

A NUMEROLOGY REPORT DOES NOT CAST A CHART. Asking somebody for the hour and the city of their birth
to add up the digits of a date is asking for something we will not use - it costs the order and it
tells the reader we do not know what we are doing. So this product has its own request shape: a
name, a date, and optionally numbers they would like looked at.

EVERY OTHER PRODUCT IS UNTOUCHED. The validator gained a branch; it did not lose a rule. Half of
this file asserts that a chart report still refuses to be ordered without birth details.

Invented people only; `tests/` is published.
"""

import datetime as dt

import pytest
from pydantic import ValidationError

from app.ai.products import PRODUCTS
from app.ai.report import build_data
from app.ai.routes import ReportRequest
from app.payments.catalogue import prices_inr

BORN = dt.date(1991, 4, 3)
BIRTH = {"date": "1991-04-03", "time": "06:12", "city": "Nashik"}


def _numerology(**extra):
    return ReportRequest(product="numerology-report", name="Keshav", born=BORN, **extra)


# ---- the numerology path -------------------------------------------------------------------------------


def test_it_is_ordered_with_a_name_and_a_date_and_nothing_else():
    request = _numerology()
    assert request.born == BORN and request.name == "Keshav"
    assert request.birth is None


def test_it_casts_no_chart():
    assert _numerology().births() == []


def test_it_refuses_birth_details_rather_than_quietly_ignoring_them():
    """Accepting a birth time and throwing it away would let the order form keep asking for one."""
    with pytest.raises(ValidationError) as caught:
        ReportRequest(product="numerology-report", name="Keshav", born=BORN, birth=BIRTH)
    assert "does not cast a chart" in str(caught.value)


@pytest.mark.parametrize("missing", ["name", "born"])
def test_it_needs_both_a_name_and_a_date(missing):
    fields = {"product": "numerology-report", "name": "Keshav", "born": BORN}
    fields.pop(missing)
    with pytest.raises(ValidationError):
        ReportRequest(**fields)


def test_a_blank_name_is_not_a_name():
    with pytest.raises(ValidationError):
        ReportRequest(product="numerology-report", name="   ", born=BORN)


def test_the_numbers_are_computed_by_the_same_module_the_calculator_uses():
    """One implementation, so the report and the free page cannot disagree about somebody's mulank.
    Worked by hand in tests/test_numerology_core.py: 3 April 1991 is 3 and 9; KESHAV is 22 -> 4."""
    facts = _numerology().numerology_facts()
    assert facts["mulank"] == 3 and facts["bhagyank"] == 9
    assert facts["name_number"] == 4
    assert facts["system"] == "Chaldean"


def test_numbers_to_check_come_back_with_their_fit():
    facts = _numerology(numbers=["98765 43210"]).numerology_facts()
    checked = facts["numbers_checked"]
    assert len(checked) == 1
    assert checked[0]["number"] == 9                       # 45 -> 9
    assert checked[0]["fits"]["mulank"]["level"] in ("strong", "good", "neutral")


def test_an_unreadable_number_is_dropped_rather_than_scored_as_zero():
    facts = _numerology(numbers=["no digits", "98765 43210"]).numerology_facts()
    assert len(facts["numbers_checked"]) == 1


def test_at_most_four_numbers_are_accepted():
    with pytest.raises(ValidationError):
        _numerology(numbers=["1", "2", "3", "4", "5"])


def test_the_report_data_has_no_chart_in_it():
    import json

    full, prompt = build_data(PRODUCTS["numerology-report"], [], dt.date(2026, 10, 25), "en",
                              facts=_numerology().numerology_facts())
    assert list(full) == ["numerology"]
    assert "chart" not in json.dumps(full)
    assert full == prompt, "the model sees exactly the numbers we computed"


# ---- every other product is unchanged -------------------------------------------------------------------


@pytest.mark.parametrize("product", ["kundali-report", "kundali-report-simple",
                                     "mangal-dosha-remedy", "sade-sati-guide"])
def test_a_chart_report_still_requires_birth_details(product):
    """THE HALF OF THIS FILE THAT MATTERS MOST. The validator gained a branch; it did not lose a
    rule, and a chart report ordered without a birth time must still be refused."""
    with pytest.raises(ValidationError):
        ReportRequest(product=product)
    accepted = ReportRequest(product=product, birth=BIRTH)
    assert len(accepted.births()) == 1


def test_the_matching_report_still_requires_two_people():
    with pytest.raises(ValidationError):
        ReportRequest(product="matching-report", boy=BIRTH)
    accepted = ReportRequest(product="matching-report", boy=BIRTH, girl=BIRTH)
    assert len(accepted.births()) == 2


@pytest.mark.parametrize("product", ["kundali-report", "matching-report", "sade-sati-guide"])
def test_no_other_product_accepts_the_numerology_fields_as_a_substitute(product):
    """A name and a date must not become a way to order a chart report without a birth time."""
    with pytest.raises(ValidationError):
        ReportRequest(product=product, name="Keshav", born=BORN)


# ---- the product itself --------------------------------------------------------------------------------


def test_the_product_has_the_six_sections_and_no_remedies():
    """Numerology has no remedies to prescribe, and inventing some would be selling."""
    product = PRODUCTS["numerology-report"]
    assert len(product.sections) == 6
    assert product.min_remedies == 0
    assert product.kind == "numerology"


def test_the_spelling_section_offers_rather_than_prescribes():
    """The section people pay for is also the one that could most easily become "change your name
    or else". The brief is where that is settled."""
    brief = dict(PRODUCTS["numerology-report"].sections)["name_spelling"]
    assert "OFFERED, never prescribed" in brief
    assert "not a problem" in brief
    assert "never say a name is unlucky" in brief.lower()


def test_no_section_brief_would_fail_the_site_s_own_checker():
    from app.blog import safety

    for _id, brief in PRODUCTS["numerology-report"].sections:
        assert not safety.blocking_terms(brief), brief[:120]


def test_the_price_is_the_one_that_was_set():
    assert prices_inr()["numerology-report"] == 199


def test_the_report_is_listed_on_the_pricing_page_now_that_it_has_one():
    """THE PRICING PAGE IS BUILT FROM THE CATALOGUE so a new product appears the day it is priced -
    which is right, and which also meant this one was listed at Rs 199 with no way for a reader to
    buy it. A price with no button is a dead offer.

    It is NOT marked `sold=False`: that means "honoured for existing orders, not offered any more",
    which is a different thing and would stop the order API working at all. The product, the order
    path and the writer all work; what is missing is a landing page."""
    from fastapi.testclient import TestClient

    from app.main import app
    from app.web.routes import _NOT_YET_ON_SALE

    assert "numerology-report" not in _NOT_YET_ON_SALE, "it has a landing page now"
    page = TestClient(app).get("/pricing").text
    assert "Numerology Report" in page and "199" in page


def test_the_order_path_still_works_while_it_is_unlisted():
    """Unlisted is not unsellable. The flag is about what the pricing page advertises."""
    assert prices_inr()["numerology-report"] == 199
    assert _numerology().numerology_facts()["mulank"] == 3


# ---- the landing page ------------------------------------------------------------------------------


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_the_landing_page_shows_what_is_inside_before_asking_for_money(lang):
    """Nobody should buy a report without seeing what is in it. Every section is named, described,
    and shown with a sample."""
    from fastapi.testclient import TestClient

    from app.main import app
    from app.numerology.copy import REPORT
    from app.web import i18n

    html = TestClient(app).get(i18n.url_for("numerology-report", lang)).text
    for heading, what, sample in REPORT[lang]["sections"]:
        assert heading in html, (lang, heading)
        assert sample[:40] in html, (lang, heading)


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_the_price_is_on_the_page_before_the_button(lang):
    from fastapi.testclient import TestClient

    from app.main import app
    from app.web import i18n

    html = TestClient(app).get(i18n.url_for("numerology-report", lang)).text
    assert "199" in html


def test_there_is_no_buy_button_until_there_is_something_to_buy_with():
    """A buy button that cannot work is worse than one that is not there yet."""
    from fastapi.testclient import TestClient

    from app.main import app
    from app.web import i18n

    client = TestClient(app)
    empty = client.get(i18n.url_for("numerology-report", "en")).text
    assert "data-numerology" not in empty
    filled = client.post(i18n.url_for("numerology-report", "en"),
                         data={"name": "Keshav", "day": "3", "month": "4", "year": "1991"},
                         headers={"content-type": "application/x-www-form-urlencoded"}).text
    assert "data-numerology" in filled
    assert 'data-product="numerology-report"' in filled


def test_the_button_carries_the_name_and_date_and_no_birth_time():
    """It rides on the button the way the muhurta search does: this page makes no API call, so the
    payment panel has no request to inherit."""
    import html as html_mod
    import json

    from fastapi.testclient import TestClient

    from app.main import app
    from app.web import i18n

    page = TestClient(app).post(
        i18n.url_for("numerology-report", "en"),
        data={"name": "Keshav", "day": "3", "month": "4", "year": "1991"},
        headers={"content-type": "application/x-www-form-urlencoded"}).text
    raw = page.split("data-numerology='", 1)[1].split("'", 1)[0]
    payload = json.loads(html_mod.unescape(raw))
    assert payload == {"name": "Keshav", "born": "1991-04-03"}
    assert "time" not in payload and "lat" not in payload


def test_the_landing_page_asks_for_no_birth_time_or_city():
    from fastapi.testclient import TestClient

    from app.main import app
    from app.web import i18n

    html = TestClient(app).get(i18n.url_for("numerology-report", "en")).text
    form = html.split("<form", 1)[1].split("</form>", 1)[0]
    assert 'type="date"' not in form
    assert 'name="city"' not in form and 'name="time"' not in form
    assert 'name="day"' in form and 'name="name"' in form


@pytest.mark.parametrize("path_key,fields", [
    ("numerology", {"name": "Keshav", "day": "3", "month": "4", "year": "1991"}),
    ("lo-shu", {"day": "3", "month": "4", "year": "1991"}),
    ("number-check", {"number": "98765 43210"}),
])
def test_every_calculator_offers_the_report_under_its_result(path_key, fields):
    """UNDER A RESULT, not on an empty page. Offering to write up numbers nobody has worked out yet
    is an advertisement, which is the same rule the consultation box follows."""
    from fastapi.testclient import TestClient

    from app.main import app
    from app.web import i18n

    client = TestClient(app)
    blank = client.get(i18n.url_for(path_key, "en")).text
    assert "report-cta-heading" not in blank, "offered before there was anything to write up"
    html = client.post(i18n.url_for(path_key, "en"), data=fields,
                       headers={"content-type": "application/x-www-form-urlencoded"}).text
    assert "report-cta-heading" in html


@pytest.mark.parametrize("number", [1, 5, 9])
def test_every_mulank_page_offers_the_report(number):
    from fastapi.testclient import TestClient

    from app.main import app
    from app.web import i18n

    html = TestClient(app).get(i18n.url_for("mulank", "en", number=number)).text
    assert "report-cta-heading" in html


def test_the_cta_sends_people_to_the_page_rather_than_buying_in_place():
    """Somebody should see what is in a thing before they buy it, and the samples are what that
    page is for."""
    from fastapi.testclient import TestClient

    from app.main import app
    from app.web import i18n

    html = TestClient(app).post(
        i18n.url_for("numerology", "en"),
        data={"name": "Keshav", "day": "3", "month": "4", "year": "1991"},
        headers={"content-type": "application/x-www-form-urlencoded"}).text
    block = html.split("report-cta-heading", 1)[1][:600]
    assert i18n.url_for("numerology-report", "en") in block
    assert "data-product" not in block


def test_the_term_is_in_the_blog_link_map():
    from app.blog import links
    from app.web import i18n

    assert links.TERMS["en"]["numerology report"] == ("numerology-report", {})
    assert i18n.url_for("numerology-report", "en")


def test_the_payment_script_knows_the_numerology_shape():
    """`body.birth = request` is what every other single-person product does, and it is wrong here:
    this report is bought with a name and a date."""
    from pathlib import Path

    pay = Path("app/static/js/pay.js").read_text(encoding="utf-8")
    assert "detail.numerology" in pay
    assert "body.born" in pay and "body.name" in pay
    app_js = Path("app/static/js/app.js").read_text(encoding="utf-8")
    assert "data-numerology" in app_js
