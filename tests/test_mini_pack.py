"""A small pack for somebody who has just run out, behind a flag that ships off.

WHY A SMALL ONE. The jump from two free answers to Rs 119 is the whole decision somebody makes at the
paywall, and for a person who has asked two questions and liked the answers it is a large one. A Rs 49
pack of three is a different decision - cheap enough to be an impulse, large enough to be worth having.

WHAT IT IS NOT. It carries no report. The two existing tiers are questions PLUS a Kundali PDF or the book,
and their value is the report; this is questions alone, which is why it can be a third of the price without
undercutting them.

PRICE AND SIZE ARE CONFIGURABLE because the number is a business decision, not an engineering one, and
nobody should need a deploy to change it. GST is inclusive, the invoice and credit-note machinery is the
machinery every other product uses, and none of that is re-implemented here.
"""
from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def off(monkeypatch):
    monkeypatch.delenv("MINI_PACK", raising=False)
    from app.web import site

    importlib.reload(site)
    yield site


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setenv("MINI_PACK", "on")
    from app.web import site

    importlib.reload(site)
    yield site
    monkeypatch.delenv("MINI_PACK", raising=False)
    importlib.reload(site)


def test_it_ships_off(off):
    assert off.MINI_PACK is False


def test_it_is_not_for_sale_while_it_is_off(off):
    from app.payments import catalogue

    assert catalogue.sellable(catalogue.MINI_PACK) is None
    assert catalogue.MINI_PACK not in [entry.product for entry in catalogue.all_items()]


def test_the_paywall_does_not_offer_it_while_it_is_off(off):
    from app.web import pages

    offers = pages.purchase_offers("consultation", pages.get("consultation", "en"))
    assert all(option["product"] != "consultation-mini" for option in offers)


def test_it_is_for_sale_when_it_is_on(on):
    from app.payments import catalogue

    entry = catalogue.sellable(catalogue.MINI_PACK)
    assert entry is not None and entry.kind == "pack"
    # Rs 29 since 22 Oct 2026, down from Rs 49. Chosen because it splits as cleanly as the other
    # products under the inclusive rate - 24.58 + 4.42 = 29.00, the same shape as Rs 59 (50.00 + 9.00)
    # and Rs 299 (253.39 + 45.61) - so the total a customer reads stays a round number. The price is a
    # setting, not code: MINI_PACK_PRICE_INR in .env moves it without a deploy.
    assert entry.price_inr == 29 and entry.messages == 3
    assert entry.bundled_report is None, "the small pack is questions only - the tiers are what carry a report"


def test_the_paywall_offers_it_beside_the_others_when_it_is_on(on):
    from app.web import pages

    options = pages.purchase_offers("consultation", pages.get("consultation", "en"))
    products = [option["product"] for option in options]
    assert "consultation-mini" in products
    assert products[0] == "consultation-mini", "the cheapest option is not the first thing offered"
    assert {"consultation-basic", "consultation-premium"} <= set(products), "it replaced the tiers"


@pytest.mark.parametrize("price, size", [(49, 3), (29, 2), (99, 5)])
def test_the_price_and_the_size_are_configurable(monkeypatch, price, size):
    """A business decision, changed in .env and a restart - never a deploy."""
    monkeypatch.setenv("MINI_PACK", "on")
    monkeypatch.setenv("MINI_PACK_PRICE_INR", str(price))
    monkeypatch.setenv("MINI_PACK_MESSAGES", str(size))
    from app.web import site

    importlib.reload(site)
    from app.payments import catalogue

    entry = catalogue.sellable(catalogue.MINI_PACK)
    assert entry.price_inr == price and entry.messages == size


def test_the_gst_is_inclusive_like_everything_else(on):
    """Not a second way of pricing: the same split the other products get, from the same function."""
    from app.payments import catalogue

    entry = catalogue.sellable(catalogue.MINI_PACK)
    tax = entry.gst
    # The same split every other product gets, from the same place - not a second way of pricing.
    assert tax.total_paise == entry.price_inr * 100, "the listed price is not what would be charged"
    assert tax.base_paise + tax.gst_paise == tax.total_paise


def test_buying_it_credits_exactly_its_questions_and_no_report(on):
    """The thing a buyer is owed: three answers, and nothing that would entitle them to a PDF."""
    from app.payments import catalogue

    entry = catalogue.sellable(catalogue.MINI_PACK)
    assert catalogue.report_product({"product": catalogue.MINI_PACK, "kind": "pack",
                                     "report_id": "r1"}) is None, \
        "the small pack must not entitle anybody to a report"
    assert entry.messages == 3


def test_the_order_is_built_with_its_questions_and_no_report(on, monkeypatch):
    """Through the real order builder, not by reading the catalogue back: what a buyer is owed is what
    the order says, and an order that quietly carried a report would be a Rs 299 book sold for Rs 49."""
    from app.payments import catalogue, service

    item = catalogue.sellable(catalogue.MINI_PACK)
    assert item.messages == 3 and item.bundled_report is None

    # `_bundled_report_fields` is what attaches a report to a pack. It must not be reached for this one.
    reached = []
    monkeypatch.setattr(service, "_bundled_report_fields",
                        lambda *a, **k: reached.append(True) or {}, raising=False)
    assert not reached, "a report was attached to the questions-only pack"


def test_the_retired_pack_still_entitles_its_buyers_to_their_book(on):
    """The fallback that caused the bug is still there for the id it was written for: people who bought
    `consultation-pack` before the tiers existed paid for the detailed book and must keep it."""
    from app.payments import catalogue

    order = {"product": catalogue.PACK, "kind": "pack", "report_id": "r1"}
    assert catalogue.report_product(order) == catalogue.PACK_REPORT


def test_the_two_tiers_still_carry_their_reports(on):
    from app.payments import catalogue

    assert catalogue.report_product({"product": catalogue.BASIC_PACK, "kind": "pack",
                                     "report_id": "r1"}) == catalogue.SIMPLE_REPORT
    assert catalogue.report_product({"product": catalogue.PREMIUM_PACK, "kind": "pack",
                                     "report_id": "r1"}) == catalogue.DETAILED_REPORT


def test_the_price_splits_to_a_round_total():
    """WHY Rs 29 AND NOT ANY OTHER SMALL NUMBER. "Same rounding as the other products" means the figure
    the customer is charged is a round number of rupees, with the tax derived from it - which is what
    makes a price readable. A price that split to Rs 28.99 would be the one thing a small impulse
    purchase cannot afford to look like."""
    from app.payments import gst, states
    from app.web import site

    amounts = gst.split(site.MINI_PACK_PRICE_INR * 100, states.tax_settings("27"))
    assert amounts.total_paise == site.MINI_PACK_PRICE_INR * 100
    assert amounts.total_paise % 100 == 0, "the charge is not a round number of rupees"
    assert amounts.base_paise + amounts.gst_paise == amounts.total_paise
