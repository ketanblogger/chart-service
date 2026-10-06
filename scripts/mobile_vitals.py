"""Core Web Vitals on a THROTTLED MOBILE profile, measured in the real browser against a local server.

    .venv/bin/python scripts/mobile_vitals.py                       # the three pages of the SEO review
    .venv/bin/python scripts/mobile_vitals.py /mr/kundali /horoscope   # any paths
    .venv/bin/python scripts/mobile_vitals.py --runs 3              # median of N loads per page (default 3)

Why this and not Lighthouse. Lighthouse is a Node package that would have to be downloaded on every run, it
scores a dozen things that are not questions here, and the only numbers asked for are LCP and CLS - which are
browser APIs, not Lighthouse's. This drives the Chromium that is already installed for the PDF renderer,
through the same Playwright that every other browser check uses, so there is nothing new to install, nothing
to keep in step with a second toolchain, and the result is a number this repository can assert on.

WHAT IS MEASURED, and the throttling is the point: a mid-range Android on a mobile network, not a desktop on
fibre. 4x CPU slowdown and Slow-4G latency through CDP, a 393x852 viewport at DPR 2.625 (Pixel 7), and the
cache cleared between runs. Every figure is the MEDIAN of `--runs` loads, because a single cold load on a
throttled profile varies by hundreds of milliseconds and one number is then not a measurement of anything.

  LCP  Largest Contentful Paint - when the main thing a reader came for finished painting. Good <= 2.5s.
  CLS  Cumulative Layout Shift - how far the page moved under the reader after it appeared. Good <= 0.1.
  FCP  First Contentful Paint, and TTFB, reported because they say WHERE an LCP went: a slow TTFB is the
       server, a slow FCP with a fast TTFB is the head of the document, and a slow LCP with a fast FCP is an
       image or a font.

WHAT IT CANNOT TELL YOU. The server is this machine, so TTFB here is a millisecond and a real one is not:
add the VPS, TLS and the distance to the reader. So the figure to read is not the absolute LCP but LCP MINUS
TTFB - the part the code owns, which is how long after the bytes arrive the main content paints - and CLS,
which does not depend on the network at all. A page that is fast here can still be slow for a reader in
Nagpur; a page that is SLOW here is slow for everybody.

Exit code 0 when every page is inside both thresholds, 1 when one is not, 2 for usage. Read-only: it never
calls the AI, never touches a payment and never contacts anything outside this machine.
"""

import argparse
import json
import socket
import statistics
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import uvicorn  # noqa: E402

from app.main import app  # noqa: E402
from app.pdf.browser import launch_options  # noqa: E402

# The three pages the SEO review asks about: the Marathi kundali page (position 19), a Hindi weekly hub, and
# one English six-month reading. Different shapes on purpose - a tool page with a form, a hub of twelve cards,
# and a long generated reading - so a regression in any one of the three layouts shows up here.
DEFAULT_PATHS = ("/mr/kundali", "/hi/rashifal/saptahik", "/horoscope/capricorn/6-months")

GOOD_LCP_MS = 2500
GOOD_CLS = 0.1

# Pixel 7, which is the shape of the phone most of this site's traffic arrives on.
VIEWPORT = {"width": 393, "height": 852}
DEVICE_SCALE = 2.625
UA_MOBILE = ("Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) "
             "Chrome/120.0.0.0 Mobile Safari/536.36")
CPU_SLOWDOWN = 4
# Slow 4G, the profile Lighthouse's mobile preset uses: 1.6 Mbps down, 750 Kbps up, 150 ms RTT.
NETWORK = {"offline": False, "downloadThroughput": 1_600_000 // 8, "uploadThroughput": 750_000 // 8,
           "latency": 150}

# Collected in the page. `buffered: true` matters: LCP and the first layout shifts happen before this script
# can attach an observer, and without it the good ones are simply missed and the page looks slow.
_VITALS_JS = """
() => new Promise((resolve) => {
  let lcp = 0, cls = 0;
  new PerformanceObserver((list) => {
    for (const entry of list.getEntries()) lcp = Math.max(lcp, entry.startTime);
  }).observe({type: 'largest-contentful-paint', buffered: true});
  new PerformanceObserver((list) => {
    for (const entry of list.getEntries()) if (!entry.hadRecentInput) cls += entry.value;
  }).observe({type: 'layout-shift', buffered: true});
  const done = () => {
    const nav = performance.getEntriesByType('navigation')[0] || {};
    const fcp = performance.getEntriesByName('first-contentful-paint')[0];
    resolve({lcp, cls, fcp: fcp ? fcp.startTime : 0, ttfb: nav.responseStart || 0,
             transferred: nav.transferSize || 0, dom: document.querySelectorAll('*').length});
  };
  // Let late images and any font swap land: both move LCP, and a CLS measured before them is a smaller
  // number than the reader experiences.
  setTimeout(done, 2500);
})
"""


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _measure(browser, base: str, path: str) -> dict:
    context = browser.new_context(viewport=VIEWPORT, device_scale_factor=DEVICE_SCALE,
                                  user_agent=UA_MOBILE, is_mobile=True, has_touch=True)
    try:
        page = context.new_page()
        session = context.new_cdp_session(page)
        session.send("Network.enable")
        session.send("Network.emulateNetworkConditions", NETWORK)
        session.send("Emulation.setCPUThrottlingRate", {"rate": CPU_SLOWDOWN})
        page.goto(base + path, wait_until="load", timeout=60_000)
        return page.evaluate(_VITALS_JS)
    finally:
        context.close()


def main(argv: list[str] | None = None) -> int:
    from playwright.sync_api import sync_playwright

    parser = argparse.ArgumentParser(description="LCP / CLS on a throttled mobile profile.")
    parser.add_argument("paths", nargs="*", default=list(DEFAULT_PATHS), help="paths to measure")
    parser.add_argument("--runs", type=int, default=3, help="loads per page; the median is reported (default 3)")
    parser.add_argument("--json", type=Path, help="also write the raw figures here")
    args = parser.parse_args(argv)
    paths = args.paths or list(DEFAULT_PATHS)

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.05)
    base = f"http://127.0.0.1:{port}"

    print(f"mobile profile: {VIEWPORT['width']}x{VIEWPORT['height']} @{DEVICE_SCALE}x, CPU /{CPU_SLOWDOWN}, "
          f"Slow 4G (150 ms RTT), {args.runs} load(s) per page, median reported")
    print(f"{'path':40} {'LCP':>9} {'CLS':>7} {'FCP':>9} {'TTFB':>8} {'KB':>7} {'nodes':>6}")
    rows, failures = [], []
    with sync_playwright() as playwright:
        # The SAME launch options the PDF renderer uses (app/pdf/browser.launch_options): on this machine the
        # bundled Chromium needs an LD_LIBRARY_PATH for libnspr4, and a second way of starting a browser here
        # would be a second thing to fix the next time that changes.
        options = launch_options()
        options["args"] = [*options.get("args", []), "--no-sandbox"]
        browser = playwright.chromium.launch(**options)
        try:
            for path in paths:
                runs = [_measure(browser, base, path) for _ in range(max(1, args.runs))]
                row = {"path": path,
                       **{key: statistics.median(run[key] for run in runs)
                          for key in ("lcp", "cls", "fcp", "ttfb", "transferred", "dom")}}
                rows.append(row)
                bad = []
                if row["lcp"] > GOOD_LCP_MS:
                    bad.append(f"LCP {row['lcp'] / 1000:.2f}s > {GOOD_LCP_MS / 1000:.1f}s")
                if row["cls"] > GOOD_CLS:
                    bad.append(f"CLS {row['cls']:.3f} > {GOOD_CLS}")
                print(f"{path:40} {row['lcp'] / 1000:8.2f}s {row['cls']:7.3f} {row['fcp'] / 1000:8.2f}s "
                      f"{row['ttfb'] / 1000:7.2f}s {row['transferred'] / 1024:7.0f} {row['dom']:6.0f}"
                      + ("   RED: " + ", ".join(bad) if bad else ""))
                failures += [f"{path}: {reason}" for reason in bad]
        finally:
            browser.close()

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(rows, indent=1), encoding="utf-8")
        print(f"wrote {args.json}")
    print(("\nall inside the good thresholds (LCP <= 2.5s, CLS <= 0.1)" if not failures else
           "\n" + str(len(failures)) + " over the threshold:\n  " + "\n  ".join(failures)))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
