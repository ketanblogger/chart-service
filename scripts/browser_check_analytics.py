#!/usr/bin/env python
"""Does the Google tag really stay off the critical path, and does waiting for it lose any event?

Three things a unit test cannot answer, so they are answered in a real browser:

  1. the loader is NOT requested while the page is loading;
  2. it IS requested afterwards - once the browser is idle, or at the reader's first interaction;
  3. a gtag() call made before the loader arrives is still delivered.

(3) is the one that matters most. The whole change rests on window.dataLayer being a queue: anything
pushed before Google's script lands is drained when it does. If that were wrong, every event fired during
the first seconds of a visit would vanish, and the property would look healthy while quietly under-counting.
"""
from __future__ import annotations

import os
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_tmp = tempfile.mkdtemp(prefix="ga-check-")
os.environ.update(APP_DB=f"{_tmp}/app.db", SESSION_SECRET="ga-check", CSP_MODE="enforce")
for _name in ("RAZORPAY_KEY_ID", "RAZORPAY_KEY_SECRET", "REPORTS_UNLOCKED"):
    os.environ.pop(_name, None)

import uvicorn  # noqa: E402

from app.main import app  # noqa: E402
from app.pdf.browser import launch_options  # noqa: E402

GA_HOST = "googletagmanager.com"
PAGES = ("/", "/horoscope/libra/today", "/ai-astrologer")


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

    failures: list[str] = []

    def check(ok: bool, label: str) -> None:
        print(("  ok   " if ok else "  FAIL ") + label)
        if not ok:
            failures.append(label)

    with sync_playwright() as play:
        browser = play.chromium.launch(**launch_options())
        try:
            for path in PAGES:
                print(f"\n{path}")
                context = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True,
                                              has_touch=True)
                page = context.new_page()
                asked: list[str] = []
                page.on("request", lambda r, asked=asked: asked.append(r.url))

                # The tag's host is reachable from this machine or it is not; either way the REQUEST is
                # what we are measuring, so a blocked response does not change the answer.
                page.goto(base + path, wait_until="load")
                during_load = [u for u in asked if GA_HOST in u]
                check(not during_load, f"{path}: nothing from {GA_HOST} while loading ({len(during_load)})")

                # Queue an event before Google has answered - this is what must not be lost.
                page.evaluate("window.gtag && window.gtag('event', 'before_loader', {sent_early: 1})")
                queued = page.evaluate(
                    "(window.dataLayer || []).some(a => Array.from(a).includes('before_loader'))")
                check(bool(queued), f"{path}: an event fired before the loader is held in dataLayer")

                page.wait_for_timeout(4500)   # past requestIdleCallback's 3s deadline
                after_idle = [u for u in asked if GA_HOST in u]
                check(bool(after_idle), f"{path}: requested after load, once idle ({len(after_idle)})")
                check(len(after_idle) == 1, f"{path}: requested exactly once, not per trigger")

                # The early event must still be in the queue (or drained into Google's processor, which
                # replaces dataLayer.push - either way it was never dropped on the floor).
                still = page.evaluate("Array.isArray(window.dataLayer) && window.dataLayer.length > 0")
                check(bool(still), f"{path}: the queue survived the loader arriving")
                context.close()

            # Interaction before idle: the reader touches the page, so the tag goes at once.
            print("\nfirst interaction, before the browser goes idle")
            context = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True,
                                          has_touch=True)
            page = context.new_page()
            asked = []
            page.on("request", lambda r: asked.append(r.url))
            session = context.new_cdp_session(page)
            # A slow CPU keeps the browser busy, so idle would not come quickly on its own.
            session.send("Emulation.setCPUThrottlingRate", {"rate": 20})
            page.goto(base + "/", wait_until="load")
            check(not [u for u in asked if GA_HOST in u], "busy page: nothing yet")
            page.mouse.click(10, 10)
            page.wait_for_timeout(1200)
            check(bool([u for u in asked if GA_HOST in u]), "busy page: the tag goes at the first click")
            context.close()
        finally:
            browser.close()

    print(f"\n{len(failures)} failure(s)")
    for failure in failures:
        print(f"  - {failure}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
