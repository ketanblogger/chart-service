"""The Google tag is 526 KB and must never be in the critical path.

MEASURED, NOT ASSUMED: on the rashifal page it was 526 of 698 KB - 75% of the page's entire weight, and
more than triple all our own CSS, JS, fonts and images together. It is now fetched by analytics.js after
load, when the browser is idle or at the reader's first interaction, whichever comes first.

NO EVENT IS LOST BY WAITING, which is the only reason this is safe: window.dataLayer is a plain array
until Google's script arrives and replaces its push, so everything queued before it lands is drained in
order when it does. scripts/browser_check_analytics.py proves that in a real browser - that the loader is
absent during load, present afterwards, requested exactly once, and that an event fired before it arrives
survives. These tests hold the cheap half: that the HTML does not ask for it and the loader still exists.
"""
from __future__ import annotations

import pathlib
import re

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.web import i18n

client = TestClient(app)
ANALYTICS_JS = pathlib.Path("app/static/js/analytics.js")

#: One page from each tree plus the two heaviest, rather than all 363: this is about the shared shell.
PAGES = ["/", "/hi/", "/mr/", "/horoscope/libra/today", "/ai-astrologer", "/birth-chart"]


@pytest.mark.parametrize("path", PAGES)
def test_no_page_asks_the_browser_for_the_google_tag(path):
    """A tag in <head> is discovered by the preload scanner before anything the reader came for."""
    html = client.get(path).text
    assert "googletagmanager" not in html, f"{path} requests the tag in its HTML"


@pytest.mark.parametrize("path", PAGES)
def test_every_page_still_loads_our_own_analytics_file(path):
    """Deferring the third party must not mean dropping measurement: this file sets up the queue, fires
    the config, and is what fetches the tag later."""
    html = client.get(path).text
    assert re.search(r'src="/static/js/analytics\.js\?v=[^"]+"', html), path
    assert 'data-ga-id="G-' in html, path


def test_the_whole_site_is_checked_not_just_the_sample():
    """The sample above is six pages of 363. The shell is shared, so a tag reintroduced into base.html
    would show on all of them - but a tag added to ONE template would not, and that is worth catching."""
    for template in sorted(pathlib.Path("app/web/templates").glob("*.html")):
        text = template.read_text(encoding="utf-8")
        code = re.sub(r"\{#.*?#\}", " ", text, flags=re.S)   # prose may name the host
        assert "googletagmanager" not in code, template.name


def test_the_loader_is_fetched_after_load_and_on_first_interaction():
    """Read from the file, because the behaviour itself needs a browser (see the browser check). What is
    asserted here is that all three triggers are still wired: idle, interaction, and a hard timeout for a
    page that is never idle and never touched."""
    source = ANALYTICS_JS.read_text(encoding="utf-8")
    assert "requestIdleCallback" in source
    assert 'addEventListener("load"' in source
    for event in ("pointerdown", "keydown", "touchstart", "scroll"):
        assert event in source, event
    assert "HARD_TIMEOUT_MS" in source


def test_the_loader_is_requested_only_once_however_many_triggers_fire():
    """Five interaction events plus idle plus a timeout, one request. Without the guard a reader who
    scrolls would fetch 526 KB per scroll event."""
    source = ANALYTICS_JS.read_text(encoding="utf-8")
    assert "if (started) return;" in source
    assert "started = true;" in source


def test_the_scroll_listener_cannot_delay_scrolling():
    """A non-passive scroll listener on every page is a jank bug, and this one exists only to notice the
    first scroll."""
    source = ANALYTICS_JS.read_text(encoding="utf-8")
    assert "passive: true" in source


def test_the_measurement_id_is_still_spelled_in_exactly_one_place():
    """It was in base.html before and must stay there: the loader URL is now built in JavaScript, and a
    second copy of the id is how the two drift apart."""
    found = []
    for folder in ("app/web/templates", "app/static/js"):
        for path in sorted(pathlib.Path(folder).iterdir()):
            if path.is_file() and re.search(r"G-[A-Z0-9]{8,}", path.read_text(encoding="utf-8")):
                found.append(path.name)
    assert found == ["base.html"], found


def test_the_csp_still_allows_the_host_it_is_fetched_from():
    """Injecting the script from our own JavaScript does not exempt it from script-src: if the host were
    dropped from the policy the tag would be refused and the property would quietly stay empty."""
    from app import hardening

    policy = " ".join(hardening.CSP_DIRECTIVES) if hasattr(hardening, "CSP_DIRECTIVES") \
        else pathlib.Path("app/hardening.py").read_text(encoding="utf-8")
    assert "https://www.googletagmanager.com" in policy


@pytest.mark.parametrize("path", PAGES[:3])
def test_the_browser_ping_still_goes_out_with_the_page(path):
    """Our own "this is a browser" signal is independent of Google's tag and must not have been deferred
    with it: it is what separates a reader from something that fetches HTML and stops."""
    source = ANALYTICS_JS.read_text(encoding="utf-8")
    assert "sendBeacon" in source and "/api/seen" in source
    assert client.get(path).status_code == 200
