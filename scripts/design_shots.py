"""Screenshots of a page at several widths, for a design review. Before and after, side by side on disk.

    .venv/bin/python scripts/design_shots.py                      # the home page, live vs ?design=v2
    .venv/bin/python scripts/design_shots.py --out var/shots/x    # somewhere else
    .venv/bin/python scripts/design_shots.py --paths /mr/ --widths 390

It starts the app on a local port, opens each page at each width in the Chromium the PDF renderer already
uses, and writes one full-page PNG per (path, width, variant). No network, no AI call, nothing written to the
database - it is a camera.

Full-page rather than viewport: a design review is about what the whole page looks like, and a viewport
screenshot of a long page shows the hero and hides every decision below it.
"""

import argparse
import socket
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import uvicorn  # noqa: E402

from app.main import app  # noqa: E402
from app.pdf.browser import launch_options  # noqa: E402

DEFAULT_PATHS = ("/", "/hi/", "/mr/")
DEFAULT_WIDTHS = (1440, 1280, 390)
# "after" is now the page the site SERVES - no query string - because the full-width design became the
# default on 3 October (site.DESIGN_V2). "before" is `?design=v1`, which still renders the previous template
# and is the rollback. Left the other way round, both columns of every comparison would have been the same
# page and the guards (which only run on "after") would have been checking the design against itself.
VARIANTS = {"before": "?design=v1", "after": ""}


# The WEBSITE does not ship fonts - `--font` in site.css is a SYSTEM stack that merely NAMES "Noto Sans
# Devanagari" - and this machine has no Devanagari font installed at all. So headless Chromium drew every
# Devanagari glyph as a box, in the before shots as well as the after ones, and a screenshot set that cannot
# render the script two of the three trees are written in is worth nothing as a design review.
#
# The fix is to the CAMERA, not to the site: fontconfig is pointed at the four Noto files the PDF renderer
# already bundles, for this process only. Nothing about the page changes - the same CSS stack resolves to a
# font that now exists. A real visitor on a machine with no Devanagari font would still see boxes, which is a
# real (and pre-existing) question about self-hosting, and it belongs in the review rather than hidden here.
FONTS_DIR = ROOT / "app" / "pdf" / "fonts"
FONTCONFIG = ROOT / "var" / "fontconfig.xml"


def _fontconfig_env(base: dict | None) -> dict:
    import os

    FONTCONFIG.parent.mkdir(parents=True, exist_ok=True)
    FONTCONFIG.write_text(
        '<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd"><fontconfig>'
        f"<dir>{FONTS_DIR}</dir>"
        f"<cachedir>{ROOT / 'var' / 'fontcache'}</cachedir>"
        "</fontconfig>", encoding="utf-8")
    env = dict(base or os.environ)
    env["FONTCONFIG_FILE"] = str(FONTCONFIG)
    return env


# THE ICON GUARD. An <svg> with a viewBox and no width scales to whatever contains it, and on 2026-09-30 an
# arrow meant to be 15px rendered 571px square inside every tool card - across every language, both widths,
# and through a whole screenshot set that was reviewed and sent. It is invisible to a unit test, obvious in a
# picture, and easy to miss in a picture of a 6000px page. So the camera checks it: 32px is far above any icon
# this design uses (the largest is a 26px zodiac tile) and far below anything that could be called a mistake.
MAX_ICON_PX = 32
# `svg.icon` ONLY. A kundali chart is an <svg> with a viewBox and no width BY DESIGN - it scales to its
# container, renders at 480px and is correct at any size - so a rule over every <svg> flags the main thing the
# site draws. The pair that makes this airtight is the static test beside it: every inline <svg> in a v2
# template must carry `class="icon"` and its own width/height, so an icon cannot escape this check by not
# being one.
_ICON_JS = """() => [...document.querySelectorAll('svg.icon')].map(s => {
  const r = s.getBoundingClientRect();
  return {cls: s.getAttribute('class') || '(no class)', w: Math.round(r.width), h: Math.round(r.height)};
}).filter(i => Math.max(i.w, i.h) > %d)""" % MAX_ICON_PX


def _check_icons(page, where: str) -> list[str]:
    """Oversized inline SVGs on the page as rendered, as one complaint each."""
    return [f"{where}: <svg class=\"{icon['cls']}\"> renders {icon['w']}x{icon['h']}px "
            f"(limit {MAX_ICON_PX}px) - it has no width and is scaling to its container"
            for icon in page.evaluate(_ICON_JS)]


# THE GUTTER GUARD. `.wrap` supplies a 16px side gutter; a `padding:` SHORTHAND on an element that is also a
# `.wrap` silently resets it, and on 2026-09-30 `.v2-body` did exactly that - every card and line of text in
# the main grid ran flush into both screen edges on a phone. It is invisible at 1440, where the centring
# margin is 80px, which is why a desktop review and a unit test both missed it.
MIN_GUTTER_PX = 8
# The invariant is about the CONTENT of a `.wrap`, not the wrap itself: a `.wrap` box legitimately spans the
# full width and insets its children with padding, and a full-bleed band (the hero) is a deliberate design.
# So: for every `.wrap`, its own children must sit inside the gutter.
_GUTTER_JS = """() => { const bad = [];
  for (const wrap of document.querySelectorAll('main .wrap')) {
    for (const el of wrap.children) {
      const cs = getComputedStyle(el);
      if (cs.position === 'fixed' || cs.display === 'none' || cs.visibility === 'hidden') continue;
      const r = el.getBoundingClientRect();
      if (r.width < 40 || r.height < 8) continue;
      if (r.left < %d || (innerWidth - r.right) < %d)
        bad.push(`${el.tagName}.${(el.className || '').toString().split(' ')[0]} inside .${
          (wrap.className || '').toString().split(' ').slice(-1)[0]}`);
    } }
  return [...new Set(bad)].slice(0, 6); }""" % (MIN_GUTTER_PX, MIN_GUTTER_PX)


def _check_gutter(page, where: str, width: int) -> list[str]:
    """Blocks touching a screen edge. Only on narrow viewports: a full-bleed band is deliberate on desktop."""
    if width > 700:
        return []
    return [f"{where}: {name} touches the screen edge (needs a {MIN_GUTTER_PX}px gutter) - something reset "
            f"`.wrap`'s side padding, usually a `padding:` shorthand"
            for name in page.evaluate(_GUTTER_JS)]


# THE RESULT IS A PAGE TOO, and until now the camera never saw it. Everything below the fold on a tool page
# only exists after a submit, so a screenshot of `/birth-chart` is a picture of a form - which means the two
# guards above have never once run over the kundali, the tables or the dasha timeline. They are the tallest
# and most intricate markup on the site and exactly where an unsized icon would hide. `--fill` drives the form
# with an INVENTED person (no real birth data anywhere, here or in tests) and shoots the page again.
FILL = {"date": "1990-01-01", "time": "10:00", "city": "Pune"}


def _warm_city_index(base: str) -> None:
    """One throwaway lookup before the shoot. The first /api/cities call in a process pays for a cold index,
    and it timed out the very first form the camera tried - which looked like a broken home page rather than
    a cold cache."""
    import urllib.request

    try:
        urllib.request.urlopen(f"{base}/api/cities?q={FILL['city']}", timeout=30).read()
    except Exception:
        pass  # the fill routine reports it properly if the lookup is genuinely broken


def _fill_and_submit(page) -> bool:
    """Put an invented birth into whichever arrangement of the form this page has, and submit.

    The live page stages the fields and the prototype does not, so this walks the stages when it finds a
    Next button and fills everything at once when it does not. One routine for both arrangements, because a
    routine per arrangement would stop being a check that they behave the same."""
    left = dict(FILL)
    for _ in range(8):
        for field, value in list(left.items()):
            box = page.locator(f"#self-{field}")
            if not box.count() or not box.is_visible():
                continue
            box.fill(value)
            if field == "city":
                # The city list is a live lookup, and the first one in a process pays for a cold index. One
                # slow answer must not abort a hundred-shot run, so this retries once by retyping and then
                # gives up in a way the caller can report.
                option = page.locator("#self-city-list [role=option]").first
                for attempt in range(2):
                    try:
                        option.wait_for(state="visible", timeout=20_000)
                        break
                    except Exception:
                        if attempt:
                            return False
                        box.fill("")
                        page.wait_for_timeout(300)
                        box.fill(value)
                option.click()
            left.pop(field)
        nxt = page.locator("#tool-form [data-step-next]")
        if not nxt.count() or not nxt.is_visible():
            break
        nxt.click()
        page.wait_for_timeout(200)
    if left:
        return False
    page.locator("#submit-btn").click()
    page.wait_for_selector("#result:not([hidden])", timeout=60_000)
    page.wait_for_timeout(1_500)
    return True


# THE WIDTH GUARD. A phone page that scrolls sideways is a defect you cannot see in a full-page screenshot,
# because the screenshot simply comes out WIDER - and a wider picture of the same page looks like a picture
# of the same page. Three reading pages shipped this: a bare `1fr` grid column took its min-content width
# from a table carrying `min-width: 36rem`, and the layout viewport stretched from 390 to 594.
#
# Two checks, because either one alone misses it. `scrollWidth > innerWidth` is the usual test and it did NOT
# fire here: the layout viewport had already grown to match the content, so both were 594. The screenshot's
# own pixel width against the width that was ASKED for is what catches that.
def _check_width(page, where: str, width: int, shot: Path) -> list[str]:
    problems = []
    scroll, inner = page.evaluate("() => [document.documentElement.scrollWidth, innerWidth]")
    if scroll > inner + 1:
        problems.append(f"{where}: the page scrolls sideways - content is {scroll}px in a {inner}px viewport")
    if inner > width + 1:
        problems.append(f"{where}: the layout viewport grew to {inner}px for a {width}px screen - something "
                        f"inside has a min-width the column cannot shrink below (a bare `1fr` grid column "
                        f"takes its min-content width; use `minmax(0, 1fr)`)")
    return problems


# THE FORM-ROW GUARD. app.js builds a year <select> into the slot after the date input, and site.css gives
# that slot `display: block` - correct under a full-width field on the live page, and in the prototype's
# narrow form card it left a lone "Year" control stranded on its own line. It is a layout fact about rendered
# boxes, so it is checked where rendered boxes are: the two must share a row.
_YEAR_JUMP_JS = """() => {
  const date = document.querySelector('#self-date');
  const jump = document.querySelector('.field__jump select, .field__jump-select');
  if (!date || !jump) return null;                       // no form, or the script has not built it yet
  const a = date.getBoundingClientRect(), b = jump.getBoundingClientRect();
  return {gap: Math.round(Math.abs(a.top - b.top)), stacked: Math.abs(a.top - b.top) > 12};
}"""


def _check_form_row(page, where: str, width: int, variant: str) -> list[str]:
    # The PROTOTYPE only. On the live page the date field is full width and the jump below it is the design;
    # the guard fired on the live shots first time out, which is the guard working and the scope being wrong.
    if variant != "after" or width < 700:
        return []
    found = page.evaluate(_YEAR_JUMP_JS)
    if not found or not found["stacked"]:
        return []
    return [f"{where}: the year quick-jump sits {found['gap']}px below the date field instead of beside it"]


# THE CHART-PAIR GUARD. static/js/design-v2.js wraps the kundali and the positions table so they sit side by
# side on a wide screen. It depends on render.js emitting the table directly after `.chart-block`, which is
# an adjacency no test in the Python suite can see - if the renderer ever puts something between them the
# wrapper silently stops pairing and the result goes back to a 480px square beside 700px of nothing.
_CHART_PAIR_JS = """() => {
  const chart = document.querySelector('#result-body .chart-block');
  if (!chart) return null;                               // no chart on this page (matching, sade sati)
  const wrap = chart.parentNode;
  if (!wrap || wrap.className !== 'v2-chartpair') return {paired: false};
  const boxes = [...wrap.children].map(c => c.getBoundingClientRect());
  return {paired: true, sameRow: boxes.length === 2 && Math.abs(boxes[0].top - boxes[1].top) < 20};
}"""


def _check_chart_pair(page, where: str, width: int, variant: str) -> list[str]:
    if variant != "after" or width < 1100:
        return []
    found = page.evaluate(_CHART_PAIR_JS)
    if found is None:
        return []
    if not found["paired"]:
        return [f"{where}: the kundali is not paired with the positions table - design-v2.js found no "
                f"`.block` directly after `.chart-block`, so render.js has changed shape"]
    if not found["sameRow"]:
        return [f"{where}: the kundali and the positions table are paired but not on one row"]
    return []


# THE WIDTH-USE GUARD. The prototype's container was a fixed 1280, which on a 1920 monitor left 320px of
# empty page down each side and on a 2560 left 640px - half the screen. The container is now
# `clamp(1280px, 94vw, 1600px)`, and this asserts the page actually TAKES that width: a fixed max-width is
# one careless rule away from coming back, and it is invisible at the 1440 the review was done at.
#
# It also checks the other end. A container that grows without limit is the opposite mistake, so the rail is
# capped at 400 and the check fails if it exceeds that - a 525px "sidebar" stops being one.
WIDE_WIDTHS = (1920, 2560)
MAX_RAIL_PX = 400


def _expected_container(width: int) -> int:
    return min(int(width * 0.94), 1600)


def _check_width_use(page, where: str, width: int, variant: str) -> list[str]:
    if variant != "after" or width < 1600:
        return []
    found = page.evaluate("""() => {
      // Only a page that actually carries the design. The policy pages have no v2 template, so they keep
      // the previous 960px measure - which for a page that is nothing but prose is the RIGHT width, not a
      // missing one. Widening them to 1600 would be worse typography, so they are out of scope here rather
      // than forced into it.
      if (!document.body.classList.contains('design-v2')) return null;
      const wrap = document.querySelector('main .wrap');
      const rail = document.querySelector('.v2-rail');
      if (!wrap) return null;
      const w = wrap.getBoundingClientRect();
      return {wrap: Math.round(w.width), left: Math.round(w.left),
              rail: rail ? Math.round(rail.getBoundingClientRect().width) : 0};
    }""")
    if not found:
        return []
    problems = []
    expected = _expected_container(width)
    if found["wrap"] < expected - 4:
        problems.append(f"{where}: the container is {found['wrap']}px on a {width}px screen, {expected}px "
                        f"expected - {2 * found['left']}px of the page is empty margin")
    if found["rail"] > MAX_RAIL_PX + 4:
        problems.append(f"{where}: the rail is {found['rail']}px wide (cap {MAX_RAIL_PX}px) - at that width "
                        f"it competes with the article instead of sitting beside it")
    return problems


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main(argv: list[str] | None = None) -> int:
    from playwright.sync_api import sync_playwright

    parser = argparse.ArgumentParser(description="Before/after screenshots at several widths.")
    parser.add_argument("--paths", nargs="*", default=list(DEFAULT_PATHS))
    parser.add_argument("--widths", nargs="*", type=int, default=list(DEFAULT_WIDTHS))
    parser.add_argument("--out", type=Path, default=ROOT / "var" / "shots")
    parser.add_argument("--variants", nargs="*", default=list(VARIANTS))
    parser.add_argument("--fill", action="store_true",
                        help="on a page with a birth form, also submit it and shoot the result")
    args = parser.parse_args(argv)

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.05)
    base = f"http://127.0.0.1:{port}"
    args.out.mkdir(parents=True, exist_ok=True)
    if args.fill:
        _warm_city_index(base)

    written, problems = 0, []
    with sync_playwright() as playwright:
        options = launch_options()
        options["args"] = [*options.get("args", []), "--no-sandbox"]
        options["env"] = _fontconfig_env(options.get("env"))
        browser = playwright.chromium.launch(**options)
        try:
            for width in args.widths:
                mobile = width < 700
                # REDUCED MOTION, or the camera lies about long pages. The result's blocks carry `.reveal`
                # (`opacity: 0`) until an IntersectionObserver sees them, and a full-page screenshot never
                # scrolls - so every block below the first viewport was photographed INVISIBLE. That is how a
                # mobile result shot came to show two thousand pixels of empty cream with the dasha section
                # ghosted underneath, which was then read as a layout bug and chased through the DOM. The
                # site already honours `prefers-reduced-motion` by rendering `.reveal` fully opaque, so
                # asking for it here uses the page's own accessibility path rather than injecting CSS the
                # real page never sees.
                context = browser.new_context(viewport={"width": width, "height": 900},
                                              device_scale_factor=2 if mobile else 1,
                                              is_mobile=mobile, has_touch=mobile,
                                              reduced_motion="reduce")
                page = context.new_page()
                for path in args.paths:
                    for variant in args.variants:
                        page.goto(base + path + VARIANTS[variant], wait_until="load", timeout=60_000)
                        # Web fonts and the form's own script settle in well under this; it is a camera, not
                        # a benchmark, so the wait is generous rather than tuned.
                        page.wait_for_timeout(600)
                        slug = (path.strip("/") or "home").replace("/", "-")
                        name = f"{slug}-{width}-{variant}.png"
                        page.screenshot(path=str(args.out / name), full_page=True)
                        problems += _check_icons(page, name)
                        problems += _check_gutter(page, name, width)
                        problems += _check_width(page, name, width, args.out / name)
                        problems += _check_form_row(page, name, width, variant)
                        problems += _check_width_use(page, name, width, variant)
                        print(f"  wrote {args.out / name}")
                        written += 1

                        # A PAIR form (horoscope-matching) asks for two people under `boy-`/`girl-` ids and
                        # is not what this routine drives. Skipping it is stated, not silent: "the camera
                        # cannot drive this form" and "this form is broken" must not look the same.
                        if args.fill and page.locator("#tool-form").count():
                            if not page.locator("#self-city").count():
                                print(f"  (skipped the result of {slug}: not a single-person form)")
                                continue
                            if not _fill_and_submit(page):
                                problems.append(f"{name}: could not fill the form - a field the camera "
                                                f"expects is missing or never became visible")
                                continue
                            name = f"{slug}-result-{width}-{variant}.png"
                            page.screenshot(path=str(args.out / name), full_page=True)
                            problems += _check_icons(page, name)
                            problems += _check_gutter(page, name, width)
                            problems += _check_width(page, name, width, args.out / name)
                            problems += _check_chart_pair(page, name, width, variant)
                            print(f"  wrote {args.out / name}")
                            written += 1
                context.close()
        finally:
            browser.close()
    print(f"{written} screenshot(s) in {args.out}")
    if problems:
        print("\nLAYOUT PROBLEMS - do not send these screenshots:")
        for problem in sorted(set(problems)):
            print("  " + problem)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
