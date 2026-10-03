"""GST: 18% added ON TOP of the listed prices (owner's decision, 2026-09-28), and the tax invoice.

What these tests are actually defending, in order of what they would cost if they broke:

  1. `base + gst == total`, exactly, on every product and on every stored row. The webhook refuses a payment
     whose amount differs from `amount_paise` by one paisa, and net revenue is the total minus the stored
     GST - so a rounding that drifts either rejects real payments or files a wrong return.
  2. The charge is the TOTAL everywhere it is named: Razorpay's order, the stored `amount_paise`, the button
     the customer presses. A page that quotes ₹249 and a window that asks for ₹293.82 with no line between
     them is the complaint this whole workstream exists to prevent.
  3. NULL is "not recorded" and never zero. Every order paid before these columns existed has NULL, and
     reading one as zero prints a ₹0.00 tax row - or worse, issues a tax invoice asserting nil tax.
  4. The invoice number series is consecutive per financial year and allocated once.

No real person's name or birth details appear here: the charts are tests/reference_charts.py (documented
public figures) and every buyer is invented.
"""

import base64
import datetime as dt
import hashlib
import hmac
import json
import re

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.payments import catalogue, gst, invoice, order_page, service, states, store
from app.web import STATIC_DIR, i18n, pages, site
from tests import reference_charts

KEY_ID, KEY_SECRET, WEBHOOK_SECRET = "rzp_test_UnitTestKey01", "unit-test-key-secret-Zx81", "unit-test-webhook-secret-Qp55"
BIRTH = reference_charts.PRIMARY.request()
OTHER = reference_charts.NEHRU.request()
BUYER = "buyer@example.com"          # invented, like every address in this file
# The arithmetic, pinned as literals - computing it from the code under test would assert nothing - but keyed
# by LISTED PRICE rather than by product. That is deliberate: keyed by product, this table encoded the price
# list a second time, so every price change had to be made here too, which is how a pinned table stops being a
# check of the rule and becomes a copy of the data. Keyed by price, a price change touches NO line of it; only
# a brand-new price point does, and then `charge()` below fails and names the number to add.
#
# 18% INCLUSIVE of each whole-rupee price the catalogue uses or plausibly will: {listed paise: (base, gst)}.
SPLITS = {
    4900: (4153, 747),
    5900: (5000, 900),
    9900: (8390, 1510),
    11900: (10085, 1815),
    24900: (21102, 3798),
    29900: (25339, 4561),
    34900: (29576, 5324),
}


def charge(product: str) -> tuple[int, int, int]:
    """(base, gst, total) for a product, from SPLITS and the catalogue's CURRENT listed price.

    Under inclusive pricing the total IS the listed price, so there is nothing to look up for it; what has to
    be pinned is how that total divides."""
    listed = catalogue.item(product).price_inr * 100
    assert listed in SPLITS, (f"{product} is listed at {listed} paise and SPLITS has no entry for it - add "
                              f"{listed}: (base, gst) once you have worked out the 18% inclusive split")
    base, tax = SPLITS[listed]
    assert base + tax == listed, f"SPLITS[{listed}] does not add up to {listed}"
    return base, tax, listed


class FakeRazorpay:
    """Create-order only, recording every amount it was asked for. No network, no SDK."""

    def __init__(self):
        self.requests = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        expected = "Basic " + base64.b64encode(f"{KEY_ID}:{KEY_SECRET}".encode()).decode()
        if request.headers.get("authorization") != expected:
            return httpx.Response(401, json={"error": {"code": "BAD_REQUEST_ERROR", "description": "auth failed"}})
        if request.method == "POST" and request.url.path == "/v1/orders":
            body = json.loads(request.content)
            self.requests.append(body)
            return httpx.Response(200, json={"id": f"order_Gst{len(self.requests):010d}", "entity": "order",
                                             "amount": body["amount"], "currency": body["currency"],
                                             "receipt": body["receipt"], "status": "created", "attempts": 0,
                                             "notes": body["notes"]})
        return httpx.Response(200, json={"entity": "collection", "count": 0, "items": []})


@pytest.fixture
def rzp(monkeypatch):
    """Payments configured, Razorpay faked, and no background work: no report is generated and no e-mail sent."""
    from app.payments import razorpay

    monkeypatch.setenv("RAZORPAY_KEY_ID", KEY_ID)
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", KEY_SECRET)
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", WEBHOOK_SECRET)
    fake = FakeRazorpay()
    monkeypatch.setattr(razorpay, "_transport", httpx.MockTransport(fake))
    monkeypatch.setattr(service, "_spawn", lambda function, *args: None)
    yield fake
    monkeypatch.setattr(razorpay, "_transport", None)


@pytest.fixture
def js():
    """pay.js's pure functions in V8 - the same harness tests/test_payments.py uses."""
    mini_racer = pytest.importorskip("py_mini_racer")
    ctx = mini_racer.MiniRacer()
    ctx.eval((STATIC_DIR / "js" / "pay.js").read_text(encoding="utf-8"))

    def call(expression: str, **variables):
        names = ", ".join(variables)
        args = ", ".join(json.dumps(value, ensure_ascii=False) for value in variables.values())
        return json.loads(ctx.eval(f"JSON.stringify((function({names}) {{ return {expression}; }})({args}))"))

    return call


def buy(client: TestClient, product: str = "kundali-report", **extra) -> dict:
    body = {"product": product, "language": "en", "birth": BIRTH, "email": BUYER,
            "place_of_supply": states.seller_code(), **extra}
    response = client.post("/api/payments/order", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def pay(client: TestClient, razorpay_order_id: str, payment_id: str = "pay_Gst00000000001") -> dict:
    signature = hmac.new(KEY_SECRET.encode(), f"{razorpay_order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()
    response = client.post("/api/payments/verify", json={"razorpay_order_id": razorpay_order_id,
                                                         "razorpay_payment_id": payment_id,
                                                         "razorpay_signature": signature})
    assert response.status_code == 200, response.text
    return response.json()


# ---- the setting and the arithmetic ------------------------------------------------------------------


def test_the_rate_and_the_mode_are_one_setting_read_at_call_time(monkeypatch):
    """One place for both, and read per call - so a test or a script can change it without a restart."""
    settings = gst.get_settings()
    assert (settings.rate_bp, settings.inclusive, settings.rate_text, settings.charged) == (1800, True, "18", True)

    monkeypatch.setenv("GST_RATE_PERCENT", "12.5")
    monkeypatch.setenv("GST_INCLUSIVE", "0")
    changed = gst.get_settings()
    assert (changed.rate_bp, changed.inclusive, changed.rate_text) == (1250, False, "12.5")

    # A typo is loud. Falling back to 18% would charge a rate nobody chose, which is the one outcome worse
    # than not starting.
    monkeypatch.setenv("GST_RATE_PERCENT", "eighteen")
    with pytest.raises(ValueError):
        gst.get_settings()
    monkeypatch.setenv("GST_RATE_PERCENT", "-5")
    with pytest.raises(ValueError):
        gst.get_settings()


def test_the_mode_defaults_to_what_the_catalogue_means_and_a_typo_cannot_flip_it(monkeypatch):
    """The catalogue's prices are GST-INCLUSIVE TOTALS, so the code's default has to say so.

    This is the most expensive thing in the file to get wrong. If the default were exclusive, a deploy that
    forgot one line of .env would read ₹59 as a pre-tax base and charge ₹69.62 - a silent 18% overcharge to
    real customers, with nothing failing and nothing warning. So the default is asserted, not assumed."""
    monkeypatch.delenv("GST_INCLUSIVE", raising=False)
    assert gst.DEFAULT_INCLUSIVE is True
    assert gst.get_settings().inclusive is True, "unset must mean what the catalogue's numbers mean"
    for product in catalogue.prices_inr():
        entry = catalogue.item(product)
        assert entry.amount_paise == entry.price_inr * 100, (
            f"{product}: with inclusive pricing the charge IS the listed price - a charge above it means the "
            f"default disagrees with the catalogue, which is the overcharge this test exists to stop")

    # And an unrecognised value is refused rather than read as "no". The usual `in {"1","true",...}` idiom
    # answers False for anything it does not know, so GST_INCLUSIVE="ture" would silently mean exclusive -
    # the same overcharge, one typo away instead of one forgotten line away.
    for junk in ("ture", "yes please", "2", "maybe"):
        monkeypatch.setenv("GST_INCLUSIVE", junk)
        with pytest.raises(ValueError, match="neither a yes"):
            gst.get_settings()
    for word, expected in (("1", True), ("true", True), ("on", True), ("yes", True),
                           ("0", False), ("false", False), ("off", False), ("no", False)):
        monkeypatch.setenv("GST_INCLUSIVE", word)
        assert gst.get_settings().inclusive is expected, word


def test_the_split_always_adds_up_and_rounds_halves_up():
    """The property everything downstream rests on, over every paise value up to ₹1000, then the halves.

    Exhaustive rather than sampled: the failure being looked for is a single value where the parts do not
    reconstruct the charge, and a sample is exactly how such a value survives."""
    settings = gst.GstSettings(rate_bp=1800, inclusive=False)
    for paise in range(0, 100_001):
        amounts = gst.split(paise, settings)          # Amounts.__post_init__ raises if the three disagree
        assert amounts.base_paise == paise and amounts.total_paise == paise + amounts.gst_paise

    # Half-up, not half-to-even: 5% of 50 paise is 2.5 paise and must become 3, and it must not depend on
    # whether the neighbouring digit is odd. `round()` gives 2 here, which is why it is not used.
    half = gst.GstSettings(rate_bp=500, inclusive=False)
    assert gst.split(50, half).gst_paise == 3
    assert gst.split(150, half).gst_paise == 8          # 7.5 -> 8, where round() would give 8 as well
    assert gst.split(250, half).gst_paise == 13         # 12.5 -> 13, where round() gives 12


def test_inclusive_pricing_charges_exactly_the_listed_price():
    """The other half of the setting. Not the launch decision, but it must work, because the reason to have
    the flag at all is that flipping it is a business decision and not a code change."""
    settings = gst.GstSettings(rate_bp=1800, inclusive=True)
    amounts = gst.split(24900, settings)
    assert amounts.total_paise == 24900, "an inclusive price must charge the round number on the page"
    assert (amounts.base_paise, amounts.gst_paise) == (21102, 3798)
    for paise in range(0, 100_001, 7):
        split = gst.split(paise, settings)
        assert split.total_paise == paise and split.base_paise + split.gst_paise == paise


def test_a_zero_rate_is_gst_switched_off_and_not_a_zero_tax_line():
    """GST_RATE_PERCENT=0 has to mean "we do not charge GST", not "we charge nil GST": the difference shows
    up as a ₹0.00 row on a customer's order page and as a nil-tax invoice, neither of which is true."""
    off = gst.GstSettings(rate_bp=0, inclusive=False)
    amounts = gst.split(24900, off)
    assert (amounts.base_paise, amounts.gst_paise, amounts.total_paise) == (24900, 0, 24900)
    assert off.charged is False
    assert order_page.money({"base_paise": 24900, "gst_paise": 0, "amount_paise": 24900, "gst_rate_bp": 0}, "en") is None


def test_money_is_written_the_way_a_statement_writes_it():
    assert gst.money(24900) == "249" and gst.money(29382) == "293.82" and gst.money(5782) == "57.82"
    assert gst.money(24910) == "249.10", "a real paise figure keeps both digits; 249.1 is not an amount"
    assert gst.money(0) == "0" and gst.money(None) == ""


def test_every_catalogue_item_charges_its_listed_price_and_splits_it_correctly():
    """`price_inr` is the LISTED price and `amount_paise` is what is CHARGED; under inclusive pricing those are
    the SAME number and the split lives inside it. Every product is walked, so a new one cannot arrive
    unpriced, unsplit, or at a price point whose arithmetic nobody has checked."""
    for product in catalogue.prices_inr():
        base, tax, total = charge(product)
        entry = catalogue.item(product)
        assert entry.base_paise == total == entry.price_inr * 100, (
            f"{product}: Item.base_paise is the LISTED price in paise, which inclusive pricing makes the total")
        assert (entry.gst.base_paise, entry.gst.gst_paise, entry.gst.total_paise) == (base, tax, total), product
        assert entry.gst.rate_bp == 1800, product
        assert entry.amount_paise == total, f"{product}: amount_paise is the charge, and that is the listed price"


# ---- what is charged and what is stored --------------------------------------------------------------


def test_razorpay_is_asked_for_the_total_and_the_order_records_the_split(rzp):
    client = TestClient(app)
    for product in ("kundali-report", "kundali-report-simple", "mangal-dosha-remedy"):
        base, tax, total = charge(product)
        created = buy(client, product)
        assert rzp.requests[-1]["amount"] == total, f"{product}: Razorpay must be charged the tax-inclusive total"
        assert created["amount"] == total
        # and the split is quoted back, so the browser never needs to do tax arithmetic
        assert (created["base_inr"], created["gst_inr"], created["total_inr"], created["gst_rate"]) == \
            (base / 100, tax / 100, total / 100, "18")
        row = store.by_razorpay_id(created["order_id"])
        assert (row["amount_paise"], row["base_paise"], row["gst_paise"], row["gst_rate_bp"]) == (total, base, tax, 1800)
        assert row["base_paise"] + row["gst_paise"] == row["amount_paise"]


def test_net_revenue_is_the_stored_base_and_is_computable_from_the_row(rzp):
    """The whole reason base is a column: net revenue is a sum over rows, not a rate applied afterwards.

    Applying today's rate to `amount_paise` would be wrong for every row written under a different rate, and
    there is no way to tell those rows apart once the rate has changed - which is what the stored rate is for."""
    client = TestClient(app)
    sold = ["kundali-report", "kundali-report-simple", "matching-report"]
    for product in sold:
        created = buy(client, product, birth=BIRTH if product != "matching-report" else None,
                      **({"boy": BIRTH, "girl": OTHER} if product == "matching-report" else {}))
        pay(client, created["order_id"], f"pay_Net{len(product):013d}")
    rows = [store.by_razorpay_id(f"order_Gst{n:010d}") for n in range(1, len(sold) + 1)]
    assert all(row["status"] == "paid" for row in rows)
    gross = sum(row["amount_paise"] for row in rows)
    net = sum(row["base_paise"] for row in rows)
    collected = sum(row["gst_paise"] for row in rows)
    assert gross == sum(charge(p)[2] for p in sold)
    assert net == sum(charge(p)[0] for p in sold) and collected == gross - net
    assert net < gross, "net revenue must be strictly below the charge whenever GST is collected"


def test_the_webhook_accepts_the_total_and_refuses_the_pre_tax_amount(rzp):
    """The amount check is what stops a partial payment unlocking a report, and the figure it compares
    against is the tax-inclusive total, i.e. the listed price. A webhook carrying the TAXABLE VALUE - the
    pre-tax part of that same price, and the other number printed on the invoice - must not fulfil."""
    client = TestClient(app)
    created = buy(client, "kundali-report")
    base, _tax, total = charge("kundali-report")

    def deliver(amount: int) -> str:
        event = {"event": "payment.captured",
                 "payload": {"payment": {"entity": {"id": "pay_Hook0000000001", "order_id": created["order_id"],
                                                    "amount": amount, "currency": "INR"}}}}
        raw = json.dumps(event).encode()
        signature = hmac.new(WEBHOOK_SECRET.encode(), raw, hashlib.sha256).hexdigest()
        response = client.post("/api/payments/webhook", content=raw,
                               headers={"x-razorpay-signature": signature, "content-type": "application/json"})
        assert response.status_code == 200, response.text
        return response.json()["status"]

    assert deliver(base) == "amount_mismatch"
    assert store.by_razorpay_id(created["order_id"])["status"] != "paid"
    assert deliver(total) == "ok"
    assert store.by_razorpay_id(created["order_id"])["status"] == "paid"


def test_an_order_paid_before_gst_existed_is_never_read_as_zero_tax(rzp, monkeypatch):
    """The NULL case, end to end: no breakdown, no invoice link, no invoice, and the amount row survives.

    This is the one that costs real money if it is wrong. Those orders were charged a price with no tax
    behind them; a reader that takes NULL as 0 puts a "GST ₹0.00" row on the customer's page and, given the
    chance, issues them a tax invoice stating that tax was collected and was nil."""
    client = TestClient(app)
    created = buy(client, "kundali-report")
    view = pay(client, created["order_id"])
    order_id = store.by_razorpay_id(created["order_id"])["id"]

    # make it look like a pre-GST sale: the columns did not exist, so they are NULL
    from app import db

    with db.transaction() as conn:
        conn.execute("UPDATE orders SET base_paise = NULL, gst_paise = NULL, gst_rate_bp = NULL, invoice_no = NULL "
                     "WHERE id = ?", (order_id,))
    order = store.get_order(order_id)
    assert gst.recorded(order) is None
    assert order_page.money(order, "en") is None
    assert invoice.context(order) is None and invoice.render(order) is None
    assert invoice.assign(order) is None, "an untaxed sale must not consume a number in the invoice series"

    fresh = service.public_view(order, reveal_token=True)
    assert fresh["gst"] is None and fresh["invoice_url"] is None
    assert fresh["amount_inr"] == charge("kundali-report")[2] / 100, "the charge is still the charge"
    page = client.get(view["order_url"]).text
    assert order_page.LABELS["en"]["amount"] in page and order_page.LABELS["en"]["total"] not in page
    assert "0.00" not in page and "/api/payments/invoice/" not in page
    assert client.get(f"/api/payments/invoice/{order['token']}").status_code == 404


def test_a_row_whose_parts_do_not_add_up_is_treated_as_not_recorded():
    """Belt and braces on the one invariant: a breakdown that disagrees with the money must not be shown."""
    assert gst.recorded({"base_paise": 24900, "gst_paise": 4482, "amount_paise": 29382}) is not None
    assert gst.recorded({"base_paise": 24900, "gst_paise": 4482, "amount_paise": 24900}) is None
    assert gst.recorded({"base_paise": 24900, "gst_paise": None, "amount_paise": 29382}) is None
    assert gst.recorded({"base_paise": None, "gst_paise": 4482, "amount_paise": 29382}) is None


# ---- the tax invoice ---------------------------------------------------------------------------------


def test_the_invoice_number_is_consecutive_per_financial_year_and_fits_the_rule():
    """Rule 46(b): consecutive, unique within the financial year, at most 16 characters.

    The financial year is read in IST. A sale at 03:00 IST on 1 April is in the new year; the same instant
    read in UTC is 31 March and would be filed in the old one."""
    ist = invoice.IST
    assert invoice.series_for(dt.datetime(2026, 9, 28, 12, 0, tzinfo=ist).timestamp()) == "2627"
    assert invoice.series_for(dt.datetime(2027, 3, 31, 23, 0, tzinfo=ist).timestamp()) == "2627"
    assert invoice.series_for(dt.datetime(2027, 4, 1, 3, 0, tzinfo=ist).timestamp()) == "2728"
    assert invoice.financial_year(dt.datetime(2026, 3, 31, tzinfo=ist)) == (2025, 2026)

    number = invoice.NUMBER_TEMPLATE.format(prefix=invoice.prefix(), series="2627", n=99999)
    assert len(number) <= invoice.MAX_NUMBER_LENGTH == 16, number
    assert re.fullmatch(r"[A-Za-z0-9/-]+", number), "only alphanumerics, '-' and '/' are allowed in the series"


def test_each_paid_order_gets_the_next_number_once_and_keeps_it(rzp):
    client = TestClient(app)
    numbers = []
    for n, (product, extra) in enumerate([("kundali-report", {}), ("kundali-report-simple", {"birth": OTHER}),
                                          ("sade-sati-guide", {})], start=1):
        created = buy(client, product, **extra)
        pay(client, created["order_id"], f"pay_Inv{n:013d}")
        row = store.by_razorpay_id(created["order_id"])
        numbers.append(row["invoice_no"])
    assert numbers == ["RK/2627/00001", "RK/2627/00002", "RK/2627/00003"], numbers

    # idempotent: confirm_payment runs again on every webhook and reconcile, and an invoice already sent to
    # somebody may not be renumbered
    order = store.by_razorpay_id("order_Gst0000000001")
    assert invoice.assign(order) == order["invoice_no"] == "RK/2627/00001"
    assert store.assign_invoice_number(order["id"], "2627", "RK", invoice.NUMBER_TEMPLATE, 16) == "RK/2627/00001"

    # A number that would break the 16-character rule is refused, not truncated: it is the serial's own
    # digits that would be cut off, which is the part that makes the series consecutive. Asserted against an
    # order that has NO number yet - one that already has one returns it and never formats anything.
    unnumbered = store.by_razorpay_id(buy(client, "matching-report", birth=None, boy=BIRTH, girl=OTHER)["order_id"])
    assert unnumbered["invoice_no"] is None
    with pytest.raises(ValueError):
        store.assign_invoice_number(unnumbered["id"], "2627", "AN-EXTREMELY-LONG-PREFIX", invoice.NUMBER_TEMPLATE, 16)
    assert store.get_order(unnumbered["id"])["invoice_no"] is None, "a refused allocation must write nothing"


def test_the_invoice_carries_everything_a_gst_invoice_has_to_carry(rzp):
    client = TestClient(app)
    created = buy(client, "kundali-report", language="mr", name="Keshav Apte")
    view = pay(client, created["order_id"])
    base, tax, total = charge("kundali-report")

    assert view["invoice_url"] == f"/api/payments/invoice/{store.by_razorpay_id(created['order_id'])['token']}"
    response = client.get(view["invoice_url"])
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/html")
    # a document that names the buyer and what they bought is private, uncached and unindexable, like the
    # order page it hangs off
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-robots-tag"] == "noindex, nofollow" and response.headers["referrer-policy"] == "no-referrer"
    body = response.text
    # The COMPOSITE tax figure is deliberately not in this list. This buyer is in the seller's state, so the tax
    # appears as two halves and ₹45.61 is nowhere on the document - only ₹22.81 + ₹22.80, which sum to it.
    for needle in (site.LEGAL_ENTITY, site.LEGAL_ADDRESS, site.GSTIN, invoice.sac_code(), "RK/2627/00001",
                   BUYER, "Tax invoice", f"₹{gst.money(base)}", f"₹{gst.money(total)}",
                   # Rule 46(p): the invoice must SAY whether tax is payable on reverse charge. "No" is an
                   # answer; leaving the field off is not, and it is the kind of omission an assessing
                   # officer notices rather than the customer.
                   "Reverse charge", ">No<"):
        assert needle in body, needle
    halves = gst.heads(gst.Amounts(base, tax, total, 1800), True)
    assert sum(head.paise for head in halves) == tax
    for head in halves:
        assert f"₹{gst.money(head.paise)}" in body, head
    # The buyer chose the seller's own state, so the tax is filed as CGST + SGST at half the rate each. The
    # COMPOSITE line must be gone: showing both "GST @ 18%" and "CGST @ 9% / SGST @ 9%" would state the tax
    # twice on a document whose total is the sum of one of them.
    assert "CGST @ 9%" in body and "SGST @ 9%" in body and "GST @ 18%" not in body and "IGST" not in body
    assert f"Maharashtra ({states.seller_code()})" in body, "the place of supply, with the code a return uses"
    assert "not recorded" not in body, "this order HAS a place of supply, so the fallback footnote must be gone"
    assert KEY_SECRET not in body and WEBHOOK_SECRET not in body
    # the line describes what the buyer saw, in the language they bought in
    assert order_page.PRODUCT_NAMES["kundali-report"]["mr"] in body
    # it is a complete standalone document: no site layout to inherit, and nothing to fetch
    assert body.lstrip().startswith("<!doctype html>") and "<html lang=\"en\">" in body
    assert "http://" not in body and "https://" not in body

    # the token is the credential, and a wrong one is a 404 rather than a 403 - a 403 would confirm the order
    stranger = TestClient(app)
    assert stranger.get(view["invoice_url"]).status_code == 200      # the link works from any device
    assert stranger.get("/api/payments/invoice/" + "Z" * 32).status_code == 404
    assert stranger.get("/api/payments/invoice/short").status_code == 404


def test_the_invoice_splits_the_tax_on_the_place_of_supply_without_moving_the_money(rzp):
    """CGST+SGST for the seller's own state, IGST for anywhere else, and the CUSTOMER PAYS THE SAME either way.

    That last clause is the one worth a test. The split is a classification for a return; if it ever changed the
    charge, two buyers of the same product in different states would be billed differently for the same thing."""
    client = TestClient(app)
    inter = next(code for code in states.CODES if code != states.seller_code())
    charged, documents = set(), {}
    for code in (states.seller_code(), inter):
        created = buy(client, "kundali-report", birth={**BIRTH, "date": f"199{code[-1]}-04-05"}, place_of_supply=code)
        view = pay(client, created["order_id"], f"pay_Pos{code}000000000")
        order = store.by_razorpay_id(created["order_id"])
        assert order["place_of_supply"] == code
        charged.add(order["amount_paise"])
        documents[code] = client.get(view["invoice_url"]).text

    assert len(charged) == 1, f"the place of supply must not change what is charged, got {charged}"
    base, tax, total = charge("kundali-report")
    assert charged == {total}

    intra_doc, inter_doc = documents[states.seller_code()], documents[inter]
    assert "CGST @ 9%" in intra_doc and "SGST @ 9%" in intra_doc and "IGST" not in intra_doc
    assert f"IGST @ 18%" in inter_doc and "CGST" not in inter_doc and "SGST" not in inter_doc
    assert states.name(inter) in inter_doc and "outside the seller's state" in inter_doc
    # and the heads add up to the tax that was stored, in both cases - the identity the money rests on
    amounts = gst.recorded(store.by_razorpay_id(created["order_id"]))
    for intra in (True, False):
        heads = gst.heads(amounts, intra)
        assert sum(head.paise for head in heads) == amounts.gst_paise == tax
        assert [head.name for head in heads] == (["CGST", "SGST"] if intra else ["IGST"])
    # an odd number of paise still reconciles: it cannot be halved, so the remainder lands on SGST by convention
    odd = gst.Amounts(base_paise=1001, gst_paise=181, total_paise=1182, rate_bp=1800)
    cgst, sgst = gst.heads(odd, True)
    assert cgst.paise + sgst.paise == 181 and abs(cgst.paise - sgst.paise) == 1


def test_a_sale_with_no_recorded_place_of_supply_is_not_given_one(rzp):
    """The orders that predate the checkout field. They keep the composite line and say so; they are NOT
    assigned the seller's state, which would print a CGST/SGST claim against a state nobody collected."""
    from app import db

    client = TestClient(app)
    created = buy(client, "kundali-report")
    view = pay(client, created["order_id"])
    order_id = store.by_razorpay_id(created["order_id"])["id"]
    with db.transaction() as conn:
        conn.execute("UPDATE orders SET place_of_supply = NULL WHERE id = ?", (order_id,))
    order = store.get_order(order_id)

    assert states.is_intra_state(None) is False and states.is_intra_state(order["place_of_supply"]) is False
    data = invoice.context(order)
    assert data["heads"] == [] and data["place_of_supply"] == "" and data["intra_state"] is False
    body = client.get(view["invoice_url"]).text
    assert "GST @ 18%" in body and "CGST" not in body and "IGST" not in body
    assert "Place of supply was not recorded" in body
    assert "Place of supply</dt>" not in body, "no empty row where the state would have been"


def test_the_state_list_is_the_one_a_return_accepts_and_never_a_translated_label():
    """The place of supply is COMPARED, so what is stored has to be stable across the three languages."""
    assert len(states.CODES) == 36, "28 states and 8 union territories"
    assert "25" not in states.CODES and "28" not in states.CODES, (
        "25 and 28 are retired codes (25 merged into 26, 28 became 37); offering them invites a place of "
        "supply that no return accepts")
    for code in states.CODES:
        assert len(code) == 2 and code.isdigit(), code
        for lang in states.LANGS:
            assert states.name(code, lang).strip(), (code, lang)
    # every language has its own form, and the two Devanagari ones are not simply each other
    assert states.name("27", "en") == "Maharashtra" and states.name("27", "mr") == states.name("27", "hi")
    assert states.name("32", "hi") != states.name("32", "mr"), "Kerala is written differently in the two"

    # the seller's state is DERIVED from the GSTIN, so it cannot drift from the registration on the invoice
    assert states.seller_code() == site.GSTIN[:2] == "27"
    assert states.is_intra_state("27") and not states.is_intra_state("29")
    # and an unknown or missing code is never quietly treated as the seller's own
    for absent in (None, "", "99", "25", "Maharashtra", "mh"):
        assert not states.is_intra_state(absent) and not states.is_known(absent), absent
        assert states.name(absent) == ""

    # the dropdown is sorted by the name the reader sees, not by the filing code
    for lang in states.LANGS:
        offered = states.for_language(lang)
        assert len(offered) == 36 and [name for _code, name in offered] == sorted(name for _c, name in offered)
        assert dict(offered)["27"] == states.name("27", lang)


# ---- "Outside India": a zero-rated export, behind a flag that is OFF ---------------------------------


def _checkout_pages(client: TestClient) -> list[tuple[str, str, str]]:
    """(lang, page key, html) for every page that renders the place-of-supply dropdown."""
    return [(lang, key, client.get(i18n.url_for(key, lang)).text)
            for lang in i18n.LANGS for key in (*i18n.TOOL_KEYS, "consultation") if lang in i18n.page_langs(key)]


def test_outside_india_is_unreachable_while_export_sales_are_off(rzp):
    """THE test of this pair. The export entry bills at 0% GST, so while it is off it has to be off in the two
    places that matter, and the second one is the one that holds the money: the option is absent from the page,
    AND the API refuses the code when it is posted directly.

    A dropdown is a suggestion. Everything a customer sends is editable, and `place_of_supply` is a plain field
    on a JSON body - so "we do not render the option" is not a control, it is a hint. If only the page enforced
    this, every buyer on earth could have the tax taken off their order by typing two digits into devtools, and
    nothing would look wrong anywhere: the charge would be the same ₹299, the order would be paid, and the
    return would be short by 18% of it with an invoice claiming an undertaking that has not been filed.

    Off is also the DEFAULT, asserted here rather than set up, because an env var that has to be remembered on
    the VPS is not a control either."""
    assert gst.DEFAULT_EXPORT_SALES is False and gst.export_sales_enabled() is False
    assert states.sells_to(states.EXPORT_CODE) is False
    assert states.sells_to("27") is True

    # not in the dropdown, in any language, and the 36 states are untouched
    for lang in states.LANGS:
        offered = states.for_language(lang)
        assert len(offered) == 36 and states.EXPORT_CODE not in dict(offered)
        assert states.EXPORT_NAMES[lang] not in [label for _code, label in offered]

    # nor in the rendered <select> of either checkout page, in any of the three trees
    client = TestClient(app)
    pages_checked = _checkout_pages(client)
    for lang, key, html in pages_checked:
        assert f'value="{states.EXPORT_CODE}"' not in html, (lang, key)
        for label in states.EXPORT_NAMES.values():
            assert label not in html, (lang, key, label)
    assert len(pages_checked) >= 12, f"only {len(pages_checked)} checkout pages rendered - is the page list right?"

    # and the API refuses it when it is posted anyway, for every product on sale, with no order row created
    before = len(rzp.requests)
    for entry in catalogue.all_items():
        body = {"product": entry.product, "language": "en", "birth": BIRTH, "email": BUYER,
                "place_of_supply": states.EXPORT_CODE}
        if entry.kind == "pack":
            body["session_id"] = "session-that-is-long-enough"
        response = client.post("/api/payments/order", json=body)
        assert response.status_code == 422, (entry.product, response.status_code, response.text)
        assert "place_of_supply" in response.text
    assert len(rzp.requests) == before, "a refused place of supply must not have reached Razorpay"

    # the last line of defence: if something ever bypasses the API model, the split refuses rather than guessing.
    # Both available guesses are wrong - 0% is the leak, 18% is a tax invoice against a foreign supply.
    with pytest.raises(ValueError):
        states.tax_settings(states.EXPORT_CODE)


def test_a_domestic_order_is_byte_identical_after_the_export_work(rzp):
    """The assertion that lets someone trust this diff. `service.create_order` stopped calling `item.gst` and
    now splits through `states.tax_settings(place_of_supply)` - so the thing to prove is that for all 36 Indian
    codes that function returns the configured setting UNCHANGED, and every existing sale stores exactly what
    it stored before.

    ALL 36 codes go through `tax_settings`, which is the check that matters: a sampled pair would have passed
    just as happily if the export branch had swallowed a whole range of codes. That part costs nothing because
    it is a pure function.

    The stored row is then asserted on a spread rather than on all 36, because `POST /api/payments/order` is
    rate-limited to ORDERS_PER_HOUR_PER_USER (10) and 36 orders trips it - which is the endpoint working, not a
    problem to route around. The row is worth asserting at all because it, not the function's return value, is
    what the webhook's amount comparison, the invoice and net revenue read."""
    client = TestClient(app)
    settings = gst.get_settings()
    for code in states.CODES:
        assert states.tax_settings(code) == settings, code
        assert states.sells_to(code) and not states.is_export(code), code

    base, tax, total = charge("kundali-report")
    # the seller's own state, its neighbours in the table, and both ends of the range
    spread = (states.seller_code(), states.CODES[0], states.CODES[-1], "07", "29", "37")
    for n, code in enumerate(spread):
        # a distinct birth date per order so the same-report-already-paid shortcut does not return an earlier one
        created = buy(client, "kundali-report", birth={**BIRTH, "date": f"19{60 + n:02d}-04-05"}, place_of_supply=code)
        order = store.by_razorpay_id(created["order_id"])
        assert (order["base_paise"], order["gst_paise"], order["gst_rate_bp"]) == (base, tax, 1800), code
        assert order["amount_paise"] == total and order["place_of_supply"] == code, code
        assert rzp.requests[-1]["amount"] == total, code


def test_the_export_flag_refuses_a_typo_rather_than_reading_it_as_off(monkeypatch):
    """Same doctrine as GST_INCLUSIVE: the usual `value in {"1","true"}` idiom answers False for anything it
    does not recognise, so `EXPORT_SALES_ENABLED="ture"` would mean "off" - which is the safe direction here
    but silent, so the day it is switched on nobody could tell a typo from a deliberate no."""
    for junk in ("ture", "yes please", "maybe", "2", "enabled"):
        monkeypatch.setenv("EXPORT_SALES_ENABLED", junk)
        with pytest.raises(ValueError, match="EXPORT_SALES_ENABLED"):
            gst.export_sales_enabled()
    for word, expected in (("1", True), ("on", True), ("yes", True), ("0", False), ("off", False), ("no", False)):
        monkeypatch.setenv("EXPORT_SALES_ENABLED", word)
        assert gst.export_sales_enabled() is expected, word
    monkeypatch.delenv("EXPORT_SALES_ENABLED")
    assert gst.export_sales_enabled() is gst.DEFAULT_EXPORT_SALES is False


def test_export_sales_switched_on_bill_as_zero_rated_under_lut(rzp, monkeypatch):
    """With the flag on: the option is offered, the order records it, the tax is NOTHING, and the invoice says
    why it is nothing instead of showing a split it does not have.

    The charge does not move. ₹299 is ₹299 to Pune and ₹299 to a buyer outside India - zero-rating raises the
    taxable value to the whole of the listed price rather than lowering the price - so `base + gst == total`
    still holds with gst == 0, which is the identity the webhook's amount check and net revenue both rest on."""
    monkeypatch.setenv("EXPORT_SALES_ENABLED", "1")
    client = TestClient(app)

    # offered, in every language, and LAST rather than sorted between Odisha and Puducherry
    for lang in states.LANGS:
        offered = states.for_language(lang)
        assert len(offered) == 37 and offered[-1] == (states.EXPORT_CODE, states.EXPORT_NAMES[lang])
        assert [label for _code, label in offered[:-1]] == sorted(label for _c, label in offered[:-1])
    for lang, key, html in _checkout_pages(client):
        assert f'value="{states.EXPORT_CODE}"' in html and states.EXPORT_NAMES[lang] in html, (lang, key)

    _base, domestic_tax, total = charge("kundali-report")
    created = buy(client, "kundali-report", place_of_supply=states.EXPORT_CODE)
    order = store.by_razorpay_id(created["order_id"])
    assert order["place_of_supply"] == states.EXPORT_CODE
    assert order["gst_paise"] == 0 and order["gst_rate_bp"] == 0
    assert order["base_paise"] == order["amount_paise"] == total, "the listed price is the charge AND the taxable value"
    assert rzp.requests[-1]["amount"] == total, "the place of supply must not change what Razorpay is asked for"
    assert domestic_tax > 0, "the comparison is only worth making while the domestic sale really is taxed"

    amounts = gst.recorded(order)
    assert amounts.base_paise + amounts.gst_paise == amounts.total_paise == total
    assert amounts.gst_paise == 0 and amounts.rate_bp == 0
    assert gst.heads(amounts, True) == () and gst.heads(amounts, False) == (), "nothing to file under a head"

    view = pay(client, created["order_id"], "pay_GstExport00001")
    body = client.get(view["invoice_url"]).text
    assert gst.EXPORT_TREATMENT in body
    assert f"Outside India ({states.EXPORT_CODE})" in body
    assert "(GST 0%)" in body and "Letter of Undertaking" in body
    # No split, no sentence claiming tax was computed in either direction, and NO ZERO AMOUNT in the tax column:
    # "₹0.00" there would assert that tax was collected and was nil, which is not what a zero-rated supply is.
    assert "CGST @" not in body and "SGST @" not in body and "IGST @" not in body
    assert "GST @ 18%" not in body and "GST @ 0%" not in body and "includes GST" not in body
    assert "₹0" not in body, "a zero-rated export must show no tax amount at all"
    assert "not recorded" not in body, "this order HAS a place of supply"

    # And no tax row anywhere the CUSTOMER looks either. A "GST at 0%  ₹0.00" line on the order page would
    # contradict the invoice, which says no tax was chargeable at all - and it is the page they read first.
    assert view["gst"] is None and order_page.money(order, "en") is None
    for lang in ("en", "hi", "mr"):
        page = client.get(f"/order/{order['token']}", params={"lang": lang})
        assert page.status_code == 200, (lang, page.status_code)
        assert order_page.LABELS[lang]["gst"].replace("{rate}", "0") not in page.text, lang
        assert "₹0" not in page.text, lang

    # AND THE DOCUMENT IS FROZEN. Switching exports back off must not reprint this sale as a domestic one with
    # no tax on it - the flag governs what may be SOLD, never how a past order reads.
    monkeypatch.setenv("EXPORT_SALES_ENABLED", "0")
    assert states.sells_to(states.EXPORT_CODE) is False
    reread = client.get(view["invoice_url"]).text
    assert gst.EXPORT_TREATMENT in reread and f"Outside India ({states.EXPORT_CODE})" in reread
    assert states.is_export(order["place_of_supply"]) and not states.is_intra_state(order["place_of_supply"])


def test_an_unpaid_order_has_no_invoice(rzp):
    client = TestClient(app)
    created = buy(client, "kundali-report")
    order = store.by_razorpay_id(created["order_id"])
    assert order["status"] == "created" and order["invoice_no"] is None
    assert invoice.assign(order) is None and invoice.render(order) is None
    assert client.get(f"/api/payments/invoice/{order['token']}").status_code == 404


# ---- what the customer sees, in three languages -----------------------------------------------------


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_the_order_page_shows_price_gst_and_total_in_the_orders_language(rzp, lang):
    client = TestClient(app)
    created = buy(client, "kundali-report", language=lang)
    view = pay(client, created["order_id"])
    base, tax, total = charge("kundali-report")
    assert view["gst"] == {"base_inr": base / 100, "gst_inr": tax / 100, "total_inr": total / 100, "rate": "18"}

    page = client.get(view["order_url"]).text
    labels = order_page.LABELS[lang]
    assert f'<html lang="{lang}"' in page
    # Scoped to the facts list. The Hindi word for "amount" is a prefix of the Hindi word for "rashifal",
    # which is in the navigation of every page - a whole-page search for it passes on the wrong text.
    facts = page.split('class="facts order__facts"', 1)[1].split("</dl>", 1)[0]
    for text in (labels["price_before_tax"], labels["gst"].replace("{rate}", "18"), labels["total"]):
        assert text in facts, (lang, text)
    for amount in (gst.money(base), gst.money(tax), gst.money(total)):
        assert f"₹{amount}" in facts, (lang, amount)
    # the single "Amount" row belongs to untaxed orders only: showing both would print the charge twice
    assert labels["amount"] not in facts or labels["amount"] == labels["total"]
    assert labels["invoice"] in page and view["invoice_url"] in page


def test_the_gst_labels_exist_in_every_language_and_are_each_their_own():
    """The order page's labels and pay.js's dictionaries both have to carry the new keys in all three
    languages - a missing key renders an empty <dt> on a page about money."""
    for key in ("price_before_tax", "gst", "total", "invoice"):
        for lang in i18n.LANGS:
            assert order_page.LABELS[lang][key].strip(), (lang, key)
    assert "{rate}" in order_page.LABELS["en"]["gst"], "the rate is substituted, never written into a label"
    # Hindi and Marathi say it in their own words rather than in each other's
    assert order_page.LABELS["hi"]["total"] != order_page.LABELS["mr"]["total"]
    assert order_page.LABELS["en"]["price_before_tax"] not in order_page.LABELS["hi"]["price_before_tax"]


def test_every_buy_button_carries_the_charge_and_every_page_says_gst_is_added():
    """The invariant that keeps pay.js honest: it reads these attributes and shows them, so if the server
    stops rendering them the panel quietly shows the pre-tax price as the amount to pay.

    `data-price-inr` remains the LISTED price, because that is what the button's own label quotes and what
    tests/test_pages_i18n.py checks the copy against."""
    client = TestClient(app)
    checked = 0
    for lang in i18n.LANGS:
        for key in (*i18n.TOOL_KEYS, "consultation"):
            if lang not in i18n.page_langs(key):
                continue
            html = client.get(i18n.url_for(key, lang)).text
            buttons = re.findall(r"<button[^>]*data-product=\"([^\"]+)\"[^>]*?>", html, re.S)
            offered = [option["product"] for option in pages.purchase_options(key)]
            assert buttons == offered, (lang, key)
            for option in pages.purchase_options(key):
                entry = catalogue.item(option["product"])
                # data-base-inr is asserted because NOT asserting it is how a bug shipped: pay.js inferred the
                # taxable value from data-price-inr, which is the same number only while GST is added on top,
                # so under inclusive pricing the panel printed "₹249 + ₹37.98 GST = ₹249". The attribute is
                # what makes the base a fact from the server rather than a guess in the browser.
                pattern = (rf'data-product="{re.escape(option["product"])}"[^>]*'
                           rf'data-price-inr="{entry.price_inr}"[^>]*'
                           rf'data-base-inr="{re.escape(gst.money(entry.gst.base_paise))}"[^>]*'
                           rf'data-gst-inr="{re.escape(gst.money(entry.gst.gst_paise))}"[^>]*'
                           rf'data-total-inr="{re.escape(gst.money(entry.gst.total_paise))}"[^>]*'
                           rf'data-gst-rate="18"')
                assert re.search(pattern, html, re.S), (lang, key, option["product"])
                checked += 1
            # and the reader is told, in their own language, beside the button
            assert pages.ui(lang)["gst_note"] in html, (lang, key)
            assert "{gst_rate}" not in html, (lang, key)
    assert checked >= 12, f"only {checked} buttons checked - is the page list right?"


def test_the_gst_note_has_one_true_sentence_per_mode_in_every_language(monkeypatch):
    """A rate is a setting, like a price, so the note carries {gst_rate} and never a typed number.

    And the MODE is a setting too, which is the part that was missed: one sentence saying "prices are exclusive
    of GST" became a false statement about price, printed beside the price, in three languages, the moment the
    flag it describes was flipped - and the flag exists to be flipped. So each module carries one sentence per
    mode and pages.ui() resolves exactly one of them."""
    for lang in i18n.LANGS:
        for key in ("gst_note_exclusive", "gst_note_inclusive"):
            raw = pages.content(lang).UI[key]
            assert "{gst_rate}" in raw, (lang, key)
            assert not re.search(r"\d", raw.replace("{gst_rate}", "")), (lang, key, "no number belongs here")
        assert "gst_note" not in pages.content(lang).UI, (
            f"{lang}: the unresolved variants are the copy; a bare `gst_note` would be a third thing to keep in step")
        # the templates see exactly one key, and which one follows the setting rather than the template
        resolved = pages.ui(lang)
        assert resolved["gst_note"] == pages.ui(lang)["gst_note"]
        assert "gst_note_exclusive" not in resolved and "gst_note_inclusive" not in resolved, lang
    assert pages.common_values("en")["gst_rate"] == gst.get_settings().rate_text

    words = {"inclusive": "include", "exclusive": "exclusive"}
    for flag, expected in (("1", "inclusive"), ("0", "exclusive")):
        monkeypatch.setenv("GST_INCLUSIVE", flag)
        note = pages.ui("en")["gst_note"]
        assert words[expected] in note.lower(), (flag, note)
        assert words["inclusive" if expected == "exclusive" else "exclusive"] not in note.lower(), (flag, note)


def test_pay_js_prints_the_total_it_is_handed_and_computes_no_tax(js):
    """pay.js must read the charge off the button and never multiply anything by a rate."""
    source = (STATIC_DIR / "js" / "pay.js").read_text(encoding="utf-8")
    assert "{total}" in source and "{price}" not in source, \
        "the Pay button quotes the TOTAL: a button that says the list price opens a window asking for more"
    for suspicious in ("1.18", "0.18", "* 18", "/ 100 * ", "rate / 100"):
        assert suspicious not in source, f"pay.js looks like it is computing tax: {suspicious!r}"

    def read(attrs, detail=None):
        return js("AstroPay.charge({getAttribute: function (n) { return attrs[n] === undefined ? null : attrs[n]; }}, detail)",
                  attrs=attrs, detail=detail or {})

    assert read({"data-price-inr": "249", "data-gst-inr": "44.82", "data-total-inr": "293.82", "data-gst-rate": "18"}) == \
        {"base": 249, "gst": 44.82, "total": 293.82, "rate": "18"}
    # No tax attributes: the server is not charging GST, so the listed price IS the charge. This is the only
    # fallback, and it is a fallback to the server's own number rather than to arithmetic.
    assert read({"data-price-inr": "249"}) == {"base": 249, "gst": 0, "total": 249, "rate": None}
    assert read({"data-price-inr": "249", "data-gst-inr": "0", "data-total-inr": "249", "data-gst-rate": "0"}) == \
        {"base": 249, "gst": 0, "total": 249, "rate": None}
    # and a button with nothing on it falls back to the event detail rather than printing "undefined"
    assert read({}, {"priceInr": 99}) == {"base": 99, "gst": 0, "total": 99, "rate": None}

    # The taxable value comes from its own attribute. Reading it off data-price-inr is only right while GST is
    # added on top; under inclusive pricing the listed price IS the total, and that mistake printed three
    # numbers that do not add up on the panel where the customer decides to pay.
    inclusive = {"data-price-inr": "299", "data-base-inr": "253.39", "data-gst-inr": "45.61",
                 "data-total-inr": "299", "data-gst-rate": "18"}
    assert read(inclusive) == {"base": 253.39, "gst": 45.61, "total": 299, "rate": "18"}

    def shown(attrs):
        return js("AstroPay.chargeText({getAttribute: function (n) { return attrs[n] === undefined ? null : attrs[n]; }},"
                  " AstroPay.charge({getAttribute: function (n) { return attrs[n] === undefined ? null : attrs[n]; }}, {}))",
                  attrs=attrs)

    # DISPLAY comes from the server's strings, never from the parsed number: Number("83.90") prints as "83.9",
    # and a ₹99 product under inclusive pricing showed a taxable value of "₹83.9" - a rupee amount with one
    # decimal place, which no bank statement has ever shown. Money is formatted once, by gst.money().
    assert shown({"data-price-inr": "99", "data-base-inr": "83.90", "data-gst-inr": "15.10",
                  "data-total-inr": "99", "data-gst-rate": "18"}) == {"base": "83.90", "gst": "15.10", "total": "99"}
    assert gst.money(8390) == "83.90" and gst.money(1510) == "15.10", "the server is the one that formats money"
    # with no attributes at all the strings fall back to the numbers, so nothing renders as "undefined"
    assert shown({"data-price-inr": "249"}) == {"base": "249", "gst": "0", "total": "249"}

    for lang in i18n.LANGS:
        labels = js("AstroPay.textFor(lang)", lang=lang)
        for key in ("priceLabel", "gstLabel", "totalLabel"):
            assert labels[key].strip(), (lang, key)
        assert "{rate}" in labels["gstLabel"] and "{total}" in labels["pay"], lang


def test_the_config_endpoint_publishes_the_rate_and_the_charge_without_changing_the_price_list():
    """`prices_inr` is read by existing callers as the LISTED price and must not quietly become the total."""
    client = TestClient(app)
    config = client.get("/api/payments/config").json()
    assert config["prices_inr"] == catalogue.prices_inr()
    assert config["prices_inr"]["kundali-report"] == catalogue.item("kundali-report").price_inr
    assert config["gst"]["rate"] == "18" and config["gst"]["inclusive"] is True
    assert config["gst"]["charged_paise"] == {p: charge(p)[2] for p in catalogue.prices_inr()}
    for product in catalogue.prices_inr():
        base, tax, total = charge(product)
        assert config["gst"]["amounts_inr"][product] == {"base": base / 100, "gst": tax / 100, "total": total / 100}
