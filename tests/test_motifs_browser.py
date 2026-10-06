"""The motifs as a browser actually paints them: the kundali, the dasha card, the sidebar, the avatar.

A sprite that parses and a stylesheet that balances prove nothing about what a reader sees. Every claim
here is read back off a rendered page - the diamond has lines in it, the glyph a `<use>` points at
actually resolved to geometry, the progress bar has a width, the empty state asks its question in the
reader's own language.
"""

import socket
import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

BIRTH = {"name": "Asha Vernekar", "date": "1988-03-11", "time": "19:30", "lat": 18.5204, "lon": 73.8567,
         "timezone": "Asia/Kolkata", "city": "Pune", "language": "en"}
PAGES = {"en": "/ai-astrologer", "hi": "/hi/ai-jyotish", "mr": "/mr/ai-jyotish"}
ASKS = {"en": "Whose chart", "hi": "किसकी कुंडली", "mr": "कोणाची कुंडली"}


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
    yield f"http://127.0.0.1:{port}"
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


def seeded(email: str, language: str = "en") -> dict:
    """One chat for this account, started through the API, so the browser has something to open."""
    from fastapi.testclient import TestClient

    from app.main import app
    from app.web import accounts

    client = TestClient(app, raise_server_exceptions=False)
    client.cookies.set(accounts.COOKIE_NAME, accounts.sign(email))
    client.post("/api/consultation/start", json={**BIRTH, "language": language})
    return {"name": accounts.COOKIE_NAME, "value": accounts.sign(email),
            "domain": "127.0.0.1", "path": "/"}


def show_sidebar(page):
    """The sidebar is a drawer on a phone and a column on a desktop; the toggle exists only in the first."""
    toggle = page.locator("#chat-list-toggle")
    if toggle.count() and toggle.is_visible():
        toggle.click()
        page.wait_for_timeout(600)


def opened(browser, live, cookie, path="/ai-astrologer", width=1400):
    context = browser.new_context(viewport={"width": width, "height": 1000})
    if cookie:
        context.add_cookies([cookie])
    page = context.new_page()
    page.goto(live + path, wait_until="networkidle")
    page.wait_for_timeout(2500)
    return context, page


def test_the_chat_panel_draws_the_real_kundali(live, browser):
    cookie = seeded("motif.kundali@gmail.com")
    context, page = opened(browser, live, cookie)
    try:
        svg = page.locator('[data-panel="kundali"] svg')
        assert svg.count() == 1, "the chat panel drew no kundali"
        box = svg.bounding_box()
        assert box and box["width"] > 150 and box["height"] > 150, f"the diamond has no size: {box}"
        # the diamond is a frame, its diagonals and twelve numbered houses - not an empty box
        assert page.locator('[data-panel="kundali"] svg rect').count() >= 1, "no frame"
        assert page.locator('[data-panel="kundali"] svg path').count() >= 1, "no diagonals"
        assert page.locator('[data-panel="kundali"] svg text').count() >= 12, "no houses are numbered"
    finally:
        context.close()


def test_the_dasha_card_shows_a_glyph_a_bar_and_a_date(live, browser):
    cookie = seeded("motif.dasha@gmail.com")
    context, page = opened(browser, live, cookie)
    try:
        card = page.locator('[data-panel="dasha-card"]')
        assert card.is_visible(), "the dasha card never appeared"
        href = page.get_attribute('[data-panel="dasha-glyph"]', "href")
        assert href and "glyphs.svg?v=" in href, f"the dasha glyph is unversioned or missing: {href}"
        # THE BAR IS SET, not "the bar is wide". A mahadasha that began last week is a legitimate chart
        # whose bar is a sliver, and `width > 0` would have turned that into a failing test on whatever
        # morning this person's dasha happened to change - a green that depends on the calendar, which is
        # how a date-dependent test got into this repository once already.
        filled = page.eval_on_selector('[data-panel="dasha-fill"]', "e => e.style.width")
        assert filled.endswith("%"), f"the progress bar was never given a width: {filled!r}"
        share = float(filled.rstrip("%"))
        assert 0 <= share <= 100, f"the bar is drawn at {share}% of the period"
        ends = page.text_content('[data-panel="dasha-ends"]') or ""
        assert any(ch.isdigit() for ch in ends), f"no end date on the dasha card: {ends!r}"
    finally:
        context.close()


def test_the_glyph_a_use_points_at_actually_resolves(live, browser):
    """An external `<use>` that does not resolve renders nothing at all, and renders it silently."""
    cookie = seeded("motif.resolve@gmail.com")
    context, page = opened(browser, live, cookie)
    try:
        painted = page.eval_on_selector('[data-panel="dasha-glyph"]', """
            use => {
              const box = use.getBoundingClientRect();
              return box.width > 0 && box.height > 0;
            }""")
        assert painted, "the <use> resolved to nothing: the sprite is not reachable from the page"
    finally:
        context.close()


def test_the_astrologer_replies_wear_an_om_and_the_reader_does_not(live, browser):
    cookie = seeded("motif.avatar@gmail.com")
    context, page = opened(browser, live, cookie)
    try:
        assert page.locator(".chat__msg--assistant .chat__avatar").count() >= 1
        assert page.locator(".chat__msg--user .chat__avatar:visible").count() == 0
    finally:
        context.close()


@pytest.mark.parametrize("lang", list(PAGES))
def test_an_account_with_no_chats_is_asked_whose_chart(lang, live, browser):
    """The empty sidebar asks a question, in the reader's language, with a figure beside it."""
    from app.web import accounts

    email = f"motif.empty.{lang}@gmail.com"
    cookie = {"name": accounts.COOKIE_NAME, "value": accounts.sign(email),
              "domain": "127.0.0.1", "path": "/"}
    context, page = opened(browser, live, cookie, PAGES[lang])
    try:
        show_sidebar(page)
        note = page.text_content("#chat-list-note") or ""
        assert ASKS[lang] in note, f"{lang}: the empty sidebar says {note!r}"
        assert page.locator("#chat-list-note .v2-chats__figure").count() == 1
    finally:
        context.close()


def test_the_sidebar_shows_the_persons_rashi(live, browser):
    cookie = seeded("motif.sidebar@gmail.com")
    context, page = opened(browser, live, cookie)
    try:
        show_sidebar(page)
        who = page.text_content("#chat-list-panel .v2-chats__who") or ""
        # Not a hardcoded sign - the invariant is that the NAME and the GLYPH agree. A row that said
        # "Vrishchika" beside the Tula mark would be the failure worth catching, and pinning one chart's
        # answer would only break the day the ephemeris is updated.
        SIGNS = ("Mesha", "Vrishabha", "Mithuna", "Karka", "Simha", "Kanya",
                 "Tula", "Vrishchika", "Dhanu", "Makara", "Kumbha", "Meena")
        named = [sign for sign in SIGNS if sign in who]
        assert len(named) == 1, f"the sidebar names no single rashi: {who!r}"
        href = page.get_attribute("#chat-list-panel .v2-chats__rashi use", "href") or ""
        assert href.endswith("#r-" + named[0].lower()), f"{named[0]} is shown with the mark {href!r}"
    finally:
        context.close()


def test_the_decoration_cannot_push_the_page_sideways(live, browser):
    """A fixed sky and a figure at 100vw are exactly the shapes that cause a phone to scroll sideways."""
    cookie = seeded("motif.width@gmail.com")
    for width in (390, 1400):
        context, page = opened(browser, live, cookie, width=width)
        try:
            overflow = page.evaluate("() => document.documentElement.scrollWidth - window.innerWidth")
            assert overflow <= 0, f"{width}px: the page scrolls sideways by {overflow}px"
        finally:
            context.close()
