"""What the chat offers when the free questions run out.

THE DECISION THIS EXISTS TO MAKE SMALLER: two free answers, then Rs 119. Somebody who has asked two
questions and liked the answers is being asked a large question, and the small pack - three more
questions, no report - is a different sort of decision. app/web/site.py has said so since it was
written; what had not happened is the 402 payload learning about it.

THE CARD WAS ALREADY RIGHT. It is server-rendered from pages.purchase_options("consultation"), which
lists every tier the catalogue will actually sell, mini first, with copy in all three languages. The
PAYLOAD named one product as a constant - so with the small pack live it advertised the tier nobody
would pick first, which is the same class of mistake as the retired product id its own docstring was
written about.
"""
from __future__ import annotations

import pytest

from app.ai import chat
from app.web import pages, site


@pytest.fixture()
def mini_on(monkeypatch):
    monkeypatch.setattr(site, "MINI_PACK", True)


@pytest.fixture()
def mini_off(monkeypatch):
    monkeypatch.setattr(site, "MINI_PACK", False)


def test_the_payload_leads_with_the_cheapest_tier_on_sale(mini_on):
    payload = chat.paywall()
    assert payload["product"] == "consultation-mini"
    assert payload["price_inr"] == 29 and payload["messages"] == 3


def test_it_leads_with_the_entry_tier_when_the_small_pack_is_off(mini_off):
    """The flag ships off, so this is what production answers today and it must not change."""
    payload = chat.paywall()
    assert payload["product"] == "consultation-basic"
    assert payload["price_inr"] == 119


def test_the_payload_and_the_card_never_describe_different_things(mini_on):
    """ONE SOURCE. The card is built from purchase_options; so is this. A second list would agree until
    the day somebody changed one of them - which is exactly how this payload came to quote a price
    nothing charged, and later a product nobody could buy."""
    payload = chat.paywall()
    card = [option["product"] for option in pages.purchase_options("consultation")]
    assert [offer["product"] for offer in payload["offers"]] == card


@pytest.mark.parametrize("flag", [True, False])
def test_every_offer_is_actually_sellable(monkeypatch, flag):
    from app.payments import catalogue

    monkeypatch.setattr(site, "MINI_PACK", flag)
    for offer in chat.paywall()["offers"]:
        assert catalogue.sellable(offer["product"]), f"{offer['product']} is offered and cannot be bought"


def test_the_old_keys_are_still_there(mini_off):
    """A 402 is an API answer. `offers` is an addition; removing `product`, `price_inr` or `messages`
    would break a client that reads them, including the browser's own older cached script."""
    payload = chat.paywall()
    for key in ("code", "product", "price_inr", "messages"):
        assert key in payload
    assert payload["code"] == "payment_required"


def test_prices_come_from_the_catalogue_and_not_from_the_chat_settings(mini_on):
    """The rule this module's docstring sets out: the catalogue is the only place an amount to charge
    comes from. A price read from CHAT_PACK_PRICE_INR agreed with it only by coincidence, until it did
    not."""
    from app.payments import catalogue

    for offer in chat.paywall()["offers"]:
        assert offer["price_inr"] == catalogue.item(offer["product"]).price_inr


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_the_small_pack_has_button_copy_in_every_language(lang):
    """A tier that renders with an empty button is a tier nobody buys. Read through the same accessor
    the page uses, rather than walking the content module - the first version of this test went looking
    through dictionaries and reported a gap that was not there."""
    original = site.MINI_PACK
    site.MINI_PACK = True
    try:
        copy = pages.get("consultation", lang)   # price-filled, as the route builds it
        offers = pages.purchase_offers("consultation", copy)
    finally:
        site.MINI_PACK = original

    mini = [offer for offer in offers if offer["product"] == "consultation-mini"]
    assert mini, f"{lang}: the small pack is not offered"
    assert mini[0]["label"].strip(), f"{lang}: the small pack button has no words"
    assert "{" not in mini[0]["label"], \
        f"{lang}: the button still has an unfilled placeholder: {mini[0]['label']!r}"
    assert str(site.MINI_PACK_PRICE_INR) in mini[0]["label"], \
        f"{lang}: the button does not name the price: {mini[0]['label']!r}"
