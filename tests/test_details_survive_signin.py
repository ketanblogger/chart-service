"""Birth details must survive the trip to the sign-in page and back.

WHAT THE FUNNEL SHOWED. Several people signed up in the window and then never asked a single question -
they gave an address, waited for a code and came back, which is the hard part, and then asked nothing.

Reproduced on a 390px phone: fill in name, date of birth, exact time and city; the page says the chat
needs a free account; tap Sign in; the browser LEAVES for /login; sign in; come back to /ai-astrologer -
and every field is empty. Four pieces of information, one of them a birth time most people have to look
up, typed again on a phone keyboard. That is where they stopped.

The details are held in this browser only, in sessionStorage, for the length of one tab - the same data
the person just typed into the same form on the same device. Nothing is sent anywhere to achieve this.
"""
from __future__ import annotations

import socket
import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

FIELDS = {"name": "Asha Vernekar", "date": "1988-03-11", "time": "19:30"}


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


def fill(page):
    for field, value in FIELDS.items():
        # THE DATE IS THREE SELECTS. Typing an ISO string into the hidden input behind them waits out
        # a thirty-second timeout on an element no reader can touch.
        if field == "date":
            year, month, day = value.split("-")
            page.select_option("#self-year", year)
            page.select_option("#self-month", str(int(month)))
            page.select_option("#self-day", str(int(day)))
            continue
        page.fill(f"#self-{field}", value)
    page.fill("#self-city", "Pune")
    option = page.locator("#self-city-list [role=option]").first
    option.wait_for(state="visible", timeout=20_000)
    option.click()


def test_the_details_are_still_there_after_the_sign_in_round_trip(live, browser):
    """THE ONE THAT MATTERS. Leave for the sign-in page, come back, and the form is as it was."""
    context = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True)
    try:
        page = context.new_page()
        page.goto(live + "/ai-astrologer", wait_until="networkidle")
        page.wait_for_timeout(600)
        fill(page)

        page.goto(live + "/login?next=/ai-astrologer", wait_until="networkidle")
        page.goto(live + "/ai-astrologer", wait_until="networkidle")
        page.wait_for_timeout(900)

        for field, value in FIELDS.items():
            assert page.input_value(f"#self-{field}") == value, (
                f"{field} was lost on the way to signing in - the person must type it again")
        assert page.input_value("#self-city") == "Pune"
    finally:
        context.close()


def test_the_details_never_leave_the_browser(live, browser):
    """They are kept to spare somebody retyping, not collected: nothing is sent to achieve it."""
    context = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True)
    try:
        page = context.new_page()
        # THE REAL CLAIM, not "nothing was sent": the page already sends an analytics page view on load,
        # and asserting silence made this test about that instead of about birth details. What must be
        # true is that none of the typed values leaves the browser.
        seen = []
        page.on("request", lambda r: seen.append((r.url, (r.post_data or "") if r.method != "GET" else "")))
        page.goto(live + "/ai-astrologer", wait_until="networkidle")
        page.wait_for_timeout(600)
        fill(page)
        page.wait_for_timeout(800)

        secrets = [FIELDS["name"], FIELDS["name"].split()[0], FIELDS["date"], FIELDS["time"]]
        for url, body in seen:
            haystack = f"{url} {body}"
            for secret in secrets:
                assert secret not in haystack and secret.replace(" ", "+") not in haystack, (
                    f"{secret!r} left the browser in a request to {url.split('?')[0]}")
    finally:
        context.close()


def test_a_fresh_tab_starts_empty(live, browser):
    """Kept for one tab, not remembered about somebody: a new context has nothing."""
    first = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True)
    try:
        page = first.new_page()
        page.goto(live + "/ai-astrologer", wait_until="networkidle")
        page.wait_for_timeout(600)
        fill(page)
    finally:
        first.close()

    second = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True)
    try:
        page = second.new_page()
        page.goto(live + "/ai-astrologer", wait_until="networkidle")
        page.wait_for_timeout(800)
        assert page.input_value("#self-name") == "", "one person's details appeared in another's browser"
    finally:
        second.close()
