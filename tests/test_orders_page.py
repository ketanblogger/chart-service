""""My orders" with orders actually in it.

IT WAS A 500 FOR EVERY REAL CUSTOMER. The orders table's primary key is `id`; the page asked for
`order["order_id"]`, which does not exist, so the first paid order on an account raised KeyError and the
visitor got "Something went wrong. An unexpected error happened on our side." The template then reached for
`product_label`, `created_label` and `amount_inr`, none of which exist on an order row either.

Every test of this page had an EMPTY database, so the loop never ran and the page always rendered. That is
the whole lesson: a list page tested only with an empty list is a page tested only where it cannot fail.
"""

import re
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from app import db
from app.main import app
from app.payments import store
from app.web import accounts

# gmail.com, because that is a provider whose +tags and dots ARE one inbox. At example.com they
# are not, and must not be: folding everywhere would merge two different people.
EMAIL = "listedcustomer@gmail.com"


@pytest.fixture
def paid_order():
    """One paid order, under an ALIAS of the account's address, so the matching is exercised too."""
    order_id = store.new_order_id()
    store.insert_order(order_id=order_id, product="kundali-report", kind="report", amount_paise=29900,
                       currency="INR", razorpay_order_id="order_" + uuid.uuid4().hex[:14],
                       user_id="u" * 32, email="Listed.Customer+shop@gmail.com")
    with db.transaction() as conn:
        conn.execute("UPDATE orders SET status='paid' WHERE id=?", (order_id,))
    yield store.get_order(order_id)
    with db.transaction() as conn:
        conn.execute("DELETE FROM orders WHERE id=?", (order_id,))


def signed_in() -> TestClient:
    client = TestClient(app, raise_server_exceptions=False)
    client.cookies.set(accounts.COOKIE_NAME, accounts.sign(EMAIL))
    return client


@pytest.mark.parametrize("path", ["/orders", "/hi/orders", "/mr/orders"])
def test_the_page_renders_for_a_customer_who_actually_has_an_order(path, paid_order):
    response = signed_in().get(path)
    assert response.status_code == 200, f"{path} is {response.status_code} for a customer with an order"
    assert "went wrong" not in response.text.lower()


def test_the_order_is_shown_with_its_name_date_amount_and_links(paid_order):
    html = signed_in().get("/orders").text
    assert "Detailed Janam Kundali Report" in html or paid_order["product"] in html
    assert "₹299" in html
    assert f'/order/{paid_order["token"]}' in html
    assert f'/invoice/{paid_order["token"]}' in html


def test_an_order_bought_under_an_alias_of_the_address_is_still_the_customers(paid_order):
    """The order was placed as `Listed.Customer+shop@gmail.com`; the account is `listedcustomer@`. One
    inbox, one account - and a list that hid it would be telling a customer their purchase does not exist."""
    assert paid_order["email"] != EMAIL
    assert f'/order/{paid_order["token"]}' in signed_in().get("/orders").text


def test_an_account_with_no_orders_gets_the_empty_state_and_not_an_error():
    client = TestClient(app, raise_server_exceptions=False)
    client.cookies.set(accounts.COOKIE_NAME, accounts.sign("nothing.bought@example.com"))
    response = client.get("/orders")
    assert response.status_code == 200
    assert "v2-orders__empty" in response.text


def test_the_list_shows_no_birth_details(paid_order):
    """A list of purchases, not of charts. A page that prints a date of birth leaks one the first time a
    session is wrong."""
    import re

    # THE LIST ITSELF, not the whole page: the site nav carries a "Birth Chart" link on every English page,
    # and a check over the whole document flags that - a word in the navigation is not a birth detail.
    html = signed_in().get("/orders").text
    listing = re.search(r'<ul class="v2-orderlist">.*?</ul>', html, re.S)
    assert listing, "no order list to check"
    body = listing.group(0).lower()
    for field in ("birth", "1988-", "janma", "lagna", "nakshatra", "rashi"):
        assert field not in body.replace("janam kundali", ""), field


# ---- the links on the page must actually resolve ----------------------------------------------------
#
# The orders page was shipped with BOTH document links broken: the payments router is mounted at
# `/api/payments`, and `public_paths()` spelled the paths out without that prefix, so the invoice and the
# credit note both answered the site's 404 page. Nothing had ever matched them.
#
# The tests above did not catch it because they assert the page RENDERS and that the links are PRESENT.
# A link that is present is not a link that works. So this follows every href the page offers and expects
# an answer - the same lesson as the empty-list bug one file up: assert over the real population.


@pytest.fixture
def order_with_both_documents():
    """A paid order carrying an invoice AND a credit note, which is the state that has every link on it."""
    from app.payments import credit_note

    order_id = store.new_order_id()
    store.insert_order(order_id=order_id, product="kundali-report", kind="report", amount_paise=29900,
                       currency="INR", razorpay_order_id="order_" + uuid.uuid4().hex[:14],
                       user_id="u" * 32, email="Listed.Customer+shop@gmail.com",
                       base_paise=25339, gst_paise=4561, gst_rate_bp=1800, place_of_supply="MH")
    with db.transaction() as conn:
        conn.execute("UPDATE orders SET status='paid', paid_at=? WHERE id=?", (time.time(), order_id))
    store.assign_invoice_number(order_id, series="2627", prefix="RK",
                                template="{prefix}/{series}/{n:05d}", max_length=16)
    refund_id = "rfnd_" + uuid.uuid4().hex[:12]
    store.record_refund(order_id, refund_id=refund_id, amount_paise=5760, at=time.time())
    number = credit_note.issue(store.get_order(order_id), refund_id)
    assert number and "/" in number, number  # RK-CN/2627/00001 - the slashes live in the NUMBER, not the URL
    yield store.get_order(order_id), store.get_refund(refund_id)
    with db.transaction() as conn:
        conn.execute("DELETE FROM webhook_refunds WHERE refund_id=?", (refund_id,))
        conn.execute("DELETE FROM orders WHERE id=?", (order_id,))


def _links_on_the_page(html: str) -> list[str]:
    block = re.search(r'<div class="v2-order__links">(.*?)</div>', html, re.S)
    assert block, "the order has no links block at all"
    return re.findall(r'href="([^"]+)"', block.group(1))


@pytest.mark.parametrize("prefix", ["", "/hi", "/mr"])
def test_every_link_the_page_offers_actually_resolves(prefix, order_with_both_documents):
    """EN/HI/MR, for an order with an invoice and a credit note, bought under a +tag alias."""
    client = signed_in()
    html = client.get(f"{prefix}/orders").text
    links = _links_on_the_page(html)
    # Three: the order page, the invoice, the credit note. The PDF of each is offered BY those documents
    # rather than here, and is checked below - reading comes first, filing second.
    assert len(links) == 3, f"expected order, invoice and credit note, got {links}"
    assert sum("credit-note" in href for href in links) == 1
    assert sum(href.startswith("/order/") for href in links) == 1

    for href in links:
        response = client.get(href)
        assert response.status_code == 200, f"{prefix or '/'}: {href} -> {response.status_code}"
        assert response.headers.get("cache-control") == "private, no-store" or href.startswith("/order/")


def test_the_pdf_of_each_document_downloads(order_with_both_documents):
    """Offered by the documents themselves, so followed from there rather than from the list."""
    from app.payments import routes as payment_routes

    order, refund = order_with_both_documents
    client = signed_in()
    for href in (payment_routes.public_paths(order["token"])["invoice_pdf"],
                 payment_routes.credit_note_path(order["token"], refund["refund_id"], pdf=True)):
        response = client.get(href)
        assert response.status_code == 200, f"{href} -> {response.status_code}"
        assert response.headers["content-type"] == "application/pdf"
        assert response.headers["content-disposition"].startswith("attachment")


def test_the_credit_note_link_carries_the_refund_id_and_not_the_number(order_with_both_documents):
    """The guess worth ruling out: the number RK-CN/2627/00001 has slashes in it, which WOULD break a path.
    It is not in the URL - the refund id is, and that is `rfnd_` plus hex. The prefix was the fault."""
    order, refund = order_with_both_documents
    href = [link for link in _links_on_the_page(signed_in().get("/orders").text) if "credit-note" in link][0]
    assert href.endswith(f"/{refund['refund_id']}")
    assert refund["credit_no"] not in href and "RK-CN" not in href


def test_the_document_paths_come_from_the_router_and_not_from_a_literal():
    """What actually went wrong, pinned: the paths are built from the router's own prefix, so a remount
    moves them with it. Spelled out by hand they were wrong for as long as they existed."""
    from app.payments import routes as payment_routes

    assert payment_routes.router.prefix == "/api/payments"
    paths = payment_routes.public_paths("t" * 32)
    assert paths["invoice"].startswith(payment_routes.router.prefix + "/")
    assert payment_routes.credit_note_path("t" * 32, "rfnd_1").startswith(payment_routes.router.prefix + "/")
    assert payment_routes.credit_note_path("t" * 32, "rfnd_1", pdf=True).endswith("/pdf")
    # /order/{token} is the WEB router's page and is deliberately NOT prefixed - it was right by accident,
    # which is why the order page's own invoice link worked while this page's did not.
    assert paths["order"] == "/order/" + "t" * 32


# ---- and only the customer's own documents ----------------------------------------------------------


def test_a_refund_id_from_another_order_is_not_a_credit_note_on_this_one(order_with_both_documents):
    """The refund id is in the path but is NOT a second credential: crossing the two is a 404, so neither
    a right token nor a right refund id can be used to learn that the other exists."""
    from app.payments import routes as payment_routes

    order, refund = order_with_both_documents
    stranger = store.new_order_id()
    store.insert_order(order_id=stranger, product="kundali-report", kind="report", amount_paise=29900,
                       currency="INR", razorpay_order_id="order_" + uuid.uuid4().hex[:14],
                       user_id="s" * 32, email="someone.else@gmail.com")
    with db.transaction() as conn:
        conn.execute("UPDATE orders SET status='paid', paid_at=? WHERE id=?", (time.time(), stranger))
    other = store.get_order(stranger)
    client = signed_in()
    try:
        # my refund, their token
        assert client.get(payment_routes.credit_note_path(other["token"], refund["refund_id"])).status_code == 404
        # my token, a refund that does not exist
        assert client.get(payment_routes.credit_note_path(order["token"], "rfnd_000000000000")).status_code == 404
        # being signed in as somebody is not itself a credential for a document
        assert client.get(payment_routes.public_paths(other["token"])["invoice"]).status_code == 404
    finally:
        with db.transaction() as conn:
            conn.execute("DELETE FROM orders WHERE id=?", (stranger,))


def test_the_list_only_ever_holds_the_signed_in_customers_own_orders(order_with_both_documents):
    """The documents are reached by token, so the page that HANDS OUT tokens is the boundary that matters."""
    order, _ = order_with_both_documents
    other = TestClient(app, raise_server_exceptions=False)
    other.cookies.set(accounts.COOKIE_NAME, accounts.sign("someone.else@gmail.com"))
    html = other.get("/orders").text
    assert order["token"] not in html
    assert "ord_" not in html
