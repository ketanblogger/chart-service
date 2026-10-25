"""A numerology consultation sells questions, and never a plan that bundles a Kundali report.

THE DECISION (2026-11-04): Rs 29 buys 3 questions, Rs 119 buys 10, no report is included, and the
Rs 199 numerology report stays a separate purchase that may be linked to but never bundled.

THE REASON IT MATTERS MORE THAN A PROMISE. A numerology consultation is started from a name and a
date of birth - no birth time, no place - so it cannot cast a chart. Every chart tier bundles a
Kundali report, which is a reading of one. Offering it was not only a thing we could not deliver:
`_birth_from_json` raised KeyError('time') building the birth details, so the purchase returned 500.
A reader who tried to pay got an error page.
"""
import datetime as dt
import os
import re
import tempfile

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.payments import catalogue
from app.web import i18n, pages

LANGS = ("en", "hi", "mr")


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


# ---- the tiers themselves ------------------------------------------------------------------------

def test_the_two_tiers_are_what_was_decided():
    mini = catalogue.sellable(catalogue.NUMEROLOGY_MINI)
    pack = catalogue.sellable(catalogue.NUMEROLOGY_PACK)
    assert (mini.price_inr, mini.messages) == (29, 3)
    assert (pack.price_inr, pack.messages) == (119, 10)


@pytest.mark.parametrize("product", catalogue.NUMEROLOGY_PACKS)
def test_no_numerology_tier_bundles_anything(product):
    """The rule, as a property of every tier rather than of the two that exist today."""
    entry = catalogue.item(product)
    assert entry.bundled_report is None, f"{product} bundles {entry.bundled_report}"
    assert entry.kind == "pack" and entry.sold


def test_a_numerology_tier_entitles_its_buyer_to_no_report():
    """report_product() decides what an order unlocks. A pack carrying no report must unlock none -
    the retired id's fallback once meant any questions-only pack bought the detailed book."""
    for product in catalogue.NUMEROLOGY_PACKS:
        order = {"product": product, "kind": "pack", "report_id": "x" * 32}
        assert catalogue.report_product(order) is None, product


def test_the_rs_199_report_is_still_a_separate_product():
    report = catalogue.sellable("numerology-report")
    assert report.price_inr == 199 and report.kind == "report"
    assert report.product not in catalogue.NUMEROLOGY_PACKS


def test_the_offer_list_and_the_catalogue_cannot_drift():
    """pages.py names the ids as literals, because app.payments is imported inside functions there."""
    assert pages.PURCHASE_OPTIONS["consultation-numerology"] == catalogue.NUMEROLOGY_PACKS


# ---- the till: the thing that must never happen ---------------------------------------------------

@pytest.fixture
def paid(monkeypatch):
    """Payments configured with TEST keys and Razorpay replaced by a transport that never leaves
    this process. No order here reaches anybody's API, which is the standing rule for payment
    checks on a laptop."""
    import httpx

    from app.payments import razorpay

    # THE PROJECT'S OWN FAKE, not a smaller one of my making. Mine returned a fixed amount and the
    # real client rightly refused it ("unexpected order entity ... amount=1") - that check exists
    # because an order entity that does not match what was asked for is a charge nobody authorised.
    from tests.test_payments import KEY_ID, KEY_SECRET, FakeRazorpay

    monkeypatch.setenv("RAZORPAY_KEY_ID", KEY_ID)
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", KEY_SECRET)
    monkeypatch.setattr(razorpay, "_transport", httpx.MockTransport(FakeRazorpay()))


@pytest.fixture
def sessions(tmp_path, monkeypatch, paid):
    """One numerology session and one chart session, in a database of their own."""
    monkeypatch.setenv("APP_DB", str(tmp_path / "t.db"))
    from app.ai import chat

    numerology = chat.start_session("u1", "b1", "ip1", {"date": "1988-03-29"}, "Asha", "en",
                                    numerology=True)
    chart = chat.start_session("u2", "b2", "ip2",
                               {"date": "1988-03-29", "time": "07:30", "lat": 16.8, "lon": 74.6,
                                "timezone": "Asia/Kolkata", "city": "Pune"}, "Devdatta", "en")
    return {"numerology": numerology["session_id"], "chart": chart["session_id"]}


BUNDLING = (catalogue.BASIC_PACK, catalogue.PREMIUM_PACK)


@pytest.mark.parametrize("product", BUNDLING)
def test_a_numerology_session_can_never_buy_a_bundling_plan(sessions, product):
    """THE TEST THE PROPRIETOR ASKED FOR. It is at the till and not only in the offer list, because
    the offer list is a view: a client posting the product id directly must get the same answer."""
    from app.payments import service

    with pytest.raises(service.OrderError) as caught:
        service.create_order(catalogue.sellable(product), "u1",
                             session_id=sessions["numerology"],
                             email="nobody@example.invalid", place_of_supply="27")
    assert caught.value.code == "not_for_this_consultation"
    assert caught.value.status == 422
    # the message must tell the reader what to do instead, not merely refuse
    assert "questions-only" in str(caught.value) or "questions only" in str(caught.value)


@pytest.mark.parametrize("product", catalogue.NUMEROLOGY_PACKS)
def test_a_numerology_session_can_buy_the_questions_only_tiers(sessions, product):
    from app.payments import service

    created = service.create_order(catalogue.sellable(product), "u1",
                                   session_id=sessions["numerology"],
                                   email="nobody@example.invalid", place_of_supply="27")
    assert created.get("order_id") or created.get("id") or created


@pytest.mark.parametrize("product", BUNDLING)
def test_a_chart_session_is_completely_unaffected(sessions, product):
    """The paid chart consultation is live. Its tiers must behave exactly as they did."""
    from app.payments import service

    created = service.create_order(catalogue.sellable(product), "u2", session_id=sessions["chart"],
                                   email="nobody@example.invalid", place_of_supply="27")
    assert created


def test_the_guard_reads_the_session_and_not_the_product_name(sessions):
    """A session with no birth time is numerology whatever its summary says - the structural signal
    is the one that matters, because it is exactly what the bundled report would need."""
    from app.ai.chat import _is_numerology_session
    from app.payments.service import _is_numerology

    for detector in (_is_numerology_session, _is_numerology):
        assert detector({"summary": {}, "birth": {"date": "1988-03-29"}}) is True
        assert detector({"summary": {"kind": "numerology"},
                         "birth": {"date": "x", "time": "07:30"}}) is True
        assert detector({"summary": {}, "birth": {"date": "x", "time": "07:30", "lat": 1}}) is False


# ---- the paywall a numerology chat is shown ------------------------------------------------------

def test_the_numerology_paywall_offers_only_the_two_tiers():
    from app.ai.chat import paywall

    offered = {o["product"] for o in paywall(numerology=True)["offers"]}
    assert offered == set(catalogue.NUMEROLOGY_PACKS)
    assert not offered & set(catalogue.PACKS), "a chart tier is on the numerology paywall"


def test_the_chart_paywall_is_unchanged():
    from app.ai.chat import paywall

    offered = {o["product"] for o in paywall()["offers"]}
    assert offered and not offered & set(catalogue.NUMEROLOGY_PACKS)


def test_the_numerology_paywall_leads_with_the_cheapest():
    from app.ai.chat import paywall

    wall = paywall(numerology=True)
    assert wall["product"] == catalogue.NUMEROLOGY_MINI and wall["price_inr"] == 29


# ---- what the pages say --------------------------------------------------------------------------

def _ask_lead(body):
    found = re.search(r'<section class="ask-box"[^>]*>.*?<p>(.*?)</p>', body, re.S)
    return " ".join(found.group(1).split()) if found else ""


@pytest.mark.parametrize("lang", LANGS)
def test_the_calculator_quotes_both_tiers_and_promises_no_report(client, lang):
    body = client.post(i18n.url_for("numerology", lang),
                       content="name=Asha&day=29&month=3&year=1988",
                       headers={"content-type": "application/x-www-form-urlencoded"}).text
    lead = _ask_lead(body)
    assert "29" in lead and "119" in lead and "199" in lead, lead
    assert "{" not in lead, f"an unfilled placeholder reached the page: {lead}"


@pytest.mark.parametrize("lang", LANGS)
def test_the_mulank_pages_say_the_same_thing(client, lang):
    lead = _ask_lead(client.get(i18n.url_for("mulank", lang, number=5)).text)
    assert "29" in lead and "119" in lead and "199" in lead, lead
    assert "{" not in lead


@pytest.mark.parametrize("lang", LANGS)
def test_no_numerology_page_still_promises_a_bundled_kundali_report(client, lang):
    """The copy used to say the pack "also includes a short kundali report, which needs your birth
    time and city" - on a page that never asks for either."""
    stale = ("short kundali report", "छोटी कुंडली रिपोर्ट", "छोटा कुंडली अहवाल")
    for path in (i18n.url_for("numerology", lang), i18n.url_for("mulank", lang, number=3)):
        body = client.get(path).text
        for phrase in stale:
            assert phrase not in body, f"{path} still promises a bundled report: {phrase}"


@pytest.mark.parametrize("lang", LANGS)
def test_the_chat_page_offers_numerology_tiers_only_in_numerology_mode(client, lang):
    base = i18n.url_for("consultation", lang)
    numerology = client.get(base + "?numerology=1&name=Asha&date=1988-03-29").text
    chart = client.get(base).text
    assert set(re.findall(r'data-product="(numerolog[^"]*|consultation[^"]*)"', numerology)) == \
        set(catalogue.NUMEROLOGY_PACKS)
    assert not set(re.findall(r'data-product="(numerology-[^"]*)"', chart)), \
        "a numerology tier is on the chart consultation page"


@pytest.mark.parametrize("lang", LANGS)
def test_every_tier_button_has_its_words_in_every_language(client, lang):
    """A missing buy_/gets_ key is a KeyError at render time, not a blank button."""
    offers = pages.purchase_offers("consultation-numerology", pages.get("consultation", lang))
    for offer in offers:
        assert offer["label"].strip() and "{" not in offer["label"], offer
        assert offer["blurb"].strip() and "{" not in offer["blurb"], offer


# ---- the route, not only the service --------------------------------------------------------------

def test_the_order_api_accepts_the_numerology_tiers(paid, tmp_path, monkeypatch):
    """THE SUITE CAUGHT THIS AND MY OWN TESTS DID NOT. OrderRequest.product is a Literal of every
    sellable id; the two new tiers were missing from it, so the paywall offered two products the
    API refused with 422 before any of the logic below ran. Testing the service directly walked
    straight past the validator."""
    monkeypatch.setenv("APP_DB", str(tmp_path / "api.db"))
    from app.ai import chat

    session = chat.start_session("u9", "b9", "ip9", {"date": "1988-03-29"}, "Asha", "en",
                                 numerology=True)
    with TestClient(app) as client:
        for product in catalogue.NUMEROLOGY_PACKS:
            reply = client.post("/api/payments/order",
                                json={"product": product, "session_id": session["session_id"],
                                      "email": "nobody@example.invalid",
                                      "place_of_supply": "27"})
            assert reply.status_code != 422, f"{product} is not in the API's product list: {reply.text[:160]}"
            assert reply.status_code == 200, reply.text[:200]


def test_the_order_api_refuses_a_bundling_plan_for_a_numerology_session(paid, tmp_path, monkeypatch):
    """The same refusal as the service test, through the door a browser actually uses."""
    monkeypatch.setenv("APP_DB", str(tmp_path / "api2.db"))
    from app.ai import chat

    session = chat.start_session("u8", "b8", "ip8", {"date": "1988-03-29"}, "Asha", "en",
                                 numerology=True)
    with TestClient(app) as client:
        reply = client.post("/api/payments/order",
                            json={"product": catalogue.BASIC_PACK,
                                  "session_id": session["session_id"],
                                  "email": "nobody@example.invalid", "place_of_supply": "27"})
    assert reply.status_code == 422
    # the envelope names the field "error", not "code" - checked against the real response rather
    # than assumed from the raise site
    assert reply.json()["detail"]["error"] == "not_for_this_consultation", reply.text[:200]
    assert "questions-only" in reply.json()["detail"]["message"]


def test_every_sellable_id_is_in_the_api_product_list():
    """The property, so the next product added cannot repeat this: anything the catalogue sells must
    be something the order endpoint will accept."""
    import typing

    from app.payments.routes import OrderRequest

    allowed = set(typing.get_args(OrderRequest.model_fields["product"].annotation))
    sellable = {entry.product for entry in catalogue.all_items()}
    assert sellable <= allowed, f"the catalogue sells ids the API refuses: {sorted(sellable - allowed)}"
