"""Real-browser check of the Phase 5 "done when": on /consultation the 3rd message shows the paywall card.

    LD_LIBRARY_PATH=~/.local/share/astro-chromium/root/usr/lib/x86_64-linux-gnu \\
        .venv/bin/python scripts/browser_check_consultation.py [OUT_DIR]

Self-contained: starts the real app on a free local port *inside this process*, with the AI client replaced
by a canned fake (there is deliberately no env flag in the app that could switch the AI off in production),
a temporary database, and then drives headless Chromium through the page on a phone and a desktop viewport.
Needs Playwright (not in requirements.txt), see scripts/browser_check.py. Exit code 0 = all checks passed.
"""

import os
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path



ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from reference_charts import PRIMARY  # noqa: E402

# A public, independently published chart - never anyone's personal birth record.
REFERENCE_BIRTH = PRIMARY.request()

# Prices and product ids come from the catalogue, never from a literal here: a hard-coded 199 is
# exactly what made this check describe a product we no longer sell.
from app.payments import catalogue, razorpay  # noqa: E402

PACK = catalogue.item(catalogue.BASIC_PACK)
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "var" / "browser_check"

_tmp = tempfile.mkdtemp(prefix="consultation-check-")
os.environ.update(APP_DB=f"{_tmp}/app.db", SESSION_SECRET="browser-check", CHAT_RATE_PER_MINUTE="100",
                  CHAT_FREE_PER_IP_PER_DAY="100")

import uvicorn  # noqa: E402

from app import db  # noqa: E402
from app.ai import chat, chat_routes, chat_store  # noqa: E402
from app.ai.client import ChatResult  # noqa: E402
from app.main import app  # noqa: E402

REPLIES = [
    "With Shani in Kumbha in your 7th house, steady and patient effort in partnerships pays off. Your Rahu mahadasha "
    "favours learning new skills.\n\nAstrology is a traditional faith-based practice, offered as guidance.",
    "तुमच्या कुंडलीत चंद्र धनु राशीत पंचम स्थानात आहे, त्यामुळे शिक्षण आणि सर्जनशील कामात तुम्हाला समाधान मिळते. शनिवारी गरजूंना अन्नदान करा.",
]


class FakeChat:
    calls = 0

    def generate_chat(self, *, system, messages):
        FakeChat.calls += 1
        time.sleep(0.6)  # long enough to see the typing indicator
        return ChatResult(text=REPLIES[(FakeChat.calls - 1) % len(REPLIES)], model="fake", usage={})


chat.get_chat_client = lambda: FakeChat()
chat_routes.STARTS_PER_HOUR = 1000


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

    with sync_playwright() as p:
        browser = p.chromium.launch()
        for name, viewport in [("mobile", {"width": 390, "height": 844}), ("desktop", {"width": 1280, "height": 900})]:
            print(f"[{name}]")
            FakeChat.calls = 0
            with db.transaction() as conn:  # same birth details + same IP would (rightly) get no second free trial
                conn.execute("DELETE FROM chat_free_buckets")
                conn.execute("DELETE FROM rate_events")
            context = browser.new_context(viewport=viewport, has_touch=(name == "mobile"))
            page = context.new_page()
            logs, purchases = [], []
            page.on("console", lambda m: logs.append(f"{m.type}: {m.text}") if m.type in ("error", "warning") else None)
            page.on("pageerror", lambda e: logs.append(f"PAGEERROR: {e}"))
            page.goto(f"{base}/consultation")
            check(page.locator("#result").is_hidden() and page.locator("#chat-paywall").is_hidden(), "chat hidden before start")

            page.fill("#self-name", "Keshav")
            page.fill("#self-date", REFERENCE_BIRTH["date"])
            page.fill("#self-time", REFERENCE_BIRTH["time"])
            page.fill("#self-city", "mir")
            page.locator("#self-city-list [role=option]").first.click()
            page.click("#submit-btn")
            page.wait_for_selector("#chat-form:visible")
            check("Simha" in page.inner_text("#result-body") and "Dhanu" in page.inner_text("#result-body"), "chart summary header shown")
            check(page.inner_text("#chat-quota") == "2 free questions left", "quota shows 2 free questions")
            check(page.locator("#chat-start").is_hidden(), "birth form collapses once the chat opens")

            page.fill("#chat-input", "How is my career?")
            page.click("#chat-send")
            page.wait_for_selector("#chat-typing:visible")
            page.wait_for_selector(".chat__msg--assistant:not(.chat__msg--hint)")
            check(page.inner_text("#chat-quota") == "1 free question left", "1st reply delivered, 1 free question left")

            page.fill("#chat-input", "माझे शिक्षण कसे राहील?")
            page.press("#chat-input", "Enter")
            page.wait_for_selector("#chat-paywall:visible")
            check(page.locator(".chat__msg--assistant:not(.chat__msg--hint)").count() == 2, "2nd reply delivered (Marathi)")
            check("धनु" in page.locator(".chat__msg--assistant").last.inner_text(), "Devanagari reply rendered")
            check(page.locator("#chat-form").is_hidden(), "input replaced by the paywall card after 2 free replies")
            paywall = page.inner_text("#chat-paywall")
            check(f"₹{PACK.price_inr}" in paywall and str(PACK.messages) in paywall,
                  f"paywall says ₹{PACK.price_inr} for {PACK.messages}")

            # a 3rd message forced through the API from the page still gets 402 and no AI call
            status = page.evaluate("""async () => (await fetch('/api/consultation/message', {method: 'POST',
                headers: {'Content-Type': 'application/json'}, credentials: 'same-origin',
                body: JSON.stringify({session_id: sessionStorage.getItem('consultation-session'), message: 'third'})})).status""")
            check(status == 402 and FakeChat.calls == 2, f"3rd message -> HTTP 402, AI calls stay at 2 (status {status}, calls {FakeChat.calls})")

            page.evaluate("document.addEventListener('product:purchase', e => { window.__purchase = e.detail; })")
            page.click("#chat-buy")
            detail = page.evaluate("window.__purchase")
            check(detail and detail["product"] == PACK.product and detail["priceInr"] == PACK.price_inr
                  and bool(detail["sessionId"]),
                  f"paywall button fires product:purchase with {PACK.product}, price and sessionId")
            # What happens next depends on whether Razorpay keys are present: with payments ON, pay.js
            # handles the event and opens checkout; with them OFF, the page shows the launching-soon
            # note. Asserting one of those unconditionally is how this check went stale.
            if razorpay.configured():
                check(not page.locator("#cta-notice").is_visible(),
                      "payments configured -> pay.js handles the event, no launching-soon note")
            else:
                check(page.locator("#cta-notice").is_visible(),
                      "payments not configured -> 'payment launching soon' note")

            overflow = page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth")
            check(not overflow, "no horizontal overflow")
            page.screenshot(path=str(OUT / f"consultation-{name}-paywall.png"), full_page=True)

            page.reload()
            page.wait_for_selector("#chat-paywall:visible")
            check(page.locator(".chat__msg--user").count() == 2, "conversation and paywall restored after reload")

            # Phase 6 path: credit a pack server-side, tell the page, chat re-opens
            chat_store.credit_session(detail["sessionId"], 10, reference=f"check-{name}")
            page.evaluate("document.dispatchEvent(new CustomEvent('consultation:credited'))")
            page.wait_for_selector("#chat-form:visible")
            check(page.inner_text("#chat-quota") == "10 questions left", "after crediting a pack: input back, 10 questions left")
            page.fill("#chat-input", "When will I die?")
            page.click("#chat-send")
            page.wait_for_function("() => document.querySelectorAll('.chat__msg--assistant:not(.chat__msg--hint)').length === 3")
            check("don't make predictions" in page.locator(".chat__msg--assistant").last.inner_text()
                  and page.inner_text("#chat-quota") == "10 questions left" and FakeChat.calls == 2,
                  "death question: fixed safe reply, not counted, no AI call")
            page.screenshot(path=str(OUT / f"consultation-{name}-chat.png"), full_page=True)
            unexpected = [entry for entry in logs if "402" not in entry]  # the forced 3rd message logs its 402 on purpose
            check(not unexpected, f"no unexpected console errors {unexpected or ''}")
            context.close()
        browser.close()
    server.should_exit = True
    print(f"\n{'FAILED: ' + str(len(failures)) if failures else 'ALL CHECKS PASSED'} - screenshots in {OUT}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
