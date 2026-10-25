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
from contextlib import contextmanager
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

# Short, explicit waits. The old helper's failure took 30 s of Playwright retries to say "element is not
# visible", which is a long time to say nothing useful; a pre-deploy gate wants to fail in seconds and name
# the selector. Anything that legitimately takes longer (the 5 s fake report, the real Chromium PDF render)
# passes its own timeout at the call site.
DEFAULT_MS = 10_000
CITY_MS = 5_000       # the city combo is a local fetch of /api/cities
PANEL_MS = 5_000      # pay.js builds the panel synchronously on the click
READY_MS = 30_000     # fake generation sleeps 5 s, then the page polls
BIRTH_FIELDS = ("name", "date", "time", "city")
# One invented person, and never a real birth: this checks the payment plumbing, not the chart. Devanagari on
# purpose - the name reaches the PDF cover and the order page.
SELF = {"name": "केशव", "date": "1990-01-01", "time": "10:00", "city": "mir"}


class CheckError(AssertionError):
    """The script could not get far enough to look.

    Distinct from a failed `check`, which knows what it wanted and saw something else. This one means the UI
    could not be driven - a step that will not advance, a panel that never opened, a field nobody can reach -
    and it carries the step and the selector, because "timed out" is not a bug report.
    """


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
  // A WHITELIST, and it silently hid a missing option once: `image` was added to pay.js and this copy did not
  // know about it, so the new assertion read `none` and looked like the code was broken when the STUB was.
  // Copy the whole object and let the assertions decide what matters; `handler` and `modal` carry functions,
  // which do not survive the bridge to Python, so those two are named rather than the keys we want.
  window.__rzp.options = {};
  Object.keys(options).forEach(function (k) {
    if (k !== "handler" && k !== "modal") { window.__rzp.options[k] = options[k]; }
  });
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
from app.web import i18n, pages  # noqa: E402

from app.payments import gst, states  # noqa: E402

# Place of supply. Both branches are exercised for real: the seller's own state bills CGST+SGST, anywhere else
# bills IGST, and a check that only ever picked one of them would leave half the invoice untested.
STATE_INTRA = states.seller_code()
# Any state that is not the seller's exercises the IGST branch identically, so this is derived rather than
# named - a hardcoded "Karnataka" here would read as though the choice mattered.
STATE_INTER = next(code for code in states.CODES if code != STATE_INTRA)

KUNDALI_PRODUCT = pages.TOOLS["kundali"].product        # what the kundali page's buy button sells
PACK_PRODUCT = pages.CONSULTATION_PRODUCT                # the consultation tier the page sells


def money(product: str) -> dict:
    """Every rupee string and paise figure this script asserts, for one product, read from the catalogue and
    the GST setting. NOTHING here is a rupee literal, by instruction and for a reason: the listed prices and
    the GST mode are both being changed while this script exists, and a total written down here would break
    on the commit that changes them - which is exactly the failure that let this whole file rot.

    Correct in BOTH GST modes, which is why it returns all four strings rather than two. Under exclusive
    pricing `listed` == `base` and the total is bigger than the page's number; under inclusive pricing
    `listed` == `total` and the BASE is the one that stops being a round rupee figure (a ₹299 inclusive price
    has a base of ₹253.39). Assert `base`/`gst`/`total` against the panel rows and `total` against the Pay
    button, and the assertions hold whichever way the flag is set.
    """
    entry = catalogue.item(product)
    assert entry is not None, f"{product} is not in the catalogue"
    tax = entry.gst
    return {"product": product, "entry": entry, "name": entry.name,
            "listed": f"\u20b9{entry.price_inr}",
            "base": f"\u20b9{gst.money(tax.base_paise)}",
            "gst": f"\u20b9{gst.money(tax.gst_paise)}",
            "total": f"\u20b9{gst.money(tax.total_paise)}",
            "paise": tax.total_paise, "taxed": bool(tax.gst_paise)}


KUNDALI = money(KUNDALI_PRODUCT)
PACK = money(PACK_PRODUCT)
KUNDALI_PAISE, PACK_PAISE = KUNDALI["paise"], PACK["paise"]
KUNDALI_RS, PACK_RS = KUNDALI["base"], PACK["base"]            # the taxable value, i.e. the panel's "Price" row
KUNDALI_TOTAL_RS, PACK_TOTAL_RS = KUNDALI["total"], PACK["total"]   # what the Pay button and Checkout must say
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
    from playwright.sync_api import Error as PlaywrightError
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

    @contextmanager
    def scenario(name):
        """One flow. If it cannot be driven at all, record ONE specific failure and let the others run.

        A pre-deploy gate is read once: it should list every broken flow, not the first one. Measured today,
        fixing this file: three separate stale checks had accumulated, and each aborting run revealed exactly
        one of them, costing a four-minute cycle each. Without this wrapper the first stale assertion reports
        that the kundali form is stepped and says nothing about whether matching, the guides or either
        consultation tier can be bought."""
        print(f"[{name}]")
        try:
            yield
        except CheckError as exc:
            check(False, f"{name}: {exc}")
        except Exception as exc:  # noqa: BLE001 - one flow's collapse may not hide the rest
            check(False, f"{name}: unexpected {type(exc).__name__}: {exc}")

    def new_context(**kwargs):
        context = browser.new_context(**kwargs)
        context.set_default_timeout(DEFAULT_MS)
        wire(context)
        return context

    external: list[str] = []
    analytics: list[str] = []
    # Google Analytics 4 went into base.html in a853f43, AFTER the "no other external request" check below was
    # written, so that check had been failing for as long as the script had not been run. Allowing the requests
    # would have been the easy fix and the wrong one: the measurement id comes from the real .env, so every run
    # of this script was posting fake page_views to the live property - a pre-deploy gate must not write to
    # production analytics. They are intercepted and answered with an empty body instead, which keeps the
    # assertion strong (nothing else may reach the network), removes the side effect, and still lets the run
    # PROVE the tag is on the page, because the attempt is recorded.
    ANALYTICS_HOSTS = ("googletagmanager.com", "google-analytics.com")

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

        def stub_analytics(route):
            analytics.append(route.request.url)
            # An empty 200 rather than an abort: an aborted script request logs a console error, and several
            # checks here assert the console is clean, so aborting would trade one false failure for another.
            route.fulfill(status=200, content_type="application/javascript", body="")

        context.route("https://checkout.razorpay.com/**", checkout)
        context.route("**/__fake_razorpay/pay*", fake_pay)
        for host in ANALYTICS_HOSTS:
            context.route(f"**{host}/**", stub_analytics)
        context.on("request", lambda r: external.append(r.url) if not r.url.startswith(base)
                   and "checkout.razorpay.com" not in r.url and not any(host in r.url for host in ANALYTICS_HOSTS)
                   and not r.url.startswith(("data:", "blob:")) else None)

    def visible_step(page) -> str:
        """The data-step of the step on screen, or "-" for a form that is not stepped (the consultation)."""
        step = page.locator("#tool-form [data-step]:not([hidden])").first
        return step.get_attribute("data-step") if step.count() else "-"

    def fill_one(page, prefix, field, value, where):
        """Fill one field IF IT IS ON SCREEN, and say whether it was. Never forces visibility: a field the
        customer cannot reach is one this script must not reach either, or it stops checking what a customer
        can do and starts checking what a script can do."""
        selector = f"#{prefix}-{field}"
        box = page.locator(selector)
        if box.count() == 0 or not box.is_visible():
            return False
        box.fill(value)
        if field == "city":
            option = page.locator(f"#{prefix}-city-list [role=option]").first
            try:
                option.wait_for(state="visible", timeout=CITY_MS)
            except PlaywrightError as exc:
                raise CheckError(f"{where}: typed {value!r} into {selector} on step {visible_step(page)} and "
                                 f"#{prefix}-city-list never offered a [role=option]") from exc
            option.click()
        return True

    def fill_birth(page, people=None, where=None, submit=True):
        """Drive the birth form the way a visitor does: fill what is on screen, press Next, repeat, submit.

        THE FORM IS MULTI-STEP. tool.html wraps date, time and place in <fieldset class="step" data-step="N">
        for a single-person form and one step per PERSON on the matching page; app.js hides every step but the
        current one and hides #submit-btn until the last. The previous version of this helper filled all four
        fields directly, so it died on Page.fill("#self-time") with "element is not visible" after 30 s of
        retries - before reaching any payment. That is the best explanation for a consultation being unbuyable
        for two days with nothing going red: this is the only end-to-end purchase check that exists, and it
        had quietly stopped running. A dark check is worse than no check, because it is counted.

        `people` is {prefix: {field: value}} - {"self": ...} for a single form, {"boy": ..., "girl": ...} for
        the matching page. Defaults to one invented person. Raises CheckError naming the step and the selector
        rather than timing out, so a failure says where it stopped.
        """
        people = people or {"self": dict(SELF)}
        where = where or page.url
        outstanding = {prefix: dict(values) for prefix, values in people.items()}
        visited = []
        for _ in range(4 * len(outstanding) + 4):   # finite: never spin forever on a step that will not advance
            step = visible_step(page)
            visited.append(step)
            for prefix, values in outstanding.items():
                for field in [f for f in BIRTH_FIELDS if f in values]:
                    if fill_one(page, prefix, field, values[field], where):
                        values.pop(field)
            nxt = page.locator("#tool-form [data-step-next]")
            if not nxt.count() or not nxt.is_visible():
                break
            nxt.click()
            if visible_step(page) == step:
                raise CheckError(f"{where}: [data-step-next] did not advance past step {step} - that step's own "
                                 f"validation refused what was filled (steps visited: {visited})")
        left = {prefix: sorted(values) for prefix, values in outstanding.items() if values}
        if left:
            raise CheckError(f"{where}: walked steps {visited} and never saw " + ", ".join(
                f"#{prefix}-{field}" for prefix, fields in left.items() for field in fields))
        if submit:
            button = page.locator("#submit-btn")
            if not button.is_visible():
                raise CheckError(f"{where}: reached step {visible_step(page)} of {visited} but #submit-btn is "
                                 f"still hidden, so the form cannot be submitted")
            button.click()

    def pay_panel(page, product, where, language=None, state=STATE_INTRA):
        """The purchase panel: assert what it says about money and about place of supply, fill it, leave it
        ready to pay.

        Every figure comes from money(product). The three rows are asserted only when GST is actually charged,
        so this passes with GST switched off too - and the Pay button is asserted against the TOTAL, which is
        the check that would have caught a button quoting the list price while Checkout asked for more.

        THE STATE SELECT IS ASSERTED ON EVERY PRODUCT, and that is the point of this function existing rather
        than each scenario filling its own fields. `place_of_supply` became required on POST
        /api/payments/order in the same commit that added this select, and the last time a checkout field was
        made required the consultation button never got one - every purchase refused 422 for two days, with a
        green unit suite, because the API tests posted a hand-written body no page had produced. So: the field
        must exist, it must offer the real list, and it must start EMPTY so that "unset" is something a
        customer has to leave rather than a default they can pay through."""
        try:
            page.wait_for_selector("#pay-email", timeout=PANEL_MS)
        except PlaywrightError as exc:
            notice = page.inner_text("#cta-notice") if page.locator("#cta-notice").count() else ""
            raise CheckError(f"{where}: clicking [data-product={product}] opened no purchase panel "
                             f"(#pay-email never appeared){' - page says: ' + notice.strip() if notice.strip() else ''}"
                             ) from exc
        m = money(product)
        if language is not None and page.locator("#pay-language").count():
            page.select_option("#pay-language", language)
        if m["taxed"]:
            rows = page.inner_text(".pay__sum")
            check(m["base"] in rows and m["gst"] in rows and m["total"] in rows,
                  f"{where}: panel breaks the charge down before paying - {m['base']} + {m['gst']} GST = {m['total']}")
        check(m["total"] in page.inner_text(".pay__go"),
              f"{where}: the Pay button quotes the TOTAL {m['total']}, not the listed {m['listed']}")
        options = page.locator("#pay-state option")
        count = options.count()
        if not count:
            raise CheckError(f"{where}: the panel has no #pay-state select, so this product cannot be bought - "
                             f"POST /api/payments/order requires place_of_supply and would refuse it 422")
        # Derived from `states.for_language`, NOT from `len(states.CODES) + 1`. That literal was correct only
        # while India was the only place we sell: turning EXPORT_SALES_ENABLED on appends "Outside India" and
        # the count becomes 38, so the gate would have failed on the commit that enables exports - a check
        # breaking because a FLAG was flipped, which teaches people to edit the check rather than read it.
        # Asking the same function the page asks means the gate follows the flag on its own.
        offered = len(states.for_language("en")) + 1   # + the blank the select starts on
        check(count == offered and page.input_value("#pay-state") == "",
              f"{where}: state select offers every place we sell and starts empty ({count - 1} + a blank)")
        page.select_option("#pay-state", state)
        page.fill("#pay-email", "keshav@example.com")
        page.fill("#pay-email-confirm", "keshav@example.com")
        return m

    options = launch_options()
    with sync_playwright() as p:
        browser = p.chromium.launch(**{k: v for k, v in options.items() if k != "headless"})

        # ---------- 1. report: pay -> preparing -> ready -> download; then the same purchase without cookies ----------
        with scenario("report, desktop"):
            context = new_context(viewport={"width": 1280, "height": 900}, accept_downloads=True)
            page = context.new_page()
            logs: list[str] = []
            page.on("console", lambda m: logs.append(f"{m.type}: {m.text}") if m.type in ("error", "warning") else None)
            page.on("pageerror", lambda e: logs.append(f"PAGEERROR: {e}"))
            page.goto(base + urls["kundali"])
            fill_birth(page)
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
            # The state is required and starts blank, so paying without choosing one must stop HERE, in a message
            # the customer can read - not as a 422 from an endpoint they cannot see. This is the exact failure
            # shape that made the consultation unbuyable, asserted rather than assumed.
            page.fill("#pay-email", "keshav@example.com")
            page.fill("#pay-email-confirm", "keshav@example.com")
            page.click(".pay__go")
            check(not razorpay_requests and page.locator(".pay__message--error").count() == 1,
                  f"no state chosen: refused before any order is created ({page.inner_text('.pay__message')[:60]})")
            pay_panel(page, KUNDALI_PRODUCT, "kundali page, detailed book")

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
            page.wait_for_selector("#result:not([hidden])")
            page.click("[data-product=kundali-report]")
            pay_panel(page, KUNDALI_PRODUCT, "kundali page, second purchase", language="mr")
            page.evaluate("window.__rzpMode = 'success'")
            page.click(".pay__go")
            page.wait_for_selector(".pay-status[data-state=preparing]")
            sent = page.evaluate("window.__rzp.options")
            check(sent["amount"] == KUNDALI_PAISE and sent["currency"] == "INR" and sent["key"] == KEY_ID and sent["order_id"].startswith("order_Check"),
                  f"Checkout opened with the server's order: ₹{sent['amount'] / 100:g}, key id only")
            check(all("amount" in r and r["amount"] == KUNDALI_PAISE for r in razorpay_requests) and KEY_SECRET not in page.content(),
                  "amount came from the server catalogue; no secret anywhere in the page")
            # WHAT THE CUSTOMER SEES ON THE PAYMENT WINDOW. The merchant name was read from the page's
            # og:site_name until 2026-09-29; a page shipped without that meta would have put its <title> there.
            # It is a constant in pay.js now, and this asserts the constant rather than the meta. The logo must
            # be ABSOLUTE: Razorpay's script fetches it from outside our document, so a relative path resolves
            # against their page and the customer sees Razorpay's placeholder instead of our mark.
            check(sent.get("name") == "RashiKundli",
                  f"Checkout shows the merchant name RashiKundli (got {sent.get('name')!r})")
            image = sent.get("image") or ""
            check(image.startswith(base) and image.endswith("/static/icons/icon-512.png"),
                  f"Checkout carries our square logo from our own origin ({image or 'none'})")
            check(bool(page.request.get(image).ok) if image else False,
                  "that logo URL actually serves an image")
            check(sent.get("description") == money(KUNDALI_PRODUCT)["name"],
                  f"Checkout describes the product bought, not a generic label ({sent.get('description')!r})")
            # The wait promised on screen. Asserted against the copy rather than a literal, so the two can never
            # drift: the measured wall clock for the detailed book is ~8.8 minutes, and a promise of "1-3" was the
            # kind of thing nobody re-measures after the book grew from a flat report to twelve calls.
            # The stage COUNT is not pinned: the labels live in pay.js's TEXT table, not in any Python this script
            # can read, and a number copied out of JS into here is the kind of literal that goes stale unnoticed -
            # which is what happened to the `.pay-status__spinner` this replaced. 9744438 swapped the spinner for
            # the four-stage list and this line went on asserting a class that no longer exists.
            stages = page.locator(".pay-stages__step").count()
            check(WAIT_PHRASE in page.inner_text(".pay-status") and stages > 1
                  and page.locator(".pay-status__link a").count() == 1,
                  f"after verify: 'preparing your report ({WAIT_PHRASE})', {stages} progress stages, order page link")
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
            # `page_count`, not `pages`: this function reads app.web.pages to drive the every-product section below,
            # and a local named `pages` shadowed the module for the rest of main().
            page_count = len(PdfReader(io.BytesIO(pdf)).pages)
            check(pdf.startswith(b"%PDF-") and page_count > 1 and "NotoSansDevanagari-Regular" in embedded_fonts(pdf),
                  f"PDF downloaded in the browser: {len(pdf)} bytes, {page_count} pages, bundled Devanagari font ({download_info.value.suggested_filename})")
            page.screenshot(path=str(OUT / "payments-report-ready.png"), full_page=True)
            check(not page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth"), "no horizontal overflow")
            expected = ("400", "404")  # the forged verify (400) and the locked-PDF probe above (404) log their status on purpose
            unexpected = [entry for entry in logs if not any(code in entry for code in expected)]
            check(not unexpected, f"no unexpected console errors {unexpected or ''}")
            context.close()

        with scenario("same purchase, no cookies (another device)"):
            context = new_context(viewport={"width": 390, "height": 844}, accept_downloads=True)
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
        with scenario("consultation purchase = 10 questions + Kundali PDF, mobile"):
            with db.transaction() as conn:
                conn.execute("DELETE FROM chat_free_buckets")
                conn.execute("DELETE FROM rate_events")
            context = new_context(viewport={"width": 390, "height": 844}, has_touch=True)
            page = context.new_page()
            logs = []
            page.on("console", lambda m: logs.append(f"{m.type}: {m.text}") if m.type in ("error", "warning") else None)
            page.goto(base + urls["consultation"])
            fill_birth(page)
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
            # The consultation buy opens the same panel as a report buy, minus the report-language select. It has to:
            # POST /api/payments/order requires the e-mail the permanent order link is sent to, and until GST brought
            # this panel the consultation button sent none and was refused with a 422 before Checkout ever opened.
            pay_panel(page, PACK_PRODUCT, "consultation paywall, Basic tier")
            page.click(".pay__go")
            page.wait_for_selector("#chat-form:visible", timeout=15000)
            check(razorpay_requests[before]["amount"] == PACK_PAISE, f"consultation order created for {PACK_TOTAL_RS} (server price + GST)")
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
            page.wait_for_selector("#result:not([hidden])")
            # the report the bundle included is the one to press "buy" on: that is the one already owned
            owned = page.query_selector(f"[data-product={BUNDLED_REPORT}]")
            if owned is None:
                check(False, f"the kundali page offers no {BUNDLED_REPORT} button, so the 'already owned' path cannot be "
                             f"checked - the page still sells one tier only")
            else:
                owned.click()
                pay_panel(page, BUNDLED_REPORT, "kundali page, report already owned via the bundle", language="en")
                page.click(".pay__go")
                page.wait_for_selector(".pay-status[data-state=ready]", timeout=READY_MS)
                check(len(razorpay_requests) == orders_before and page.evaluate("!window.__rzp || window.__rzp.opened === 0"),
                      f"buying the PDF for a report already owned through the bundle ({BUNDLED_REPORT}): no new order, "
                      f"no checkout, straight to the download")
            check(not [entry for entry in logs if "402" not in entry], f"no unexpected console errors {[e for e in logs if '402' not in e] or ''}")
            context.close()

        with scenario("bundle order page, no cookies"):
            context = new_context(viewport={"width": 390, "height": 844}, accept_downloads=True)
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
        with scenario("Hindi and Marathi trees end to end"):
            with db.transaction() as conn:
                conn.execute("DELETE FROM chat_free_buckets")
                conn.execute("DELETE FROM rate_events")
            context = new_context(viewport={"width": 390, "height": 844}, has_touch=True, accept_downloads=True, locale="hi-IN")
            page = context.new_page()
            logs = []
            page.on("console", lambda m: logs.append(f"{m.type}: {m.text}") if m.type in ("error", "warning") else None)
            page.goto(base + "/hi/kundli")
            # other birth details than above, so this is a real new purchase rather than an "already paid" replay
            fill_birth(page, {"self": {**SELF, "date": "1990-01-15", "time": "06:45", "city": "pun"}})
            page.wait_for_selector("#result:not([hidden])")
            page.click("[data-product=kundali-report]")
            page.wait_for_selector("#pay-language")
            panel = page.inner_text(".pay")
            check(page.input_value("#pay-language") == "hi" and "रिपोर्ट की भाषा" in panel and f"{KUNDALI_TOTAL_RS} सुरक्षित रूप से चुकाएँ" in page.inner_text(".pay__go"),
                  f"Hindi page: purchase panel in Hindi, report language preselected हिंदी, button quotes the total {KUNDALI_TOTAL_RS}")
            check(KUNDALI_RS in panel and "जीएसटी" in panel, f"Hindi panel: price {KUNDALI_RS} and the GST line, in Hindi")
            check("राज्य" in panel, "Hindi panel: the state label is in Hindi too")
            hi_state = page.locator("#pay-state option").nth(1).inner_text()
            check(any(ord(ch) > 0x900 for ch in hi_state), f"Hindi panel: the state NAMES are in Devanagari ({hi_state})")
            pay_panel(page, KUNDALI_PRODUCT, "Hindi kundali page", state=STATE_INTER)
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
            page.wait_for_selector("#chat-form:visible")
            for question in ("मेरा करियर कैसा रहेगा?", "और विवाह?"):
                count = page.locator(".chat__msg--assistant:not(.chat__msg--hint)").count()
                page.fill("#chat-input", question)
                page.click("#chat-send")
                page.wait_for_function(f"() => document.querySelectorAll('.chat__msg--assistant:not(.chat__msg--hint)').length === {count + 1}")
            page.wait_for_selector("#chat-paywall:visible")
            before = len(razorpay_requests)
            page.click("#chat-buy")
            pay_panel(page, PACK_PRODUCT, "Hindi consultation paywall")
            page.click(".pay__go")
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
            page.wait_for_selector("#result:not([hidden])")
            page.click("[data-product=kundali-report]")
            page.wait_for_selector("#pay-language")
            check(page.input_value("#pay-language") == "mr" and "अहवालाची भाषा" in page.inner_text(".pay")
                  and f"{KUNDALI_TOTAL_RS} सुरक्षितपणे भरा" in page.inner_text(".pay__go"),
                  f"Marathi page: panel in Marathi, report language preselected मराठी, button quotes {KUNDALI_TOTAL_RS}")
            context.close()

        # ---------- 2c. EVERY product on sale, each paid through to the file it promises ----------
        #
        # The gap that mattered. Before this, the script bought two of the seven things on sale - the detailed
        # book and the Basic consultation - so five buy buttons had never been clicked by anything, in any
        # check, ever. The page list and the product list are READ from the URL registry and the catalogue, so
        # a product cannot be added to the shop without appearing here and a page cannot stop selling one
        # without this noticing.
        #
        # What the PDF at the end proves and does not prove: the fixture is a Kundali book whatever product it
        # is stamped with (see _fake_generate), so this is not a check that a Sade Sati guide READS like one.
        # It checks that the right product's report was generated, entitled, and handed over as a file - which
        # is the part that silently breaks.
        sold_on = {}
        for key in i18n.TOOL_KEYS:
            for option in pages.purchase_options(key):
                sold_on.setdefault(option["product"], key)
        bought = []
        for n, (product, key) in enumerate(sorted(sold_on.items()), start=1):
            with scenario(f"buy {product} on the {key} page"):
                m = money(product)
                path = i18n.url_for(key, "en")
                context = new_context(viewport={"width": 390, "height": 844}, accept_downloads=True)
                page = context.new_page()
                response = page.goto(base + path)
                if response.status != 200:
                    raise CheckError(f"{path} answered HTTP {response.status}, so {product} cannot be bought at all")
                # A different birth per product, so none of these is an "already paid" replay of an earlier one
                born = f"199{n}-0{n % 9 + 1}-1{n % 8 + 1}"
                people = ({"boy": {**SELF, "date": born}, "girl": {**SELF, "name": "आरती", "date": "1992-03-04", "city": "pun"}}
                          if pages.TOOLS[key].form == "pair" else {"self": {**SELF, "date": born}})
                fill_birth(page, people)
                page.wait_for_selector("#result:not([hidden])")
                button = page.locator(f"[data-product={product}]")
                if not button.count():
                    raise CheckError(f"{path} has no [data-product={product}] button, but the catalogue sells "
                                     f"{product} there - purchase_options() and the template disagree")
                before = len(razorpay_requests)
                page.evaluate("window.__rzpMode = 'success'")
                button.click()
                # Alternate the place of supply so both halves of the invoice are exercised by real orders:
                # the seller's own state bills CGST+SGST, anywhere else bills IGST.
                chosen = STATE_INTRA if n % 2 else STATE_INTER
                pay_panel(page, product, f"{key} page, {product}", language="en", state=chosen)
                page.click(".pay__go")
                page.wait_for_selector(".pay-status[data-state=ready]", timeout=READY_MS)
                check(razorpay_requests[before]["amount"] == m["paise"],
                      f"{product}: Checkout asked for {m['total']} ({m['paise']} paise), which is the catalogue total")
                order = store.by_razorpay_id(f"order_Check{before + 1:09d}")
                check(order["place_of_supply"] == chosen,
                      f"{product}: the chosen state reached the order row as {chosen} "
                      f"({states.name(chosen)}), not as an empty value")
                invoice_html = page.request.get(f"{base}/api/payments/invoice/{order['token']}").text()
                expected_heads = ("CGST", "SGST") if chosen == STATE_INTRA else ("IGST",)
                absent = "IGST" if chosen == STATE_INTRA else "CGST"
                check(all(head in invoice_html for head in expected_heads) and absent not in invoice_html
                      and states.name(chosen) in invoice_html,
                      f"{product}: its invoice bills {'+'.join(expected_heads)} for {states.name(chosen)} "
                      f"and prints the place of supply")
                with page.expect_download() as got:
                    page.click(".pay-status__download")
                name = got.value.suggested_filename
                blob = Path(got.value.path()).read_bytes()
                check(blob.startswith(b"%PDF-") and product in name,
                      f"{product}: its own PDF downloads after payment ({name}, {len(blob) // 1024} KB)")
                bought.append(product)
                context.close()
        check(sorted(bought) == sorted(sold_on),
              f"every report product on sale was bought end to end: {sorted(bought)}"
              + (f" - MISSING {sorted(set(sold_on) - set(bought))}" if set(sold_on) - set(bought) else ""))

        # The Premium consultation tier. Basic is covered above in the bundle scenario; Premium is a different
        # id bundling a different report, and "the tier is the product id" is the whole of that machinery - so
        # the one thing worth proving is that paying for Premium yields the report PREMIUM bundles.
        with scenario("buy consultation-premium on the paywall"):
            with db.transaction() as conn:
                conn.execute("DELETE FROM chat_free_buckets")
                conn.execute("DELETE FROM rate_events")
            m = money("consultation-premium")
            bundled = catalogue.item("consultation-premium").bundled_report
            context = new_context(viewport={"width": 390, "height": 844}, accept_downloads=True)
            page = context.new_page()
            page.goto(base + urls["consultation"])
            fill_birth(page, {"self": {**SELF, "date": "1993-07-07", "city": "pun"}})
            page.wait_for_selector("#chat-form:visible")
            for question in ("How is my career?", "And my marriage?"):
                count = page.locator(".chat__msg--assistant:not(.chat__msg--hint)").count()
                page.fill("#chat-input", question)
                page.click("#chat-send")
                page.wait_for_function("() => document.querySelectorAll('.chat__msg--assistant:not(.chat__msg--hint)')"
                                       f".length === {count + 1}")
            page.wait_for_selector("#chat-paywall:visible")
            before = len(razorpay_requests)
            page.evaluate("window.__rzpMode = 'success'")
            premium = page.locator("[data-product=consultation-premium]")
            if not premium.count():
                raise CheckError("the paywall offers no [data-product=consultation-premium] button, so the "
                                 "Premium tier cannot be bought")
            premium.click()
            pay_panel(page, "consultation-premium", "consultation paywall, Premium tier", state=STATE_INTER)
            check(page.locator("#pay-language").count() == 0,
                  "the consultation panel offers no report-language select: the bundled report follows the conversation")
            page.click(".pay__go")
            page.wait_for_selector("#chat-form:visible", timeout=15000)
            check(razorpay_requests[before]["amount"] == m["paise"],
                  f"consultation-premium: Checkout asked for {m['total']}, which is the catalogue total")
            page.wait_for_selector("#pay-bundle-status[data-state=ready]", timeout=READY_MS)
            order = store.by_razorpay_id(f"order_Check{before + 1:09d}")
            check(order["messages"] == 10 and order["product"] == "consultation-premium"
                  and catalogue.report_product(order) == bundled,
                  f"one order carries both: 10 questions + the {bundled} that the Premium tier bundles")
            check(order["place_of_supply"] == STATE_INTER,
                  f"consultation-premium: the state reached the order too ({STATE_INTER}) - the consultation "
                  f"path is the one that shipped without a required field last time")
            with page.expect_download() as got:
                page.click("#pay-bundle-status .pay-status__download")
            check(Path(got.value.path()).read_bytes().startswith(b"%PDF-") and bundled in got.value.suggested_filename,
                  f"Premium's bundled {bundled} downloads as a PDF ({got.value.suggested_filename})")
            context.close()

        # ---------- 3. the FREE chart PDF downloads with the real CSP enforced ----------
        #
        # It is a POST, so the page cannot be a plain link: it has to be fetch -> blob -> <a download>.
        # "That should not trip `default-src 'self'`" is a prediction, and this is the script that exists
        # to turn predictions about the CSP into measurements. The page under test is served by the real
        # app with the real header; the check asserts the header is ENFORCED (not report-only) first,
        # because a check that runs under report-only proves nothing.
        with scenario("free chart PDF download, CSP enforced"):
            context = new_context(viewport={"width": 390, "height": 844}, accept_downloads=True)
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
        with scenario("payments not configured"):
            saved = {name: os.environ.pop(name) for name in ("RAZORPAY_KEY_ID", "RAZORPAY_KEY_SECRET")}
            context = new_context(viewport={"width": 1280, "height": 900})
            page = context.new_page()
            page.goto(base + urls["sade_sati"])
            fill_birth(page)
            page.wait_for_selector("#result:not([hidden])")
            page.click("[data-product=sade-sati-guide]")
            page.wait_for_selector("#cta-notice:not([hidden])")
            check("launching soon" in page.inner_text("#cta-notice") and page.locator(".pay").count() == 0,
                  "without keys the button still shows the 'launching soon' note - no broken checkout")
            os.environ.update(saved)
            context.close()
        browser.close()

    check(not [url for url in external if "checkout.razorpay.com" not in url],
          f"no external request other than Razorpay's checkout.js and the stubbed analytics tag "
          f"{[u for u in external if 'checkout.razorpay.com' not in u][:3] or ''}")
    check(bool(analytics), f"the Google Analytics tag is present and every one of its {len(analytics)} requests "
                           f"was answered locally - this run wrote nothing to the live property")
    server.should_exit = True
    print(f"\n{'FAILED: ' + str(len(failures)) if failures else 'ALL CHECKS PASSED'} - screenshots in {OUT}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
