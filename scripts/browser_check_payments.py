"""Real-browser check of the payment flows: the report the kundali page sells (click -> order -> Razorpay Checkout
-> verify -> PDF download) and the consultation purchase (+10 questions AND the report that tier includes, both on
one order page) - plus the FREE chart PDF download, which is not a payment flow but is the other thing on that page
that hands the visitor a file. Every price and product id is read from app/payments/catalogue.py, never written here.

    .venv/bin/python scripts/browser_check_payments.py [OUT_DIR]

Self-contained and offline. Inside THIS process only (the app has no switch that could fake a payment in production):
- the real app runs on a free local port with a temporary database / report cache / PDF cache;
- Razorpay's REST API is an httpx.MockTransport (fake key id + secret from this file);
- report writing is replaced by "wait 5 s, then store the hand-written fixture report under the purchased id";
- https://checkout.razorpay.com/v1/checkout.js is intercepted by Playwright and replaced by a stub `Razorpay` class that
  "pays" by asking this script for a payment id + a signature made with the fake key secret (modes: success / dismiss /
  forged signature). Everything else - pay.js, the API, signature verification, entitlement, the order page and the PDF
  (real headless Chromium render with the bundled fonts) - is the production code.
Exit code 0 = all checks passed. What it cannot prove: the real Razorpay popup and real keys - see docs/PAYMENTS.md.
"""

import base64
import hashlib
import hmac
import io
import json
import os
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "var" / "browser_check"

KEY_ID, KEY_SECRET = "rzp_test_BrowserCheck01", "browser-check-key-secret"
_tmp = tempfile.mkdtemp(prefix="payments-check-")
os.environ.update(APP_DB=f"{_tmp}/app.db", REPORTS_DIR=f"{_tmp}/reports", PDFS_DIR=f"{_tmp}/pdfs", SESSION_SECRET="browser-check",
                  RAZORPAY_KEY_ID=KEY_ID, RAZORPAY_KEY_SECRET=KEY_SECRET, RAZORPAY_WEBHOOK_SECRET="browser-check-webhook",
                  CHAT_RATE_PER_MINUTE="100", CHAT_FREE_PER_IP_PER_DAY="100")
os.environ.pop("REPORTS_UNLOCKED", None)

import httpx  # noqa: E402
import uvicorn  # noqa: E402

from app import db  # noqa: E402
from app.ai import chat, chat_routes  # noqa: E402
from app.ai import report as report_module  # noqa: E402
from app.ai.client import ChatResult  # noqa: E402
from app.ai.products import PRODUCTS  # noqa: E402  (the double names the product it claims to be)
from app.main import app  # noqa: E402
from app.payments import razorpay, routes, service, store  # noqa: E402
from app.payments.order_page import STATUS, WAIT_RANGE  # noqa: E402  (the wait we promise, read from the copy)

# The book fixture: real engine data for a PUBLISHED chart with placeholder prose (no AI call, nobody's
# private birth data). Rebuilt by scripts/build_book_fixture.py.
FIXTURE = json.loads((ROOT / "tests/fixtures/kundali_book_mr.json").read_text(encoding="utf-8"))
# The wait this run should see on screen, built from the same table the page prints from: this script buys
# the DETAILED book, so it must be promised the detailed wait and never the simple one.
WAIT_PHRASE = STATUS["en"]["preparing"][1].split("This takes ", 1)[1].split(".", 1)[0].replace(
    "{wait}", WAIT_RANGE["detailed"])
assert WAIT_PHRASE.startswith(WAIT_RANGE["detailed"]) and "minute" in WAIT_PHRASE, WAIT_PHRASE
razorpay_requests: list[dict] = []
generated: list[str] = []


def _fake_razorpay(request: httpx.Request) -> httpx.Response:
    assert request.headers["authorization"] == "Basic " + base64.b64encode(f"{KEY_ID}:{KEY_SECRET}".encode()).decode()
    body = json.loads(request.content)
    razorpay_requests.append(body)
    return httpx.Response(200, json={"id": f"order_Check{len(razorpay_requests):09d}", "entity": "order", "status": "created",
                                     "amount": body["amount"], "currency": body["currency"], "receipt": body["receipt"]})


def _fake_generate(product, language, births, *, as_of):
    time.sleep(5)  # long enough to see and poll the "preparing your report" state
    report = json.loads(json.dumps(FIXTURE))
    report["id"] = report_module.report_id(product, language, births, as_of)
    # The fixture is a kundali-report (the detailed book), so the product MUST be overwritten: a double that
    # always claims to be the book entitles the wrong thing for a simple-tier bundle, and the bundled PDF
    # download 402s while every assertion here still passes. A fake may be simpler than reality, never more
    # cooperative than it.
    report["product"] = product
    entry = PRODUCTS.get(product)
    if entry is not None:
        report["product_name"] = entry.name
    report["language"], report["meta"]["as_of"] = language, as_of.isoformat()
    report_module._save_report(report)
    generated.append(report["id"])
    return report


class FakeChat:
    def generate_chat(self, *, system, messages):
        return ChatResult(text="Steady effort in partnerships pays off in this period.", model="fake", usage={})


razorpay._transport = httpx.MockTransport(_fake_razorpay)
service.generate_report = _fake_generate
chat.get_chat_client = lambda: FakeChat()
chat_routes.STARTS_PER_HOUR = routes.ORDERS_PER_HOUR_PER_USER = routes.ORDERS_PER_HOUR_PER_IP = 1000

CHECKOUT_STUB = """
window.__rzp = {opened: 0, options: null};
window.Razorpay = function (options) {
  var listeners = {};
  window.__rzp.options = {key: options.key, amount: options.amount, currency: options.currency, name: options.name,
                          description: options.description, order_id: options.order_id, prefill: options.prefill};
  this.on = function (name, fn) { listeners[name] = fn; };
  this.open = function () {
    window.__rzp.opened += 1;
    var mode = window.__rzpMode || "success";
    if (mode === "dismiss") { setTimeout(function () { options.modal.ondismiss(); }, 50); return; }
    fetch("/__fake_razorpay/pay?mode=" + mode + "&order_id=" + encodeURIComponent(options.order_id))
      .then(function (r) { return r.json(); }).then(function (payment) { options.handler(payment); });
  };
};
"""


# Page URLs: the new three-language tree if it is already routed, otherwise the pre-restructure URLs.
PAGE_CANDIDATES = {"kundali": ("/birth-chart", "/janam-kundali"), "consultation": ("/ai-astrologer", "/consultation"),
                   "sade_sati": ("/sade-sati-calculator", "/sade-sati")}
from app.payments import catalogue  # noqa: E402  (prices are never literals here)
from app.web import pages  # noqa: E402

KUNDALI_PRODUCT = pages.TOOLS["kundali"].product        # what the kundali page's buy button sells
PACK_PRODUCT = pages.CONSULTATION_PRODUCT                # the consultation tier the page sells
KUNDALI_PAISE = catalogue.item(KUNDALI_PRODUCT).amount_paise
PACK_PAISE = catalogue.item(PACK_PRODUCT).amount_paise
KUNDALI_RS = f"\u20b9{catalogue.item(KUNDALI_PRODUCT).price_inr}"
PACK_RS = f"\u20b9{catalogue.item(PACK_PRODUCT).price_inr}"
BUNDLED_REPORT = catalogue.item(PACK_PRODUCT).bundled_report


def _pages() -> dict[str, str]:
    from fastapi.testclient import TestClient

    client = TestClient(app)
    return {key: next((path for path in paths if client.get(path).status_code == 200), paths[-1]) for key, paths in PAGE_CANDIDATES.items()}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> int:
    from playwright.sync_api import sync_playwright

    from app.pdf.browser import embedded_fonts, launch_options

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.05)
    base = f"http://127.0.0.1:{port}"
    OUT.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    urls = _pages()
    print("pages under test:", urls)

    def check(condition, label):
        print(("  ok   " if condition else "  FAIL ") + label)
        if not condition:
            failures.append(label)

    external: list[str] = []

    def wire(context):
        def checkout(route):
            external.append(route.request.url)
            route.fulfill(status=200, content_type="application/javascript", body=CHECKOUT_STUB)

        def fake_pay(route):
            query = parse_qs(urlparse(route.request.url).query)
            order_id, payment_id = query["order_id"][0], f"pay_Check{int(time.time() * 1000) % 10 ** 9:09d}"
            secret = "somebody-guessing" if query["mode"][0] == "forged" else KEY_SECRET
            signature = hmac.new(secret.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()
            route.fulfill(status=200, content_type="application/json", body=json.dumps(
                {"razorpay_order_id": order_id, "razorpay_payment_id": payment_id, "razorpay_signature": signature}))

        context.route("https://checkout.razorpay.com/**", checkout)
        context.route("**/__fake_razorpay/pay*", fake_pay)
        context.on("request", lambda r: external.append(r.url) if not r.url.startswith(base) and "checkout.razorpay.com" not in r.url
                   and not r.url.startswith(("data:", "blob:")) else None)

    def fill_birth(page, who="self"):
        page.fill(f"#{who}-name", "केशव")
        page.fill(f"#{who}-date", "1990-01-01")   # any birth: this checks the payment plumbing, not the chart
        page.fill(f"#{who}-time", "10:00")
        page.fill(f"#{who}-city", "mir")
        page.locator(f"#{who}-city-list [role=option]").first.click()

    options = launch_options()
    with sync_playwright() as p:
        browser = p.chromium.launch(**{k: v for k, v in options.items() if k != "headless"})

        # ---------- 1. report: pay -> preparing -> ready -> download; then the same purchase without cookies ----------
        print("[report, desktop]")
        context = browser.new_context(viewport={"width": 1280, "height": 900}, accept_downloads=True)
        wire(context)
        page = context.new_page()
        logs: list[str] = []
        page.on("console", lambda m: logs.append(f"{m.type}: {m.text}") if m.type in ("error", "warning") else None)
        page.on("pageerror", lambda e: logs.append(f"PAGEERROR: {e}"))
        page.goto(base + urls["kundali"])
        fill_birth(page)
        page.click("#submit-btn")
        page.wait_for_selector("#result:not([hidden])")
        page.click("[data-product=kundali-report]")
        page.wait_for_selector("#pay-language")
        check(page.locator("#cta-notice").is_hidden(), "payments on: no 'launching soon' note, the purchase panel opens instead")
        check(page.locator("#pay-language option").all_inner_texts() == ["English", "हिंदी", "मराठी"], "language selector: English / हिंदी / मराठी")
        check(not any("checkout.razorpay.com" in url for url in external), "checkout.js is NOT loaded before the Pay click")
        page.select_option("#pay-language", "mr")
        page.fill("#pay-email", "not-an-email")
        page.click(".pay__go")
        check("e-mail" in page.inner_text(".pay__message") and not razorpay_requests, "bad optional e-mail is caught before any order is created")
        page.fill("#pay-email", "keshav@example.com")

        page.evaluate("window.__rzpMode = 'dismiss'")
        page.click(".pay__go")
        page.wait_for_function("() => document.querySelector('.pay__message') && /not completed/.test(document.querySelector('.pay__message').textContent)")
        first = store.by_razorpay_id(razorpay_requests and f"order_Check{1:09d}")
        check(first["status"] == "created" and first["fulfilment"] == "none", "checkout dismissed: order stays unpaid, clear message, can retry")
        check(sum("checkout.razorpay.com" in url for url in external) == 1, "checkout.js loaded lazily, exactly once, on the Pay click")

        page.evaluate("window.__rzpMode = 'forged'")
        page.click(".pay__go")
        page.wait_for_function("() => document.querySelector('.pay__message--error') && /verified|confirm/i.test(document.querySelector('.pay__message--error').textContent)")
        forged = store.by_razorpay_id(f"order_Check{2:09d}")
        locked = page.evaluate(f"async () => (await fetch('/api/report/{forged['report_id']}/pdf')).status")
        # 404, not 402: no report was ever generated for the unpaid order, so there is nothing to unlock (a generated one gives 402)
        check(forged["status"] == "created" and locked in (402, 404) and not generated,
              f"forged signature: verify rejected, order unpaid, no report job started, PDF route HTTP {locked}")
        page.screenshot(path=str(OUT / "payments-report-rejected.png"), full_page=True)

        page.reload()
        fill_birth(page)
        page.click("#submit-btn")
        page.wait_for_selector("#result:not([hidden])")
        page.click("[data-product=kundali-report]")
        page.select_option("#pay-language", "mr")
        page.evaluate("window.__rzpMode = 'success'")
        page.click(".pay__go")
        page.wait_for_selector(".pay-status[data-state=preparing]")
        sent = page.evaluate("window.__rzp.options")
        check(sent["amount"] == KUNDALI_PAISE and sent["currency"] == "INR" and sent["key"] == KEY_ID and sent["order_id"].startswith("order_Check"),
              f"Checkout opened with the server's order: ₹{sent['amount'] / 100:g}, key id only")
        check(all("amount" in r and r["amount"] == KUNDALI_PAISE for r in razorpay_requests) and KEY_SECRET not in page.content(),
              "amount came from the server catalogue; no secret anywhere in the page")
        # The wait promised on screen. Asserted against the copy rather than a literal, so the two can never
        # drift: the measured wall clock for the detailed book is ~8.8 minutes, and a promise of "1-3" was the
        # kind of thing nobody re-measures after the book grew from a flat report to twelve calls.
        check(WAIT_PHRASE in page.inner_text(".pay-status") and page.locator(".pay-status__spinner").count() == 1,
              f"after verify: 'preparing your report ({WAIT_PHRASE})' state with the order page link")
        order_url = page.get_attribute(".pay-status__link a", "href")
        page.screenshot(path=str(OUT / "payments-report-preparing.png"), full_page=True)
        page.wait_for_selector(".pay-status[data-state=ready]", timeout=30000)
        check(len(generated) == 1, "exactly one report job ran for the paid order")
        with page.expect_download() as download_info:
            page.click(".pay-status__download")
        pdf_path = OUT / "payments-downloaded-report.pdf"
        download_info.value.save_as(str(pdf_path))
        pdf = pdf_path.read_bytes()
        from pypdf import PdfReader
        pages = len(PdfReader(io.BytesIO(pdf)).pages)
        check(pdf.startswith(b"%PDF-") and pages > 1 and "NotoSansDevanagari-Regular" in embedded_fonts(pdf),
              f"PDF downloaded in the browser: {len(pdf)} bytes, {pages} pages, bundled Devanagari font ({download_info.value.suggested_filename})")
        page.screenshot(path=str(OUT / "payments-report-ready.png"), full_page=True)
        check(not page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth"), "no horizontal overflow")
        expected = ("400", "404")  # the forged verify (400) and the locked-PDF probe above (404) log their status on purpose
        unexpected = [entry for entry in logs if not any(code in entry for code in expected)]
        check(not unexpected, f"no unexpected console errors {unexpected or ''}")
        context.close()

        print("[same purchase, no cookies (another device)]")
        context = browser.new_context(viewport={"width": 390, "height": 844}, accept_downloads=True)
        wire(context)
        page = context.new_page()
        paid = store.by_razorpay_id(sent["order_id"])
        status = page.request.get(f"{base}/api/report/{paid['report_id']}/pdf").status
        check(status == 402, f"without cookie or token the report PDF is HTTP {status}")
        response = page.goto(base + order_url)
        check(response.status == 200 and "noindex" in response.headers.get("x-robots-tag", ""), "permanent order page opens from the link alone, noindex")
        from app.payments import order_page as order_text
        check(page.evaluate("document.documentElement.lang") == "mr" and order_text.STATUS["mr"]["ready"][0] in page.inner_text("#order-status")
              and KUNDALI_RS in page.inner_text(".order"), f"order page: paid {KUNDALI_RS}, report ready - in the order's language (Marathi)")
        with page.expect_download() as download_info:
            page.click(".pay-status__download")
        check(Path(download_info.value.path()).read_bytes().startswith(b"%PDF-"), "PDF downloads again from the order page (token access)")
        page.screenshot(path=str(OUT / "payments-order-page-mobile.png"), full_page=True)
        context.close()

        # ---------- 2. consultation pack on a phone ----------
        print("[consultation purchase = 10 questions + Kundali PDF, mobile]")
        with db.transaction() as conn:
            conn.execute("DELETE FROM chat_free_buckets")
            conn.execute("DELETE FROM rate_events")
        context = browser.new_context(viewport={"width": 390, "height": 844}, has_touch=True)
        wire(context)
        page = context.new_page()
        logs = []
        page.on("console", lambda m: logs.append(f"{m.type}: {m.text}") if m.type in ("error", "warning") else None)
        page.goto(base + urls["consultation"])
        fill_birth(page)
        page.click("#submit-btn")
        page.wait_for_selector("#chat-form:visible")
        for question in ("How is my career?", "And my marriage?"):
            count = page.locator(".chat__msg--assistant:not(.chat__msg--hint)").count()
            page.fill("#chat-input", question)
            page.click("#chat-send")
            page.wait_for_function(f"() => document.querySelectorAll('.chat__msg--assistant:not(.chat__msg--hint)').length === {count + 1}")
        page.wait_for_selector("#chat-paywall:visible")
        before = len(razorpay_requests)
        page.evaluate("window.__rzpMode = 'success'")
        page.click("#chat-buy")
        page.wait_for_selector("#chat-form:visible", timeout=15000)
        check(razorpay_requests[before]["amount"] == PACK_PAISE, f"consultation order created for {PACK_RS} (server price)")
        check(page.inner_text("#chat-quota") == "10 questions left", "after verified payment: paywall gone, '10 questions left'")
        page.wait_for_selector("#pay-bundle-status[data-state=preparing]")
        check("10 questions added" in page.inner_text("#pay-bundle-status") and "Kundali PDF" in page.inner_text("#pay-bundle-status"),
              "status box above the chat: questions added, the included Kundali PDF is being prepared")
        page.fill("#chat-input", "Third question, now paid")
        page.click("#chat-send")
        page.wait_for_function("() => document.querySelectorAll('.chat__msg--assistant:not(.chat__msg--hint)').length === 3")
        check(page.inner_text("#chat-quota") == "9 questions left", "a paid question is answered while the report is still being written (9 left)")
        page.screenshot(path=str(OUT / "payments-consultation-mobile.png"), full_page=True)
        jobs_before = len(generated)
        page.wait_for_selector("#pay-bundle-status[data-state=ready]", timeout=30000)
        bundle_order = store.by_razorpay_id(f"order_Check{before + 1:09d}")
        check(len(generated) == jobs_before or generated[-1] == bundle_order["report_id"], "the bundled report was generated for the consultation's birth details")
        check(bundle_order["language"] == "en" and bundle_order["messages"] == 10 and bundle_order["report_id"] in generated,
              "one order row carries both: 10 messages + kundali report (consultation language)")
        with page.expect_download() as download_info:
            page.click("#pay-bundle-status .pay-status__download")
        check(Path(download_info.value.path()).read_bytes().startswith(b"%PDF-"), "included Kundali PDF downloads from the consultation page")
        bundle_url = page.get_attribute("#pay-bundle-status .pay-status__link a", "href")
        page.screenshot(path=str(OUT / "payments-consultation-bundle-ready.png"), full_page=True)

        # the same person now opens the kundali page for the same details (English report): already theirs, no second charge
        orders_before = len(razorpay_requests)
        page.goto(base + urls["kundali"])
        fill_birth(page)
        page.click("#submit-btn")
        page.wait_for_selector("#result:not([hidden])")
        # the report the bundle included is the one to press "buy" on: that is the one already owned
        owned = page.query_selector(f"[data-product={BUNDLED_REPORT}]")
        if owned is None:
            check(False, f"the kundali page offers no {BUNDLED_REPORT} button, so the 'already owned' path cannot be "
                         f"checked - the page still sells one tier only")
        else:
            owned.click()
            page.select_option("#pay-language", "en")
            page.click(".pay__go")
            page.wait_for_selector(".pay-status[data-state=ready]")
            check(len(razorpay_requests) == orders_before and page.evaluate("!window.__rzp || window.__rzp.opened === 0"),
                  f"buying the PDF for a report already owned through the bundle ({BUNDLED_REPORT}): no new order, "
                  f"no checkout, straight to the download")
        check(not [entry for entry in logs if "402" not in entry], f"no unexpected console errors {[e for e in logs if '402' not in e] or ''}")
        context.close()

        print("[bundle order page, no cookies]")
        context = browser.new_context(viewport={"width": 390, "height": 844}, accept_downloads=True)
        wire(context)
        page = context.new_page()
        page.goto(base + bundle_url)
        page.wait_for_selector("#order-status .pay-status__download")
        text = page.inner_text(".order")
        check(PACK_RS in text and "10 questions added" in page.inner_text("#order-status") and "Kundali PDF is ready" in page.inner_text("#order-status"),
              f"one order page shows both parts of the {PACK_RS} purchase: 10 questions added + the Kundali PDF")
        with page.expect_download() as download_info:
            page.click("#order-status .pay-status__download")
        check(Path(download_info.value.path()).read_bytes().startswith(b"%PDF-"), "PDF downloads from the bundle's order page with the token alone")
        page.screenshot(path=str(OUT / "payments-bundle-order-page.png"), full_page=True)
        context.close()

        # ---------- 2b. Hindi tree end to end: /hi/kundli and /hi/ai-jyotish (the bundle); Marathi pay panel ----------
        print(f"[Hindi: {KUNDALI_RS} report on /hi/kundli + {PACK_RS} consultation on /hi/ai-jyotish]")
        with db.transaction() as conn:
            conn.execute("DELETE FROM chat_free_buckets")
            conn.execute("DELETE FROM rate_events")
        context = browser.new_context(viewport={"width": 390, "height": 844}, has_touch=True, accept_downloads=True, locale="hi-IN")
        wire(context)
        page = context.new_page()
        logs = []
        page.on("console", lambda m: logs.append(f"{m.type}: {m.text}") if m.type in ("error", "warning") else None)
        page.goto(base + "/hi/kundli")
        page.fill("#self-date", "1990-01-15")   # other birth details than above, so this is a real new purchase
        page.fill("#self-time", "06:45")
        page.fill("#self-city", "pun")
        page.locator("#self-city-list [role=option]").first.click()
        page.click("#submit-btn")
        page.wait_for_selector("#result:not([hidden])")
        page.click("[data-product=kundali-report]")
        page.wait_for_selector("#pay-language")
        panel = page.inner_text(".pay")
        check(page.input_value("#pay-language") == "hi" and "रिपोर्ट की भाषा" in panel and f"{KUNDALI_RS} सुरक्षित रूप से चुकाएँ" in page.inner_text(".pay__go"),
              f"Hindi page: purchase panel in Hindi, report language preselected हिंदी, server price {KUNDALI_RS}")
        page.screenshot(path=str(OUT / "payments-hi-panel.png"))
        before = len(razorpay_requests)
        page.evaluate("window.__rzpMode = 'success'")
        page.click(".pay__go")
        page.wait_for_selector(".pay-status[data-state=preparing]")
        check("भुगतान मिल गया" in page.inner_text(".pay-status") and razorpay_requests[before]["amount"] == KUNDALI_PAISE, "paid: Hindi 'preparing your report' state")
        page.wait_for_selector(".pay-status[data-state=ready]", timeout=30000)
        hi_order = store.by_razorpay_id(f"order_Check{before + 1:09d}")
        check(hi_order["language"] == "hi" and "आपकी रिपोर्ट तैयार है" in page.inner_text(".pay-status"), "Hindi report ordered (language=hi) and ready, status in Hindi")
        with page.expect_download() as download_info:
            page.click(".pay-status__download")
        check(Path(download_info.value.path()).read_bytes().startswith(b"%PDF-") and "-hi.pdf" in download_info.value.suggested_filename,
              f"Hindi PDF downloaded ({download_info.value.suggested_filename})")

        page.goto(base + "/hi/ai-jyotish")
        fill_birth(page)
        page.click("#submit-btn")
        page.wait_for_selector("#chat-form:visible")
        for question in ("मेरा करियर कैसा रहेगा?", "और विवाह?"):
            count = page.locator(".chat__msg--assistant:not(.chat__msg--hint)").count()
            page.fill("#chat-input", question)
            page.click("#chat-send")
            page.wait_for_function(f"() => document.querySelectorAll('.chat__msg--assistant:not(.chat__msg--hint)').length === {count + 1}")
        page.wait_for_selector("#chat-paywall:visible")
        before = len(razorpay_requests)
        page.click("#chat-buy")
        page.wait_for_selector("#chat-form:visible", timeout=15000)
        page.wait_for_selector("#pay-bundle-status")
        check(razorpay_requests[before]["amount"] == PACK_PAISE and "10" in page.inner_text("#chat-quota"), f"Hindi bundle: {PACK_RS} order, 10 questions credited at once")
        check("सवाल जोड़ दिए गए" in page.inner_text("#pay-bundle-status"), "bundle status box in Hindi (सवाल, like the page copy)")
        page.wait_for_selector("#pay-bundle-status[data-state=ready]", timeout=30000)
        hi_bundle = store.by_razorpay_id(f"order_Check{before + 1:09d}")
        check(hi_bundle["language"] == "hi" and hi_bundle["messages"] == 10 and hi_bundle["report_id"] in generated,
              "bundled Kundali report generated in the consultation's language (hi)")
        page.screenshot(path=str(OUT / "payments-hi-bundle.png"), full_page=True)
        expected = ("402",)
        check(not [e for e in logs if not any(code in e for code in expected)], f"no unexpected console errors {[e for e in logs if '402' not in e] or ''}")

        hi_order_url = page.get_attribute("#pay-bundle-status .pay-status__link a", "href")
        page.goto(base + hi_order_url)
        page.wait_for_selector("#order-status .pay-status__download")
        order_text_hi = page.inner_text(".order")
        check(page.evaluate("document.documentElement.lang") == "hi" and "आपका ऑर्डर" in order_text_hi and "10 सवाल जोड़ दिए गए" in order_text_hi
              and "कुंडली PDF तैयार है" in order_text_hi and PACK_RS in order_text_hi and "Your order" not in order_text_hi,
              "Hindi bundle's order page is entirely in Hindi: both parts, amount, download")
        page.screenshot(path=str(OUT / "payments-hi-order-page.png"), full_page=True)

        page.goto(base + "/mr/kundali")
        fill_birth(page)
        page.click("#submit-btn")
        page.wait_for_selector("#result:not([hidden])")
        page.click("[data-product=kundali-report]")
        page.wait_for_selector("#pay-language")
        check(page.input_value("#pay-language") == "mr" and "अहवालाची भाषा" in page.inner_text(".pay") and f"{KUNDALI_RS} सुरक्षितपणे भरा" in page.inner_text(".pay__go"),
              f"Marathi page: purchase panel in Marathi, report language preselected मराठी, {KUNDALI_RS}")
        context.close()

        # ---------- 3. the FREE chart PDF downloads with the real CSP enforced ----------
        #
        # It is a POST, so the page cannot be a plain link: it has to be fetch -> blob -> <a download>.
        # "That should not trip `default-src 'self'`" is a prediction, and this is the script that exists
        # to turn predictions about the CSP into measurements. The page under test is served by the real
        # app with the real header; the check asserts the header is ENFORCED (not report-only) first,
        # because a check that runs under report-only proves nothing.
        print("[free chart PDF download, CSP enforced]")
        context = browser.new_context(viewport={"width": 390, "height": 844}, accept_downloads=True)
        wire(context)
        page = context.new_page()
        logs = []
        page.on("console", lambda m: logs.append(m.text) if "Content Security Policy" in m.text else None)
        response = page.goto(base + urls["kundali"])
        policy = response.headers.get("content-security-policy", "")
        check("default-src 'self'" in policy and "content-security-policy-report-only" not in response.headers,
              "the page under test carries an ENFORCED CSP with default-src 'self'")
        page.evaluate("""() => { window.__csp = [];
            document.addEventListener('securitypolicyviolation',
                event => window.__csp.push(event.violatedDirective + ' <- ' + event.blockedURI)); }""")

        download_js = """async (body) => {
            const response = await fetch('/api/chart/pdf', {
                method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
            if (!response.ok) return 'status ' + response.status;
            const url = URL.createObjectURL(await response.blob());
            const link = document.createElement('a');
            link.href = url;
            link.download = 'basic-chart.pdf';
            document.body.appendChild(link);
            link.click();
            setTimeout(() => URL.revokeObjectURL(url), 10000);
            return 'ok';
        }"""
        birth = {"date": "1990-01-01", "time": "10:00", "city": "Miraj", "language": "en", "name": "केशव"}
        with page.expect_download(timeout=60000) as downloaded:
            outcome = page.evaluate(download_js, birth)
        check(outcome == "ok", f"POST /api/chart/pdf from the page returned a blob ({outcome})")
        saved = Path(downloaded.value.path())
        blob = saved.read_bytes()
        check(blob.startswith(b"%PDF-") and len(blob) > 20_000,
              f"fetch -> blob -> <a download> hands over a real PDF ({len(blob) // 1024} KB), CSP and all")
        check(downloaded.value.suggested_filename.endswith(".pdf"), "the browser treats it as a file, not a navigation")
        check(not embedded_fonts(blob) - {"NotoSans-Regular", "NotoSans-Bold",
                                          "NotoSansDevanagari-Regular", "NotoSansDevanagari-Bold"},
              "the free sheet embeds only the bundled fonts")
        violations = page.evaluate("window.__csp") + logs
        check(not violations, f"no CSP violation anywhere on the download path {violations[:3] or ''}")
        # and the same download again is served from cache without spending a render
        with page.expect_download(timeout=60000):
            page.evaluate(download_js, birth)
        check(True, "a repeat download of the same sheet is served again (from the cache)")
        page.screenshot(path=str(OUT / "free-chart-download.png"), full_page=True)
        context.close()

        # ---------- 4. payments not configured: nothing breaks ----------
        print("[payments not configured]")
        saved = {name: os.environ.pop(name) for name in ("RAZORPAY_KEY_ID", "RAZORPAY_KEY_SECRET")}
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        wire(context)
        page = context.new_page()
        page.goto(base + urls["sade_sati"])
        fill_birth(page)
        page.click("#submit-btn")
        page.wait_for_selector("#result:not([hidden])")
        page.click("[data-product=sade-sati-guide]")
        page.wait_for_selector("#cta-notice:not([hidden])")
        check("launching soon" in page.inner_text("#cta-notice") and page.locator(".pay").count() == 0,
              "without keys the button still shows the 'launching soon' note - no broken checkout")
        os.environ.update(saved)
        context.close()
        browser.close()

    check(not [url for url in external if "checkout.razorpay.com" not in url], f"no other external request was made {[u for u in external if 'checkout.razorpay.com' not in u][:3] or ''}")
    server.should_exit = True
    print(f"\n{'FAILED: ' + str(len(failures)) if failures else 'ALL CHECKS PASSED'} - screenshots in {OUT}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
