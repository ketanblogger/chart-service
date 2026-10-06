"""The sign-in gate as a browser meets it: fresh context, no cookies, gate ON, all three languages.

This is the guard for a bug that reached the live site. Every other chat test runs with the gate off or
with a session cookie already set, so none of them is ever a VISITOR - and a visitor was the only one who
saw the failure. The whole point of this file is that it has no cookie.
"""

import socket
import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

PAGES = {"en": "/ai-astrologer", "hi": "/hi/ai-jyotish", "mr": "/mr/ai-jyotish"}
GENERIC = ("could not calculate", "परिणाम नहीं निकल सका", "निकाल काढता आला नाही")


@pytest.fixture(scope="module", autouse=True)
def _test_mode():
    """Sign-in codes to the journal, so this file needs no mail provider. Set here rather than relied on
    from the environment: a test that only passes when somebody exported a variable is a test that will
    quietly stop running."""
    import os

    before = os.environ.get("MAIL_TEST_MODE")
    os.environ["MAIL_TEST_MODE"] = "1"
    yield
    if before is None:
        os.environ.pop("MAIL_TEST_MODE", None)
    else:
        os.environ["MAIL_TEST_MODE"] = before


@pytest.fixture(scope="module")
def live():
    import uvicorn

    from app.main import app

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.05)
    base = f"http://127.0.0.1:{port}"
    from design_shots import _warm_city_index

    _warm_city_index(base)
    yield base
    server.should_exit = True


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright

    from app.pdf.browser import launch_options
    from design_shots import _fontconfig_env

    options = launch_options()
    options["args"] = [*options.get("args", []), "--no-sandbox"]
    options["env"] = _fontconfig_env(options.get("env"))
    with sync_playwright() as play:
        instance = play.chromium.launch(**options)
        yield instance
        instance.close()


def _fill(page, city="Miraj"):
    """An INVENTED person. No real birth details anywhere in this repository."""
    page.fill("#self-name", "Asha Vernekar")
    page.fill("#self-date", "1988-03-11")
    page.fill("#self-time", "19:30")
    page.fill("#self-city", city)
    option = page.locator("#self-city-list [role=option]").first
    option.wait_for(state="visible", timeout=20_000)
    option.click()


@pytest.mark.parametrize("lang", list(PAGES))
def test_a_visitor_with_no_cookie_is_offered_a_sign_in_and_never_blamed(lang, live, browser):
    context = browser.new_context(viewport={"width": 1366, "height": 900})   # NO cookies, on purpose
    try:
        page = context.new_page()
        page.goto(live + PAGES[lang], wait_until="load")
        page.wait_for_timeout(400)

        gate = page.locator("#chat-signin")
        assert gate.count() and gate.is_visible(), "the page does not say a sign-in is needed"
        assert page.locator("#chat-signin-link").count(), "it asks for a sign-in and offers nothing to click"

        _fill(page)
        page.click("#submit-btn")
        page.wait_for_timeout(1800)

        message = page.locator("#form-status").inner_text().strip()
        assert message, "the submit produced no message at all"
        for phrase in GENERIC:
            assert phrase not in message, f"a locked chat reported as bad birth details: {message[:80]!r}"
        assert page.locator("#chat-signin-link").count(), "no way forward after the refusal"
    finally:
        context.close()


def test_the_whole_way_through_from_a_cold_browser(live, browser):
    """Fresh context -> form -> sign-in offered -> code -> chat opens. The journey the bug broke."""
    import logging
    import re

    context = browser.new_context(viewport={"width": 1366, "height": 900})
    try:
        page = context.new_page()
        page.goto(live + PAGES["en"], wait_until="load")
        page.wait_for_timeout(300)
        assert page.locator("#chat-signin").is_visible()

        page.goto(live + "/login", wait_until="load")
        page.fill("#login-name", "Asha Vernekar")
        page.fill("#login-email", "cold.browser@example.com")

        records = []
        handler = logging.Handler()
        handler.emit = records.append
        logging.getLogger("app.mailer").addHandler(handler)
        try:
            page.click("#login-send")
            page.wait_for_timeout(900)
            codes = [m for r in records if (m := re.search(r"is (\d{6})", r.getMessage()))]
            assert codes, "test mode did not write a code to the journal"
            page.fill("#login-code", codes[-1].group(1))
            page.click("#login-verify")
            page.wait_for_timeout(900)
        finally:
            logging.getLogger("app.mailer").removeHandler(handler)

        page.goto(live + PAGES["en"], wait_until="load")
        page.wait_for_timeout(300)
        gate = page.locator("#chat-signin")
        assert not (gate.count() and gate.is_visible()), "still asked to sign in after signing in"

        _fill(page)
        page.click("#submit-btn")
        page.wait_for_selector("#chat-log", timeout=40_000)
        assert page.locator("#result").is_visible(), "the chat did not open for a signed-in reader"
    finally:
        context.close()
