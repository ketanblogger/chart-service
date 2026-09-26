"""Real-browser look at the rashifal pages: one populated page and one transit-facts fallback page, on a
phone and a desktop viewport, in English and Marathi.

    LD_LIBRARY_PATH=~/.local/share/astro-chromium/root/usr/lib/x86_64-linux-gnu \\
    XDG_DATA_HOME=~/.local/share/astro-chromium/root/usr/share \\
        .venv/bin/python scripts/browser_check_rashifal.py [OUT_DIR]

Self-contained: a temporary database, the real app on a free local port inside this process, and the fake
AI client from tests/ passed straight to `refresh()` for ONE rashi - there is no switch in the app that could
publish fake text in production, and var/app.db is never touched. The fake text is marked [TEST CONTENT].
Checks: no console errors, no horizontal overflow, H1 / date range / reading or fallback present, Devanagari
renders. Screenshots: OUT_DIR/rashifal-*.png. Exit code 0 = all checks passed.
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
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "var" / "browser_check"

os.environ["APP_DB"] = f"{tempfile.mkdtemp(prefix='rashifal-check-')}/app.db"

import uvicorn  # noqa: E402

from app.main import app  # noqa: E402
from app.rashifal.generate import refresh  # noqa: E402
from tests.rashifal_fake import FakeRashifalClient  # noqa: E402

PAGES = [  # (name, path, populated?)
    ("populated-today", "/rashifal/dhanu/today", True),
    ("populated-today-mr", "/rashifal/dhanu/today?lang=mr", True),
    ("populated-yearly", "/rashifal/dhanu/yearly", True),
    ("fallback-today", "/rashifal/simha/today", False),
    ("fallback-yearly-hi", "/rashifal/simha/yearly?lang=hi", False),
    ("index", "/rashifal", None),
    ("hub", "/rashifal/dhanu", None),
]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> int:
    from playwright.sync_api import sync_playwright

    summary = refresh(rashis=["dhanu"], client=FakeRashifalClient())
    assert summary.count("generated") == 5, summary.outcomes

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
        for viewport_name, viewport in [("mobile", {"width": 390, "height": 844}), ("desktop", {"width": 1280, "height": 900})]:
            context = browser.new_context(viewport=viewport, has_touch=(viewport_name == "mobile"))
            for name, path, populated in PAGES:
                print(f"[{viewport_name}] {path}")
                page = context.new_page()
                logs = []
                page.on("console", lambda m: logs.append(f"{m.type}: {m.text}") if m.type in ("error", "warning") else None)
                page.on("pageerror", lambda e: logs.append(f"PAGEERROR: {e}"))
                response = page.goto(base + path)
                check(response.status == 200, "HTTP 200")
                check(page.locator("h1").count() == 1 and page.locator("h1").inner_text().strip() != "", "one H1")
                overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
                check(overflow <= 0, f"no horizontal overflow ({overflow}px)")
                check(not logs, f"no console errors {logs}")
                if populated is not None:
                    check(page.locator("#period-range").inner_text().strip() != "", "period date range visible")
                    check(page.locator("#reading").count() == (1 if populated else 0), "reading shown" if populated else "no reading")
                    check(page.locator("#pending").count() == (0 if populated else 1), "fallback notice" if not populated else "no fallback notice")
                    check(page.locator("#transit-facts tbody tr").count() >= 8, "graha table has rows")
                    check(page.locator(".ad-slot").count() == 3 and page.locator(".ad-slot:visible").count() == 0, "3 hidden ad slots")
                    toggle = page.locator(".lang-toggle a")
                    check(toggle.count() == 3, "language toggle with 3 languages")
                if populated and "lang=" not in path and name == "populated-today" and viewport_name == "mobile":
                    page.locator(".lang-toggle a", has_text="मराठी").click()
                    page.wait_for_url("**lang=mr")
                    check(page.locator("html").get_attribute("lang") == "mr", "toggle switches to Marathi")
                    page.go_back()
                page.screenshot(path=str(OUT / f"rashifal-{name}-{viewport_name}.png"), full_page=True)
                page.close()
            context.close()
        browser.close()
    server.should_exit = True
    print(f"\nscreenshots in {OUT}/rashifal-*.png")
    print("FAILED: " + "; ".join(failures) if failures else "all rashifal browser checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
