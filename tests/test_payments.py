"""Phase 6: Razorpay payments. No network: Razorpay's API is an httpx.MockTransport, background jobs are captured."""

import base64
import datetime as dt
import hashlib
import hmac
import importlib.util
import json
import time
import logging
import re
import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app import db
from app.ai import chat, chat_store, entitlement
from app.ai import report as report_module
from app.ai.client import AIUnavailable
from app.main import app
from app.payments import catalogue, first_sale, gst, order_page, razorpay, routes, service, states, store
from app.pdf import service as pdf_service
from tests import reference_charts
from app.web import STATIC_DIR, site

ROOT = Path(__file__).resolve().parents[1]
KEY_ID, KEY_SECRET, WEBHOOK_SECRET = "rzp_test_UnitTestKey01", "unit-test-key-secret-Zx81", "unit-test-webhook-secret-Qp55"
# Published charts (tests/reference_charts.py), never anyone's private data. These tests are about the
# payment plumbing, so any valid birth would do - but using the reference ones keeps a single source.
MIRAJ = reference_charts.PRIMARY.request()
PUNE = reference_charts.NEHRU.request()
FIXTURE = json.loads((ROOT / "tests/fixtures/kundali_book_mr.json").read_text(encoding="utf-8"))
FIXTURE_DAY = reference_charts.AS_OF.date()  # the fixture's as_of: orders created "today" get its report id
# The id recipe belongs to app/ai (CACHE_VERSION bumps change it): always stamp the fixture with the CURRENT id for
# these birth details, so the payment tests do not depend on when tests/fixtures was last rebuilt.
_REQUEST = reference_charts.PRIMARY.request()
FIXTURE["id"] = report_module.report_id("kundali-report", "mr", [report_module.Birth(
    dt.date.fromisoformat(_REQUEST["date"]), dt.time.fromisoformat(_REQUEST["time"]),
    _REQUEST["lat"], _REQUEST["lon"], _REQUEST["timezone"], None)], FIXTURE_DAY)
# Launch prices, 2026-09-22 (app/payments/catalogue.py): simple report ₹49, detailed book ₹249, matching ₹99,
# consultation Basic ₹99 (+ the simple report), Premium ₹299 (+ the book). The bundle tests below buy PREMIUM,
# because the report FIXTURE they check against is the detailed one.
#
# Those prices are GST-EXCLUSIVE (owner's decision, 2026-09-28): 18% is added on top, so what is CHARGED is
# the total - and that is the role these constants play in every assertion below. They are what Razorpay is
# asked for, what `amount_paise` holds, and what a webhook has to carry to be accepted. The LISTED prices are
# asserted as themselves in test_catalogue_is_the_price_list_and_the_pages_agree_with_it, and the tax
# arithmetic itself lives in tests/test_gst.py.
# WHAT IS CHARGED, which under GST-inclusive pricing is the listed price itself - see app/payments/gst.py.
# These moved twice in one day and the second move is the instructive one: they were first the pre-tax prices,
# then the pre-tax price plus 18%, and now the listed price again, because the MODE changed rather than the
# arithmetic. A constant that happens to equal the right number for the wrong reason is the thing to avoid
# here, so each is stated as the charge and the listed price it comes from is named beside it.
# The place of supply every order body here carries. REQUIRED on POST /api/payments/order since 2026-09-28: it
# decides whether the tax is CGST+SGST or IGST, and nothing can derive it. The seller's own state, so these
# orders exercise the intra-state split; tests/test_gst.py covers the inter-state one.
PLACE = states.seller_code()
SIMPLE_PAISE, KUNDALI_PAISE, MATCHING_PAISE = 5900, 29900, 11900   # ₹59, ₹299, ₹119 - GST INCLUDED
BASIC_PAISE, PACK_PAISE = 11900, 34900                             # ₹119, ₹349 - GST INCLUDED


class FakeRazorpay:
    """Just enough of api.razorpay.com: create order, list an order's payments. Records what it was sent."""

    def __init__(self):
        self.requests, self.payments, self.down = [], {}, False

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("razorpay is down", request=request)
        expected = "Basic " + base64.b64encode(f"{KEY_ID}:{KEY_SECRET}".encode()).decode()
        if request.headers.get("authorization") != expected:
            return httpx.Response(401, json={"error": {"code": "BAD_REQUEST_ERROR", "description": "Authentication failed"}})
        if request.method == "POST" and request.url.path == "/v1/orders":
            body = json.loads(request.content)
            self.requests.append(body)
            return httpx.Response(200, json={"id": f"order_Fake{len(self.requests):010d}", "entity": "order", "amount": body["amount"],
                                             "amount_paid": 0, "amount_due": body["amount"], "currency": body["currency"],
                                             "receipt": body["receipt"], "status": "created", "attempts": 0, "notes": body["notes"]})
        match = re.fullmatch(r"/v1/orders/(order_\w+)/payments", request.url.path)
        if request.method == "GET" and match:
            items = self.payments.get(match.group(1), [])
            return httpx.Response(200, json={"entity": "collection", "count": len(items), "items": items})
        return httpx.Response(404, json={"error": {"code": "BAD_REQUEST_ERROR", "description": "not found"}})


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("PDFS_DIR", str(tmp_path / "pdfs"))
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret")
    monkeypatch.delenv("REPORTS_UNLOCKED", raising=False)
    monkeypatch.setattr(service, "today_ist", lambda: FIXTURE_DAY)
    monkeypatch.setattr(pdf_service, "render_book", lambda build_html, **kw: b"%PDF-1.7 fake")
    monkeypatch.setenv("FIRST_SALE_MARKER", str(tmp_path / "first_live_sale.json"))
    monkeypatch.setattr(routes, "ORDERS_PER_HOUR_PER_USER", 1000)
    monkeypatch.setattr(routes, "ORDERS_PER_HOUR_PER_IP", 1000)
    # Safety net: a real ANTHROPIC_API_KEY may be in the developer's .env. No test may ever start a real report job
    # or reach the real generator; tests that need a job use the `jobs` fixture and install their own fake generator.
    monkeypatch.setattr(service, "_spawn", _JOBS.capture)
    monkeypatch.setattr(service, "generate_report", _no_real_ai)
    _JOBS.clear()


def _no_real_ai(*args, **kwargs):
    raise AssertionError("a test reached the real report generator")


class _Jobs(list):
    """Background report jobs are collected instead of started; run them with jobs.run().

    The order-link e-mail is spawned the same way, on every newly-paid order, and it is NOT a report
    job: the many `jobs == []` assertions here mean "no report is being generated", which is a different
    claim and stayed true when e-mail arrived. So the e-mail lands in `emails` instead, where
    `test_the_order_link_email_is_sent_once_per_paid_order` reads it."""

    def __init__(self):
        super().__init__()
        self.emails = []

    def capture(self, function, *args):
        (self.emails if function.__name__ == "_email_order_link" else self).append((function, args))

    def clear(self):
        super().clear()
        self.emails.clear()

    def run(self):
        while self:
            function, args = self.pop(0)
            function(*args)

    def run_emails(self):
        while self.emails:
            function, args = self.emails.pop(0)
            function(*args)


_JOBS = _Jobs()


@pytest.fixture
def rzp(monkeypatch):
    """Payments configured, Razorpay faked."""
    fake = FakeRazorpay()
    monkeypatch.setenv("RAZORPAY_KEY_ID", KEY_ID)
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", KEY_SECRET)
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", WEBHOOK_SECRET)
    monkeypatch.setattr(razorpay, "_transport", httpx.MockTransport(fake))
    return fake


@pytest.fixture
def jobs():
    """The queue of captured background jobs (capturing itself is always on - see `isolated`)."""
    return _JOBS


def sign(order_id: str, payment_id: str, secret: str = KEY_SECRET) -> str:
    return hmac.new(secret.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()


def verify_body(order_id: str, payment_id: str = "pay_Test0000000001", **kw) -> dict:
    return {"razorpay_order_id": order_id, "razorpay_payment_id": payment_id,
            "razorpay_signature": kw.get("signature") or sign(order_id, payment_id)}


def webhook(client, event: str, order_id: str, payment_id: str = "pay_Test0000000001", amount: int = KUNDALI_PAISE, *,
            secret: str = WEBHOOK_SECRET, event_id: str | None = "evt_1", raw: bytes | None = None, signature: str | None = None):
    payload = {"entity": "event", "account_id": "acc_Test", "event": event, "contains": ["payment"], "created_at": 1790000000,
               "payload": {"payment": {"entity": {"id": payment_id, "entity": "payment", "amount": amount, "currency": "INR",
                                                  "status": "captured", "order_id": order_id, "captured": True,
                                                  "error_description": "Payment failed at bank", "email": "x@example.com"}}}}
    body = raw if raw is not None else json.dumps(payload, separators=(",", ":")).encode()
    headers = {"Content-Type": "application/json",
               "X-Razorpay-Signature": signature if signature is not None else hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()}
    if event_id:
        headers["X-Razorpay-Event-Id"] = event_id
    return client.post("/api/payments/webhook", content=body, headers=headers)


def report_order(client, **extra) -> dict:
    response = client.post("/api/payments/order", json={"email": "buyer@example.com", "place_of_supply": PLACE, "product": "kundali-report", "language": "mr", "birth": MIRAJ,
                                                        "name": "केशव", **extra})
    assert response.status_code == 200, response.text
    return response.json()


def cache_fixture_report() -> str:
    report_module._save_report(json.loads(json.dumps(FIXTURE)))
    return FIXTURE["id"]


def start_session(client) -> str:
    started = client.post("/api/consultation/start", json={**MIRAJ, "language": "en"})
    assert started.status_code == 200, started.text
    return started.json()["session_id"]


def paid_balance(session_id: str) -> int:
    user_id = chat_store.get_session(session_id)["user_id"]
    with db.transaction(write=False) as conn:
        return conn.execute("SELECT paid_balance FROM chat_users WHERE user_id = ?", (user_id,)).fetchone()["paid_balance"]


# ---- catalogue: one price list -----------------------------------------------------------------------


def test_catalogue_is_the_price_list_and_the_pages_agree_with_it():
    prices = {entry.product: entry.price_inr for entry in catalogue.all_items()}
    assert prices == catalogue.prices_inr() == {
        "kundali-report-simple": 59, "kundali-report": 299, "matching-report": 119,
        "mangal-dosha-remedy": 59, "sade-sati-guide": 59,
        "consultation-basic": 119, "consultation-premium": 349}
    assert catalogue.item("free-lunch") is None
    # Under GST-inclusive pricing the listed price IS the charge, so these two are the same number - and that
    # is the point worth pinning rather than the number: the taxable value is the one that is now different.
    assert catalogue.item("kundali-report").amount_paise == KUNDALI_PAISE == 299 * 100
    assert catalogue.item("kundali-report-simple").amount_paise == SIMPLE_PAISE
    # `Item.base_paise` is the LISTED price despite its name (see its docstring); the TAXABLE value, which is
    # what net revenue is made of, is `Item.gst.base_paise` - 18% smaller, and the distinction the exclusive
    # mode never forced anyone to make, because there the two were the same figure.
    item = catalogue.item("kundali-report")
    assert item.base_paise == 29900 == item.price_inr * 100 == item.amount_paise
    assert item.gst.base_paise == 25339 and item.gst.gst_paise == 4561
    assert item.gst.base_paise + item.gst.gst_paise == item.amount_paise
    assert not catalogue.pending_products(), "a priced product app/ai cannot generate is not for sale"


def test_each_consultation_tier_says_which_report_it_includes():
    """The tier machinery is one rule: a consultation order records the report it includes IN ITS PRODUCT ID,
    and an id's bundled report never changes. So an order can never drift from the tier that was paid for."""
    basic, premium = catalogue.item(catalogue.BASIC_PACK), catalogue.item(catalogue.PREMIUM_PACK)
    assert (basic.price_inr, basic.messages, basic.bundled_report) == (119, 10, "kundali-report-simple")
    assert (premium.price_inr, premium.messages, premium.bundled_report) == (349, 10, "kundali-report")
    assert "Kundali PDF" in basic.name and "book" in premium.name
    for entry in (basic, premium):
        assert entry.sold and catalogue.sellable(entry.product) == entry

    for product, expected in ((catalogue.BASIC_PACK, "kundali-report-simple"),
                              (catalogue.PREMIUM_PACK, "kundali-report"),
                              (catalogue.PACK, "kundali-report")):
        order = {"kind": "pack", "product": product, "report_id": "x"}
        assert catalogue.report_product(order) == expected
        assert catalogue.report_product({**order, "report_id": None}) is None
    # a report order entitles its buyer to itself, whatever the tiers do
    assert catalogue.report_product({"kind": "report", "product": "matching-report", "report_id": "x"}) == "matching-report"


def test_the_retired_consultation_id_is_honoured_but_cannot_be_bought(rzp):
    """`consultation-pack` was the single bundle before the tiers. Anyone who bought one keeps exactly what
    they paid for - ten questions and the DETAILED book - but the id is no longer on sale."""
    retired = catalogue.item(catalogue.PACK)
    assert retired is not None and retired.bundled_report == "kundali-report" == catalogue.PACK_REPORT
    assert retired.sold is False and catalogue.sellable(catalogue.PACK) is None
    assert catalogue.PACK not in catalogue.prices_inr()
    assert catalogue.PACK in order_page.PRODUCT_NAMES, "an old order page must still name its purchase"

    client = TestClient(app)
    refused = client.post("/api/payments/order", json={"email": "buyer@example.com", "place_of_supply": PLACE, "product": catalogue.PACK, "session_id": start_session(client)})
    assert refused.status_code == 422 and "consultation-pack" not in str(refused.json()).split("Literal")[-1][:200]


def test_the_chat_paywall_quotes_a_price_the_catalogue_charges():
    """The 402 the chat returns names a product and a price; the catalogue is what is actually charged."""
    paywall = chat.paywall()
    entry = catalogue.item(paywall["product"]) or catalogue.item(catalogue.BASIC_PACK)
    assert paywall["price_inr"] == entry.price_inr and paywall["messages"] == entry.messages == 10


def test_page_copy_takes_its_prices_from_the_catalogue():
    """Page config must read prices from app.payments.catalogue (never hard-code them), so copy cannot drift from the charge."""
    from app.web import pages

    if not hasattr(pages, "prices"):  # pre-restructure page config with literal prices
        pytest.skip("app.web.pages has no prices() yet")
    assert pages.prices() == catalogue.prices_inr()
    offer = pages.chat_offer()
    basic = catalogue.item(catalogue.BASIC_PACK)
    assert offer["price_inr"] == basic.price_inr == 119 and offer["pack_messages"] == 10 and offer["free_messages"] == 2
    assert pages.CONSULTATION_PRODUCT == catalogue.BASIC_PACK  # the page sells a tier, never the retired id
    assert catalogue.sellable(pages.CONSULTATION_PRODUCT) is not None
    for page_key, spec in pages.TOOLS.items():
        assert pages.product_price(page_key) == catalogue.item(spec.product).price_inr, page_key
    source = (ROOT / "app/web/pages.py").read_text(encoding="utf-8")
    assert not re.search(r"price_inr\s*=\s*\d", source), "a literal price in pages.py"


def test_amount_always_comes_from_the_server_catalogue(rzp, jobs):
    client = TestClient(app)
    created = report_order(client, amount=1, price_inr=1, priceInr=1, currency="USD")  # a client can say what it likes
    assert created["amount"] == KUNDALI_PAISE and created["currency"] == "INR" and created["key_id"] == KEY_ID
    assert rzp.requests[-1]["amount"] == KUNDALI_PAISE and rzp.requests[-1]["currency"] == "INR"
    assert len(rzp.requests[-1]["receipt"]) <= 40 and rzp.requests[-1]["notes"]["product"] == "kundali-report"
    assert "केशव" not in json.dumps(rzp.requests[-1], ensure_ascii=False)  # no personal data in Razorpay notes
    assert store.by_razorpay_id(created["order_id"])["amount_paise"] == KUNDALI_PAISE

    matching = client.post("/api/payments/order", json={"email": "buyer@example.com", "place_of_supply": PLACE, "product": "matching-report", "boy": MIRAJ, "girl": PUNE, "amount": 100})
    assert matching.json()["amount"] == MATCHING_PAISE and rzp.requests[-1]["amount"] == MATCHING_PAISE
    pack = client.post("/api/payments/order", json={"email": "buyer@example.com", "place_of_supply": PLACE, "product": "consultation-premium", "session_id": start_session(client), "amount": 100})
    assert pack.json()["amount"] == PACK_PAISE and rzp.requests[-1]["amount"] == PACK_PAISE


def test_order_request_validation(rzp):
    client = TestClient(app)
    for body in ({"product": "kundali-report"}, {"product": "matching-report", "birth": MIRAJ}, {"product": "consultation-premium"},
                 {"product": "gold-plan", "birth": MIRAJ}, {"product": "kundali-report", "birth": {"date": MIRAJ["date"], "time": MIRAJ["time"], "city": "Atlantis"}},
                 {"product": "kundali-report", "birth": MIRAJ, "email": "not-an-email"},
                 {"product": "kundali-report", "birth": MIRAJ, "phone": "12"}, {"product": "kundali-report", "birth": MIRAJ, "language": "fr"},
                 # place_of_supply: missing, not two digits, and two digits that are not a state GST accepts.
                 # 25 and 28 are RETIRED codes (25 merged into 26, 28 became 37), which is why "two digits" is
                 # not the whole check - an invoice cannot name a place of supply no return accepts.
                 {"product": "kundali-report", "birth": MIRAJ, "email": "buyer@example.com"},
                 {"product": "kundali-report", "birth": MIRAJ, "email": "buyer@example.com", "place_of_supply": "Maharashtra"},
                 {"product": "kundali-report", "birth": MIRAJ, "email": "buyer@example.com", "place_of_supply": "99"},
                 {"product": "kundali-report", "birth": MIRAJ, "email": "buyer@example.com", "place_of_supply": "25"},
                 {"product": "kundali-report", "birth": MIRAJ, "email": "buyer@example.com", "place_of_supply": "28"}):
        assert client.post("/api/payments/order", json=body).status_code == 422, body
    unknown = client.post("/api/payments/order", json={"email": "buyer@example.com", "place_of_supply": PLACE, "product": "consultation-premium", "session_id": "x" * 32})
    assert unknown.status_code == 404 and unknown.json()["detail"]["error"] == "session_not_found"
    assert rzp.requests == []  # nothing reached Razorpay


# ---- signatures ----------------------------------------------------------------------------------------


def test_payment_signature_accepts_the_right_triple_and_rejects_everything_else(rzp):
    order_id, payment_id = "order_ABC123", "pay_XYZ789"
    good = sign(order_id, payment_id)
    # independent check of the recipe: hex HMAC-SHA256(order_id + "|" + payment_id, key_secret)
    assert good == hmac.new(KEY_SECRET.encode(), b"order_ABC123|pay_XYZ789", hashlib.sha256).hexdigest()
    assert razorpay.verify_payment_signature(order_id, payment_id, good)
    assert razorpay.verify_payment_signature(order_id, payment_id, good.upper())
    for bad in (good[:-1] + ("0" if good[-1] != "0" else "1"), "", "0" * 64, sign(order_id, payment_id, "other-secret"),
                sign(payment_id, order_id), "सही" * 20):
        assert not razorpay.verify_payment_signature(order_id, payment_id, bad), bad
    assert not razorpay.verify_payment_signature("order_OTHER", payment_id, good)
    assert not razorpay.verify_payment_signature(order_id, "pay_OTHER", good)
    assert not razorpay.verify_payment_signature(order_id, payment_id, sign(order_id, payment_id, WEBHOOK_SECRET))


def test_no_secret_means_nothing_verifies(monkeypatch):
    assert not razorpay.configured() and not razorpay.webhook_configured()
    assert not razorpay.verify_payment_signature("order_A", "pay_B", hmac.new(b"", b"order_A|pay_B", hashlib.sha256).hexdigest())
    assert not razorpay.verify_webhook_signature(b"{}", hmac.new(b"", b"{}", hashlib.sha256).hexdigest())
    with pytest.raises(razorpay.PaymentsNotConfigured):
        razorpay.create_order(9900, "r1")


def test_forged_or_unpaid_orders_unlock_nothing(rzp, jobs):
    client = TestClient(app)
    rid = cache_fixture_report()
    created = report_order(client)
    assert client.get(f"/api/report/{rid}/pdf").status_code == 402  # an order alone is not a payment

    for body in (verify_body(created["order_id"], signature="0" * 64),
                 verify_body(created["order_id"], signature=sign(created["order_id"], "pay_Test0000000001", "guess")),
                 {**verify_body(created["order_id"]), "razorpay_payment_id": "pay_Another00000001"}):
        rejected = client.post("/api/payments/verify", json=body)
        assert rejected.status_code == 400 and rejected.json()["detail"]["error"] == "bad_signature"
    assert client.post("/api/payments/verify", json=verify_body("order_Nope0000000001")).status_code == 404
    order = store.by_razorpay_id(created["order_id"])
    assert order["status"] == "created" and order["fulfilment"] == "none" and order["payment_id"] is None
    assert client.get(f"/api/report/{rid}/pdf").status_code == 402 and client.get(f"/api/report/{rid}").status_code == 402
    assert client.get(f"/order/{order['token']}").status_code == 404  # no purchase page for an unpaid order
    status = client.get(f"/api/payments/order/{created['order_id']}").json()
    assert status["status"] == "created" and status["order_url"] is None and status["pdf_url"] is None and jobs == []


# ---- report: pay -> entitled -> PDF --------------------------------------------------------------------


def test_paid_report_unlocks_exactly_that_report_and_its_pdf(rzp, jobs):
    client = TestClient(app)
    rid = cache_fixture_report()
    other = json.loads(json.dumps(FIXTURE)); other["id"] = "f" * 32
    report_module._save_report(other)
    created = report_order(client)
    assert store.by_razorpay_id(created["order_id"])["report_id"] == rid  # computed before payment, as_of pinned + stored
    assert store.by_razorpay_id(created["order_id"])["as_of"] == FIXTURE_DAY.isoformat()

    paid = client.post("/api/payments/verify", json=verify_body(created["order_id"]))
    assert paid.status_code == 200, paid.text
    view = paid.json()
    assert view["status"] == "paid" and view["fulfilment"] == "ready" and jobs == []  # report was already in the cache
    assert view["order_url"].startswith("/order/") and f"/api/report/{rid}/pdf?" in view["pdf_url"] and "token=" in view["pdf_url"]

    pdf = client.get(view["pdf_url"])
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf" and pdf.content.startswith(b"%PDF")
    assert client.get(f"/api/report/{rid}/pdf").status_code == 200        # the buyer's cookie alone is enough too
    assert client.get(f"/api/report/{rid}").json()["id"] == rid
    assert client.get(f"/api/report/{'f' * 32}/pdf").status_code == 402     # some other report stays locked
    assert client.get(f"/api/report/{'f' * 32}/pdf?token={view['order_url'].split('/')[-1]}").status_code == 402


def test_purchase_survives_cookie_loss_through_the_order_token(rzp, jobs):
    buyer = TestClient(app)
    rid = cache_fixture_report()
    created = report_order(buyer)
    view = buyer.post("/api/payments/verify", json=verify_body(created["order_id"])).json()
    token = view["order_url"].rsplit("/", 1)[1]
    assert len(token) >= 32

    stranger = TestClient(app)  # no cookies: another device, or cookies cleared
    assert stranger.get(f"/api/report/{rid}/pdf").status_code == 402
    wrong = token[:-1] + ("x" if token[-1] != "x" else "y")  # (a fixed "x" would equal the real token 1 time in 64)
    assert stranger.get(f"/api/report/{rid}/pdf?token={wrong}").status_code == 402
    assert stranger.get(f"/api/report/{rid}/pdf?token={token}").status_code == 200
    assert stranger.get(f"/api/report/{rid}", headers={"X-Order-Token": token}).status_code == 200
    assert stranger.get(f"/api/payments/order/{created['order_id']}").status_code == 404   # status is not public
    assert stranger.get(f"/api/payments/order/{created['order_id']}?token={token}").json()["pdf_url"] == view["pdf_url"]

    page = stranger.get(view["order_url"])
    assert page.status_code == 200 and "noindex" in page.headers["x-robots-tag"] and page.headers["cache-control"] == "private, no-store"
    assert page.headers["referrer-policy"] == "no-referrer" and '<meta name="robots" content="noindex, nofollow">' in page.text
    # the page speaks the ORDER's language (this report was bought in Marathi): texts come from app.payments.order_page
    from app.payments import order_page
    assert '<html lang="mr"' in page.text and order_page.STATUS["mr"]["ready"][0] in page.text
    assert order_page.LABELS["mr"]["download"] in page.text and order_page.LABELS["mr"]["heading"] in page.text and 'data-poll="0"' in page.text
    assert view["pdf_url"].replace("&", "&amp;") in page.text
    assert f"₹{catalogue.item('kundali-report').price_inr}" in page.text
    assert order_page.LANGUAGE_NAMES["mr"]["mr"] in page.text and order_page.PRODUCT_NAMES["kundali-report"]["mr"] in page.text
    assert KEY_SECRET not in page.text
    assert stranger.get("/order/" + "A" * 32).status_code == 404 and stranger.get("/order/short").status_code == 404


def test_same_report_is_not_charged_twice_to_the_same_person(rzp, jobs):
    client = TestClient(app)
    cache_fixture_report()
    created = report_order(client)
    client.post("/api/payments/verify", json=verify_body(created["order_id"]))
    again = report_order(client)
    assert again["already_paid"] is True and again["status"] == "paid" and again["pdf_url"] and len(rzp.requests) == 1
    assert report_order(TestClient(app))["already_paid"] is False  # somebody else pays for their own copy


# ---- idempotency: verify + verify + webhook ------------------------------------------------------------


def start_marathi_session(client, name="केशव") -> str:
    started = client.post("/api/consultation/start", json={**MIRAJ, "language": "mr", "name": name})
    assert started.status_code == 200, started.text
    return started.json()["session_id"]


def fake_generator(calls: list):
    def generate(product, language, births, *, as_of):
        calls.append((product, language, as_of, births[0].city))
        report = json.loads(json.dumps(FIXTURE))
        report["id"] = report_module.report_id(product, language, births, as_of)
        report_module._save_report(report)
        return report

    return generate


def test_consultation_purchase_is_ten_questions_plus_the_kundali_pdf_exactly_once(rzp, jobs, monkeypatch):
    """The ₹299 Premium bundle: double verify + two webhooks + a duplicate = +10 once, ONE report job, one order page with both."""
    calls = []
    monkeypatch.setattr(service, "generate_report", fake_generator(calls))
    client = TestClient(app)
    session_id = start_marathi_session(client)
    created = client.post("/api/payments/order", json={"email": "buyer@example.com", "place_of_supply": PLACE, "product": "consultation-premium", "session_id": session_id, "amount": 1}).json()
    assert created["amount"] == PACK_PAISE and rzp.requests[-1]["amount"] == PACK_PAISE
    assert created["description"] == catalogue.item(catalogue.PREMIUM_PACK).name  # what Razorpay Checkout shows
    order = store.by_razorpay_id(created["order_id"])
    # the consultation's own birth details, language and name reach the order; the report is pinned before payment
    assert order["report_id"] == FIXTURE["id"] and order["language"] == "mr" and order["as_of"] == FIXTURE_DAY.isoformat()
    assert order["request"]["births"][0]["city"] == MIRAJ.get("city") and order["names"] == {"self": "केशव"}
    assert order["request"]["births"][0]["date"] == MIRAJ["date"] and order["messages"] == 10
    assert paid_balance(session_id) == 0 and client.get(f"/api/report/{FIXTURE['id']}/pdf").status_code in (402, 404)

    first = client.post("/api/payments/verify", json=verify_body(created["order_id"]))
    view = first.json()
    assert first.status_code == 200 and view["kind"] == "pack" and view["messages"] == 10 and view["includes_report"] is True
    assert view["fulfilment"] in ("pending", "generating") and view["pdf_url"] is None and view["order_url"]
    assert paid_balance(session_id) == 10  # questions are usable at once, before the report exists
    assert client.post("/api/payments/verify", json=verify_body(created["order_id"])).status_code == 200
    assert webhook(client, "payment.captured", created["order_id"], amount=PACK_PAISE, event_id="evt_a").json() == {"status": "ok"}
    assert webhook(client, "order.paid", created["order_id"], amount=PACK_PAISE, event_id="evt_b").json() == {"status": "ok"}
    assert webhook(client, "order.paid", created["order_id"], amount=PACK_PAISE, event_id="evt_b").json() == {"status": "duplicate"}
    client.get(f"/api/payments/order/{created['order_id']}")
    jobs.run()
    # exactly one generation, of the KUNDALI report (the reference chart is given as coordinates, no city)
    assert calls == [("kundali-report", "mr", FIXTURE_DAY, MIRAJ.get("city"))]
    assert paid_balance(session_id) == 10                             # exactly +10
    assert client.get(f"/api/consultation/session/{session_id}").json()["quota"]["paid_left"] == 10

    done = client.get(f"/api/payments/order/{created['order_id']}").json()
    assert done["fulfilment"] == "ready" and f"/api/report/{FIXTURE['id']}/pdf?" in done["pdf_url"] and "name=%E0%A4%95" in done["pdf_url"]
    assert client.get(done["pdf_url"]).status_code == 200 and client.get(f"/api/report/{FIXTURE['id']}").json()["product"] == "kundali-report"
    stranger = TestClient(app)  # the bundle's report survives cookie loss like any purchased report
    assert stranger.get(f"/api/report/{FIXTURE['id']}/pdf").status_code == 402
    assert stranger.get(done["pdf_url"]).status_code == 200
    assert stranger.get(f"/api/report/{'f' * 32}/pdf?token={done['order_url'].rsplit('/', 1)[1]}").status_code in (402, 404)
    page = stranger.get(done["order_url"])
    assert page.status_code == 200 and 'id="order-status"' in page.text
    assert f"₹{catalogue.item(catalogue.PREMIUM_PACK).price_inr}" in page.text
    final = store.by_razorpay_id(created["order_id"])
    assert final["paid_via"] == "verify" and final["payment_id"] == "pay_Test0000000001" and final["attempts"] == 1


def test_bundle_and_single_report_never_charge_or_generate_the_same_report_twice(rzp, jobs, monkeypatch):
    calls = []
    monkeypatch.setattr(service, "generate_report", fake_generator(calls))
    client = TestClient(app)
    session_id = start_marathi_session(client)
    bundle = client.post("/api/payments/order", json={"email": "buyer@example.com", "place_of_supply": PLACE, "product": "consultation-premium", "session_id": session_id}).json()
    client.post("/api/payments/verify", json=verify_body(bundle["order_id"]))
    jobs.run()
    # the same person now presses "buy the detailed PDF" on the kundali page for the same details + language: already theirs
    again = report_order(client)
    assert again["already_paid"] is True and again["status"] == "paid" and again["pdf_url"] and len(rzp.requests) == 1
    assert client.get(again["pdf_url"]).status_code == 200
    assert report_order(client, language="en")["already_paid"] is False  # another language is another report

    # the other way round: the report first, the consultation later - the questions are charged, but the report
    # part points at the report they already own: no second generation, no second PDF
    other = TestClient(app)
    single = report_order(other, language="mr")
    other.post("/api/payments/verify", json=verify_body(single["order_id"], "pay_Single00000001"))
    jobs.run()
    assert len(calls) == 1  # cached from the first buyer: even a different buyer costs no second AI call
    sid = start_marathi_session(other)
    monkeypatch.setattr(service, "today_ist", lambda: FIXTURE_DAY + dt.timedelta(days=9))  # ... bought days later
    later = other.post("/api/payments/order", json={"email": "buyer@example.com", "place_of_supply": PLACE, "product": "consultation-premium", "session_id": sid}).json()
    assert later["already_paid"] is False and later["amount"] == PACK_PAISE
    assert store.by_razorpay_id(later["order_id"])["report_id"] == FIXTURE["id"]  # reuses the owned report, not a new dated one
    view = other.post("/api/payments/verify", json=verify_body(later["order_id"], "pay_Later000000001")).json()
    assert view["fulfilment"] == "ready" and view["pdf_url"] and jobs == [] and len(calls) == 1 and paid_balance(sid) == 10

    # a second consultation purchase by the same person: +10 again, still the one report
    more = other.post("/api/payments/order", json={"email": "buyer@example.com", "place_of_supply": PLACE, "product": "consultation-premium", "session_id": sid}).json()
    other.post("/api/payments/verify", json=verify_body(more["order_id"], "pay_More0000000001"))
    assert paid_balance(sid) == 20 and store.by_razorpay_id(more["order_id"])["report_id"] == FIXTURE["id"] and len(calls) == 1


def test_bundle_report_failure_keeps_the_questions_and_retries_the_report(rzp, jobs, monkeypatch):
    outcomes = [AIUnavailable("down"), "ok"]
    calls = []
    good = fake_generator(calls)

    def flaky(product, language, births, *, as_of):
        if isinstance(outcomes.pop(0), Exception):
            raise AIUnavailable("down")
        return good(product, language, births, as_of=as_of)

    monkeypatch.setattr(service, "generate_report", flaky)
    client = TestClient(app)
    session_id = start_marathi_session(client)
    created = client.post("/api/payments/order", json={"email": "buyer@example.com", "place_of_supply": PLACE, "product": "consultation-premium", "session_id": session_id}).json()
    client.post("/api/payments/verify", json=verify_body(created["order_id"]))
    jobs.run()
    order = store.by_razorpay_id(created["order_id"])
    assert (order["status"], order["fulfilment"], order["attempts"]) == ("paid", "failed", 1) and paid_balance(session_id) == 10
    view = client.get(f"/api/payments/order/{created['order_id']}").json()
    assert view["retrying"] is True and view["pdf_url"] is None and view["messages"] == 10
    with db.transaction() as conn:
        conn.execute("UPDATE orders SET next_retry_at = 0")
    client.get(f"/api/payments/order/{created['order_id']}")
    jobs.run()
    done = client.get(f"/api/payments/order/{created['order_id']}").json()
    assert done["fulfilment"] == "ready" and client.get(done["pdf_url"]).status_code == 200
    assert paid_balance(session_id) == 10 and len(calls) == 1  # the retry re-ran the report only - never the credit


def test_forged_bundle_payment_gives_neither_questions_nor_report(rzp, jobs):
    client = TestClient(app)
    session_id = start_session(client)  # an English session: the bundled report follows the consultation's language
    created = client.post("/api/payments/order", json={"email": "buyer@example.com", "place_of_supply": PLACE, "product": "consultation-premium", "session_id": session_id, "language": "mr"}).json()
    order = store.by_razorpay_id(created["order_id"])
    assert order["language"] == "en" and order["names"] == {}
    assert client.post("/api/payments/verify", json=verify_body(created["order_id"], signature="0" * 64)).status_code == 400
    assert webhook(client, "payment.captured", created["order_id"], amount=KUNDALI_PAISE).json() == {"status": "amount_mismatch"}
    assert paid_balance(session_id) == 0 and jobs == [] and store.by_razorpay_id(created["order_id"])["status"] == "created"
    assert client.get(f"/api/report/{order['report_id']}/pdf").status_code in (402, 404)


def test_double_verify_plus_webhook_is_one_report_job(rzp, jobs, monkeypatch):
    calls = []

    def fake_generate(product, language, births, *, as_of):
        calls.append((product, language, as_of, births[0].city))
        report_module._save_report(json.loads(json.dumps(FIXTURE)))
        return FIXTURE

    monkeypatch.setattr(service, "generate_report", fake_generate)
    client = TestClient(app)
    created = report_order(client)
    for _ in range(2):
        assert client.post("/api/payments/verify", json=verify_body(created["order_id"])).json()["fulfilment"] in ("pending", "generating")
    assert webhook(client, "payment.captured", created["order_id"]).json() == {"status": "ok"}
    client.get(f"/api/payments/order/{created['order_id']}")  # polls while pending may queue the job again ...
    assert len(jobs) >= 1
    jobs.run()                                                # ... but only one of them wins the claim
    assert calls == [("kundali-report", "mr", FIXTURE_DAY, MIRAJ.get("city"))]
    status = client.get(f"/api/payments/order/{created['order_id']}").json()
    assert status["fulfilment"] == "ready" and "name=%E0%A4%95" in status["pdf_url"]  # cover name travels with the link
    assert client.get(status["pdf_url"]).status_code == 200
    assert store.by_razorpay_id(created["order_id"])["attempts"] == 1


# ---- webhook ---------------------------------------------------------------------------------------------


def test_webhook_alone_fulfils_when_the_tab_was_closed(rzp, jobs):
    client = TestClient(app)
    rid = cache_fixture_report()
    created = report_order(client)
    assert webhook(client, "payment.captured", created["order_id"]).json() == {"status": "ok"}
    order = store.by_razorpay_id(created["order_id"])
    assert order["status"] == "paid" and order["paid_via"] == "webhook" and order["fulfilment"] == "ready"
    assert client.get(f"/api/report/{rid}/pdf").status_code == 200


def test_webhook_signature_is_over_the_raw_body(rzp, jobs):
    client = TestClient(app)
    created = report_order(client)
    oid = created["order_id"]
    assert webhook(client, "payment.captured", oid, signature="0" * 64).status_code == 400
    assert webhook(client, "payment.captured", oid, signature="").status_code == 400
    assert webhook(client, "payment.captured", oid, secret=KEY_SECRET).status_code == 400  # wrong secret
    # a body that parses to the same JSON but is not byte-identical to what was signed must fail
    body = json.dumps({"event": "payment.captured", "payload": {"payment": {"entity": {"id": "pay_1", "order_id": oid,
                                                                                         "amount": KUNDALI_PAISE, "currency": "INR"}}}})
    good = hmac.new(WEBHOOK_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
    assert webhook(client, "", oid, raw=body.replace(" ", "").encode(), signature=good).status_code == 400
    assert store.by_razorpay_id(oid)["status"] == "created"
    assert webhook(client, "", oid, raw=body.encode(), signature=good, event_id=None).json() == {"status": "ok"}
    assert store.by_razorpay_id(oid)["status"] == "paid"
    assert webhook(client, "", oid, raw=b"not json", signature=hmac.new(WEBHOOK_SECRET.encode(), b"not json", hashlib.sha256).hexdigest()).status_code == 400


def test_webhook_edge_cases(rzp, jobs, monkeypatch):
    client = TestClient(app)
    created = report_order(client)
    oid = created["order_id"]
    assert webhook(client, "payment.captured", "order_SomebodyElse01", event_id="e1").json() == {"status": "ignored"}
    assert webhook(client, "refund.created", oid, event_id="e2").json() == {"status": "ignored"}
    assert webhook(client, "payment.captured", oid, amount=100, event_id="e3").json() == {"status": "amount_mismatch"}
    assert store.by_razorpay_id(oid)["status"] == "created"
    assert webhook(client, "payment.failed", oid, event_id="e4").json() == {"status": "noted"}
    assert store.by_razorpay_id(oid)["status"] == "failed"
    assert webhook(client, "payment.captured", oid, event_id="e5").json() == {"status": "ok"}  # the retry succeeded
    assert store.by_razorpay_id(oid)["status"] == "paid"
    assert webhook(client, "payment.failed", oid, event_id="e6").json() == {"status": "noted"}
    assert store.by_razorpay_id(oid)["status"] == "paid"  # a late failure event never un-pays an order
    monkeypatch.delenv("RAZORPAY_WEBHOOK_SECRET")
    assert webhook(client, "payment.captured", oid, event_id="e7").status_code == 503


def test_every_webhook_event_leaves_exactly_one_line_in_the_journal(rzp, jobs, caplog):
    """A live refund arrived on 2026-09-29 and the journal said nothing about it, so it had to be confirmed
    from the database. The refund path did log - at WARNING, and only once it had something to record - while
    `ignored`, `duplicate` and `amount_mismatch` returned silently, which is the case where an operator most
    needs to know the event was received and what we decided.

    Every exit now goes through `_webhook_result`, so the line and the HTTP body cannot disagree. Asserted as
    exactly ONE line per event rather than "some line", because a handler that logs twice on one path and not
    at all on another reads, in a journal, as a missing event."""
    client = TestClient(app)
    created = report_order(client)
    oid = created["order_id"]
    ours = store.by_razorpay_id(oid)["id"]
    # (event, razorpay order id, event id, extra, status, the order id the line must name). The last two
    # share an event id: that is a Razorpay retry, and it must still leave a line saying it was seen.
    events = [("payment.captured", "order_SomebodyElse01", "evt-a", {}, "ignored", "-"),
              ("refund.created", oid, "evt-b", {}, "ignored", ours),
              ("payment.captured", oid, "evt-c", {"amount": 100}, "amount_mismatch", ours),
              ("payment.failed", oid, "evt-d", {}, "noted", ours),
              ("payment.captured", oid, "evt-e", {}, "ok", ours),
              ("payment.captured", oid, "evt-e", {}, "duplicate", "-")]
    for name, order_id, event_id, extra, expected, named in events:
        caplog.clear()
        with caplog.at_level(logging.INFO, logger="app.payments.routes"):
            assert webhook(client, name, order_id, event_id=event_id, **extra).json() == {"status": expected}
        # INFO only: the amount-mismatch path also logs an ERROR that begins "webhook ", and that line is a
        # separate promise (it says WHY we refused), not a second copy of this one.
        lines = [record.getMessage() for record in caplog.records
                 if record.levelno == logging.INFO and record.getMessage().startswith("webhook ")]
        assert lines == [f"webhook {name}: order {named} -> {expected}"], (name, expected, lines)
        assert "@" not in lines[0], "no e-mail address in the journal"


def test_a_refund_event_says_so_in_the_journal(rzp, jobs, caplog):
    client = TestClient(app)
    order = _a_paid_order(client)
    with caplog.at_level(logging.INFO, logger="app.payments.routes"):
        assert refund_webhook(client, order["id"], "rfnd_log", 2000).json() == {"status": "partial"}
    assert f"webhook refund.processed: order {order['id']} -> partial" in caplog.text
    assert "REFUND rfnd_log" in caplog.text        # the existing WARNING, with the amounts, is unchanged


def test_the_webhook_handler_has_no_silent_exit():
    """The guarantee above, proved from the source rather than by enumerating events: a `return {"status": ...}`
    anywhere in the handler would be an event that reaches Razorpay and never reaches the journal."""
    source = (Path(__file__).resolve().parents[1] / "app/payments/routes.py").read_text(encoding="utf-8")
    body = source[source.index("async def webhook("):source.index("async def _in_thread(")]
    assert 'return {"status"' not in body, "every exit must go through _webhook_result"
    assert body.count("_webhook_result(") >= 8


# ---- a paid order is never lost ---------------------------------------------------------------------------


def test_generation_failure_keeps_the_order_paid_and_retryable(rzp, jobs, monkeypatch, caplog):
    outcomes = [AIUnavailable("Claude is down"), RuntimeError("disk full"), "ok"]

    def flaky(product, language, births, *, as_of):
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        report_module._save_report(json.loads(json.dumps(FIXTURE)))
        return FIXTURE

    monkeypatch.setattr(service, "generate_report", flaky)
    client = TestClient(app)
    created = report_order(client)
    oid = created["order_id"]
    client.post("/api/payments/verify", json=verify_body(oid))
    with caplog.at_level(logging.ERROR):
        jobs.run()
    order = store.by_razorpay_id(oid)
    assert order["status"] == "paid" and order["fulfilment"] == "failed" and order["attempts"] == 1
    assert "AIUnavailable" in order["error"] and order["next_retry_at"] > order["updated_at"]
    assert any("PAID order" in record.message and "retry in 30s" in record.message for record in caplog.records)

    status = client.get(f"/api/payments/order/{oid}").json()
    assert status == {**status, "status": "paid", "fulfilment": "failed", "retrying": True, "pdf_url": None} and jobs == []  # not due yet
    from app.payments import order_page
    waiting = client.get(status["order_url"])  # a failed-but-retrying order reads as "preparing" to the customer, in the order's language
    assert waiting.status_code == 200 and order_page.STATUS["mr"]["preparing"][0] in waiting.text and 'data-poll="1"' in waiting.text

    def make_due():
        with db.transaction() as conn:
            conn.execute("UPDATE orders SET next_retry_at = 0 WHERE razorpay_order_id = ?", (oid,))

    make_due()
    client.get(f"/api/payments/order/{oid}")          # the customer's own poll restarts the job
    jobs.run()
    assert store.by_razorpay_id(oid)["attempts"] == 2 and store.by_razorpay_id(oid)["fulfilment"] == "failed"
    make_due()
    client.get(f"/order/{status['order_url'].rsplit('/', 1)[1]}")  # ... and so does opening the order page
    jobs.run()
    done = client.get(f"/api/payments/order/{oid}").json()
    assert done["fulfilment"] == "ready" and done["pdf_url"] and client.get(done["pdf_url"]).status_code == 200
    assert store.by_razorpay_id(oid)["attempts"] == 3 and store.by_razorpay_id(oid)["error"] is None


def test_retries_stop_automatically_but_the_admin_script_still_delivers(rzp, jobs, monkeypatch, capsys):
    monkeypatch.setattr(service, "generate_report", lambda *a, **kw: (_ for _ in ()).throw(AIUnavailable("down")))
    client = TestClient(app)
    created = report_order(client)
    oid = created["order_id"]
    client.post("/api/payments/verify", json=verify_body(oid))
    for _ in range(service.MAX_AUTO_ATTEMPTS + 3):
        with db.transaction() as conn:
            conn.execute("UPDATE orders SET next_retry_at = 0 WHERE razorpay_order_id = ?", (oid,))
        client.get(f"/api/payments/order/{oid}")
        jobs.run()
    order = store.by_razorpay_id(oid)
    assert order["attempts"] == service.MAX_AUTO_ATTEMPTS and order["status"] == "paid"
    view = client.get(f"/api/payments/order/{oid}").json()
    assert view["fulfilment"] == "failed" and view["retrying"] is False
    from app.payments import order_page
    assert order_page.STATUS["mr"]["delayed"][0] in client.get(view["order_url"]).text

    spec = importlib.util.spec_from_file_location("fulfil_order", ROOT / "scripts/fulfil_order.py")
    cli = importlib.util.module_from_spec(spec); spec.loader.exec_module(cli)
    assert cli.main(["--list"]) == 0 and order["id"] in capsys.readouterr().out
    assert cli.main([order["id"], "--run"]) == 1  # still failing: reported, not hidden

    def works(product, language, births, *, as_of):
        report_module._save_report(json.loads(json.dumps(FIXTURE)))
        return FIXTURE

    monkeypatch.setattr(service, "generate_report", works)
    assert cli.main([oid, "--run"]) == 0 and "fulfilment=ready" in capsys.readouterr().out
    assert client.get(f"/api/payments/order/{oid}").json()["fulfilment"] == "ready"
    assert cli.main(["--list"]) == 0 and "no paid order is waiting" in capsys.readouterr().out


def test_interrupted_job_is_picked_up_again_and_reconcile_finds_missed_payments(rzp, jobs, monkeypatch, capsys):
    client = TestClient(app)
    created = report_order(client)
    oid = created["order_id"]
    client.post("/api/payments/verify", json=verify_body(oid))
    jobs.clear()
    assert store.claim_fulfilment(store.by_razorpay_id(oid)["id"], lease_seconds=900) is not None  # a worker took it ... and died
    client.get(f"/api/payments/order/{oid}")
    assert jobs == []                                   # lease still valid: nobody else starts it
    with db.transaction() as conn:
        conn.execute("UPDATE orders SET lease_until = 1 WHERE razorpay_order_id = ?", (oid,))
    client.get(f"/api/payments/order/{oid}")
    assert len(jobs) == 1                               # lease expired: the next poll restarts it

    # an order we never heard about again (no verify, no webhook), but Razorpay has a captured payment for it
    cache_fixture_report()
    missed = report_order(TestClient(app))
    spec = importlib.util.spec_from_file_location("fulfil_order", ROOT / "scripts/fulfil_order.py")
    cli = importlib.util.module_from_spec(spec); spec.loader.exec_module(cli)
    rzp.payments[missed["order_id"]] = [{"id": "pay_failed1", "status": "failed", "amount": KUNDALI_PAISE, "currency": "INR"}]
    assert cli.main([missed["order_id"], "--reconcile"]) == 1 and store.by_razorpay_id(missed["order_id"])["status"] == "created"
    rzp.payments[missed["order_id"]].append({"id": "pay_Captured01", "status": "captured", "amount": KUNDALI_PAISE, "currency": "INR"})
    assert cli.main([missed["order_id"], "--reconcile"]) == 0
    order = store.by_razorpay_id(missed["order_id"])
    assert (order["status"], order["paid_via"], order["payment_id"], order["fulfilment"]) == ("paid", "reconcile", "pay_Captured01", "ready")


def test_restart_resumes_interrupted_paid_orders_and_big_webhooks_are_refused(rzp, jobs):
    client = TestClient(app)
    created = report_order(client)
    client.post("/api/payments/verify", json=verify_body(created["order_id"]))
    jobs.clear()                                      # the process died before the job ran
    with TestClient(app):                             # startup event
        pass
    assert len(jobs) == 1 and service.resume_unfinished() == 1
    huge = client.post("/api/payments/webhook", content=b"x" * (routes.MAX_WEBHOOK_BYTES + 1), headers={"X-Razorpay-Signature": "0" * 64})
    assert huge.status_code == 413


# ---- configuration, limits, outages -------------------------------------------------------------------------


def test_unconfigured_payments_are_a_clean_503_and_the_pages_keep_the_launching_soon_note():
    client = TestClient(app)
    config = client.get("/api/payments/config").json()
    assert config["enabled"] is False and config["key_id"] is None
    assert config["prices_inr"] == catalogue.prices_inr() and config["prices_inr"]["kundali-report"] == 299
    assert config["packs"] == [{"product": "consultation-basic", "price_inr": 119, "messages": 10,
                                "includes_report": "kundali-report-simple"},
                               {"product": "consultation-premium", "price_inr": 349, "messages": 10,
                                "includes_report": "kundali-report"}]
    assert config["pack"] == config["packs"][0]  # older callers still see one offer: the Basic tier
    for path, body in (("/api/payments/order", {"product": "kundali-report", "birth": MIRAJ,
                                                "email": "buyer@example.com", "place_of_supply": PLACE}),
                       ("/api/payments/verify", verify_body("order_Fake0000000001"))):
        response = client.post(path, json=body)
        assert response.status_code == 503 and response.json()["detail"]["error"] == "payments_not_configured"
    assert client.post("/api/payments/webhook", content=b"{}").status_code == 503
    for path in ("/janam-kundali", "/kundali-matching", "/consultation"):
        assert re.search(r'<script src="/static/js/pay\.js\?v=\w+" defer data-pay data-enabled="0">', client.get(path).text), path


def test_configured_pages_switch_pay_js_on_and_never_show_a_secret(rzp):
    client = TestClient(app)
    for path in ("/janam-kundali", "/sade-sati", "/consultation"):
        html = client.get(path).text
        assert 'data-pay data-enabled="1"' in html and KEY_SECRET not in html and WEBHOOK_SECRET not in html
    config = client.get("/api/payments/config").json()
    assert config["enabled"] is True and config["key_id"] == KEY_ID and config["test_mode"] is True
    assert KEY_SECRET not in json.dumps(config)


def test_secrets_never_reach_responses_or_logs(rzp, jobs, caplog):
    client = TestClient(app)
    cache_fixture_report()
    with caplog.at_level(logging.DEBUG):
        created = report_order(client, email="keshav@example.com", phone="9876543210")
        bad = client.post("/api/payments/verify", json=verify_body(created["order_id"], signature="0" * 64))
        good = client.post("/api/payments/verify", json=verify_body(created["order_id"]))
        webhook(client, "payment.captured", created["order_id"], signature="1" * 64)
        rzp.down = True
        outage = client.post("/api/payments/order", json={"email": "buyer@example.com", "place_of_supply": PLACE, "product": "sade-sati-guide", "birth": MIRAJ})
    seen = json.dumps([created, bad.json(), good.json(), outage.json()]) + caplog.text
    for secret in (KEY_SECRET, WEBHOOK_SECRET, "test-session-secret"):
        assert secret not in seen
    assert "keshav@example.com" not in caplog.text and "9876543210" not in caplog.text  # no contact details in logs
    assert created["prefill"] == {"name": "केशव", "email": "keshav@example.com", "contact": "9876543210"}
    # Pinned so a new field cannot arrive here unnoticed. The four GST fields are the charge broken up -
    # base, tax, total and the rate - which the page needs to show what it is about to charge; `amount` is
    # still the total, and nothing here is a secret. `merchant` is the configured site name, which Razorpay's
    # window shows as the merchant: it is public, it is already in every page's og:site_name, and it rides on
    # the order so pay.js does not have to read it from the DOM or carry the brand as a literal.
    assert set(created) == {"already_paid", "order_id", "amount", "currency", "key_id", "product", "description",
                            "merchant", "prefill", "base_inr", "gst_inr", "total_inr", "gst_rate"}
    assert created["merchant"] == site.SITE_NAME


def test_razorpay_outage_charges_nothing_and_stores_nothing(rzp):
    rzp.down = True
    response = TestClient(app).post("/api/payments/order", json={"email": "buyer@example.com", "place_of_supply": PLACE, "product": "kundali-report", "birth": MIRAJ})
    assert response.status_code == 503 and response.json()["detail"]["error"] == "payment_service_unavailable"
    assert "not been charged" in response.json()["detail"]["message"]
    with db.transaction(write=False) as conn:
        assert conn.execute("SELECT COUNT(*) AS n FROM orders").fetchone()["n"] == 0


def test_order_creation_is_rate_limited_per_user_and_per_network(rzp, monkeypatch):
    monkeypatch.setattr(routes, "ORDERS_PER_HOUR_PER_USER", 2)
    client = TestClient(app)
    assert [client.post("/api/payments/order", json={"email": "buyer@example.com", "place_of_supply": PLACE, "product": "sade-sati-guide", "birth": MIRAJ}).status_code for _ in range(3)] == [200, 200, 429]
    assert client.post("/api/payments/order", json={"email": "buyer@example.com", "place_of_supply": PLACE, "product": "sade-sati-guide", "birth": MIRAJ}).headers["retry-after"]
    assert TestClient(app).post("/api/payments/order", json={"email": "buyer@example.com", "place_of_supply": PLACE, "product": "sade-sati-guide", "birth": MIRAJ}).status_code == 200
    monkeypatch.setattr(routes, "ORDERS_PER_HOUR_PER_IP", 1)  # fresh cookies do not get around the per-network cap
    assert TestClient(app).post("/api/payments/order", json={"email": "buyer@example.com", "place_of_supply": PLACE, "product": "sade-sati-guide", "birth": MIRAJ}).status_code == 429
    assert len(rzp.requests) == 3


def test_uid_cookie_is_httponly_and_samesite_lax(rzp):
    response = TestClient(app).post("/api/payments/order", json={"email": "buyer@example.com", "place_of_supply": PLACE, "product": "sade-sati-guide", "birth": MIRAJ})
    cookie = response.headers["set-cookie"].lower()
    assert cookie.startswith("uid=") and "httponly" in cookie and "samesite=lax" in cookie


def test_dev_unlock_switch_warns_loudly_outside_localhost(monkeypatch, caplog):
    monkeypatch.setattr(entitlement, "_warned", False)
    monkeypatch.setenv("REPORTS_UNLOCKED", "1")
    monkeypatch.setenv("BASE_URL", "http://localhost:8000")
    assert entitlement.warn_if_unlocked_in_production() is False
    monkeypatch.setenv("BASE_URL", "https://kundali.example.com")
    with caplog.at_level(logging.CRITICAL):
        assert entitlement.warn_if_unlocked_in_production() is True
    assert "REPORTS_UNLOCKED=1" in caplog.text and "kundali.example.com" in caplog.text
    monkeypatch.setenv("REPORTS_UNLOCKED", "0")
    assert entitlement.warn_if_unlocked_in_production() is False


# ---- pay.js (pure part, in V8) and the one permitted external URL ------------------------------------------


@pytest.fixture(scope="module")
def js():
    mini_racer = pytest.importorskip("py_mini_racer")
    ctx = mini_racer.MiniRacer()
    ctx.eval((STATIC_DIR / "js" / "pay.js").read_text(encoding="utf-8"))

    def call(expression: str, **variables):
        names = ", ".join(variables)
        args = ", ".join(json.dumps(value, ensure_ascii=False) for value in variables.values())
        return json.loads(ctx.eval(f"JSON.stringify((function({names}) {{ return {expression}; }})({args}))"))

    return call


def test_pay_js_builds_order_bodies_the_api_accepts_and_never_an_amount(js, rzp, jobs):
    single = {"product": "kundali-report", "priceInr": 1, "endpoint": "/api/chart", "request": MIRAJ, "name": "Keshav", "sessionId": None}
    body = js("AstroPay.orderBody(detail, form)", detail=single,
              form={"language": "mr", "email": " k@example.com ", "phone": "98765 43210", "state": PLACE})
    assert body == {"product": "kundali-report", "language": "mr", "birth": MIRAJ, "name": "Keshav",
                    "email": "k@example.com", "phone": "9876543210", "place_of_supply": PLACE}
    pair = {"product": "matching-report", "priceInr": 1, "request": {"boy": MIRAJ, "girl": PUNE}, "name": {"boy": "Keshav", "girl": ""}}
    pair_body = js("AstroPay.orderBody(detail, form)", detail=pair,
                   form={"language": "hi", "email": "k@example.com", "emailConfirm": "k@example.com", "state": PLACE})
    assert pair_body == {"product": "matching-report", "language": "hi", "boy": MIRAJ, "girl": PUNE,
                         "boy_name": "Keshav", "email": "k@example.com", "place_of_supply": PLACE}
    client = TestClient(app)
    pack_body = js("AstroPay.orderBody(detail, form)",
                   detail={"product": "consultation-premium", "priceInr": 1, "sessionId": start_session(client)},
                   form={"email": "k@example.com", "emailConfirm": "k@example.com", "state": PLACE})
    # THE CONSULTATION BODY IS THE ONE THAT MATTERS HERE. `place_of_supply` is set before orderBody's
    # consultation early-return, exactly as `email` now is - a required field added after that return is a field
    # the paywall silently never sends, which refused every consultation purchase for two days in September.
    assert set(pack_body) == {"product", "session_id", "email", "place_of_supply"}
    assert pack_body["place_of_supply"] == PLACE
    for payload, amount in ((body, KUNDALI_PAISE), (pair_body, MATCHING_PAISE), (pack_body, PACK_PAISE)):
        assert "amount" not in payload and "priceInr" not in payload
        assert client.post("/api/payments/order", json=payload).json()["amount"] == amount

    # E-mail is required and confirmed from 2026-09-26. The address is where the permanent order link
    # goes, so the buyer who skipped it was the one who could not be helped after closing the tab; and a
    # typo does not merely lose a receipt, because that link opens the order.
    # The state is reported LAST, so a wrong address is still reported as a wrong address: the contact fields are
    # what the customer was thinking about, and a tax field jumping the queue changes which problem they fix first.
    assert [e["field"] for e in js("AstroPay.validateForm(form)", form={"email": "", "phone": ""})] == ["email", "state"]
    assert [e["field"] for e in js("AstroPay.validateForm(form)", form={"email": "nope", "phone": "123"})] == ["email", "phone", "state"]
    assert [e["field"] for e in js("AstroPay.validateForm(form)",
                                   form={"email": "k@example.com", "emailConfirm": "k@example.com"})] == ["state"]
    mismatch = js("AstroPay.validateForm(form)", form={"email": "k@example.com", "emailConfirm": "j@example.com", "state": PLACE})
    assert [e["field"] for e in mismatch] == ["emailConfirm"] and mismatch[0]["message"]
    # the confirmation is case-insensitive: addresses are, and re-typing is not a spelling test
    assert js("AstroPay.validateForm(form)", form={"email": "K@Example.com", "emailConfirm": "k@example.com", "state": PLACE}) == []
    assert js("AstroPay.validateForm(form)", form={"email": " k@example.com ", "emailConfirm": "k@example.com", "state": PLACE}) == []


def test_the_order_link_email_is_sent_once_per_paid_order(rzp, jobs, monkeypatch):
    """The one e-mail this app sends. It carries the permanent order link, in the order's language.

    Once per order: checkout-verify and the webhook both reach `confirm_payment`, and only the first
    one is `newly_paid`. Off the payment path, because it is a call to a third party on the request
    that answers a payment. And harmless when it fails - the order page is reachable without it, which
    is what lets this swallow every error instead of retrying.
    """
    from app import mailer
    from app.payments import order_email

    client = TestClient(app)
    cache_fixture_report()
    created = report_order(client)                      # language "mr", e-mail buyer@example.com
    assert jobs.emails == []                            # nothing before payment
    assert client.post("/api/payments/verify", json=verify_body(created["order_id"])).status_code == 200
    assert len(jobs.emails) == 1

    # the webhook arrives for the same payment: still one e-mail, because only one confirm is newly paid
    client.post("/api/payments/webhook", json={"event": "payment.captured", "payload": {"payment": {"entity": {
        "order_id": created["order_id"], "id": "pay_Test0000000001", "amount": KUNDALI_PAISE, "currency": "INR"}}}},
        headers={"X-Razorpay-Signature": "whatever"})
    assert len(jobs.emails) == 1

    order = store.by_razorpay_id(created["order_id"])
    to, subject, body = order_email.compose(order)
    assert to == "buyer@example.com"
    assert "तुमच्या खरेदीचा दुवा" in subject              # the order's own language, not the browser's
    assert f"/order/{order['token']}" in body and body.startswith("तुमच्या खरेदीबद्दल धन्यवाद")
    assert order["razorpay_order_id"] in body           # the reference support will be quoted
    assert "http" in body.split(f"/order/{order['token']}")[0].rsplit("\n", 1)[-1]   # absolute, not a path

    # with no key it sends nothing, says so, and does not raise - the development mode
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.setenv("REPORT_EMAIL_ENABLED", "1")
    assert mailer.configured() is False and mailer.problems()
    assert mailer.send("buyer@example.com", "s", "b") is False
    assert order_email.send_order_link(order) is False

    # the switch alone stops it even when a key is present
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("EMAIL_FROM", "RashiKundli <orders@example.com>")
    assert mailer.configured() is True and mailer.problems() == []
    monkeypatch.delenv("REPORT_EMAIL_ENABLED")
    assert mailer.configured() is False and mailer.send("buyer@example.com", "s", "b") is False

    # an address that is missing, and a provider that explodes, both cost the order nothing
    assert order_email.send_order_link({**order, "email": None}) is False
    monkeypatch.setattr(order_email, "send_order_link", _boom)
    service._email_order_link(order)                    # must not raise


def _boom(*args, **kwargs):
    raise RuntimeError("provider on fire")


def test_the_order_link_email_reads_the_same_in_all_three_languages():
    from app.payments import order_email

    order = {"razorpay_order_id": "order_X", "product": "kundali-report", "kind": "report", "token": "t" * 32,
             "email": "buyer@example.com", "messages": 0, "amount_paise": KUNDALI_PAISE}
    for lang in ("en", "hi", "mr"):
        to, subject, body = order_email.compose({**order, "language": lang})
        assert to == "buyer@example.com" and subject and "{" not in subject
        assert "{" not in body, lang                     # every placeholder filled
        assert f"/order/{'t' * 32}" in body and "order_X" in body
    english = order_email.compose({**order, "language": "en"})[1]
    marathi = order_email.compose({**order, "language": "mr"})[1]
    assert english != marathi


def test_pay_js_checkout_options_and_status_text(js):
    # `merchant` rides on the ORDER, from site.SITE_NAME, rather than being read from the page or written into
    # pay.js - the brand name is configuration and the suite rejects it as a literal in source.
    order = {"order_id": "order_X", "amount": 9900, "currency": "INR", "key_id": KEY_ID, "description": "Detailed Janam Kundali Report",
             "merchant": site.SITE_NAME, "prefill": {"email": "k@example.com"}}
    options = js("(function(){ var o = AstroPay.checkoutOptions(order, {success: function(){}, dismiss: function(){}});"
                 " o.handlerType = typeof o.handler; o.dismissType = typeof o.modal.ondismiss; return o; })()", order=order)
    assert {k: options[k] for k in ("key", "amount", "currency", "name", "description", "order_id", "prefill")} == {
        "key": KEY_ID, "amount": 9900, "currency": "INR", "name": site.SITE_NAME, "description": order["description"],
        "order_id": "order_X", "prefill": {"email": "k@example.com"}}
    # From the server's order, not the page's og:site_name: a page shipped without that meta would otherwise
    # have put its <title> on the payment window.
    assert options["name"] == site.SITE_NAME
    # Square logo from our own static path. The URL is `location.origin + path` in a browser; this harness has
    # no `location`, so here it is the bare path - the ABSOLUTE form is asserted in the browser check, which is
    # the only place a real origin exists. Razorpay's script fetches this from outside our document, so a
    # relative path would resolve against THEIR page and show nothing.
    assert options["image"].endswith("/static/icons/icon-512.png")
    assert options["handlerType"] == options["dismissType"] == "function"

    def state(**view):
        return js("AstroPay.describe(view)", view=view)

    assert state(status="created")["state"] == "unpaid"
    assert state(status="paid", kind="pack", messages=10) == {**state(status="paid", kind="pack", messages=10), "state": "credited", "done": True}
    assert "10 questions" in state(status="paid", kind="pack", messages=10)["text"]
    assert state(status="paid", kind="report", fulfilment="pending")["state"] == "preparing"
    assert state(status="paid", kind="report", fulfilment="generating")["done"] is False
    assert state(status="paid", kind="report", fulfilment="failed", retrying=True)["state"] == "preparing"
    assert state(status="paid", kind="report", fulfilment="failed", retrying=False)["state"] == "delayed"
    assert state(status="paid", kind="report", fulfilment="ready")["state"] == "ready"
    # the consultation purchase: questions are credited at once, the included Kundali PDF follows
    bundle = dict(status="paid", kind="pack", messages=10, includes_report=True)
    preparing = state(**bundle, fulfilment="generating")
    assert preparing["state"] == "preparing" and preparing["done"] is False and "10 questions added" in preparing["title"] and "Kundali PDF" in preparing["text"]
    assert state(**bundle, fulfilment="ready")["state"] == "ready" and state(**bundle, fulfilment="ready")["done"] is True
    assert state(**bundle, fulfilment="failed", retrying=False)["state"] == "delayed" and state(**bundle, fulfilment="failed", retrying=True)["done"] is False
    for lang, word in (("mr", "प्रश्न जमा झाले"), ("hi", "सवाल जोड़ दिए गए")):
        assert word in js("AstroPay.describe(view, lang)", view={**bundle, "fulfilment": "pending"}, lang=lang)["title"]
    assert js("AstroPay.describe({status: 'paid', kind: 'report', fulfilment: 'ready'}, 'hi')")["title"] == "आपकी रिपोर्ट तैयार है"
    assert js("AstroPay.defaultReportLanguage('hi', 'en')") == "hi"


def test_pay_js_dictionaries_have_the_same_keys():
    source = (STATIC_DIR / "js" / "pay.js").read_text(encoding="utf-8")
    english = source.split("    en: {", 1)[1].split("    mr: {", 1)[0]
    marathi = source.split("    mr: {", 1)[1].split("  TEXT.hi = {", 1)[0]
    hindi = source.split("  TEXT.hi = {", 1)[1].split("  function text(", 1)[0]
    keys = [set(re.findall(r"(?:^|[\s,{])([a-zA-Z]+): \"", block)) for block in (english, marathi, hindi)]
    assert keys[0] == keys[1] == keys[2] and len(keys[0]) >= 30, (keys[0] ^ keys[1], keys[0] ^ keys[2])
    assert " है" not in marathi and "आहे" not in hindi  # each language is its own, not a copy of the other


def test_checkout_js_is_the_only_external_url_on_the_site(rzp):
    """Narrow exception to "no third-party requests": Razorpay's checkout.js, in pay.js only, loaded on click only.

    The site's other third party, Google Analytics, is deliberately not here: its loader is a tag in base.html,
    so it stays visible in the HTML instead of being injected by a script. This file asserts nothing in
    static/js reaches out - analytics.js included, which is why it takes its measurement ID from its own tag."""
    absolute = re.compile(r"""["'](https?:)?//[^"'\s]+""")
    for script in sorted((STATIC_DIR / "js").glob("*.js")):
        found = [m.group(0).strip("\"'") for m in absolute.finditer(script.read_text(encoding="utf-8"))]
        found = [url for url in found if url != "http://www.w3.org/2000/svg"]  # an XML namespace, never requested
        assert found == (["https://checkout.razorpay.com/v1/checkout.js"] if script.name == "pay.js" else []), script.name
    source = (STATIC_DIR / "js" / "pay.js").read_text(encoding="utf-8")
    assert razorpay.CHECKOUT_JS == "https://checkout.razorpay.com/v1/checkout.js" and "function loadCheckout" in source
    # loaded lazily: the single call sits inside pay(), which only runs from a click on a buy / Pay button
    assert source.count("loadCheckout().then") == 1 and source.index("function pay(") < source.index("loadCheckout().then") < source.index("function openPanel(")
    assert "createElement(\"script\")" in source
    assert set(re.findall(r'"(/api/[^"]*)"', source)) == {"/api/payments/order", "/api/payments/verify", "/api/payments/order/"}
    client = TestClient(app)
    for path in ("/", "/janam-kundali", "/kundali-matching", "/mangal-dosha", "/sade-sati", "/consultation"):
        html = client.get(path).text  # even with payments ON, no page references an external asset in its HTML
        for url in re.findall(r'(?:src|href)="([^"]+)"', html):
            if url.startswith("https://www.googletagmanager.com/gtag/js?id="):
                continue  # the analytics tag in base.html, the one external asset any page references
            assert url.startswith(("/", "#")) or url.startswith("http://localhost:8000"), (path, url)
        assert "checkout.razorpay.com" not in html


# ---- /order/{token} texts in the order's language -------------------------------------------------------------


def test_the_promised_wait_is_per_tier_and_the_poll_limit_derives_from_it(js):
    """The wait we quote is measured per tier, and the browser stops polling at twice the top of it.

    Both halves of this were wrong at once before: the copy said "1-3 minutes" for a book that measures 8.8,
    and the poll limit sat beside it as an independent 12 minutes. They drifted because nothing tied them
    together, so the fix is not a better number - it is that the limit is now COMPUTED from the promise."""
    from app.payments import order_page, service

    assert order_page.WAIT_RANGE == {"simple": "3-5", "detailed": "5-10"}
    assert order_page.DEFAULT_WAIT == order_page.WAIT_RANGE["detailed"]  # unknown promises the longer wait

    # the server picks the tier off the order, including through a consultation's bundled report
    def wait_for(product, kind="report"):
        return order_page.wait_range({"product": product, "kind": kind, "report_id": "r1"})

    assert wait_for("kundali-report-simple") == "3-5" and wait_for("kundali-report") == "5-10"
    assert wait_for("consultation-basic", "pack") == "3-5"      # bundles the simple report
    assert wait_for("consultation-premium", "pack") == "5-10"   # bundles the book
    assert wait_for("matching-report") == "5-10"                # not a tiered product: the longer promise
    assert order_page.wait_range({"product": "consultation-basic", "kind": "pack", "report_id": None}) == "5-10"

    # and it reaches the browser on the order view rather than being recomputed there
    order = {"razorpay_order_id": "order_X", "status": "paid", "product": "kundali-report-simple", "kind": "report",
             "amount_paise": 4900, "fulfilment": "generating", "attempts": 0, "messages": 0, "report_id": "r1", "token": "t"}
    assert service.public_view(order, reveal_token=False)["report_wait"] == "3-5"
    assert service.public_view({**order, "product": "kundali-report"}, reveal_token=False)["report_wait"] == "5-10"

    # pay.js mirrors the table only for the panel shown BEFORE an order exists
    assert js("AstroPay.WAIT") == {k: v for k, v in
                                   {"kundali-report-simple": order_page.WAIT_RANGE["simple"]}.items()}
    assert js("AstroPay.waitFor('kundali-report-simple')") == "3-5"
    assert js("AstroPay.waitFor('kundali-report')") == "5-10"
    assert js("AstroPay.waitFor('matching-report')") == "5-10"
    assert js("AstroPay.waitFor(undefined)") == "5-10"

    # the poll limit is twice the top of the promise, with a ten-minute floor, and never trusts a bad value
    assert js("AstroPay.pollLimitMs('5-10')") == 20 * 60 * 1000
    assert js("AstroPay.pollLimitMs('3-5')") == 10 * 60 * 1000
    assert js("AstroPay.pollLimitMs(null)") == 20 * 60 * 1000
    assert js("AstroPay.pollLimitMs('nonsense')") == 20 * 60 * 1000
    # the promise must always fit inside the window, or the spinner outlives the wait we quoted
    for wait in order_page.WAIT_RANGE.values():
        top_minutes = int(wait.split("-")[-1])
        assert js("AstroPay.pollLimitMs(w)", w=wait) >= top_minutes * 60 * 1000 * 2


MINUTE = 60_000


def test_the_waiting_screen_stages_advance_and_never_finish_early(js):
    """The waiting screen shows four stages advancing on elapsed time. It knows nothing - the server reports
    one bit for this order - so the whole job of this test is the one lie it must not tell: FOUR TICKS AND NO
    DOWNLOAD. The last stage may only complete when fulfilment is actually "ready", and by then the box has
    been replaced by the ready state."""
    view = {"status": "paid", "kind": "report", "includes_report": True, "fulfilment": "generating",
            "retrying": False, "report_wait": "5-10"}          # so a stage boundary is a round number of minutes

    def at(minutes, **over):
        return [step["state"] for step in
                js("AstroPay.reportStages(view, lang, ms)", view={**view, **over}, lang="en", ms=minutes * MINUTE)]

    assert at(0) == ["active", "waiting", "waiting", "waiting"]     # 0.00 of 10 min
    assert at(1) == ["done", "active", "waiting", "waiting"]        # 0.08 -> 0.8 min
    assert at(4) == ["done", "done", "active", "waiting"]           # 0.35 -> 3.5 min
    assert at(9) == ["done", "done", "done", "active"]              # 0.80 -> 8 min
    # past the quoted wait, and far past it: the last stage stays active rather than claiming to be finished
    assert at(10) == at(45) == at(6000) == ["done", "done", "done", "active"]
    # only real readiness completes it
    assert at(1, fulfilment="ready") == ["done"] * 4

    # monotonic: no stage ever goes backwards as time passes, which is what a reload must not do either
    order = {"waiting": 0, "active": 1, "done": 2}
    previous = [0, 0, 0, 0]
    for minute in range(0, 40):
        current = [order[state] for state in at(minute)]
        assert all(now >= before for now, before in zip(current, previous)), (minute, current, previous)
        previous = current

    # the shorter tier reaches each stage sooner, because the boundaries are fractions of what was quoted
    simple = [step["state"] for step in js("AstroPay.reportStages(view, lang, ms)",
                                          view={**view, "report_wait": "3-5"}, lang="en", ms=2 * MINUTE)]
    assert simple == ["done", "done", "active", "waiting"]          # 0.35 of 5 min = 1.75 min

    for lang in ("en", "hi", "mr"):
        labels = [step["label"] for step in
                  js("AstroPay.reportStages(view, lang, ms)", view=view, lang=lang, ms=0)]
        assert len(labels) == 4 and all(label.strip() for label in labels), lang
        assert len(set(labels)) == 4, lang                          # four stages, not one repeated
    english = [s["label"] for s in js("AstroPay.reportStages(view, lang, ms)", view=view, lang="en", ms=0)]
    marathi = [s["label"] for s in js("AstroPay.reportStages(view, lang, ms)", view=view, lang="mr", ms=0)]
    assert not set(english) & set(marathi)                          # each tree in its own language, not a copy


def test_elapsed_comes_from_the_order_not_from_this_tab(js):
    """`paid_at` is what makes a reload, or the order page on another device days later, resume where the work
    is instead of restarting the stages from zero. A missing one is stage 1, which is where a payment just was."""
    assert js("AstroPay.elapsedSincePaid(view)", view={"paid_at": None}) == 0
    assert js("AstroPay.elapsedSincePaid(view)", view={}) == 0
    assert js("AstroPay.elapsedSincePaid(view)", view={"paid_at": "not a date"}) == 0
    recent = js("AstroPay.elapsedSincePaid(view)", view={"paid_at": int(time.time()) - 120})
    assert 110_000 <= recent <= 130_000                             # two minutes ago, in ms


def test_the_report_email_promise_is_off_until_something_can_send_it(monkeypatch, rzp, jobs):
    """The waiting screen offers to say a copy is coming by e-mail. Nothing sends e-mail yet, so the line is
    gated: a page that promises an e-mail nobody sends makes the customer stop watching the page that IS
    delivering. It is also personal data, so it needs the token like the URLs do."""
    from app.payments import order_page, service

    order = {"razorpay_order_id": "order_X", "status": "paid", "product": "kundali-report", "kind": "report",
             "amount_paise": 24900, "fulfilment": "generating", "attempts": 0, "messages": 0,
             "report_id": "a" * 32, "token": "t" * 32, "email": "buyer@example.com", "phone": None,
             "language": "en", "paid_at": 1_758_800_000, "currency": "INR", "as_of": "2026-09-25"}

    monkeypatch.delenv("REPORT_EMAIL_ENABLED", raising=False)
    assert service.report_email_enabled() is False
    assert service.public_view(order, reveal_token=True)["email_copy"] is None
    assert order_page.context(order, service.public_view(order, reveal_token=True))["email_copy"] is None

    monkeypatch.setenv("REPORT_EMAIL_ENABLED", "1")
    assert service.public_view(order, reveal_token=True)["email_copy"] == "buyer@example.com"
    assert service.public_view(order, reveal_token=False)["email_copy"] is None   # no token, no address
    # and it is only said while the report is still being written
    ready = order_page.context({**order, "fulfilment": "ready"},
                               service.public_view({**order, "fulfilment": "ready"}, reveal_token=True))
    assert ready["email_copy"] is None
    for lang in ("en", "hi", "mr"):
        line = order_page.context({**order, "language": lang},
                                  service.public_view({**order, "language": lang}, reveal_token=True))["email_copy"]
        assert "buyer@example.com" in line and "{email}" not in line, lang


def test_the_email_line_says_the_same_words_in_the_browser_and_on_the_server(js):
    """Same discipline as the status texts below: one wording per language, in two places."""
    from app.payments import order_page

    for lang in ("en", "hi", "mr"):
        browser = js("AstroPay.textFor(lang).emailCopy", lang=lang)
        assert browser == order_page.LABELS[lang]["email_copy"], lang


def test_order_page_texts_equal_pay_js_in_every_language_and_state(js):
    """The server-rendered first paint (app/payments/order_page.py) and pay.js describe() must say the same words."""
    from app.payments import order_page

    views = {
        "credited": dict(status="paid", kind="pack", messages=10, includes_report=False, fulfilment="ready"),
        "bundle_preparing": dict(status="paid", kind="pack", messages=10, includes_report=True, fulfilment="generating", retrying=False),
        "bundle_ready": dict(status="paid", kind="pack", messages=10, includes_report=True, fulfilment="ready", retrying=False),
        "bundle_delayed": dict(status="paid", kind="pack", messages=10, includes_report=True, fulfilment="failed", retrying=False),
        "ready": dict(status="paid", kind="report", messages=0, includes_report=True, fulfilment="ready", retrying=False),
        "delayed": dict(status="paid", kind="report", messages=0, includes_report=True, fulfilment="failed", retrying=False),
        "preparing": dict(status="paid", kind="report", messages=0, includes_report=True, fulfilment="failed", retrying=True),
    }
    for lang in ("en", "hi", "mr"):
        assert set(order_page.STATUS[lang]) == set(views) and set(order_page.LABELS[lang]) == set(order_page.LABELS["en"])
        for key, view in views.items():
            # Both tiers, because the wait is the one part of this copy that differs per product: the server
            # sends `report_wait` and the browser must print exactly what it was sent, never its own guess.
            for wait in order_page.WAIT_RANGE.values():
                browser = js("AstroPay.describe(view, lang)", view={**view, "report_wait": wait}, lang=lang)
                assert order_page.status_key(view)[0] == key
                title, text = (part.replace("{n}", "10").replace("{wait}", wait)
                               for part in order_page.STATUS[lang][key])
                assert (browser["title"], browser["text"]) == (title, text), (lang, key, wait)
                assert browser["done"] == order_page.status_key(view)[2] and browser["state"] == order_page.status_key(view)[1]
            # and with no `report_wait` at all, the browser promises the LONGER wait rather than the shorter
            fallback = js("AstroPay.describe(view, lang)", view=view, lang=lang)
            assert order_page.DEFAULT_WAIT in fallback["text"] or "{wait}" not in order_page.STATUS[lang][key][1]


def test_order_page_context_follows_the_orders_language(rzp, jobs, monkeypatch):
    from app.payments import order_page

    monkeypatch.setattr(service, "generate_report", fake_generator([]))
    client = TestClient(app)
    started = client.post("/api/consultation/start", json={**MIRAJ, "language": "hi", "name": "केशव"}).json()
    created = client.post("/api/payments/order", json={"email": "buyer@example.com", "place_of_supply": PLACE, "product": "consultation-premium", "session_id": started["session_id"]}).json()
    client.post("/api/payments/verify", json=verify_body(created["order_id"]))
    order = store.by_razorpay_id(created["order_id"])
    pending = order_page.context(order, service.public_view(order, reveal_token=True))
    assert pending["lang"] == "hi" and pending["info"]["state"] == "preparing" and pending["info"]["done"] is False
    assert pending["info"]["title"] == "भुगतान मिल गया - 10 सवाल जोड़ दिए गए" and pending["labels"]["heading"] == "आपका ऑर्डर"
    assert pending["product_name"] == order_page.PRODUCT_NAMES["consultation-premium"]["hi"].format(n=10)
    assert pending["language_name"] == "हिन्दी"
    assert re.fullmatch(r"\d{1,2} \S+ \d{4}, \d\d:\d\d IST", pending["paid_on"])
    jobs.run()
    order = store.by_razorpay_id(created["order_id"])
    ready = order_page.context(order, service.public_view(order, reveal_token=True))
    assert ready["info"] == {"state": "ready", "done": True, "title": "10 सवाल जोड़ दिए गए - आपकी कुंडली PDF तैयार है",
                             "text": order_page.STATUS["hi"]["bundle_ready"][1]}

    english = report_order(TestClient(app), language="en")
    assert order_page.context({**store.by_razorpay_id(english["order_id"]), "paid_at": 1790000000.0},
                              {"kind": "report", "fulfilment": "pending", "messages": 0})["labels"]["heading"] == "Your order"
    assert order_page.order_language({"language": "xx"}) == "en" and order_page.order_language({"language": None}) == "en"


# ---- the first REAL paid sale (the Swiss Ephemeris licence clock) ---------------------------------------


LIVE_KEY = "rzp_live_UnitTestKey01"


def _order_row(order_id: str = "ord_abc123", **kw) -> dict:
    """A paid order for the first-sale tests, paid AN HOUR AGO rather than on a fixed date.

    It used to carry a literal timestamp, which made the licence week expire by the calendar: the marker was
    dated 2026-09-21, LICENCE_DAYS was 7, and at 7.17 days elapsed `summary()` started saying "(OVERDUE)"
    instead of "days left" - so the test passed in the morning and failed in the afternoon of 2026-09-28,
    with nothing having changed. The countdown itself is gone now (there was no deadline to count down to),
    but the lesson stands for any test of elapsed time: measure from now, or it has a shelf life."""
    return {"id": order_id, "status": "paid", "payment_id": "pay_Test0000000001", "product": "kundali-report",
            "amount_paise": KUNDALI_PAISE, "paid_at": time.time() - 3600, **kw}


def test_a_test_mode_payment_is_never_the_first_real_sale(rzp, jobs, caplog):
    """TEST keys are how we develop; no test payment may ever start the licence week."""
    client = TestClient(app)
    created = report_order(client)
    with caplog.at_level(logging.CRITICAL):
        assert client.post("/api/payments/verify", json=verify_body(created["order_id"])).status_code == 200
    assert store.by_razorpay_id(created["order_id"])["status"] == "paid"
    assert first_sale.status() is None and not first_sale.marker_path().exists()
    assert "FIRST LIVE SALE" not in caplog.text
    assert "no real paid sale yet" in first_sale.summary()


def test_the_first_live_payment_is_recorded_once_loudly_and_durably(rzp, jobs, monkeypatch, caplog):
    monkeypatch.setenv("RAZORPAY_KEY_ID", LIVE_KEY)  # live mode: a real customer's money
    assert not razorpay.is_test_mode()

    with caplog.at_level(logging.CRITICAL, logger="app.payments.first_sale"):
        recorded = first_sale.note_paid(_order_row())
    assert recorded and recorded["order_id"] == "ord_abc123" and recorded["key_id"] == LIVE_KEY
    assert "*** FIRST LIVE SALE ***" in caplog.text  # unmissable in the journal
    assert first_sale.LICENCE_URL in caplog.text and "AGPL publishing in force" in caplog.text
    # Banning the WORD "overdue" would fail on the new line's own reassurance ("nothing is overdue"), which is
    # the point of it. So: the obligation wording must be gone, and the reassurance must be present.
    assert "within 7 days" not in caplog.text and "must be bought" not in caplog.text
    assert "nothing is overdue" in caplog.text

    marker = json.loads(first_sale.marker_path().read_text(encoding="utf-8"))  # durable, readable with cat
    assert marker["order_id"] == "ord_abc123" and marker["payment_id"] == "pay_Test0000000001"
    assert marker["amount_paise"] == KUNDALI_PAISE

    caplog.clear()
    assert first_sale.note_paid(_order_row("ord_second99", payment_id="pay_Test0000000002")) is None
    assert "FIRST LIVE SALE" not in caplog.text  # never twice, whatever calls it
    assert first_sale.status()["order_id"] == "ord_abc123"
    # INFORMATIONAL, and asserted in both directions on purpose. `summary()` used to print "5.8 days left" and
    # then "OVERDUE" against a 7-day LICENCE_DAYS, which read as a licence violation in progress on a deploy
    # check. It never was one: the AGPL is one of the Swiss Ephemeris's two licences and publishing every
    # deploy satisfies it for as long as we keep publishing. The Professional licence is wanted to CLOSE the
    # source, not to cure a breach. So the countdown and `deadline()` are gone, and these assertions keep
    # them gone - a false alarm on a deploy check is worse than silence, because it teaches the reader to
    # skip the section.
    line = first_sale.summary()
    assert "FIRST LIVE SALE on" in line and "AGPL publishing in force" in line
    # The OBLIGATION wording must be gone. Not the word "overdue" - the line says "nothing overdue", and
    # banning the word fails on the reassurance itself, which is the thing worth keeping.
    for absent in ("days left", "OVERDUE", "must be bought", "clock"):
        assert absent not in line, absent
    assert not hasattr(first_sale, "deadline"), "the deadline concept was removed; do not reintroduce it"
    assert not hasattr(first_sale, "LICENCE_DAYS")


def test_the_first_sale_record_survives_a_lost_database(rzp, monkeypatch):
    monkeypatch.setenv("RAZORPAY_KEY_ID", LIVE_KEY)
    first_sale.note_paid(_order_row())
    with db.transaction() as conn:  # a restore from an older backup, or a wiped app.db
        conn.execute("DELETE FROM milestones")
    assert first_sale.status()["order_id"] == "ord_abc123"  # read back from the marker file ...
    with db.transaction(write=False) as conn:  # ... and put back into the database
        assert conn.execute("SELECT count(*) AS n FROM milestones").fetchone()["n"] == 1


def test_a_live_payment_through_the_webhook_starts_the_clock(rzp, jobs, monkeypatch, caplog):
    client = TestClient(app)
    created = report_order(client)
    monkeypatch.setenv("RAZORPAY_KEY_ID", LIVE_KEY)  # the account went live between the order and the payment
    with caplog.at_level(logging.CRITICAL, logger="app.payments.first_sale"):
        assert webhook(client, "payment.captured", created["order_id"]).status_code == 200
    assert "*** FIRST LIVE SALE ***" in caplog.text
    record = first_sale.status()
    assert record["order_id"] == store.by_razorpay_id(created["order_id"])["id"]
    assert record["product"] == "kundali-report" and record["amount_paise"] == KUNDALI_PAISE

    caplog.clear()  # the same webhook delivered twice (Razorpay retries) must not fire it again
    assert webhook(client, "payment.captured", created["order_id"], event_id="evt_2").status_code == 200
    assert "FIRST LIVE SALE" not in caplog.text


def test_first_sale_status_script_and_the_admin_list_show_it(rzp, monkeypatch, capsys):
    import importlib.util

    spec = importlib.util.spec_from_file_location("first_sale_status", ROOT / "scripts/first_sale_status.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.main([]) == 1  # nothing yet
    assert "no real paid sale yet" in capsys.readouterr().out

    monkeypatch.setenv("RAZORPAY_KEY_ID", LIVE_KEY)
    first_sale.note_paid(_order_row())
    assert module.main([]) == 0
    printed = capsys.readouterr().out
    assert "FIRST LIVE SALE on" in printed and first_sale.LICENCE_URL in printed and "ord_abc123" in printed
    assert module.main(["--json"]) == 0
    assert json.loads(capsys.readouterr().out)["order_id"] == "ord_abc123"

    spec = importlib.util.spec_from_file_location("fulfil_order", ROOT / "scripts/fulfil_order.py")
    fulfil = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fulfil)
    assert fulfil.main(["--list"]) == 0
    assert "FIRST LIVE SALE on" in capsys.readouterr().out


# ---- what we hand to Razorpay Checkout ------------------------------------------------------------


def test_the_checkout_theme_colour_is_legible_under_the_white_text_razorpay_puts_on_it():
    """The brand contrast rules, on the one screen where a customer types card details.

    Razorpay paints its Checkout header with `theme.color` and writes the header text on it in WHITE,
    with no way to change that text. So the colour we hand over is judged against white - and the
    tempting edit ("the accent is for CTAs, and Checkout is a CTA") would put `--color-accent` there at
    2.19:1. No stylesheet test can see this: it is a JS object literal handed to a widget that renders
    outside our CSS and our CSP, so it needs a test of its own.

    This asserts the REASON, not the value: the theme must be the brand primary AND clear AA against
    white. Re-branding stays possible; gold and saffron stay impossible.
    """
    from tests import test_brand_css as brand

    pay_js = (STATIC_DIR / "js" / "pay.js").read_text(encoding="utf-8")
    found = re.findall(r"theme:\s*\{\s*color:\s*[\"'](#[0-9A-Fa-f]{3,6})[\"']", pay_js)
    assert len(found) == 1, f"expected exactly one Checkout theme colour in pay.js, found {found}"
    theme = brand._rgb(found[0])

    primary = brand._rgb(brand.ROOT_TOKENS["--color-primary"])
    assert theme == primary, (f"the Checkout theme is {brand._hex(theme)} but --color-primary is "
                              f"{brand._hex(primary)}: the two must not drift")

    ratio = brand.contrast(theme, (255, 255, 255))
    assert ratio >= brand.AA, (f"Razorpay writes WHITE on this colour: {brand._hex(theme)} is "
                               f"{ratio:.2f}:1 and fails WCAG AA on the card-entry screen")

    # and the colours that must never be handed to a widget that writes white on them
    for token in ("--color-accent", "--color-saffron"):
        forbidden = brand._rgb(brand.ROOT_TOKENS[token])
        assert brand.contrast(forbidden, (255, 255, 255)) < brand.AA, (
            f"{token} now passes on white - re-check Brand section 2 before relying on this test")
        assert theme != forbidden, f"the Checkout theme must never be {token}"


# ---- refunds (webhook refund.processed) ------------------------------------------------------------------


def refund_webhook(client, order_id: str, refund_id: str, amount: int, *, payment_id: str = "pay_Test0000000001",
                   event: str = "refund.processed", event_id: str = "evt_r1", created_at: int = 1790000000):
    """A REFUND event, which carries a refund entity - `payment_id` and no `order_id`.

    Written as its own helper rather than bent out of `webhook()` because that difference is the whole point:
    assuming the payment shape is why `refund.processed` was silently ignored while subscribed on the live
    webhook. `order_id` here is only for the caller's readability; Razorpay does not send it.
    """
    payload = {"entity": "event", "account_id": "acc_Test", "event": event, "contains": ["refund"],
               "created_at": created_at,
               "payload": {"refund": {"entity": {"id": refund_id, "entity": "refund", "amount": amount,
                                                 "currency": "INR", "payment_id": payment_id,
                                                 "status": "processed", "created_at": created_at}}}}
    body = json.dumps(payload, separators=(",", ":")).encode()
    headers = {"Content-Type": "application/json",
               "X-Razorpay-Signature": hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest(),
               "X-Razorpay-Event-Id": event_id}
    return client.post("/api/payments/webhook", content=body, headers=headers)


def _a_paid_order(client, payment_id: str = "pay_Test0000000001", **extra):
    """`extra` reaches the order request. Needed because the SAME request twice is the same order by design -
    `create_order` returns the existing paid one - so a test that wants a SECOND order must ask for a
    different thing (a different product, say), or it silently gets the first one back.

    `payment_id` is separate for the same class of reason: a refund is matched to its order by the PAYMENT id
    (that is all a refund entity carries), so two orders sharing one fake payment id would send both their
    refunds to whichever the lookup found first."""
    created = report_order(client, **extra)
    assert client.post("/api/payments/verify", json=verify_body(created["order_id"], payment_id)).status_code == 200
    return store.by_razorpay_id(created["order_id"])


def test_a_refund_is_recorded_without_taking_the_reading_away(rzp, jobs):
    """The money went back; the customer keeps the PDF. Revoking a delivered reading is a separate decision
    nobody has made, and `service.py` gates delivery on status == 'paid' - so the refund is recorded BESIDE the
    payment rather than on top of it."""
    client = TestClient(app)
    order = _a_paid_order(client)
    assert refund_webhook(client, order["id"], "rfnd_1", KUNDALI_PAISE).json() == {"status": "full"}
    after = store.get_order(order["id"])
    assert after["status"] == "paid", "a refund must not un-deliver what was already delivered"
    assert after["refunded_paise"] == KUNDALI_PAISE and after["refund_state"] == "full"
    assert after["refund_id"] == "rfnd_1" and after["refunded_at"] == 1790000000.0


def test_partial_refunds_add_up_and_the_same_refund_never_counts_twice(rzp, jobs):
    """Razorpay allows several partial refunds against one payment and retries its webhooks. Two Rs 30 refunds
    on a Rs 59 order is FULLY refunded; overwriting instead of accumulating would leave it looking half
    refunded forever, and a retried delivery would double the total."""
    client = TestClient(app)
    order = _a_paid_order(client)
    half = KUNDALI_PAISE // 2

    assert refund_webhook(client, order["id"], "rfnd_a", half, event_id="evt_a").json() == {"status": "partial"}
    assert store.get_order(order["id"])["refunded_paise"] == half

    # the SAME refund again, under a different event id: Razorpay retried, and it must not count twice
    assert refund_webhook(client, order["id"], "rfnd_a", half, event_id="evt_a_again").json() == {"status": "partial"}
    assert store.get_order(order["id"])["refunded_paise"] == half

    # a DIFFERENT refund for the rest: now it is full
    assert refund_webhook(client, order["id"], "rfnd_b", KUNDALI_PAISE - half, event_id="evt_b").json() == {"status": "full"}
    after = store.get_order(order["id"])
    assert after["refunded_paise"] == KUNDALI_PAISE and after["refund_state"] == "full"


def test_a_refund_does_not_get_the_amount_check_that_guards_a_payment(rzp, jobs):
    """`payment.captured` refuses an amount that differs from the charge. A PARTIAL refund legitimately
    differs, so copying that check across would have rejected the case refunds exist to record."""
    client = TestClient(app)
    order = _a_paid_order(client)
    assert refund_webhook(client, order["id"], "rfnd_small", 100).json() == {"status": "partial"}
    assert store.get_order(order["id"])["refunded_paise"] == 100


def test_a_refund_for_an_unknown_payment_is_ignored_not_an_error(rzp, jobs):
    client = TestClient(app)
    _a_paid_order(client)
    assert refund_webhook(client, "x", "rfnd_z", 100, payment_id="pay_SomebodyElse01").json() == {"status": "ignored"}
    assert refund_webhook(client, "x", "", 100, event_id="evt_no_id").json() == {"status": "ignored"}


def test_a_refund_gets_a_credit_note_in_its_own_consecutive_series(rzp, jobs):
    """Section 34: a refund is reversed by a CREDIT NOTE, not by editing the invoice - its own consecutive
    series, naming the invoice it reduces, reducing the taxable value and the tax proportionally. The live
    test order refunded on 2026-09-29 is what made this necessary.

    The number is checked for the 16-character limit as well as the format: "RK-CN/2627/00001" is exactly 16,
    which is why the counter is padded to five digits and not six."""
    from app.payments import credit_note

    client = TestClient(app)
    order = _a_paid_order(client)
    invoiced = gst.recorded(store.get_order(order["id"]))
    assert store.get_order(order["id"])["invoice_no"].startswith("RK/")

    refund_webhook(client, order["id"], "rfnd_cn1", KUNDALI_PAISE)
    row = store.get_refund("rfnd_cn1")
    assert row["credit_no"] == "RK-CN/2627/00001" and len(row["credit_no"]) <= 16
    # the split is frozen on the refund row, not recomputed when the document is opened
    assert row["base_paise"] + row["gst_paise"] == KUNDALI_PAISE
    assert row["rate_bp"] == invoiced.rate_bp and row["invoice_no"] == store.get_order(order["id"])["invoice_no"]
    # a FULL refund credits back exactly what was invoiced
    assert row["base_paise"] == invoiced.base_paise and row["gst_paise"] == invoiced.gst_paise

    # idempotent: Razorpay retries deliveries, and renumbering a note somebody holds is not an option
    refund_webhook(client, order["id"], "rfnd_cn1", KUNDALI_PAISE, event_id="evt_retry")
    assert store.get_refund("rfnd_cn1")["credit_no"] == "RK-CN/2627/00001"
    assert credit_note.issue(store.get_order(order["id"]), "rfnd_cn1") == "RK-CN/2627/00001"

    # Its own counter, proved both ways: a second sale's INVOICE continues the invoice series (00002) while
    # the next credit note continues the credit-note series (also 00002). Sharing one counter would make both
    # series full of holes, and "consecutive" is the entire property being claimed.
    second = _a_paid_order(client, payment_id="pay_Test0000000002", product="sade-sati-guide")
    assert store.get_order(second["id"])["invoice_no"] == "RK/2627/00002"
    refund_webhook(client, second["id"], "rfnd_cn2", 100, payment_id="pay_Test0000000002", event_id="evt_cn2")
    assert store.get_refund("rfnd_cn2")["credit_no"] == "RK-CN/2627/00002"


def test_two_partial_credit_notes_add_back_to_exactly_the_invoiced_taxable_value(rzp, jobs):
    """The reason the split is computed against the RUNNING TOTAL rather than each refund on its own. Two
    refunds of half a Rs 299 order, split independently, credit 12669 + 12669 = 25338 paise of taxable value
    against an invoiced 25339 - and a fully refunded invoice whose notes do not add back to it is a
    reconciliation somebody has to explain. Against the running total, the second note states what is left."""
    client = TestClient(app)
    order = _a_paid_order(client)
    invoiced = gst.recorded(store.get_order(order["id"]))
    half = KUNDALI_PAISE // 2

    refund_webhook(client, order["id"], "rfnd_h1", half, event_id="evt_h1")
    refund_webhook(client, order["id"], "rfnd_h2", KUNDALI_PAISE - half, event_id="evt_h2")
    notes = store.refunds_for(order["id"])
    assert [n["credit_no"] for n in notes] == ["RK-CN/2627/00001", "RK-CN/2627/00002"]
    assert sum(n["base_paise"] for n in notes) == invoiced.base_paise
    assert sum(n["gst_paise"] for n in notes) == invoiced.gst_paise
    assert sum(n["amount_paise"] for n in notes) == KUNDALI_PAISE
    for note in notes:                       # each note is internally consistent too
        assert note["base_paise"] + note["gst_paise"] == note["amount_paise"]


def test_the_credit_note_document_says_what_the_law_needs_it_to_say(rzp, jobs):
    client = TestClient(app)
    order = _a_paid_order(client)
    refund_webhook(client, order["id"], "rfnd_doc", 5760)
    row = store.get_refund("rfnd_doc")

    response = client.get(f"/api/payments/credit-note/{order['token']}/rfnd_doc")
    assert response.status_code == 200
    html = response.text
    assert "Credit note" in html and row["credit_no"] in html
    assert store.get_order(order["id"])["invoice_no"] in html          # the invoice it relates to
    assert "section 34" in html and site.GSTIN in html and site.LEGAL_ENTITY in html
    assert "rfnd_doc" in html and "refunded in part" in html
    assert gst.money(row["base_paise"]) in html                 # the taxable value credited
    assert gst.money(row["amount_paise"]) in html                # the total credited
    assert 'name="robots" content="noindex, nofollow"' in html
    assert response.headers["cache-control"] == "private, no-store"
    # The place of supply decides the HEADS the tax is credited under, exactly as on the invoice - and the
    # heads are what is printed, not the composite figure. That is the point: a credit note has to reverse the
    # tax under the heads it was collected under, so ₹8.79 of "GST" appears nowhere on an intra-state note.
    amounts = gst.Amounts(base_paise=row["base_paise"], gst_paise=row["gst_paise"],
                          total_paise=row["amount_paise"], rate_bp=row["rate_bp"])
    intra = states.is_intra_state(store.get_order(order["id"])["place_of_supply"])
    heads = gst.heads(amounts, intra)
    assert [head.name for head in heads] == (["CGST", "SGST"] if intra else ["IGST"])
    for head in heads:
        assert f"{head.name} @ {head.rate_text}% credited" in html and gst.money(head.paise) in html
    assert sum(head.paise for head in heads) == row["gst_paise"]

    # the token is the credential; a wrong token and a wrong refund id are the same 404
    assert client.get("/api/payments/credit-note/" + "x" * 30 + "/rfnd_doc").status_code == 404
    assert client.get(f"/api/payments/credit-note/{order['token']}/rfnd_nothing").status_code == 404


def test_the_order_page_offers_every_credit_note_in_the_orders_language(rzp, jobs):
    from app.payments.order_page import LABELS

    client = TestClient(app)
    order = _a_paid_order(client)
    page = client.get(f"/order/{order['token']}")
    assert page.status_code == 200 and "credit-note" not in page.text     # nothing refunded yet

    refund_webhook(client, order["id"], "rfnd_p1", 1000, event_id="evt_p1")
    refund_webhook(client, order["id"], "rfnd_p2", 2000, event_id="evt_p2")
    view = service.public_view(store.get_order(order["id"]), reveal_token=True)
    assert [n["number"] for n in view["credit_notes"]] == ["RK-CN/2627/00001", "RK-CN/2627/00002"]

    page = client.get(f"/order/{order['token']}").text
    language = store.get_order(order["id"])["language"]
    assert LABELS[language]["credit_note"] in page
    for note in view["credit_notes"]:
        assert note["url"] in page and note["number"] in page


def test_a_sale_with_no_gst_recorded_gets_no_credit_note(rzp, jobs):
    """An order paid before the GST columns existed has no tax to reverse, so there is nothing for a note to
    reduce - and a note claiming to reverse a tax that was never recorded would be a false statement on a tax
    document. The refund is still recorded; the order page simply offers no link."""
    client = TestClient(app)
    order = _a_paid_order(client)
    with db.transaction() as conn:
        conn.execute("UPDATE orders SET base_paise = NULL, gst_paise = NULL, invoice_no = NULL WHERE id = ?",
                     (order["id"],))
    refund_webhook(client, order["id"], "rfnd_pre", 100)
    assert store.get_order(order["id"])["refunded_paise"] == 100        # the money is still recorded
    assert store.get_refund("rfnd_pre")["credit_no"] is None
    assert service.public_view(store.get_order(order["id"]), reveal_token=True)["credit_notes"] == []
    assert client.get(f"/api/payments/credit-note/{order['token']}/rfnd_pre").status_code == 404


def pdf_page_count(pdf: bytes) -> int:
    import io

    import pypdf

    return len(pypdf.PdfReader(io.BytesIO(pdf)).pages)


def test_both_documents_download_as_a_pdf_and_the_html_stays(rzp, jobs):
    """The owner's decision: the invoice download is a PDF, through the same Chromium pipeline as the report.
    The HTML document is NOT replaced - it is what the PDF is printed from, it is one click away on the order
    page, and its text can be copied, which the Devanagari in a Chromium PDF cannot (37e5e62). Both exist.

    A real render, not a stub: this is the only way to find out that the document prints at all, and the page
    size is a CSS rule in the template that nothing else would check."""
    client = TestClient(app)
    order = _a_paid_order(client)
    refund_webhook(client, order["id"], "rfnd_pdf", 1000)
    number = store.get_order(order["id"])["invoice_no"]
    note_number = store.get_refund("rfnd_pdf")["credit_no"]

    for url, name in ((f"/api/payments/invoice/{order['token']}/pdf", f"invoice-{number.replace('/', '-')}.pdf"),
                      (f"/api/payments/credit-note/{order['token']}/rfnd_pdf/pdf",
                       f"credit-note-{note_number.replace('/', '-')}.pdf")):
        response = client.get(url)
        assert response.status_code == 200, (url, response.text[:200])
        assert response.headers["content-type"] == "application/pdf"
        # A file to forward, not a page to read: the file name carries the document's own number, with the
        # "/" replaced because it is a path separator on every platform.
        assert f'filename="{name}"' in response.headers["content-disposition"]
        assert response.headers["cache-control"] == "private, no-store"
        assert response.content.startswith(b"%PDF-") and len(response.content) > 2000
        pages = pdf_page_count(response.content)
        assert pages == 1, f"{url} printed {pages} pages; a one-page document should be one page"

    # the HTML is still served, and still where the order page points for reading
    assert client.get(f"/api/payments/invoice/{order['token']}").status_code == 200
    view = service.public_view(store.get_order(order["id"]), reveal_token=True)
    assert view["invoice_url"].endswith(order["token"]) and view["invoice_pdf_url"].endswith("/pdf")
    page = client.get(f"/order/{order['token']}").text
    assert view["invoice_pdf_url"] in page and view["invoice_url"] in page
    assert view["credit_notes"][0]["pdf_url"] in page

    # a second download is served from the content cache: no second browser for a document that cannot change
    from app.pdf.service import documents_dir
    before = sorted(p.name for p in documents_dir().glob("*.pdf"))
    assert client.get(f"/api/payments/invoice/{order['token']}/pdf").status_code == 200
    assert sorted(p.name for p in documents_dir().glob("*.pdf")) == before


def test_the_order_email_carries_the_invoice_links(rzp, jobs):
    """A receipt that names the invoice and links the file, because forwarding it to an accountant is what
    people do with one. Only when the sale actually has an invoice: a sentence about a document that does not
    exist is worse than silence."""
    from app.payments import order_email

    client = TestClient(app)
    order = store.get_order(_a_paid_order(client)["id"])
    _, _, body = order_email.compose(order)
    assert order["invoice_no"] in body
    assert f"/api/payments/invoice/{order['token']}/pdf" in body
    assert f"/api/payments/invoice/{order['token']}\n" in body or \
           f"/api/payments/invoice/{order['token']})" in body
    assert body.startswith(order_email.TEXTS[order["language"]][1].split("{")[0])

    _, _, without = order_email.compose({**order, "invoice_no": None})
    assert "invoice" not in without.lower() and "इनव्हॉइस" not in without


def test_the_backfill_issues_a_missing_credit_note_oldest_refund_first(rzp, jobs, capsys):
    """The live test refund on 2026-09-29 was processed before credit notes existed, so one has to be issued
    by hand. Read-only unless asked, because this allocates numbers in a series claimed to be consecutive and
    a number cannot be given back - and OLDEST FIRST, or a January refund backfilled after a March one would
    be numbered in the order somebody ran a script."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import issue_credit_notes

    client = TestClient(app)
    order = _a_paid_order(client)
    refund_webhook(client, order["id"], "rfnd_old", 1000, event_id="evt_old", created_at=1780000000)
    refund_webhook(client, order["id"], "rfnd_new", 2000, event_id="evt_new", created_at=1790000000)
    # Two refunds as they would have been recorded before this code existed: no notes, and the counter never
    # advanced either. Both parts matter - leaving the counter at 2 would number the backfill 3 and 4, which
    # is the RIGHT behaviour for a number that was really allocated (a number is never reused) and the wrong
    # setup for a database where these notes never existed.
    with db.transaction() as conn:
        conn.execute("UPDATE webhook_refunds SET credit_no = NULL, base_paise = NULL, gst_paise = NULL")
        conn.execute("DELETE FROM invoice_numbers WHERE series LIKE 'CN%'")

    assert issue_credit_notes.main([]) == 0                       # lists, changes nothing
    listing = capsys.readouterr().out
    assert "2 refund(s) with no credit note" in listing and "nothing was changed" in listing
    assert store.get_refund("rfnd_old")["credit_no"] is None

    assert issue_credit_notes.main(["--issue"]) == 0
    assert capsys.readouterr().out.count("-> RK-CN/") == 2
    # the older refund gets the earlier number, whatever order the script was run in
    assert store.get_refund("rfnd_old")["credit_no"] == "RK-CN/2627/00001"
    assert store.get_refund("rfnd_new")["credit_no"] == "RK-CN/2627/00002"

    assert issue_credit_notes.main(["--issue"]) == 0              # idempotent: nothing left to do
    assert "no refund is waiting" in capsys.readouterr().out


def test_the_invoice_states_a_refund_rather_than_staying_silent(rzp, jobs):
    """An invoice that says nothing about a refund asserts, by omission, that the money was kept. It is not a
    credit note - that needs its own series and is still an open question with the accountant."""
    from app.payments import invoice

    client = TestClient(app)
    order = _a_paid_order(client)
    # Invoice-level, not a line item: the refund is about the document, not about what was sold.
    assert invoice.context(store.get_order(order["id"]))["refund"] is None
    refund_webhook(client, order["id"], "rfnd_inv", 100)
    got = invoice.context(store.get_order(order["id"]))["refund"]
    assert got["state"] == "partial" and got["id"] == "rfnd_inv"
    html = client.get(f"/api/payments/invoice/{order['token']}").text
    assert "Refunded:" in html and "rfnd_inv" in html and "credit note" in html.lower()
    # and it NAMES the note, rather than leaving the reader to go and look for it
    number = store.get_refund("rfnd_inv")["credit_no"]
    assert number and f"Reversed by credit note {number}" in html
    assert invoice.context(store.get_order(order["id"]))["credit_notes"] == [number]
