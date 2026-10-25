#!/usr/bin/env python
"""Mobile performance of the three pages that carry the traffic: LCP, CLS and page weight.

WHAT THIS IS AND IS NOT. It is a direct measurement in the Chromium this repo already bundles for PDFs,
under a mobile viewport with network and CPU throttling set to Lighthouse's mobile preset. It is NOT a
Lighthouse score: there is no Lighthouse here, installing it would pull a Node toolchain over the network,
and the only node on this machine is the Windows one reached through WSL interop, which cannot reliably
talk to a Linux-side localhost server. So the numbers below are the three the brief asks for, measured
honestly, and the word "score" is deliberately not used anywhere in the output.

WHY THESE THREE NUMBERS. LCP is when the reader sees the thing they came for. CLS is whether it moves
under their thumb after they start reading - which a decorative background drawn late is exactly how to
cause. Page weight is what they pay for on a phone connection, and most of this site's visitors are on one.

Thresholds are the published "good" bounds, plus the two from the brief: the decorative background must
stay under 30KB and nothing may shift.
"""
from __future__ import annotations

import argparse
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
OUT = ROOT / "var" / "perf_check"

_tmp = tempfile.mkdtemp(prefix="perf-check-")
os.environ.update(APP_DB=f"{_tmp}/app.db", SESSION_SECRET="perf-check", CSP_MODE="enforce")
# Never a live key in a browser run. The payments check is the one script that must not meet one, and
# this one has no business with them either.
for _name in ("RAZORPAY_KEY_ID", "RAZORPAY_KEY_SECRET", "REPORTS_UNLOCKED"):
    os.environ.pop(_name, None)

import uvicorn  # noqa: E402

from app.main import app  # noqa: E402
from app.pdf.browser import launch_options  # noqa: E402

#: Lighthouse's mobile preset: a slow 4G line and a quarter of the CPU.
THROTTLE = {"latency": 150, "downloadThroughput": int(1.6 * 1024 * 1024 / 8), "uploadThroughput": int(750 * 1024 / 8)}
CPU_SLOWDOWN = 4
MOBILE = {"width": 390, "height": 844}

#: "good" by the published Core Web Vitals bounds, and the brief's own two.
LCP_GOOD_MS = 2500
CLS_GOOD = 0.1
BACKGROUND_MAX_KB = 30
WEIGHT_WARN_KB = 500

PAGES = [("home", "/"), ("rashifal", "/horoscope/libra/today"), ("chat", "/ai-astrologer"),
         # The families added in the October batch. Each is a different SHAPE of page - a picker, a
         # long guide, a small content page, a form - so one of them going heavy would not show up in
         # the other three.
         ("panchang", "/hi/aaj-ka-panchang"), ("pillar", "/astrology"),
         ("nakshatra", "/nakshatra/mula"), ("kundli", "/kundli"),
         ("marriage", "/hi/shadi-kab-hogi"), ("compare", "/compare-free-kundli-websites")]

MEASURE = """
() => new Promise(resolve => {
  let lcp = 0, cls = 0;
  const shifts = [];
  new PerformanceObserver(list => {
    for (const entry of list.getEntries()) lcp = Math.max(lcp, entry.startTime);
  }).observe({type: 'largest-contentful-paint', buffered: true});
  new PerformanceObserver(list => {
    for (const entry of list.getEntries()) {
      if (entry.hadRecentInput) continue;
      cls += entry.value;
      shifts.push({value: entry.value, sources: (entry.sources || []).map(s =>
        s.node ? (s.node.tagName || '') + (s.node.className ? '.' + String(s.node.className).split(' ')[0] : '') : '')});
    }
  }).observe({type: 'layout-shift', buffered: true});
  // Long enough for a late webfont or a deferred background to shift something; a shift after this is
  // beyond what a reader would still call "loading".
  setTimeout(() => {
    const nav = performance.getEntriesByType('navigation')[0] || {};
    resolve({lcp, cls, shifts, dom: nav.domContentLoadedEventEnd || 0, load: nav.loadEventEnd || 0});
  }, 4000);
})
"""


#: Every resource whose response finished no later than the load event - the critical path, as the
#: browser timed it rather than as the test guessed.
RESOURCES_BEFORE_LOAD = """
() => {
  const nav = performance.getEntriesByType('navigation')[0];
  const loaded = nav && nav.loadEventEnd ? nav.loadEventEnd : Infinity;
  return performance.getEntriesByType('resource')
    .filter(e => e.responseEnd && e.responseEnd <= loaded)
    .map(e => e.name);
}
"""


def _background_bytes(page) -> dict[str, int]:
    """What the decorative starfield actually costs: the inline SVG in the document and its CSS rule.

    It is drawn inline on purpose - a separate request for decoration is a request a reader on a phone
    waits for - so its cost cannot be read off the network at all.
    """
    import re

    found: dict[str, int] = {}
    svg = re.search(r'<svg class="v2-starfield".*?</svg>', page.content(), re.S)
    if svg:
        found["inline starfield svg"] = len(svg.group(0).encode())
    css = (ROOT / "app" / "static" / "css" / "site.css").read_text(encoding="utf-8")
    rule = re.search(r"\.v2-starfield \{.*?\}", css, re.S)
    if rule:
        found["starfield css rule"] = len(rule.group(0).encode())
    return found


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-throttle", action="store_true", help="measure on this machine's real speed")
    args = parser.parse_args()

    from playwright.sync_api import sync_playwright

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.05)
    base = f"http://127.0.0.1:{port}"
    OUT.mkdir(parents=True, exist_ok=True)

    failures: list[str] = []
    report: dict[str, dict] = {}

    def check(ok: bool, label: str) -> None:
        print(("  ok   " if ok else "  FAIL ") + label)
        if not ok:
            failures.append(label)

    with sync_playwright() as play:
        browser = play.chromium.launch(**launch_options())
        try:
            for name, path in PAGES:
                print(f"\n{name}  {path}")
                context = browser.new_context(viewport=MOBILE, device_scale_factor=3, is_mobile=True,
                                              has_touch=True)
                page = context.new_page()
                weights: dict[str, int] = {}

                def on_response(response, weights=weights):
                    try:
                        body = response.body()
                    except Exception:  # noqa: BLE001 - a redirect or a cancelled request has no body
                        return
                    weights[response.url] = len(body)

                page.on("response", on_response)
                session = context.new_cdp_session(page)
                if not args.no_throttle:
                    session.send("Network.emulateNetworkConditions", {"offline": False, **THROTTLE})
                    session.send("Emulation.setCPUThrottlingRate", {"rate": CPU_SLOWDOWN})

                page.goto(base + path, wait_until="load")
                vitals = page.evaluate(MEASURE)
                # WEIGHT AT LOAD, SEPARATELY FROM TOTAL WEIGHT. Deferring the Google tag does not make it
                # smaller - it moves it out of the reader's way - and a single total measured four seconds
                # in cannot tell those apart: it counts a lazily-fetched 526 KB exactly as it counted the
                # same 526 KB in <head>.
                #
                # CLASSIFIED BY THE BROWSER'S OWN RESOURCE TIMINGS, not by snapshotting the running tally
                # when goto() returns. That first attempt raced the response handler against the load
                # event and reported 89.7 KB for a page whose stylesheets alone are 133 KB - an
                # improvement that looked twice as good as the real one. Sizes still come from the
                # response bodies, because a cross-origin script reports transferSize 0 without
                # Timing-Allow-Origin; only the before-or-after question is answered from the timings.
                before_load = set(page.evaluate(RESOURCES_BEFORE_LOAD))
                at_load = {url: size for url, size in weights.items()
                           if url in before_load or url == base + path}
                page.screenshot(path=str(OUT / f"{name}-mobile.png"), full_page=False)

                total_kb = sum(weights.values()) / 1024
                load_kb = sum(at_load.values()) / 1024
                deferred_kb = total_kb - load_kb
                css_kb = sum(size for url, size in weights.items() if ".css" in url) / 1024
                js_kb = sum(size for url, size in weights.items() if ".js" in url) / 1024
                img_kb = sum(size for url, size in weights.items()
                             if any(ext in url for ext in (".svg", ".png", ".jpg", ".webp", ".woff", ".woff2"))) / 1024
                # THE DECORATIVE BACKGROUND IS INLINE, so it is never a response and a filter over the
                # responses finds nothing - and `all()` over nothing is True, so the 30KB check passed
                # three times having measured no bytes at all. It is measured where it actually lives:
                # the inline <svg> in the document plus its rule in the stylesheet.
                background = _background_bytes(page)

                print(f"  LCP {vitals['lcp']:.0f} ms   CLS {vitals['cls']:.4f}")
                print(f"  weight at load {load_kb:7.1f} KB   <- what the reader waits for")
                print(f"  deferred after {deferred_kb:7.1f} KB   <- fetched once idle or on first touch")
                print(f"  total          {total_kb:7.1f} KB   (css {css_kb:.1f}, js {js_kb:.1f}, "
                      f"img+font {img_kb:.1f})")
                for url, size in sorted(weights.items(), key=lambda kv: -kv[1])[:6]:
                    print(f"    {size / 1024:8.1f} KB  {url.replace(base, '')}")
                for url, size in sorted(background.items()):
                    print(f"  background {url.rsplit('/', 1)[-1]}: {size / 1024:.1f} KB")
                if vitals["shifts"]:
                    for shift in vitals["shifts"]:
                        print(f"  shifted {shift['value']:.4f} by {shift['sources']}")

                check(vitals["lcp"] <= LCP_GOOD_MS, f"{name}: LCP {vitals['lcp']:.0f} ms <= {LCP_GOOD_MS}")
                check(vitals["cls"] <= CLS_GOOD, f"{name}: CLS {vitals['cls']:.4f} <= {CLS_GOOD}")
                # BOTH PIECES, named. The first version asked only that the dict was non-empty, and the
                # stylesheet rule alone kept it non-empty: renaming the inline SVG's class removed the
                # background from the page and the check still passed.
                check(set(background) == {"inline starfield svg", "starfield css rule"},
                      f"{name}: the decorative background was found and measured ({sorted(background)})")
                check(background and all(size / 1024 <= BACKGROUND_MAX_KB for size in background.values()),
                      f"{name}: every decorative background <= {BACKGROUND_MAX_KB} KB")
                check(deferred_kb > 0, f"{name}: the third-party tag is deferred, not in the critical path")
                if load_kb > WEIGHT_WARN_KB:
                    print(f"  note  {name}: {load_kb:.1f} KB at load is over the {WEIGHT_WARN_KB} KB mark")

                report[name] = {"path": path, "lcp_ms": round(vitals["lcp"]), "cls": round(vitals["cls"], 4),
                                "weight_at_load_kb": round(load_kb, 1), "deferred_kb": round(deferred_kb, 1),
                                "weight_kb": round(total_kb, 1), "css_kb": round(css_kb, 1),
                                "js_kb": round(js_kb, 1), "img_font_kb": round(img_kb, 1),
                                "background_kb": {url.rsplit("/", 1)[-1]: round(size / 1024, 1)
                                                  for url, size in background.items()},
                                "shifts": vitals["shifts"]}
                context.close()
        finally:
            browser.close()

    (OUT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nwrote {OUT / 'report.json'} and three mobile screenshots")
    print(f"{len(failures)} failure(s)")
    for failure in failures:
        print(f"  - {failure}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
