"""Ask first, sign in second.

THE ORDER THE SITE USED TO INSIST ON. Fill in four birth fields, be told the chat needs an account, leave
for the sign-in page, come back, and only then find out what the thing actually does. Everything is spent
before anything is received, which is the wrong way round for a service nobody has tried yet.

WHAT CHANGES. A signed-out visitor types their question and presses Send. The page says the answer is
being prepared and asks them to sign in; the question and the birth details ride through the e-mail round
trip; the answer arrives the moment they are back.

WHAT DOES NOT CHANGE, and these are the claims worth testing hardest: NO ANSWER IS GENERATED BEFORE THE
SIGN-IN. Not a model call, not a token, nothing that costs money or can be abused by somebody who never
proves an address. The free allowance and every rate limit behave exactly as they did - the question
simply waits.
"""
from __future__ import annotations

import socket
import sys
import threading
import time
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

BIRTH = {"name": "Asha Vernekar", "date": "1988-03-11", "time": "19:30"}
QUESTION = "will this year be good for a job change?"


class Counts:
    """A model that answers, and says how many times it was asked."""

    calls = 0

    def generate_chat(self, **kwargs):
        Counts.calls += 1

        class Result:
            pass

        Result.text = "Guru supports a change this year; keep your routine steady."
        Result.usage = {"input_tokens": 3000, "output_tokens": 200}
        Result.model, Result.request_id, Result.data = "claude-sonnet-5", None, None
        return Result


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


def fill_birth(page):
    for field, value in BIRTH.items():
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


def test_a_signed_out_visitor_can_type_a_question_and_send_it(live, browser):
    """The box must be reachable WITHOUT an account - that is the whole change."""
    context = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True)
    try:
        page = context.new_page()
        page.goto(live + "/ai-astrologer", wait_until="networkidle")
        page.wait_for_timeout(700)
        fill_birth(page)
        box = page.locator("#ask-first")
        assert box.count() and box.is_visible(), "a signed-out visitor has nowhere to type a question"
        box.fill(QUESTION)
        page.locator("#ask-first-send").click()
        page.wait_for_timeout(900)
        said = page.locator("#ask-first-status").inner_text().lower()
        assert "sign in" in said, f"the page did not ask them to sign in: {said!r}"
    finally:
        context.close()


def test_nothing_is_generated_before_the_sign_in(live, browser, monkeypatch):
    """THE CLAIM THAT MATTERS. A question from somebody with no account must not reach the model."""
    import app.ai.chat as chat

    Counts.calls = 0
    monkeypatch.setattr(chat, "get_chat_client", lambda: Counts())

    context = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True)
    try:
        page = context.new_page()
        asked = []
        page.on("request", lambda r: asked.append(r.url) if "/api/consultation" in r.url else None)
        page.goto(live + "/ai-astrologer", wait_until="networkidle")
        page.wait_for_timeout(700)
        fill_birth(page)
        page.locator("#ask-first").fill(QUESTION)
        page.locator("#ask-first-send").click()
        page.wait_for_timeout(1500)
        assert Counts.calls == 0, "a model was called for a visitor with no account"
        started = [u for u in asked if u.endswith("/start") or u.endswith("/message")]
        assert not started, f"a consultation was opened before sign-in: {started}"
    finally:
        context.close()


def test_the_question_survives_the_round_trip(live, browser):
    context = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True)
    try:
        page = context.new_page()
        page.goto(live + "/ai-astrologer", wait_until="networkidle")
        page.wait_for_timeout(700)
        fill_birth(page)
        page.locator("#ask-first").fill(QUESTION)
        page.locator("#ask-first-send").click()
        page.wait_for_timeout(700)

        page.goto(live + "/login?next=/ai-astrologer", wait_until="networkidle")
        page.goto(live + "/ai-astrologer", wait_until="networkidle")
        page.wait_for_timeout(900)

        kept = page.evaluate("() => { try { return sessionStorage.getItem('rk.birth.v1'); } "
                             "catch (e) { return null; } }")
        assert kept and QUESTION in kept, "the question was lost on the way to signing in"
        assert BIRTH["name"] in kept
    finally:
        context.close()


def test_the_pending_question_is_answered_right_after_signing_in(live, browser, monkeypatch):
    """The payoff: back from the e-mail, the answer is already on its way - nothing retyped, nothing
    pressed again."""
    import app.ai.chat as chat
    from app.web import accounts

    Counts.calls = 0
    monkeypatch.setattr(chat, "get_chat_client", lambda: Counts())
    email = f"askfirst{uuid.uuid4().hex[:8]}@gmail.com"

    context = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True)
    try:
        page = context.new_page()
        page.goto(live + "/ai-astrologer", wait_until="networkidle")
        page.wait_for_timeout(700)
        fill_birth(page)
        page.locator("#ask-first").fill(QUESTION)
        page.locator("#ask-first-send").click()
        page.wait_for_timeout(700)

        # sign in the way the OTP round trip ends: a session cookie, then back to the page
        context.add_cookies([{"name": accounts.COOKIE_NAME, "value": accounts.sign(email),
                              "domain": "127.0.0.1", "path": "/"}])
        page.goto(live + "/ai-astrologer", wait_until="networkidle")
        page.wait_for_timeout(4000)

        log = page.locator("#chat-log").inner_text()
        assert QUESTION.lower() in log.lower(), "the question was not asked after signing in"
        assert Counts.calls >= 1, "signing in did not produce the answer"
    finally:
        context.close()
