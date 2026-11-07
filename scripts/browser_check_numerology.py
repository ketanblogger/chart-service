"""Real-browser check of the two numerology things the QA round could not test by reading code.

    LD_LIBRARY_PATH=~/.local/share/astro-chromium/root/usr/lib/x86_64-linux-gnu \\
        .venv/bin/python scripts/browser_check_numerology.py [OUT_DIR]

1. THE REPORT'S "CONTINUE", up to but NOT including payment. The form reveals the buy panel, the
   panel posts an order, and the run stops there - Razorpay's checkout is never opened.
2. THE MOBILE LAYOUT at 390px on the calculator, a mulank page, the number checker and the report
   page: no sideways scroll, nothing spilling out of the viewport, and tap targets big enough.

NO LIVE KEYS, EVER. Razorpay is replaced by a fake in this process: nothing reaches their API and
no real order can be created, which is why this is safe to run on a laptop. The standing rule is
that payment checks never run against live keys, and a check that needs them is the wrong check.

NO EMAIL. An order e-mail is sent on verify/webhook - after a payment - and this stops before that.
The mailer is stubbed anyway and the run FAILS if anything tries to send: asserting it is cheaper
than reasoning about it. The database is a throwaway temp file, so the test order it writes exists
only inside this process and is gone when it exits.
"""

import json
import os
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "var" / "browser_check_numerology"

_tmp = tempfile.mkdtemp(prefix="numerology-check-")
WEBHOOK_SECRET = "browser-check-webhook"
os.environ.update(APP_DB=f"{_tmp}/app.db", SESSION_SECRET="browser-check",
                  RAZORPAY_KEY_ID="rzp_test_browsercheck", RAZORPAY_KEY_SECRET="not-a-real-secret",
                  RAZORPAY_WEBHOOK_SECRET=WEBHOOK_SECRET,
                  REPORTS_DIR=f"{_tmp}/reports", PDFS_DIR=f"{_tmp}/pdfs",
                  ORDERS_PER_HOUR_PER_IP="1000", ORDERS_PER_HOUR_PER_USER="1000")

import uvicorn  # noqa: E402

from app import mailer  # noqa: E402
from app.main import app  # noqa: E402
from app.payments import razorpay  # noqa: E402
from app.web import i18n  # noqa: E402

# ---- the fakes -----------------------------------------------------------------------------------

SENT: list[str] = []
ORDERS: list[dict] = []


def _record_mail(to, subject, text, *args, **kwargs):
    """Record a mail instead of sending one.

    IT NO LONGER REFUSES. Until the post-payment path was added here, any attempt to send was a
    failure - nothing in this run should have reached a mailer. Now the run goes all the way to a
    delivered order, and the e-mail with the download link IS part of what must work, so it is
    recorded and asserted. Nothing leaves the process either way: no transport is configured.
    """
    SENT.append({"to": to, "subject": subject})
    return True


mailer.send = _record_mail
mailer.send_recorded = _record_mail

razorpay.configured = lambda: True
razorpay.webhook_configured = lambda: True
razorpay.is_test_mode = lambda: True
razorpay.key_id = lambda: "rzp_test_browsercheck"


def _fake_order(amount_paise: int, receipt: str, notes=None, currency: str = "INR") -> dict:
    """What Razorpay would have returned. Nothing leaves this process."""
    ORDERS.append({"amount": amount_paise, "receipt": receipt, "notes": notes or {}})
    return {"id": f"order_fake{len(ORDERS):04d}", "amount": amount_paise, "currency": currency,
            "receipt": receipt, "status": "created"}


razorpay.create_order = _fake_order
razorpay.order_payments = lambda order_id: []

# ---- past payment ---------------------------------------------------------------------------------
#
# THE WHOLE REASON THIS SECTION EXISTS. This check used to stop at Razorpay's door: it created an
# order, blocked checkout.js and called that a pass. So webhook -> fulfilment -> PDF -> e-mail had
# never run once for the numerology report, in any test, and a real customer's paid order failed
# five times on 5 November with the suite green. A captured payment is simulated by posting the
# event Razorpay would post, signed with the same secret - no money, no live key, no checkout.

from app.payments import service as payments_service  # noqa: E402

WRITTEN: list[str] = []


def _fake_report(product, language, births, *, as_of, numerology_facts=None):
    """A report without an AI call. The PDF below is rendered for real from it - the deliverable is
    the thing being checked, and it must not depend on a billed call to be checked."""
    from app.ai import report as report_module

    assert numerology_facts and numerology_facts.get("mulank"), (
        "fulfilment called the writer with no numerology_facts - the 5 November failure")
    WRITTEN.append(language)
    rid = report_module.report_id(product, language, [], as_of,
                                  report_module.facts_digest(numerology_facts))
    built = {"id": rid, "product": product, "language": language, "as_of": as_of.isoformat(),
             "sections": [{"key": "your_numbers", "title": "Your numbers",
                           "body": "Your mulank is 2 and your bhagyank is 4."}],
             "disclaimer": "Astrology is a traditional faith-based practice, offered as guidance.",
             "meta": {"model": "browser-check"}}
    report_module._save_report(built)
    return built


payments_service.generate_report = _fake_report
payments_service._spawn = lambda fn, *a: fn(*a)      # fulfil inline, so the page can be checked


def _capture(base: str, razorpay_order_id: str, paise: int) -> dict:
    """Post the webhook Razorpay posts when a payment is captured."""
    import hashlib
    import hmac
    import urllib.request

    payload = {"entity": "event", "account_id": "acc_BrowserCheck", "event": "payment.captured",
               "contains": ["payment"], "created_at": 1790000000,
               "payload": {"payment": {"entity": {"id": "pay_BrowserCheck01", "entity": "payment",
                                                  "amount": paise, "currency": "INR",
                                                  "status": "captured", "order_id": razorpay_order_id,
                                                  "captured": True,
                                                  "email": "nobody@example.invalid"}}}}
    body = json.dumps(payload, separators=(",", ":")).encode()
    request = urllib.request.Request(
        f"{base}/api/payments/webhook", data=body, method="POST",
        headers={"Content-Type": "application/json",
                 "X-Razorpay-Event-Id": "evt_browser_check",
                 "X-Razorpay-Signature": hmac.new(WEBHOOK_SECRET.encode(), body,
                                                  hashlib.sha256).hexdigest()})
    with urllib.request.urlopen(request, timeout=30) as reply:
        return json.loads(reply.read())


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> int:
    from playwright.sync_api import sync_playwright

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.05)
    base = f"http://127.0.0.1:{port}"
    OUT.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []

    def check(condition, label):
        print(("  ok   " if condition else "  FAIL ") + label)
        if not condition:
            failures.append(label)

    # Filled inside the browser block, used after it: the PDF renderer is itself Playwright, and
    # driving sync Playwright from inside a sync Playwright context is refused by the library.
    delivered: dict = {}

    with sync_playwright() as p:
        browser = p.chromium.launch()

        # ---- 1. the report form's Continue, stopping before payment ------------------------------
        print("[report: Continue -> order, no payment]")
        context = browser.new_context(viewport={"width": 390, "height": 844}, has_touch=True)
        page = context.new_page()
        problems: list[str] = []
        page.on("console", lambda m: problems.append(f"{m.type}: {m.text}")
                if m.type == "error" else None)
        page.on("pageerror", lambda e: problems.append(f"PAGEERROR: {e}"))
        # Razorpay's own script must never be reached from a laptop run.
        blocked: list[str] = []
        context.route("https://checkout.razorpay.com/**",
                      lambda route: (blocked.append(route.request.url), route.abort()))

        page.goto(f"{base}{i18n.url_for('numerology', 'en')}")
        page.fill("#num-name", "Asha Vernekar")
        page.select_option("select[name=year]", "1988")
        page.select_option("select[name=month]", "3")
        page.select_option("select[name=day]", "29")
        page.click("button[type=submit]")
        page.wait_for_selector(".numerology-result")
        check(page.locator(".num-card__working").count() == 2, "the result shows its working")

        # THE CARD IS THE PRIMARY OFFER NOW, and a form rather than a link.
        check(page.locator(".report-card").count() == 1, "the report card is on the result")
        order = page.evaluate("""() => {
            const card = document.querySelector('.report-card');
            const chat = document.querySelector('.ask-box');
            const grid = document.querySelector('.lo-shu');
            return {card: !!card, beforeChat: card && chat ? (card.compareDocumentPosition(chat) & 4) > 0 : null,
                    afterGrid: card && grid ? (grid.compareDocumentPosition(card) & 4) > 0 : null};
        }""")
        check(order["beforeChat"] is True, "the report card comes before the chat card")
        check(order["afterGrid"] is True, "the report card sits under the Lo Shu grid")
        check(page.locator(".report-card__personal").count() == 1, "it reads this reader's grid back")
        check(page.locator(".report-card__preview").count() == 1, "it shows a page of the real report")

        # THE STICKY BAR, and that it covers nothing.
        page.wait_for_timeout(300)
        bar = page.locator("#report-bar")
        check(bar.is_visible(), "the sticky bar is shown on a phone after a calculation")
        covered = page.evaluate("""() => {
            const bar = document.getElementById('report-bar');
            if (!bar || bar.hidden) return null;
            const r = bar.getBoundingClientRect();
            // Anything the bar sits on top of at its own midpoint, other than itself.
            const under = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
            return {padded: document.body.classList.contains('has-report-bar'),
                    overlaps: under ? !bar.contains(under) : false};
        }""")
        check(covered and covered["padded"], "the page carries padding for the bar")
        check(covered and not covered["overlaps"], "the bar covers no page content")
        page.screenshot(path=str(OUT / "result-card-390.png"), full_page=False)
        page.click("#report-bar-dismiss")
        check(not page.locator("#report-bar").is_visible(), "the bar can be dismissed")
        check(not page.evaluate("() => document.body.classList.contains('has-report-bar')"),
              "dismissing it gives the padding back")

        # NOTHING IDENTIFYING IN A URL, which is the whole point of the handover.
        hrefs = page.evaluate("() => Array.from(document.links).map(a => a.getAttribute('href'))")
        leaky = [h for h in hrefs if h and ("name=" in h or "date=" in h or "&day=" in h)]
        check(not leaky, f"no link carries a name or a date ({leaky[:3]})")

        # the card's form carries them instead, in a body
        page.locator(".report-card__form button[type=submit]").click()
        page.wait_for_selector("#rep-name")
        check("name=" not in page.url and "day=" not in page.url,
              f"the report page's own URL carries nothing identifying ({page.url})")
        check(page.input_value("#rep-name") == "Asha Vernekar", "report form has the name prefilled")
        check(page.input_value("select[name=day]") == "29", "report form has the date prefilled")
        page.screenshot(path=str(OUT / "report-prefilled-390.png"), full_page=True)

        # "Continue" reveals the buy panel; nothing is bought by pressing it
        buy = page.locator("button[data-product=numerology-report]")
        check(buy.count() == 1, "the buy button is ready on arrival")
        before = len(ORDERS)
        buy.click()
        page.wait_for_selector(".pay", timeout=10000)
        check(len(ORDERS) == before, "opening the panel creates no order")
        page.screenshot(path=str(OUT / "report-pay-panel-390.png"), full_page=True)

        # The panel's own form: this is the step that creates the order.
        #
        # FILL IT AFTER IT HAS SETTLED. pay.js asks the server for a known e-mail address and
        # rebuilds the e-mail row when that answer arrives, which wiped a value typed too early -
        # the panel then said "Please enter your e-mail address" and no order was made. There are
        # TWO e-mail fields (the address and its confirmation) and a required place of supply.
        panel = page.locator(".pay")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(400)
        emails = panel.locator("input[type=email]")
        for i in range(emails.count()):
            emails.nth(i).fill("nobody@example.invalid")
        for i in range(panel.locator("select").count()):
            sel = panel.locator("select").nth(i)
            options = [v for v in sel.locator("option").evaluate_all(
                "els => els.map(e => e.value)") if v]
            if options:
                sel.select_option(options[0])
        check(panel.locator(".pay__go").count() == 1, "the panel has its pay button")
        panel.locator(".pay__go").first.click()   # pay.js's own button, not a guess
        page.wait_for_timeout(1200)
        message = panel.locator(".pay__message")
        if message.count() and message.first.inner_text().strip():
            print(f"       panel says: {message.first.inner_text().strip()[:120]}")
        page.wait_for_timeout(2500)
        check(len(ORDERS) == before + 1, f"Continue created exactly one order (got {len(ORDERS) - before})")
        if len(ORDERS) > before:
            order = ORDERS[-1]
            check(order["amount"] == 19900, f"the order is for Rs 199 ({order['amount']} paise)")
        check(not SENT, f"nothing tried to send mail ({SENT})")
        # WHERE THE RUN STOPS, stated as the thing it is. Creating the order is the last step before
        # payment; fetching Razorpay's checkout.js is the FIRST step of payment, and this run blocks
        # it at the network. My first version asserted the script was "never fetched", which was
        # wrong about the flow: the page is supposed to ask for it, and the point is that it never
        # arrives. The console error below is the abort, not a page fault.
        check(len(blocked) == 1, f"the run stopped at the payment step, with checkout blocked ({blocked})")
        real = [x for x in problems if "ERR_FAILED" not in x and "checkout.razorpay" not in x]
        check(not real, f"no console errors other than the blocked checkout ({real[:3]})")
        page.screenshot(path=str(OUT / "report-after-continue-390.png"), full_page=True)

        # ---- PAST PAYMENT: the path that had never run -------------------------------------
        print("[past payment: webhook -> fulfilment -> PDF -> e-mail]")
        rzp_id = f"order_fake{len(ORDERS):04d}"
        captured = _capture(base, rzp_id, 19900)
        check(captured == {"status": "ok"}, f"the captured-payment webhook was accepted ({captured})")

        from app.payments import store as payments_store

        order = payments_store.by_razorpay_id(rzp_id)
        check(order is not None, "the order exists after the webhook")
        if order:
            check(order["status"] == "paid", f"the order is paid ({order['status']})")
            check(order["fulfilment"] == "ready",
                  f"fulfilment finished ({order['fulfilment']}: {(order.get('error') or '-')[:90]})")
            check(WRITTEN == ["en"], f"the report was written once, in the order's language ({WRITTEN})")
            check(len(SENT) == 1 and SENT[0]["to"] == "nobody@example.invalid",
                  f"exactly one e-mail was queued, to the buyer ({SENT})")

            from app.ai.report import load_report

            built = load_report(order["report_id"])
            check(built is not None, "the generated report was saved")
            delivered["order"] = order      # the PDF is rendered after this block - see below

            # AND WHAT THE CUSTOMER SEES. This is the screen that lied for three hours.
            page.goto(f"{base}/order/{order['token']}")
            page.wait_for_load_state("networkidle")
            # SCOPED TO THE ORDER BLOCK. Reading the whole body caught the site navigation's
            # "Birth Chart" menu link and the footer - the status text itself was already right.
            status = page.inner_text(".order")
            check("kundali" not in status.lower() and "chart" not in status.lower(),
                  f"the order page does not call a numerology report a chart ({status[:110]!r})")
            download = page.locator("a[href*='/pdf'], a[download], .btn--cta")
            check(download.count() > 0, "the order page offers the download")
            page.screenshot(path=str(OUT / "order-page-delivered-390.png"), full_page=True)
        context.close()

        # ---- 2. the mobile layout at 390px -------------------------------------------------------
        print("[mobile layout, 390px]")
        pages = [("calculator", i18n.url_for("numerology", "en")),
                 ("mulank", i18n.url_for("mulank", "en", number=2)),
                 ("checker", i18n.url_for("lo-shu", "en")),
                 ("report", i18n.url_for("numerology-report", "en"))]
        context = browser.new_context(viewport={"width": 390, "height": 844}, has_touch=True)
        for name, path in pages:
            page = context.new_page()
            page.goto(f"{base}{path}")
            page.wait_for_load_state("networkidle")
            width = page.evaluate("() => document.documentElement.scrollWidth")
            check(width <= 390, f"{name}: no sideways scroll (scrollWidth {width})")
            # anything actually sticking out past the viewport, named so it can be found
            spills = page.evaluate("""() => {
                const out = [];
                for (const el of document.querySelectorAll('body *')) {
                    const r = el.getBoundingClientRect();
                    if (r.width > 0 && r.right > 391.5)
                        out.push(el.tagName.toLowerCase() +
                                 (el.className && typeof el.className === 'string'
                                  ? '.' + el.className.split(' ')[0] : '') +
                                 ' right=' + Math.round(r.right));
                }
                return out.slice(0, 5);
            }""")
            check(not spills, f"{name}: nothing spills out of the viewport ({spills})")
            # tap targets: links and buttons a thumb has to hit
            small = page.evaluate("""() => {
                const out = [];
                for (const el of document.querySelectorAll('a.btn, button, .mulank-others a, .ask-box__chips a')) {
                    const r = el.getBoundingClientRect();
                    if (r.width > 0 && (r.height < 32 || r.width < 32))
                        out.push((el.textContent || '').trim().slice(0, 18) +
                                 ' ' + Math.round(r.width) + 'x' + Math.round(r.height));
                }
                return out.slice(0, 5);
            }""")
            check(not small, f"{name}: tap targets are big enough ({small})")
            page.screenshot(path=str(OUT / f"{name}-390.png"), full_page=True)
            page.close()
        context.close()
        browser.close()

    # ---- the deliverable, rendered outside the browser context --------------------------------
    if delivered.get("order"):
        print("[the deliverable]")
        from app.ai.report import load_report
        from app.pdf.service import ensure_pdf

        order = delivered["order"]
        pdf = ensure_pdf(load_report(order["report_id"]), order.get("names"))
        check(pdf.exists() and pdf.stat().st_size > 1000,
              f"a PDF the customer can open was rendered ({pdf.stat().st_size if pdf.exists() else 0} bytes)")

    print(f"\nscreenshots in {OUT}")
    if failures:
        print(f"{len(failures)} FAILED:")
        for label in failures:
            print(f"  - {label}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
