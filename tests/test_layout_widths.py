"""No page may scroll sideways, at any width a phone actually has, in any of the three trees.

This exists because an 11-pixel horizontal overflow reached production and survived two rounds of "no
horizontal overflow at 320-1600px" in reports of mine. Both of those reports were true about the checks that
produced them and useless as a guarantee: they came from throwaway Playwright scripts written for a specific
feature, and none of those scripts asserted this. A guarantee that lives in a script somebody has to remember
to run is not a guarantee, so it lives here now.

The overflow was in the shared header - the wordmark and the language switcher on one line - which means it
was on all 246 URLs of a deployed site, and mobile is most of the traffic.

**Why the stress case is the important half.** How wide "RashiKundli" and the three language names render
depends on which font the device actually resolves, and that differs between machines: the same header
measured 401px against a 390px viewport on one and 374px on another, from the same stylesheet. So measuring
the header as it happens to render here proves very little. The second test inflates the header's type by a
quarter and demands the layout still not overflow - which passes only if the design can reflow, rather than
because this machine's fonts happen to be narrow enough.
"""

import socket
import threading
import time

import pytest

from app.pdf import browser as pdf_browser
from app.web import i18n

# Every common phone width, the tablet band, and the two sides of the 1240px header breakpoint.
WIDTHS = (320, 360, 375, 390, 412, 414, 430, 480, 600, 768, 1024, 1239, 1240, 1440, 1600)
# One page of each shape: the chrome is shared, the differences are what the body puts in it.
PAGES = (("home", {}), ("kundali", {}), ("rashifal-rashi", {"rashi": "tula"}), ("consultation", {}))


@pytest.fixture(scope="module")
def chromium():
    ok, reason = pdf_browser.chromium_available()
    if not ok:
        pytest.skip(f"headless Chromium cannot launch here: {reason}")


@pytest.fixture(scope="module")
def live_site(chromium):
    import uvicorn

    from app.main import app

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), 0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True


def _overflow_at_each_width(page, url):
    """[(width, scrollWidth, clientWidth, widest element)] for every width that scrolls sideways.

    One load, then resize: a reflow per width rather than a navigation per width."""
    page.goto(url, wait_until="networkidle")
    found = []
    for width in WIDTHS:
        page.set_viewport_size({"width": width, "height": 860})
        page.wait_for_timeout(60)  # let the reflow settle before measuring
        doc = page.evaluate("() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]")
        if doc[0] > doc[1]:
            widest = page.evaluate("""() => {
                let worst = null, right = 0;
                document.querySelectorAll("*").forEach(el => {
                  const box = el.getBoundingClientRect();
                  if (box.width && box.right > right) { right = box.right; worst = el; }
                });
                return worst ? `${worst.tagName.toLowerCase()}.${worst.className || "-"} @${Math.round(right)}px` : "?";
            }""")
            found.append((width, doc[0], doc[1], widest))
    return found


@pytest.mark.browser
@pytest.mark.parametrize("lang", i18n.LANGS)
def test_no_page_scrolls_sideways_at_any_phone_width(live_site, lang):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as play:
        browser = play.chromium.launch(**pdf_browser.launch_options())
        page = browser.new_page(viewport={"width": 390, "height": 860})
        failures = []
        for key, params in PAGES:
            url = live_site + i18n.url_for(key, lang, **params)
            for width, scroll, client, widest in _overflow_at_each_width(page, url):
                failures.append(f"{key}/{lang} at {width}px: scrollWidth {scroll} > {client}, widest {widest}")
        browser.close()
    assert not failures, "pages scroll sideways:\n    " + "\n    ".join(failures)


@pytest.mark.browser
@pytest.mark.parametrize("lang", i18n.LANGS)
def test_the_header_still_fits_when_its_type_renders_a_quarter_wider(live_site, lang):
    """The real guarantee. The header holds a wordmark and a three-language switcher on one line, and how wide
    those are is a property of the reader's device, not of this stylesheet. Inflating the type by 25% stands in
    for a machine whose fonts are wider than ours; the layout has to reflow rather than overflow."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as play:
        browser = play.chromium.launch(**pdf_browser.launch_options())
        page = browser.new_page(viewport={"width": 390, "height": 860})
        page.goto(live_site + i18n.url_for("kundali", lang), wait_until="networkidle")
        page.add_style_tag(content=".site-header, .site-header * { font-size: 125% !important; }")
        failures = []
        for width in (320, 360, 375, 390, 412, 430):
            page.set_viewport_size({"width": width, "height": 860})
            page.wait_for_timeout(60)
            doc = page.evaluate("() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]")
            if doc[0] > doc[1]:
                culprit = page.evaluate("""() => {
                    const clipped = el => {
                      for (let p = el.parentElement; p; p = p.parentElement) {
                        const ox = getComputedStyle(p).overflowX;
                        if (ox === "auto" || ox === "scroll" || ox === "hidden") return true;
                      }
                      return false;
                    };
                    let worst = "nothing unclipped", right = innerWidth + 1;
                    document.querySelectorAll("*").forEach(el => {
                      const box = el.getBoundingClientRect();
                      if (box.width && box.right > right && !clipped(el)) {
                        right = box.right;
                        worst = `${el.tagName.toLowerCase()}.${el.className || "-"} @${Math.round(box.right)}px`;
                      }
                    });
                    return worst;
                }""")
                failures.append(f"{lang} at {width}px with 125% header type: "
                                f"scrollWidth {doc[0]} > {doc[1]}, widest {culprit}")
        browser.close()
    assert not failures, ("the header cannot reflow, so it overflows on any device whose fonts render wider "
                         "than this one's:\n    " + "\n    ".join(failures))


# The widths the UI audit asked for by name, alongside the sweep above.
AUDIT_WIDTHS = (320, 360, 414, 768, 1024, 1440)


@pytest.mark.browser
@pytest.mark.parametrize("lang", i18n.LANGS)
def test_nothing_in_the_header_is_a_hidden_scroller(live_site, lang):
    """The nav used to be `overflow-x: auto`. That is a visible scrollbar on any desktop without overlay
    scrollbars - and, worse for us, a scrolling child keeps its own overflow off the document, so every
    width test passed while the bar sat there. Checking the document width alone cannot see this class of
    bug, so the header's descendants are measured directly."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as play:
        browser = play.chromium.launch(**pdf_browser.launch_options())
        page = browser.new_page(viewport={"width": 390, "height": 860})
        page.goto(live_site + i18n.url_for("kundali", lang), wait_until="networkidle")
        failures = []
        for width in AUDIT_WIDTHS:
            page.set_viewport_size({"width": width, "height": 860})
            page.wait_for_timeout(80)
            scrollers = page.evaluate("""() => {
                const out = [];
                document.querySelectorAll(".site-header, .site-header *").forEach(el => {
                  if (el.scrollWidth > el.clientWidth + 1)
                    out.push(`${el.tagName.toLowerCase()}.${el.className || "-"} ` +
                             `${el.scrollWidth}>${el.clientWidth}`);
                });
                return out;
            }""")
            if scrollers:
                failures.append(f"{lang} at {width}px: {scrollers}")
        browser.close()
    assert not failures, "the header scrolls sideways inside itself:\n    " + "\n    ".join(failures)


@pytest.mark.browser
@pytest.mark.parametrize("lang", i18n.LANGS)
def test_every_nav_link_is_reachable_without_scrolling_the_nav(live_site, lang):
    """Collapsing the nav must not lose anything: at every width, each item is either visible already or one
    press of a disclosure away, and is inside the viewport once shown."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as play:
        browser = play.chromium.launch(**pdf_browser.launch_options())
        page = browser.new_page(viewport={"width": 390, "height": 860})
        page.goto(live_site + i18n.url_for("home", lang), wait_until="networkidle")
        expected = page.locator(".site-nav ul li").count()
        assert expected >= 6, expected
        failures = []
        for width in AUDIT_WIDTHS:
            page.set_viewport_size({"width": width, "height": 860})
            page.wait_for_timeout(80)
            toggle = page.locator(".site-nav__toggle")
            if toggle.is_visible():
                assert toggle.get_attribute("aria-expanded") == "false", (lang, width)
                toggle.click()
                assert toggle.get_attribute("aria-expanded") == "true", (lang, width)
            shown = page.locator(".site-nav ul a")
            for index in range(expected):
                box = shown.nth(index).bounding_box()
                if not box:
                    failures.append(f"{lang} at {width}px: nav item {index} is not rendered")
                elif box["x"] < -1 or box["x"] + box["width"] > width + 1:
                    failures.append(f"{lang} at {width}px: nav item {index} sits outside the viewport")
            if toggle.is_visible():
                toggle.click()
        browser.close()
    assert not failures, "nav items are unreachable:\n    " + "\n    ".join(failures)


@pytest.mark.browser
def test_the_language_switcher_is_reachable_at_every_width(live_site):
    """Wrapping is the escape valve for the overflow, so it must not drop the switcher out of reach: at every
    width all three languages stay inside the viewport and clickable."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as play:
        browser = play.chromium.launch(**pdf_browser.launch_options())
        page = browser.new_page(viewport={"width": 390, "height": 860})
        page.goto(live_site + i18n.url_for("home", "hi"), wait_until="networkidle")
        failures = []
        for width in (320, 360, 390, 430, 768, 1240, 1600):
            page.set_viewport_size({"width": width, "height": 860})
            page.wait_for_timeout(60)
            links = page.locator(".lang-switch a")
            assert links.count() == 3, width
            for index in range(3):
                box = links.nth(index).bounding_box()
                if not box or box["width"] < 24 or box["height"] < 24:
                    failures.append(f"{width}px: language link {index} is {box}")
                elif box["x"] < 0 or box["x"] + box["width"] > width + 1:
                    failures.append(f"{width}px: language link {index} sits outside the viewport at {box['x']}")
        browser.close()
    assert not failures, "the language switcher is not reachable:\n    " + "\n    ".join(failures)


# ---------------------------------------------------------------- the icon links and the header lockup
# tests/test_icons.py covers the assets themselves and the three files browsers fetch from the root. What
# belongs here is the markup that points at them and the one place a logo can do damage: the header, whose
# height at 390px was measured and tuned and which an image can silently undo.

import re  # noqa: E402  (kept beside the tests that use it)

from tests.test_web import client  # noqa: E402


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_the_head_offers_every_icon_a_browser_looks_for(lang):
    html = client.get(i18n.url_for("home", lang)).text
    head = html.split("</head>", 1)[0]
    links = re.findall(r'<link[^>]+>', head)

    def one(pattern):
        found = [link for link in links if re.search(pattern, link)]
        assert len(found) == 1, (pattern, found)
        return found[0]

    svg = one(r'rel="icon"[^>]*type="image/svg\+xml"')
    png32 = one(r'sizes="32x32"')
    png16 = one(r'sizes="16x16"')
    apple = one(r'rel="apple-touch-icon"')
    manifest = one(r'rel="manifest"')

    # The SVG is drawn for the size rather than downscaled to it, so it must be offered first.
    assert head.index(svg) < head.index(png32) < head.index(png16)
    for link in (svg, png32, png16, apple):
        assert "?v=" in link, f"{link} is not cache-busted like the stylesheet"
    assert "?v=" not in manifest, "the manifest's URL is its identity to the install prompt"
    for path in ("/static/icons/favicon-32.png", "/static/icons/favicon-16.png",
                 "/static/icons/apple-touch-icon-180.png", "/site.webmanifest"):
        assert client.get(path).status_code == 200, path
    assert '<meta name="theme-color" content="#241B54">' in head


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_the_header_logo_does_not_name_the_brand_twice(lang):
    """The wordmark beside it already names the link, so the image is decorative. It also carries width and
    height so the row reserves its space and the header cannot jump when the image arrives."""
    header = client.get(i18n.url_for("home", lang)).text.split("</header>", 1)[0]
    mark = re.search(r'<img class="brand__mark"[^>]*>', header)
    assert mark, f"{lang}: no logo in the header"
    assert 'alt=""' in mark.group(0), "a decorative logo beside the wordmark must not repeat the name"
    assert "width=" in mark.group(0) and "height=" in mark.group(0), "the logo reserves no space"
    brand = header.split('<a class="brand"', 1)[1].split("</a>", 1)[0]
    assert brand.count("RashiKundli") == 1, "the link is named twice"


def test_the_header_wears_the_emblem_rather_than_the_full_logo():
    """The full logo has a kundali lattice inside the planet. At 32 CSS px on a 1x screen that lattice does
    not read as a faint chart - it reads as dirt on the gold, which is worse than absent detail because the
    viewer reads "smeared image" rather than "small logo". The emblem is the same mark without the grid and
    is clean at every density, so one asset serves all of them and there is no resolution switch to get
    wrong. The full artwork belongs on surfaces with the pixels to show the grid.

    This was found by rendering at the density it ships at rather than at a flattering one, which is the
    whole reason it is asserted here instead of remembered."""
    header = client.get("/").text.split("</header>", 1)[0]
    mark = re.search(r'<img class="brand__mark"[^>]*src="([^"?]+)', header)
    assert mark, "no logo in the header"
    assert mark.group(1) == "/static/brand/emblem-96.png", (
        f"the header is wearing {mark.group(1)} - at 32px the full logo's grid reads as dirt on a 1x screen")
    assert client.get(mark.group(1)).status_code == 200


@pytest.mark.browser
@pytest.mark.parametrize("lang", i18n.LANGS)
def test_the_logo_does_not_cost_the_header_a_row(live_site, lang):
    """The header was measured at 141/128/128px at 390px before the logo went in. An image is exactly the
    kind of change that pushes the language switcher onto a row of its own and takes a fifth of a phone
    screen with it, so the budget is asserted rather than remembered."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as play:
        browser = play.chromium.launch(**pdf_browser.launch_options())
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.goto(live_site + i18n.url_for("kundali", lang), wait_until="networkidle")
        measured = page.evaluate("""() => {
            const header = document.querySelector(".site-header");
            const lockup = document.querySelector(".brand-lockup");
            const langs = document.querySelector(".lang-switch");
            return { height: Math.round(header.getBoundingClientRect().height),
                     sameRow: Math.abs(lockup.getBoundingClientRect().top
                                       - langs.getBoundingClientRect().top) < 40,
                     logo: Math.round(document.querySelector(".brand__mark").getBoundingClientRect().width),
                     overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth };
        }""")
        browser.close()
    assert not measured["overflow"], f"{lang}: the header overflows at 390px"
    assert measured["logo"] >= 24, f"{lang}: the logo collapsed to {measured['logo']}px"
    assert measured["sameRow"], f"{lang}: the language switcher has been pushed off the brand row"
    assert measured["height"] <= 140, (
        f"{lang}: the header is {measured['height']}px of an 844px screen. It was 141/128/128 before the "
        "logo, 146/132/132 with the logo and the poetic brand line stacked above the trust line, and "
        "122/122/122 once that line moved to the home hero. The budget is that measurement plus room for a "
        "device whose fonts render taller - not a target to grow into.")


# ---------------------------------------------------------------- the wide-screen ground
# Past 1240px the 960px reading column leaves a wide empty margin on each side, and those margins carry a
# faint star field. Three things about it are load-bearing and none of them is visible in a screenshot a
# person glances at, so they are measured here.
#
# The fourth - that the field never lands behind text - is NOT here. It is a claim about composited pixels
# under glyphs, and tests/test_rendered_contrast.py photographs that directly; a declared-colour reader
# cannot see it at all. What this file adds is the half that file does not cover: what the decoration
# COSTS, and that it cannot move anything.

import io  # noqa: E402

from app.web import STATIC_DIR  # noqa: E402

CSS = (STATIC_DIR / "css" / "site.css").read_text(encoding="utf-8")


def test_the_wide_screen_ground_is_a_tile_rather_than_a_download():
    """It is decoration on all 246 pages of a site whose traffic is mostly mid-range Android, so the size is
    asserted rather than assumed. An inline tile costs no request and rides the stylesheet's compression; a
    raster - or a tile that grows a few stars at a time - is the failure this catches."""
    tiles = re.findall(r'url\("(data:[^"]*)"\)', CSS)
    assert len(tiles) == 2, (
        f"site.css should carry exactly two inline background assets - the star field and the graha glyphs "
        f"- and it has {len(tiles)}. A third decoration is a decision, not an oversight.")
    tile, grahas = tiles
    for asset, cap, what in ((tile, 1200, "the star tile"), (grahas, 1600, "the graha tile")):
        assert asset.startswith("data:image/svg+xml,"), f"{what} must be vector, not a raster"
        assert len(asset.encode()) <= cap, f"{what} is {len(asset.encode())} bytes, over its {cap} cap"
    # Nothing twinkles. An animated background repaints forever, on every page, on a phone, for decoration -
    # and the sheet does carry animations elsewhere, so the check is scoped to this block rather than global.
    ground = CSS.split("---------- the wide-screen ground ----------", 1)[1].split("/* ----------", 1)[0]
    assert tile in ground, "the star tile has moved out of the wide-screen ground block"
    rules = re.sub(r"/\*.*?\*/", "", ground, flags=re.S)  # the prose there says "animation"; the rules must not
    for moving in ("animation", "transition", "@keyframes"):
        assert moving not in rules, f"the ground has grown a {moving} - decoration on 246 pages does not move"
    # A pattern is noise to a reader who asked for more contrast, or whose OS is choosing the colours.
    for query in ("@media (prefers-contrast: more)", "@media (forced-colors: active)"):
        assert f"{query} {{ body {{ background-image: none" in CSS, f"the ground ignores {query}"


@pytest.mark.browser
@pytest.mark.parametrize("lang", i18n.LANGS)
def test_the_wide_screen_ground_cannot_move_anything_and_stops_at_the_breakpoint(live_site, lang):
    """A background participates in no layout, so turning it off must change the page's pixels and nothing
    else: the document has to be exactly as tall without it.

    The field is now behind the reading column as well as beside it, so "nothing paints behind text" is no
    longer the claim - the claim is a BUDGET, and this measures it rather than trusting the stylesheet's
    arithmetic. Switch the field off and the only pixels that move are the ones it painted, so the darkest
    of those differences IS the field's effective strength, read straight off the screen:

        a dot of effective opacity `a` over cream paints `a*indigo + (1-a)*cream`,
        so its red channel moves by `a * (cream_red - indigo_red)` - and `a` falls out of the division.

    Both sides are asserted. Too strong is a legibility failure; too faint means the veil has gone opaque
    again and the specified effect is not there, which no contrast check would ever complain about.

    The narrow half matters just as much. Below 1240px the margins are a few pixels wide and a pattern in
    them would be grit, so the rule is scoped; 1239px proves the scope holds rather than trusting it.
    """
    from PIL import Image, ImageChops
    from playwright.sync_api import sync_playwright

    from tests import test_brand_css as brand

    cream = brand._rgb(brand.ROOT_TOKENS["--color-bg"])
    indigo = brand._rgb(brand.ROOT_TOKENS["--color-primary"])
    # The channel that moves most, so the estimate of `a` is taken where it is least noisy.
    channel = max(range(3), key=lambda i: cream[i] - indigo[i])
    span = cream[channel] - indigo[channel]

    def strength(diff):
        """The field's effective opacity in this region, from the largest difference in it."""
        extrema = diff.split()[channel].getextrema()
        return extrema[1] / span

    def shots(page, url):
        page.goto(url, wait_until="networkidle")
        plain = Image.open(io.BytesIO(page.screenshot(full_page=True))).convert("RGB")
        page.add_style_tag(content="body { background-image: none !important; }")
        page.wait_for_timeout(100)
        bare = Image.open(io.BytesIO(page.screenshot(full_page=True))).convert("RGB")
        return plain, bare

    url = live_site + i18n.url_for("home", lang)
    with sync_playwright() as play:
        browser = play.chromium.launch(**pdf_browser.launch_options())
        try:
            page = browser.new_page(viewport={"width": 1600, "height": 900})
            plain, bare = shots(page, url)
            column = page.evaluate("""() => { const w = document.querySelector("main .wrap").getBoundingClientRect();
                                             return [Math.round(w.left), Math.round(w.right)]; }""")
            page.close()
            assert plain.size == bare.size, (
                f"{lang}: the page is {plain.size} with the ground and {bare.size} without it - a background "
                "has been given something to do in layout")
            left, right = column
            in_column = strength(ImageChops.difference(plain.crop((left, 0, right, plain.height)),
                                                       bare.crop((left, 0, right, bare.height))))
            in_gutter = strength(ImageChops.difference(plain.crop((0, 0, left, plain.height)),
                                                       bare.crop((0, 0, left, bare.height))))

            page = browser.new_page(viewport={"width": 1239, "height": 900})
            narrow_plain, narrow_bare = shots(page, url)
            page.close()
        finally:
            browser.close()

    # The specified band is 4-6% behind text, with 10% an absolute ceiling. Both ends are asserted: too
    # strong spends headroom the caption token needs, and too faint means the veil has gone opaque again
    # and there is nothing for a frosted surface to be frosted OVER - which no contrast check would ever
    # complain about, because a missing decoration is perfectly legible.
    assert 0.03 <= in_column <= 0.065, (
        f"{lang}: the field reads at {in_column * 100:.1f}% behind the reading column, outside the 4-6% band")
    # The margins carry no text, so nothing about contrast constrains them - what constrains them is that
    # this exact strength was looked at and signed off, and it has already been lost once to a ceiling that
    # was later retracted as over-cautious. So it is pinned to the approved measurement rather than to a
    # safety argument: the darkest gutter pixel summed 148 across the channels at sign-off.
    assert 0.22 <= in_gutter <= 0.28, (
        f"{lang}: the field reads at {in_gutter * 100:.1f}% in the gutter. The approved strength is 25% - a "
        "group opacity of .25, whose declared value is its rendered peak because the tile is one group.")

    # The same number said in the units the decision is made in, and said against the ground that GOVERNS
    # rather than the friendliest one. --color-tint starts lower than the cream page, and although every
    # tinted surface is opaque today - measured: they move by 0/255, the field is behind them, not through
    # them - the frosted work is about to make some of them translucent, and then the tint is the ground
    # the budget has to have been written for. So it is written for it now.
    worst = min(("--color-bg", "--color-tint"),
                key=lambda token: brand.contrast(
                    brand._rgb(brand.ROOT_TOKENS["--color-muted"]),
                    tuple(round(in_column * i + (1 - in_column) * g)
                          for g, i in zip(brand._rgb(brand.ROOT_TOKENS[token]), indigo))))
    ground = tuple(round(in_column * i + (1 - in_column) * g)
                   for g, i in zip(brand._rgb(brand.ROOT_TOKENS[worst]), indigo))
    caption = brand.contrast(brand._rgb(brand.ROOT_TOKENS["--color-muted"]), ground)
    assert caption >= 5.0, (
        f"{lang}: caption text over the darkest of the field on {worst} measures {caption:.2f}:1. AA is 4.5 "
        "and this keeps half a point in hand on purpose, because the frosted surfaces go on top of it next.")

    # The margins are meant to read more strongly than the column - that split is the design, not a bug.
    assert in_gutter > in_column * 3, (
        f"{lang}: the gutter reads at {in_gutter * 100:.1f}% and the column at {in_column * 100:.1f}% - the "
        "veil over the column is no longer doing anything")

    assert ImageChops.difference(narrow_plain, narrow_bare).getbbox() is None, (
        f"{lang}: the ground is painted at 1239px, where the margins are too narrow to hold it")


# ---------------------------------------------------------------- the drifting grahas
# A desktop-only decoration: the gutters it lives in only exist past 1240px, so on a phone there is no
# element, no animation and nothing to measure. What is pinned here is the boundary (it never reaches the
# reading column, at any width), the cost (only `transform` is animated), and that both of the preferences
# that switch the star field off switch these off too.


def test_the_grahas_animate_nothing_but_transform():
    """An animation that touches layout or paint runs on the main thread every frame, forever, on every
    page. This is the difference between free and not, and it is one word in a keyframe away from being
    wrong, so it is read out of the stylesheet rather than remembered."""
    frames = re.search(r"@keyframes graha-drift\s*\{(.*?)\n\}", CSS, re.S)
    assert frames, "the graha drift keyframes have gone"
    properties = {m.group(1).strip() for m in re.finditer(r"([a-z-]+)\s*:", frames.group(1))}
    assert properties == {"transform"}, f"graha-drift animates {sorted(properties)}, not transform alone"

    block = CSS.split("---------- the drifting grahas ----------", 1)[1]
    rules = re.sub(r"/\*.*?\*/", "", block, flags=re.S)
    # The gutters exist only past the breakpoint, so the whole thing must sit behind that query.
    assert "@media (min-width: 1240px)" in rules, "the grahas are not scoped to the widths that have gutters"
    for query, what in ((r"@media \(prefers-reduced-motion: reduce\)", "reduced motion"),
                        (r"@media \(prefers-contrast: more\)", "more contrast"),
                        (r"@media \(forced-colors: active\)", "forced colours")):
        assert re.search(query + r"\s*\{[^}]*body::before", rules), f"the grahas ignore {what}"


@pytest.mark.browser
def test_the_drifting_grahas_never_reach_the_reading_column(live_site):
    """The one guarantee that matters: they are decoration for the empty margins, and the margins are the
    only place they may be.

    Measured by switching off their ink and diffing - NOT by switching off the elements. Removing them
    changes how the whole page is composited, which changes text antialiasing everywhere and swamps the
    thing being measured; an earlier version of this check did exactly that and reported the column as
    covered in glyphs when not one had moved. Toggling `background-image` leaves the layers in place, so
    the only difference between the two renders is the gold.
    """
    from PIL import Image, ImageChops
    from playwright.sync_api import sync_playwright

    def shot(page):
        return Image.open(io.BytesIO(page.screenshot())).convert("RGB")

    findings = []
    with sync_playwright() as play:
        browser = play.chromium.launch(**pdf_browser.launch_options())
        try:
            for width in (1240, 1440, 1920):
                page = browser.new_page(viewport={"width": width, "height": 1000})
                page.goto(live_site + i18n.url_for("home", "en"), wait_until="networkidle")
                page.add_style_tag(content="body::before, body::after { animation: none !important; }")
                page.wait_for_timeout(150)
                painted = shot(page)
                handle = page.add_style_tag(
                    content="body::before, body::after { background-image: none !important; }")
                page.wait_for_timeout(150)
                bare = shot(page)
                handle.evaluate("node => node.remove()")
                left, right = page.evaluate("""() => {
                    const w = document.querySelector("main .wrap").getBoundingClientRect();
                    return [Math.round(w.left), Math.round(w.right)]; }""")
                page.close()

                assert painted.size == bare.size, f"{width}px: the glyphs changed the layout"
                difference = ImageChops.difference(painted, bare)
                inside = difference.crop((left, 0, right, difference.height)).getbbox()
                if inside is not None:
                    findings.append(f"{width}px: glyph ink inside the column {left}..{right} at {inside}")
                if difference.getbbox() is None:
                    findings.append(f"{width}px: no glyph is painted anywhere - the decoration is missing")

            # And on a phone the effect must not exist at all, rather than exist and be hidden.
            page = browser.new_page(viewport={"width": 390, "height": 844})
            page.goto(live_site + i18n.url_for("home", "en"), wait_until="networkidle")
            running = page.evaluate("() => document.getAnimations().length")
            page.close()
        finally:
            browser.close()
    assert not findings, "the grahas have left the gutters:\n    " + "\n    ".join(findings)
    assert running == 0, (
        f"{running} animations are running at 390px, where there is no gutter for them to drift in - "
        "a phone should not be compositing a decoration it cannot show")


# ---------------------------------------------------------------- the kundali chart's legibility floor
# `.kundali { min-width: 288px }` plus a scrolling `.chart-holder`. 288 is not a round number chosen for
# comfort: it is what a .wrap gives at a 320px viewport after its padding, so the chart never shrinks below
# what the narrowest phone this site supports already shows. 320px was tried and measured, and it pushes two
# houses off a 320px screen until the reader drags the chart sideways - which for THIS graphic is worse than
# a small one, because a North Indian chart is read as one arrangement and a house you cannot see beside its
# neighbours is a missing house, not a smaller one.
#
# The load-bearing half of this is the browser check, not the string. A test that greps for "288px" fails
# only when somebody edits that exact character sequence; the measurements below fail when the chart starts
# clipping or stops holding its floor, whatever was edited to cause it.


def _render_a_chart(page, live_site, lang):
    """Drive the tool form until a chart is on screen. Modelled on tests/test_rendered_contrast.py, and it
    raises rather than skips for the same reason: a check that quietly measures nothing is worse than one
    that fails."""
    page.goto(live_site + i18n.url_for("kundali", lang), wait_until="networkidle")
    page.fill("#self-date", "1984-02-19")
    page.click("[data-step-next]")
    page.fill("#self-time", "09:05")
    page.click("[data-step-next]")
    page.fill("#self-city", "Pune")
    page.wait_for_timeout(400)          # the combobox filters from the city list app.js already fetched
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")
    page.click("#submit-btn")
    page.wait_for_selector("#result:not([hidden])", timeout=30000)
    page.wait_for_selector("svg.kundali", timeout=30000)
    page.wait_for_timeout(300)


def _chart_geometry(page):
    return page.evaluate("""() => {
        const svg = document.querySelector("svg.kundali");
        const holder = document.querySelector(".chart-holder");
        return { svg: Math.round(svg.getBoundingClientRect().width),
                 holderVisible: Math.round(holder.clientWidth),
                 holderContent: Math.round(holder.scrollWidth),
                 holderOverflowX: getComputedStyle(holder).overflowX,
                 pageOverflows: document.documentElement.scrollWidth > document.documentElement.clientWidth };
    }""")


def test_the_chart_floor_is_the_width_a_320px_phone_already_gives():
    """The documentary half. It pins the number and the finding, so that raising it back to 320 is a
    decision somebody makes against a recorded measurement rather than a tidy-up."""
    assert ".kundali { min-width: 288px; }" in CSS, (
        "the kundali's minimum width has moved. 288px is a 320px viewport's .wrap after padding; 320px was "
        "measured and pushes two houses off that screen")
    from tests import test_brand_css as brand   # its tiny CSS reader, rather than a second one here

    holder = next((decls for selector, decls in brand._rules(CSS) if selector == ".chart-holder"), None)
    assert holder is not None, ".chart-holder has lost its own rule"
    assert holder.get("overflow-x") == "auto", (
        f".chart-holder scrolls with overflow-x: {holder.get('overflow-x')!r} - it must scroll inside "
        "itself, like .table-wrap, or the chart widens the page instead")


@pytest.mark.browser
@pytest.mark.parametrize("lang", i18n.LANGS)
def test_the_chart_is_whole_on_the_narrowest_phone_and_never_widens_the_page(live_site, lang):
    """Half one: at 320px the chart must be at its floor AND completely visible. Those pull against each
    other - that is the point. Raise the floor and the holder starts clipping; drop the floor and the chart
    shrinks below what was measured as legible. Only the current value satisfies both.

    Half two: shrink the holder below the floor and the floor must still hold, the holder must scroll, and
    the PAGE must not. That is the half that fails if `min-width` is deleted outright, which half one alone
    would wave straight through.
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as play:
        browser = play.chromium.launch(**pdf_browser.launch_options())
        try:
            page = browser.new_page(viewport={"width": 320, "height": 900})
            _render_a_chart(page, live_site, lang)
            at_320 = _chart_geometry(page)
            # Now squeeze the holder well below the floor, at a width the site does support, so the floor
            # itself is what is being measured rather than an unsupported viewport.
            page.set_viewport_size({"width": 390, "height": 900})
            page.add_style_tag(content=".chart-block { max-width: 200px !important; }")
            page.wait_for_timeout(200)
            squeezed = _chart_geometry(page)
            page.close()
        finally:
            browser.close()

    assert at_320["svg"] >= 288, (
        f"{lang}: at a 320px viewport the chart renders {at_320['svg']}px wide - below the 288px floor, so "
        "the smallest phones are being served a chart smaller than the one that was measured as legible")
    assert at_320["holderContent"] <= at_320["holderVisible"] + 1, (
        f"{lang}: at a 320px viewport the chart is {at_320['holderContent']}px inside a "
        f"{at_320['holderVisible']}px holder, so part of it is off-screen until the reader drags it. A "
        "kundali is read as one arrangement; a house that is not beside its neighbours is a missing house.")
    assert not at_320["pageOverflows"], f"{lang}: the chart widened the whole page at 320px"

    assert squeezed["svg"] >= 288, (
        f"{lang}: squeezed into a 200px block the chart shrank to {squeezed['svg']}px - the floor is gone")
    assert squeezed["holderContent"] > squeezed["holderVisible"], (
        f"{lang}: the holder did not scroll when the chart was wider than it "
        f"({squeezed['holderContent']} in {squeezed['holderVisible']})")
    # Read the COMPUTED value, not the stylesheet. Without this the suite has a blind spot that was found
    # by mutating the rule rather than by reading the test: with the holder set to `overflow-x: visible` the
    # chart spills out of it and every geometric assertion above still passes, because at 390px there is
    # room inside .wrap to spill into and the document never gets wider. The spill only becomes a page-
    # widening bug on a narrower screen or a longer chart, which is to say it is invisible until it is not.
    assert squeezed["holderOverflowX"] in ("auto", "scroll"), (
        f"{lang}: .chart-holder computes overflow-x: {squeezed['holderOverflowX']} - the chart escapes it "
        "rather than scrolling inside it")
    assert not squeezed["pageOverflows"], (
        f"{lang}: the chart scrolled the PAGE rather than itself - .chart-holder must contain its own "
        "overflow the way .table-wrap does")
