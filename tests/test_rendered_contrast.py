"""Text contrast measured on the RENDERED PIXELS of real pages in a real browser.

`tests/test_brand_css.py` measures contrast by reading declared stylesheet colours. That is exact, and it
stays exact only while every surface behind text is opaque and flat. The moment a surface is translucent, is
patterned, or sits under an ancestor `opacity`, the declared background stops being the effective one: the
parser keeps computing a ratio from a colour that is not on the screen, and it keeps passing. (It does not
even have to be wrong to be blind - `_rgb()` there deliberately returns None for anything under 90% alpha, so
a translucent panel is simply skipped, and a skipped rule is a silent pass.) The site already carries such
surfaces - translucent white panels inside the indigo purchase card - and the page background already paints
a decorative field in the desktop gutters that is kept out from behind text by an opaque column. Whether it
really is kept out is a claim about composited pixels, and nothing in the suite could see it until now.

So nothing here computes a contrast ratio from the stylesheet. It photographs the page and measures what
the eye gets. (The sheet is read for three things that are not measurements and could not be obtained from
a picture: the palette's declared pairs, which the calibration below checks the pixels against; the
decorative tile; and the width it switches on at. All three are read from the RULES, never from the prose
in a comment - see CSS_RULES - so that no sentence in another teammate's file is load-bearing here.)

HOW THE COMPOSITE IS MEASURED
-----------------------------
Every page is rendered TWICE at the same viewport, scroll position and layout, with animations frozen:

  A. normally;
  B. with every glyph, text shadow and underline forced transparent.

Colour-only changes cannot reflow, so A and B are the same picture except where ink was laid down. That gives
three exact things per pixel, with no guessing about which pixels are "text":

  * the glyph coverage:  D = |A - B|, largest of the three channels;
  * the effective foreground: A, at the pixels where D is at its peak for that run of text - whatever the
    stylesheet says, this is the colour that was actually painted, after any translucency of the text itself,
    of its box, or of any ancestor opacity group;
  * the effective background: B, *underneath and beside the glyphs themselves* - not the element's declared
    background, and not some average of the whole line box.

ANTIALIASING. A glyph edge is a partial blend of ink and ground, so its pixels are neither. Averaging them
into the foreground drags the measured colour toward the background, which for hairline scripts means the
measurement stops being about colour and becomes about stroke width; averaging them into the background does
the reverse. Both are wrong and one of them flatters, so neither set is used: the foreground is read ONLY at
this run's peak coverage - the ink itself, top CORE_QUANTILE of the coverage histogram - and the background
comes from render B, where no glyph was ever drawn, so it cannot contain an edge blend at all. The partial
pixels in between are simply not measured. (Widening that band is not a neutral choice: a mean over the top
15% of coverage was tried first and reported 14px body copy 8% short, which turned legible 5.1:1 text into
45 reported failures on pages that were fine. That is the flattering-mean trap with its sign reversed - it
does not hide a fault, it invents one, and on hairline scripts it would invent one everywhere.)

CALIBRATION. Sensitivity is not accuracy: a detector can go red on bad composites and green on good ones
and still put the number in the wrong place, and a wrong number is what would wave a 4.6:1 frosted panel
through. So the scale is pinned against the arithmetic on flat opaque surfaces, where the declared ratio is
the right answer by definition (`test_the_pixels_agree_with_the_arithmetic_wherever_the_surface_is_opaque`).
It reproduces it EXACTLY - the foreground comes back as the declared hex, digit for digit, on every palette
pair, at every size, in all three scripts, and so does the ground.

That is only true because subpixel antialiasing is switched off (TEXT_RENDERING_ARGS). With it on, the
measurement ran 4-9% low and about 6% low right at the 4.5:1 decision, and two things followed that are
worth remembering. The first is that the gate would have needed a 3% blanket tolerance to avoid reporting
legible text as illegible - which is 3% of real failure waved through, bought with nothing. The second is
subtler: the artefact was not uniform, so it looked like a finding. It made Devanagari appear to measure
several percent closer to the arithmetic than Latin, and there was a perfectly good story about the
shirorekha rasterising to fuller pixels than thin Latin stems. The story was wrong. Both scripts measure
exactly, and the difference was the rasteriser all along.

LOCAL, NOT AVERAGE. A patterned ground has no single background colour. The mean of it is exactly the number
that hides the problem: one bright star behind one word disappears into the average of a paragraph. So the
background is the most extreme luminance that a real PATCH of ground behind the glyphs actually has - the
worst local ground the text sits on - found from both ends and scored at whichever is worse. Deliberately
not a quantile: a quantile degrades into "the dominant colour" exactly when the bad ground is rare, which
is the case a sparse pattern behind text presents.

THRESHOLDS. WCAG AA: 4.5:1 for normal text, 3:1 for large text, where large means >= 24px, or >= 18.66px at
weight >= 700. The size and weight are read from `getComputedStyle`, never from the tag name or a class.

A SECOND QUESTION, ASKED THE SAME WAY. Two tests near the end are not about ratios at all: they switch the
page's decorative tile off and require that no pixel inside any text run's box moves. That is exact rather
than graded, it needs no opinion about what a ground ought to look like, and it is the only way to check a
claim of the form "this pattern is never behind text" - which a declared-colour reader cannot see, because
the body reports the same background token whether the tile is under a word or beside it.

WHAT THIS CANNOT SEE - say it here rather than let a green run imply more than it earned:
  * text painted as a background (`background-clip: text`) is not ink, so D sees nothing and the run is
    counted unmeasurable rather than checked;
  * the far side of a horizontally scrollable table: those cells sit outside the captured page, so they are
    counted unmeasurable rather than checked. About 22 cells of the rendered chart, bounded by the ceiling
    in `test_the_rendered_chart_is_legible_on_the_pixels_it_is_painted_on` rather than left to grow;
  * a text shadow used AS the legibility mechanism gets no credit: shadows are switched off in render B and
    excluded from the foreground core, so such text is scored on its raw colours (conservative);
  * of the states the site has, two: as a page loads, and with a chart rendered into it. A hover, a focus
    ring, an opened disclosure and the panel that appears after a purchase are not photographed here;
  * video, animation and anything that changes between the two shots (both are frozen, but a late-arriving
    image would defeat that);
  * contrast of non-text things - icons, borders, chart strokes - which WCAG scores differently;
  * the two widths it is run at. 390px and 1440px are a phone and a desktop above the 1240px breakpoint
    where the page paints its decorative field; a layout that only goes wrong at, say, 768px is not seen
    here (tests/test_layout_widths.py sweeps widths, but for overflow, not for contrast).
"""

import io
import os
import re
import socket
import threading
import time
from pathlib import Path

import pytest

from app.pdf import browser as pdf_browser
from app.web import STATIC_DIR, i18n
from tests import test_brand_css as brand

CSS = (STATIC_DIR / "css" / "site.css").read_text(encoding="utf-8")
# Rules only. Everything this file reads out of the stylesheet - the tile, the breakpoint - is read from
# here, so that no sentence in a comment is ever load-bearing for a test in another teammate's file.
CSS_RULES = re.sub(r"/\*.*?\*/", " ", CSS, flags=re.S)

# Chromium finds system fonts through XDG_DATA_HOME. On a box without root, where the Noto packages were
# unpacked from .debs into a directory of their own, that has to be pointed at explicitly - otherwise every
# Devanagari glyph on the hi and mr trees renders as a missing-glyph box, and two of the three language trees
# would look measured while nothing of the sort was measured. Setting it here rather than leaving it to
# whoever types the pytest command is the difference between a guarantee and a thing somebody remembers.
UNPACKED_SHARE = Path.home() / ".local/share/astro-chromium/root/usr/share"


# Subpixel (LCD) text antialiasing spreads a glyph's coverage across the R, G and B channels separately, so
# no pixel of a stem is ever the declared colour: a neutral #767676 comes back as #7d797c, and the contrast
# it measures is 4 to 9 percent low - worst on the darkest inks and, far more awkwardly, about 6% low right
# at the 4.5:1 decision. That is not a property of the design and no design decision can change it; it is a
# property of this machine's rasteriser, and a reader on a device without subpixel AA never sees it.
#
# Switched off, the measurement is EXACT: the foreground comes back as the declared hex, digit for digit,
# and the drift across the whole contrast range is 0.0%. The trade is worth stating plainly - a reader whose
# device does use subpixel AA gets a hair less contrast than this reports. WCAG is defined on specified
# colours, so measuring them is the correct reading of the standard; and the alternative is five to nine
# percent of noise on the one number the gate exists to decide, which would make it useless near AA.
TEXT_RENDERING_ARGS = ("--disable-lcd-text",)


def launch_options() -> dict:
    """`app.pdf.browser.launch_options()`, plus the font search path and greyscale text antialiasing."""
    options = pdf_browser.launch_options()
    env = dict(options.get("env") or os.environ)
    if not env.get("XDG_DATA_HOME") and UNPACKED_SHARE.is_dir():
        env["XDG_DATA_HOME"] = str(UNPACKED_SHARE)
    options["env"] = env
    options["args"] = [*options.get("args", []), *TEXT_RENDERING_ARGS]
    return options


# ---------------------------------------------------------------- what is measured, and how hard

AA = brand.AA          # 4.5:1, normal text
AA_LARGE = 3.0         # 3:1, and "large" is measured (below), not taken on trust
LARGE_PX = 24.0
LARGE_BOLD_PX = 18.66
BOLD = 700

DEVICE_SCALE = 2       # render at 2x: a 14px Devanagari stroke has ink pixels at 2x and barely any at 1x
CORE_QUANTILE = 0.005  # the foreground is read at this run's most-covered pixels - see `measure_run`
INK_FLOOR = 14         # below this, hiding the text changed nothing here: no measurable glyph
# The worst ground behind the glyphs is found as a FEATURE, not as a quantile. A quantile answers "what is
# the darkest 5% of this sample", which silently becomes "the sample's dominant colour" as soon as the dark
# thing is rarer than 5% - and a sparse star field behind a line of text is about 1%. Measured: with the
# decorative tile painted under the content column, 46 of 156 runs had it inside their box and the quantile
# form reported a flat cream ground for every single one of them. So instead: the most extreme luminance
# that a real patch of ground actually has (MIN_FEATURE_PX of it, after the hairline erosion), and then only
# the pixels within FEATURE_BAND of that.
MIN_FEATURE_PX = 8     # a patch this big is a thing behind the text, not a stray pixel
FEATURE_BAND = 10      # luminance units around the extreme, so the feature is averaged and not its edges
BG_HALO = 9            # MaxFilter size: the ground is sampled under the glyphs and ~2 CSS px around them.
                       # Widening it past "strictly behind the ink" is deliberate - a bright point beside a
                       # stroke hurts legibility as much as one under it - and it was checked to cost
                       # nothing: at 1, 1.5, 2 and 3 CSS px the real pages report the same 1233 runs and
                       # zero failures, because the sample is bounded by the text's own line box either way.
MIN_CORE_PX = 6        # fewer full-coverage pixels than this and the run is reported, not scored
MIN_BG_PX = 24
# The ground has to be a SURFACE, not a hairline. A table cell's 1px bottom rule is two device pixels of
# --color-line sitting inside the text's own line box, and sampling it as "the background behind this text"
# turned legible table text into a 3.90:1 failure on the rendered chart. A rule beside a glyph is not the
# ground the glyph sits on. This is the same distinction app/pdf's gold detector draws with MinFilter, for
# the same reason, and it is set so that a hairline (2 device px) erodes away while the decorative tile's
# own dots (6-10 device px across) survive.
SURFACE_PX = 3
# With greyscale text (TEXT_RENDERING_ARGS) the measurement is exact on a flat surface, so this is float
# slack and nothing more. It was 3% while subpixel antialiasing was in play, which is the amount of
# real failure a gate would have had to wave through to avoid crying wolf near the threshold - a good
# illustration of what a measurement artefact costs if it is tolerated instead of removed.
MEASUREMENT_TOLERANCE = 0.002

# Pages: one of each shape the site has. The chrome (header, nav, footer, purchase card) is shared, so
# covering it once covers it everywhere; the bodies are what differ.
PAGES = (("home", {}), ("kundali", {}), ("rashifal-rashi", {"rashi": "tula"}), ("consultation", {}))
# A phone, and a desktop width above the 1240px breakpoint where the page paints its decorative field.
WIDTHS = (390, 1440)

_SKIP_TAGS = "SCRIPT, STYLE, NOSCRIPT, TEMPLATE, TITLE, OPTION, SELECT, TEXTAREA"

# Text runs, as line boxes in DOCUMENT coordinates, with the computed type they are set in. A Range over the
# text node (not the element box) gives one rect per rendered line, tight to the text itself, so a heading's
# padding and a paragraph's siblings are not dragged into the measurement.
_RUNS_JS = """() => {
  const runs = [];
  const skip = new Set(%r.split(', '));
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let node;
  while ((node = walker.nextNode())) {
    if (!node.textContent.trim()) continue;
    const el = node.parentElement;
    if (!el || skip.has(el.tagName) || el.closest('.visually-hidden, .skip-link, [hidden]')) continue;
    const style = getComputedStyle(el);
    if (style.visibility !== 'visible' || parseFloat(style.opacity) === 0) continue;
    if (el.checkVisibility && !el.checkVisibility({contentVisibilityAuto: true, visibilityProperty: true})) continue;
    const range = document.createRange();
    range.selectNodeContents(node);
    const where = el.tagName.toLowerCase() +
                  (typeof el.className === 'string' && el.className.trim()
                     ? '.' + el.className.trim().split(/\\s+/).join('.') : '');
    for (const rect of range.getClientRects()) {
      if (rect.width < 6 || rect.height < 6) continue;
      runs.push({x: rect.x + scrollX, y: rect.y + scrollY, w: rect.width, h: rect.height,
                 size: parseFloat(style.fontSize), weight: parseInt(style.fontWeight, 10) || 400,
                 clipText: style.webkitBackgroundClip === 'text' || style.backgroundClip === 'text',
                 where, text: node.textContent.replace(/\\s+/g, ' ').trim().slice(0, 32)});
    }
  }
  return runs;
}""" % _SKIP_TAGS

# Render B. `color` alone is not enough: an element may set -webkit-text-fill-color, an underline is painted
# from text-decoration-color, and a shadow survives a transparent glyph. Layout is untouched, so B is pixel
# for pixel the same page with the ink lifted off it.
_HIDE_TEXT_CSS = """*, *::before, *::after {
  color: transparent !important;
  -webkit-text-fill-color: transparent !important;
  text-decoration-color: transparent !important;
  text-shadow: none !important;
  caret-color: transparent !important;
}
/* The kundali grid is an SVG and its glyphs are painted with `fill`, which `color` does not touch. Without
   this the chart's own labels are identical in both renders, so they read as "no glyph coverage" and drop
   out of the population - the chart being exactly the surface most in need of measuring. Only text is
   targeted: the grid lines and the house polygons are part of the ground and must stay. */
svg text, svg tspan { fill: transparent !important; }"""

# Both shots must be the same picture. Anything that moves on its own would otherwise read as glyph coverage.
_FREEZE_CSS = """*, *::before, *::after {
  animation: none !important; transition: none !important; caret-color: transparent !important;
}"""


# ---------------------------------------------------------------- pixel arithmetic (PIL only, no numpy)


def _srgb_to_linear_lut():
    """256-entry LUT: sRGB byte -> WCAG-linear light, rescaled back to 0..255 so it fits in an 8-bit band."""
    out = []
    for raw in range(256):
        part = raw / 255
        out.append(round(255 * (part / 12.92 if part <= 0.03928 else ((part + 0.055) / 1.055) ** 2.4)))
    return out


_LINEAR = _srgb_to_linear_lut()


def _luma(image):
    """Relative luminance as an L image (0..255 == 0.0..1.0). Linearise each channel, then weight."""
    from PIL import Image

    bands = [band.point(_LINEAR) for band in image.split()[:3]]
    return Image.merge("RGB", bands).convert("L", (0.2126, 0.7152, 0.0722, 0))


def _coverage(shot, hidden):
    """D = |A - B| per pixel, largest channel. Non-zero exactly where ink was laid down."""
    from PIL import ImageChops

    diff = ImageChops.difference(shot, hidden).split()[:3]
    return ImageChops.lighter(ImageChops.lighter(diff[0], diff[1]), diff[2])


def _bin_at(histogram, fraction, *, from_top=False, floor=1):
    """The bin holding the `fraction` quantile of a histogram, counted from whichever end."""
    total = sum(histogram)
    if not total:
        return None
    target = max(floor, int(total * fraction))
    seen = 0
    for index in range(255, -1, -1) if from_top else range(256):
        seen += histogram[index]
        if seen >= target:
            return index
    return 255 if from_top else 0


def _count(mask):
    return mask.convert("L").histogram()[255]


def _mean_rgb(image, mask):
    from PIL import ImageStat

    return tuple(ImageStat.Stat(image, mask).mean[:3])


def _threshold(image, level, *, above=True):
    return image.point(lambda v: 255 if (v >= level if above else v <= level) else 0, mode="1")


def contrast_floor(size, weight):
    """WCAG's large-text allowance, from the type as the browser computed it - never from a class name."""
    large = size >= LARGE_PX or (size >= LARGE_BOLD_PX and weight >= BOLD)
    return AA_LARGE if large else AA


def crop_box(image, run, scale=DEVICE_SCALE):
    """A run's line box in image pixels, clamped to the capture. None when too little of it was captured."""
    box = (max(0, int(run["x"] * scale)), max(0, int(run["y"] * scale)),
           min(image.width, int((run["x"] + run["w"]) * scale + 0.999)),
           min(image.height, int((run["y"] + run["h"]) * scale + 0.999)))
    return None if box[2] - box[0] < 4 or box[3] - box[1] < 4 else box


def measure_run(shot, hidden, run, scale=DEVICE_SCALE):
    """Measure one line box. Returns a dict with `ratio`/`floor`, or with `unmeasured` saying why not.

    `shot` and `hidden` are the two full-page renders (identical but for the ink); `run` is one line box in
    CSS document coordinates as `_RUNS_JS` reports it."""
    from PIL import ImageChops, ImageFilter

    box = crop_box(shot, run, scale)
    if box is None:
        return dict(run, unmeasured="off the captured page")
    ink, ground = shot.crop(box), hidden.crop(box)

    coverage = _coverage(ink, ground)
    peak = _bin_at(coverage.histogram(), CORE_QUANTILE, from_top=True, floor=MIN_CORE_PX)
    if peak is None or peak < INK_FLOOR:
        # Hiding the glyphs changed nothing here. Either nothing is painted (text clipped to a background,
        # or covered by something opaque), or the ink is the colour of its own ground - which is a 1:1
        # contrast failure. The two are not distinguishable from pixels, so this is reported, not scored,
        # and `test_the_checker_can_still_see` keeps the unmeasured share from growing quietly.
        return dict(run, unmeasured=f"no glyph coverage (peak {peak})")

    # Every pixel the glyph touches lies on the segment between the ground B and the ink F, at its own
    # coverage: A = a*F + (1-a)*B, so D = a*|F-B|. Only the pixels at PEAK D are the ink itself, and a mean
    # over any wider band lands short of F - measured at 8% of the ink range for 14px body copy, which is
    # enough to turn a legible 5:1 pairing into a reported 4.3:1. That is the flattering-mean trap with its
    # sign reversed: it does not hide a fault, it invents one, and on hairline scripts it would invent one
    # on every page. So the band is the top CORE_QUANTILE of coverage and nothing below it.
    core = _threshold(coverage, peak)
    if _count(core) < MIN_CORE_PX:
        return dict(run, unmeasured="too few full-coverage pixels")
    foreground = _mean_rgb(ink, core)

    # The ground behind the glyphs and within ~1 CSS px of them, taken from the render with no ink in it.
    near = core.convert("L").filter(ImageFilter.MaxFilter(BG_HALO)).point(lambda v: 255 if v > 127 else 0, mode="1")
    luma = _luma(ground)
    histogram = luma.histogram(mask=near)
    if sum(histogram) < MIN_BG_PX:
        return dict(run, unmeasured="too little ground behind the glyphs")

    # Both ends of the ground's luminance, kept separately. The worse of the two is what the run is scored
    # on; keeping the pair as well is what lets a caller ask the other question - not "is this legible" but
    # "is this ground FLAT", which is how a pattern leaking in behind text is caught without having to know
    # in advance what colour the leak would be.
    # The dominant ground, which is a surface by construction and is always available as the fallback.
    tails = {"typical": _mean_rgb(ground, ImageChops.logical_and(
        _threshold(luma, _bin_at(histogram, 0.5, floor=1), above=False), near))}
    for name, from_top in (("dark", False), ("light", True)):
        # The most extreme luminance with a real patch behind it, then a narrow band around that value.
        level = _bin_at(histogram, 0.0, from_top=from_top, floor=MIN_FEATURE_PX)
        edge = min(255, level + FEATURE_BAND) if not from_top else max(0, level - FEATURE_BAND)
        # Eroded BEFORE it meets the glyph band, so what is tested is the shape of the coloured region in
        # the page, not the shape of the sliver of it that happens to lie beside a stroke.
        region = _threshold(luma, edge, above=from_top).convert("L")
        surface = region.filter(ImageFilter.MinFilter(SURFACE_PX)).point(lambda v: 255 if v > 127 else 0, mode="1")
        tail = ImageChops.logical_and(surface, near)
        if _count(tail) < MIN_FEATURE_PX:
            continue                      # that extreme was a hairline or a speck, not a ground
        tails[name] = _mean_rgb(ground, tail)
    ratio, background = min((brand.contrast(foreground, rgb), rgb) for rgb in tails.values())
    return dict(run, ratio=ratio, floor=contrast_floor(run["size"], run["weight"]),
                fg=foreground, bg=background,
                bg_dark=tails.get("dark", background), bg_light=tails.get("light", background))


def _hex(rgb):
    return "#%02x%02x%02x" % tuple(min(255, max(0, round(c))) for c in rgb)


def describe(measured, where=""):
    return (f"{where}{measured['where']} {measured['size']:.0f}px/{measured['weight']}: "
            f"{_hex(measured['fg'])} on {_hex(measured['bg'])} = {measured['ratio']:.2f}:1 "
            f"(needs {measured['floor']}:1) - {measured['text']!r}")


# ---------------------------------------------------------------- driving a page


# Chromium does not necessarily paint content that has never been scrolled into view, and a full-page
# screenshot does not force it to: the capture comes back with those regions blank. It is not a size limit
# and not a capture bug - a clipped shot of the same region is blank too, because nothing was ever painted
# there. Walking the viewport down the document once realises it all, and afterwards the capture is complete.
#
# This is not a tidy-up. Before the sweep, a rendered chart measured 266 runs and reported 277 as having no
# glyph coverage; after it, 521 and 22. The gate was reading under half the densest text on the site and
# calling the rest unmeasurable - and a floor on how many runs were measured would not have caught it,
# because 266 is a perfectly healthy-looking number. Hence the bound on the UNMEASURED share as well.
_REALISE_JS = """() => new Promise(resolve => {
  const step = Math.max(200, window.innerHeight);
  let y = 0;
  const go = () => {
    window.scrollTo({top: y, behavior: 'instant'});
    y += step;
    if (y < document.documentElement.scrollHeight + step) requestAnimationFrame(go);
    else { window.scrollTo({top: 0, behavior: 'instant'}); requestAnimationFrame(() => resolve()); }
  };
  go();
})"""


def _shoot(page):
    """Freeze anything that moves, realise the whole document, list the text runs, photograph it all."""
    from PIL import Image

    page.add_style_tag(content=_FREEZE_CSS)
    page.evaluate(_REALISE_JS)
    page.wait_for_timeout(120)
    runs = page.evaluate(_RUNS_JS)
    return runs, Image.open(io.BytesIO(page.screenshot(full_page=True))).convert("RGB")


def page_report(page, scale=DEVICE_SCALE):
    """Photograph the page twice and measure every text run. -> (failures, measured, unmeasured)."""
    from PIL import Image

    runs, shot = _shoot(page)
    handle = page.add_style_tag(content=_HIDE_TEXT_CSS)
    page.wait_for_timeout(60)
    hidden = Image.open(io.BytesIO(page.screenshot(full_page=True))).convert("RGB")
    handle.evaluate("node => node.remove()")
    assert shot.size == hidden.size, f"the two renders differ in size ({shot.size} vs {hidden.size})"

    failures, measured, unmeasured = [], [], []
    for run in runs:
        if run["clipText"]:
            unmeasured.append(dict(run, unmeasured="text is painted as a background"))
            continue
        result = measure_run(shot, hidden, run, scale)
        if "unmeasured" in result:
            unmeasured.append(result)
            continue
        measured.append(result)
        if result["ratio"] < result["floor"] * (1 - MEASUREMENT_TOLERANCE):
            failures.append(result)
    return failures, measured, unmeasured


# ---------------------------------------------------------------- fixtures


@pytest.fixture(scope="module")
def chromium():
    ok, reason = pdf_browser.chromium_available()
    if not ok:
        pytest.skip(f"headless Chromium cannot launch here: {reason}")
    pytest.importorskip("PIL")


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


@pytest.fixture(scope="module")
def browser(chromium):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as play:
        instance = play.chromium.launch(**launch_options())
        yield instance
        instance.close()


# ---------------------------------------------------------------- the controls
#
# A green result from this file is worth nothing unless the checker has been shown to go red. Each control
# below is a composite the checker MUST fail, next to one it must pass, and the pairs are chosen to be the
# exact shapes a declared-colour reader cannot see.

CONTROL_PAGE = """<!DOCTYPE html><html lang="%(lang)s"><head><meta charset="utf-8"><style>
%(css)s
body { margin: 0; padding: 24px; }
%(extra)s
</style></head><body>%(body)s</body></html>"""

# Two dark patterned grounds, and the difference between them is a finding rather than a detail.
#
# GLASS_FIELD is textured but its texture stays dark, so light text over a card on it is legible and the
# checker must not complain. BRIGHT_FIELD has near-white points in it - and a white glyph with one of those
# immediately behind it measures 1.38:1, because at that spot the stroke and the ground are the same colour.
# That is a real legibility hazard and not an artefact: it is what "light text over a star field" does. It
# surfaced by breaking the control below, which had been written with near-white stars and an assumption
# that white text over them was the SAFE case. It is not, and the two are separated here rather than the
# field being quietly dimmed until the control went green again.
GLASS_FIELD = ("background-color:#12102b;background-image:radial-gradient(#2a2f55 1.2px, transparent 1.3px),"
               "radial-gradient(#242a4a 1px, transparent 1.1px);"
               "background-size:23px 19px, 37px 31px;background-position:0 0, 11px 7px;padding:20px;")
BRIGHT_FIELD = ("background-color:#12102b;background-image:radial-gradient(#cfd6ff 1.2px, transparent 1.3px),"
                "radial-gradient(#9aa6ff 1px, transparent 1.1px);"
                "background-size:23px 19px, 37px 31px;background-position:0 0, 11px 7px;padding:20px;")
WORDS = "Kundali reading for the year ahead with dasha windows and remedies"
DEVANAGARI = "कुंडली वाचन पुढील वर्षासाठी दशा कालावधी आणि उपाय सहित तपशील"


def _control(browser, width, body, extra="", lang="en"):
    page = browser.new_page(viewport={"width": width, "height": 900}, device_scale_factor=DEVICE_SCALE)
    try:
        page.set_content(CONTROL_PAGE % {"css": CSS, "extra": extra, "body": body, "lang": lang},
                         wait_until="load")
        return page_report(page)
    finally:
        page.close()


@pytest.mark.browser
def test_a_translucent_card_over_a_field_is_measured_on_the_composite(browser):
    """The headline case. The same card, the same ground, the same stylesheet - only the ink colour differs.

    The grey passes nothing on the composite and the white passes comfortably, and NEITHER of them can be
    told apart by reading the declarations, because the surface they sit on is `rgba(..., .10)` and a
    declared-colour reader has no opaque background to compute a ratio against at all."""
    assert brand._rgb("rgba(255, 255, 255, .10)") is None, (
        "a declared-colour reader now resolves a 10%-alpha surface - re-check what this file is backstopping")

    card = "background:rgba(255,255,255,.10);border-radius:12px;padding:18px;font-size:16px;"
    body = (f'<div style="{GLASS_FIELD}">'
            f'<div style="{card}color:#7b7b8c"><p>grey {WORDS}</p></div>'
            f'<div style="{card}color:#ffffff"><p>white {WORDS}</p></div></div>')
    failures, measured, _unmeasured = _control(browser, 900, body)

    scored = {}
    for item in measured:
        scored.setdefault(item["text"].split()[0], item)
    assert set(scored) == {"grey", "white"}, sorted(scored)
    assert scored["grey"]["ratio"] < AA, f"the checker cannot see grey-on-glass: {describe(scored['grey'])}"
    assert scored["white"]["ratio"] >= AA, (
        f"the checker fails white-on-glass, which is legible: {describe(scored['white'])}")
    assert [f["text"].split()[0] for f in failures] == ["grey"], [describe(f) for f in failures]


@pytest.mark.browser
def test_an_ancestor_opacity_collapses_a_pair_the_stylesheet_calls_legible(browser):
    """The sharpest control there is: here the declared pair PASSES AA and the rendered pixels do not.

    `#595959` on `#ffffff` is 7:1 by declaration, and a parser reading those two values is right about them
    and useless about the page - an ancestor `opacity` composites BOTH of them onto the dark ground behind,
    and what the reader actually gets is under 2:1. Nothing about the card's own declarations changed."""
    declared = brand.contrast((0x59, 0x59, 0x59), (255, 255, 255))
    assert declared > AA, f"the control's declared pair must be one the stylesheet reader passes ({declared:.2f})"

    body = (f'<div style="{GLASS_FIELD}"><div style="opacity:.22">'
            f'<div style="background:#ffffff;color:#595959;padding:18px;font-size:16px">'
            f'<p>{WORDS}</p></div></div></div>')
    failures, measured, _unmeasured = _control(browser, 900, body)
    assert measured, "nothing was measured at all"
    assert failures, (f"the declared pair is {declared:.2f}:1 and the composite is "
                      f"{min(m['ratio'] for m in measured):.2f}:1, and the checker passed it")
    assert min(m["ratio"] for m in measured) < 2.5, [describe(m) for m in measured]


# Pairs from the site's own palette, on surfaces that really are opaque and flat - the case where the two
# methods MUST agree. (background token, text token, how far the measurement may drift).
#
# The allowance is not a fudge, it is a measured property of glyph rasterisation and it is one-directional.
# At body-text sizes the most-covered pixel of a stem is still not 100% covered, so the ink reads a shade
# short of its declared colour and the ratio comes out LOW. It is a function of size, not of colour: the
# same pair measured at 28px and up reproduces the declared hex exactly. It is also worst where it matters
# least - on very dark or very saturated inks, which are nowhere near the 4.5:1 decision - and under 1% on
# the mid-tone greys that actually sit close to the threshold, which is what BOUNDARY_DRIFT pins.
OPAQUE_PAIRS = (("--color-bg", "--color-ink", 0.01), ("--color-bg", "--color-muted", 0.01),
                ("--color-surface", "--color-muted", 0.01), ("--color-card", "--color-on-dark", 0.01),
                ("--color-primary", "--color-accent", 0.01), ("--color-warning-bg", "--color-warning", 0.01))
BOUNDARY_DRIFT = 0.01   # a pair sitting ON the threshold must measure within 1% of the arithmetic


@pytest.mark.browser
def test_the_pixels_agree_with_the_arithmetic_wherever_the_surface_is_opaque(browser):
    """Going red on bad composites and green on good ones is not enough: a detector can do both and still be
    numerically wrong, and a wrong number is exactly what would wave a 4.6:1 frosted panel through. So the
    scale itself is pinned. On a flat opaque surface there is no composite to argue about and the declared
    ratio IS the right answer, so the measurement has to reproduce it.

    It does, to within the rasterisation allowance above - and note which half is exact: the BACKGROUND
    comes back as the declared hex, digit for digit, on all six pairs. That is the half this file exists to
    measure, and it carries no allowance at all."""
    cases = [(f"c{index}", ground, ink, allow) for index, (ground, ink, allow) in enumerate(OPAQUE_PAIRS)]
    body = "".join(
        f'<p style="background:var({ground});color:var({ink});font-size:16px;padding:10px">{tag} {WORDS}</p>'
        for tag, ground, ink, _allow in cases)
    _failures, measured, _unmeasured = _control(browser, 900, body)
    scored = {}
    for item in measured:
        scored.setdefault(item["text"].split()[0], item)
    assert set(scored) == {tag for tag, *_ in cases}, sorted(scored)

    for tag, ground, ink, allow in cases:
        got = scored[tag]
        declared = brand.contrast(brand._rgb(brand.ROOT_TOKENS[ink]), brand._rgb(brand.ROOT_TOKENS[ground]))
        drift = (got["ratio"] - declared) / declared
        assert drift <= 0.005, (
            f"{ink} on {ground}: the pixels read {got['ratio']:.2f}:1 against a declared {declared:.2f}:1. "
            "Reading HIGH is the unsafe direction for a gate - it would pass text that is not legible")
        assert -allow <= drift, (
            f"{ink} on {ground}: {declared:.2f}:1 declared, {got['ratio']:.2f}:1 measured ({drift:+.1%}) - "
            "the measurement has drifted off the scale it claims to use")
        # the half with no allowance: the ground behind the glyphs is the ground, exactly
        assert _hex(got["bg"]) == brand._hex(brand._rgb(brand.ROOT_TOKENS[ground])), (
            f"{ground}: the ground behind the glyphs measured {_hex(got['bg'])}")

    # And the accuracy that actually decides outcomes: a pair sitting ON the threshold. This is built
    # rather than borrowed from the palette - it used to check whichever token happened to sit near 4.5,
    # which stopped existing the moment the caption token was darkened, and a control that evaporates when
    # the product improves is not a control. #767676 on white is 4.54:1 by construction.
    near = _control(browser, 900,
                    f'<p style="background:#ffffff;color:#767676;font-size:16px">edge {WORDS}</p>')[1]
    assert near, "the boundary pair measured nothing"
    declared = brand.contrast((0x76, 0x76, 0x76), (255, 255, 255))
    assert abs(declared - AA) < 0.1, f"the boundary pair is {declared:.2f}:1, not on the threshold"
    drift = (near[0]["ratio"] - declared) / declared
    assert abs(drift) <= BOUNDARY_DRIFT, (
        f"a pair sitting exactly on the {AA}:1 threshold measured {near[0]['ratio']:.2f}:1 against a "
        f"declared {declared:.2f}:1 ({drift:+.1%}). Near the threshold the reading has to be tight, or the "
        "gate starts reporting legible text as illegible and gets switched off. MEASUREMENT_TOLERANCE is "
        "sized against this number, so if it moves, that moves with it.")


@pytest.mark.browser
def test_caption_text_is_what_a_darkened_ground_costs_first(browser):
    """Which token decides what may ever sit behind text here, and how much room it has.

    Body ink on cream is 15.8:1 and is not the constraint - at a 19% wash it is still above 10:1. Captions
    are. Measured on rendered pixels, before and after the palette was changed for this reason:

        black wash over cream     caption was #6E6A8A       caption is #5C5875
          none                        4.80:1                    6.32:1
          3%                          4.48:1  <- under AA       5.89:1
          8%                          4.05:1                    5.33:1
          12%                         3.65:1                    4.81:1
          19%                         3.10:1                    4.07:1  <- under AA

    The old token passed AA at 4.84:1 with nothing behind it: a ground darkened by THREE PERCENT - fainter
    than any frosting worth drawing - took it under. The new one holds to roughly 15%, which is a budget a
    frosted surface can actually be designed against. This test pins the shape of that rather than the exact
    numbers: captions must fail before body text, and the gate must see it happen."""
    caption = brand.contrast(brand._rgb(brand.ROOT_TOKENS["--color-muted"]),
                             brand._rgb(brand.ROOT_TOKENS["--color-bg"]))
    assert caption > 5.5, (
        f"caption text is {caption:.2f}:1 on the page ground. Below about 5.5 it has no room for a "
        "translucent surface at all - re-derive the table above before trusting this test.")

    wash = ("background:var(--color-bg);padding:16px;"
            "background-image:linear-gradient(rgba(0,0,0,.19), rgba(0,0,0,.19));")
    body = (f'<div style="{wash}">'
            f'<p style="color:var(--color-muted);font-size:16px">caption {WORDS}</p>'
            f'<p style="color:var(--color-ink);font-size:16px">body {WORDS}</p></div>')
    failures, measured, _unmeasured = _control(browser, 900, body)

    scored = {}
    for item in measured:
        scored.setdefault(item["text"].split()[0], item)
    assert set(scored) == {"caption", "body"}, sorted(scored)
    assert scored["caption"]["ratio"] < scored["body"]["ratio"], "captions are no longer the first to go"
    assert scored["caption"]["ratio"] < AA, (
        "a 19% wash no longer costs caption text its AA pass - re-derive the budget: "
        + describe(scored["caption"]))
    assert scored["body"]["ratio"] > 9, describe(scored["body"])
    assert [f["text"].split()[0] for f in failures] == ["caption"], [describe(f) for f in failures]


@pytest.mark.browser
def test_the_worst_local_ground_is_scored_rather_than_the_average_one(browser):
    """A patterned ground has no single background colour, and its MEAN is the number that hides the fault.

    `#595959` text sits on a white card striped with `#bbbbbb`. Averaged, the ground is near-white and the
    pair scores about 6:1 - a comfortable pass. On the stripe it is about 3.6:1 and fails. The test asserts
    both: that the average would have passed, and that the checker fails anyway."""
    stripes = ("background-image:repeating-linear-gradient(90deg,#bbbbbb 0 4px,#ffffff 4px 16px);"
               "background-color:#ffffff;padding:18px;color:#595959;font-size:16px;")
    body = f'<div style="{stripes}"><p>{WORDS} {WORDS}</p></div>'
    failures, measured, _unmeasured = _control(browser, 900, body)

    average_ground = tuple((3 * 255 + 0xBB) / 4 for _ in range(3))   # 3 parts white to 1 part stripe
    averaged = brand.contrast((0x59, 0x59, 0x59), average_ground)
    assert averaged > AA, f"the control no longer passes on the averaged ground ({averaged:.2f}:1)"
    assert failures, (f"averaging the ground gives {averaged:.2f}:1 and the checker agreed with the average "
                      f"instead of the stripe: {[describe(m) for m in measured]}")
    assert all(f["ratio"] < 4.2 for f in failures), [describe(f) for f in failures]


@pytest.mark.browser
@pytest.mark.parametrize("veil, expected", [(0.10, "legible"), (0.22, "illegible")])
def test_caption_text_sitting_on_the_field_is_measured_deterministically(browser, veil, expected):
    """Caption text ON the decorative field, put there on purpose instead of waited for.

    This exists because the page cannot be relied on to produce the case. Measured across twelve
    page/language combinations with the field behind 640 text runs, the number of CAPTION runs whose
    sampled ground contained any of it was ZERO - caption text lives inside opaque cards, tinted panels and
    the footer, and the field is behind those rather than through them. So the gate's green on the real
    pages says "no caption happened to sit on the field", which is a weaker claim than it looks, and a
    reader of a passing run should not have to work that out for themselves.

    Here the coverage is structural: a dense field of dots, each wide enough to survive the hairline
    erosion, under caption-register text, so nearly every run has one behind it. At the strength the real
    tile actually renders (measured at 10% of the cream-to-indigo span, not the 19% its attributes declare)
    caption text must stay legible; past the budget it must not. Both directions, because a control that
    has only been shown to pass is a number nobody has tested.

    When the cards go frosted this stops being a synthetic case and becomes the common one: the 186 caption
    runs currently protected by opaque surfaces will be sitting on exactly this."""
    indigo = brand._rgb(brand.ROOT_TOKENS["--color-primary"])
    cream = brand._rgb(brand.ROOT_TOKENS["--color-bg"])
    dot = _over(indigo, cream, veil)
    # 6px dots on a 15px grid: wide enough to keep a core through MinFilter(SURFACE_PX), dense enough that
    # a line of text cannot miss them, which is the whole difference from waiting for the real tile.
    field = (f"background-color:var(--color-bg);"
             f"background-image:radial-gradient(rgb{dot} 3px, transparent 3.2px);"
             f"background-size:15px 13px;padding:16px;color:var(--color-muted);"
             f"font-size:15px;line-height:1.8;")
    body = f'<div style="{field}">' + "".join(f"<p>{WORDS}</p>" for _ in range(6)) + "</div>"
    failures, measured, _unmeasured = _control(browser, 900, body)

    assert len(measured) >= 6, f"only {len(measured)} runs measured"
    on_field = [m for m in measured if max(abs(a - b) for a, b in zip(m["bg"], cream)) > 6]
    assert len(on_field) >= len(measured) * 0.8, (
        f"only {len(on_field)} of {len(measured)} caption runs actually measured the field as their ground - "
        "this control is supposed to make that certain rather than likely")

    declared = brand.contrast(brand._rgb(brand.ROOT_TOKENS["--color-muted"]), dot)
    if expected == "legible":
        assert declared >= AA, f"the control's own premise moved: caption on {_hex(dot)} is {declared:.2f}:1"
        assert not failures, [describe(f) for f in failures]
    else:
        assert declared < AA, f"the control's own premise moved: caption on {_hex(dot)} is {declared:.2f}:1"
        assert len(failures) >= len(on_field) * 0.8, (
            f"caption text on a field past its budget: only {len(failures)} of {len(on_field)} runs were "
            f"reported: {[describe(m) for m in measured[:3]]}")


@pytest.mark.browser
def test_a_bright_speck_behind_light_text_is_caught(browser):
    """The inverse of the sparse case, and the one a dark frosted design walks into.

    A near-white point behind a white stroke leaves nothing to see at that spot - locally the glyph and its
    ground are the same colour. Over the same card, over the same field, the only difference from the
    legible case is how bright the points are. A checker that scores the ground by its average cannot tell
    these two apart at all, because on average both fields are dark."""
    card = "background:rgba(255,255,255,.10);border-radius:12px;padding:18px;font-size:16px;"
    body = (f'<div style="{BRIGHT_FIELD}"><div style="{card}color:#ffffff">'
            f'<p>{WORDS} {WORDS}</p></div></div>')
    failures, measured, _unmeasured = _control(browser, 900, body)
    assert measured, "nothing measured"
    assert failures, (
        "white text with near-white points behind it was passed - the bright half of the field is being "
        f"averaged into the dark half: {[describe(m) for m in measured]}")
    assert min(f["ratio"] for f in failures) < 2.5, [describe(f) for f in failures]


@pytest.mark.browser
def test_a_ground_that_is_bad_only_rarely_is_still_found(browser):
    """The sparse case, which is the one a decorative pattern actually presents.

    The striped control above darkens a quarter of the ground; this one darkens about one part in seventy,
    as a scatter of small dots - the shape of a star field behind a line of text. That difference is not
    cosmetic, it is the whole failure: asking for "the worst 5% of the ground" answers "the dominant colour"
    as soon as the bad ground is rarer than 5%, and returns a flat, innocent number with no sign that
    anything was missed. Measured on the real page with the decorative tile painted under the content
    column, the quantile form reported a flat cream ground for all 46 runs that had the tile inside them.

    So the ground is found as a FEATURE - the most extreme luminance with a real patch behind it - and this
    test is what stops that quietly reverting to an average."""
    speck = ("background-color:#ffffff;"
             "background-image:radial-gradient(#bbbbbb 1.6px, transparent 1.7px);"
             "background-size:26px 22px;padding:18px;color:#595959;font-size:16px;")
    body = f'<div style="{speck}"><p>{WORDS} {WORDS}</p></div>'
    failures, measured, _unmeasured = _control(browser, 900, body)
    assert measured, "nothing measured"

    on_white = brand.contrast((0x59, 0x59, 0x59), (255, 255, 255))
    on_speck = brand.contrast((0x59, 0x59, 0x59), (0xBB, 0xBB, 0xBB))
    assert on_white > AA > on_speck, f"the control's own pair no longer straddles AA ({on_white}, {on_speck})"
    assert failures, (
        "a ground that is only occasionally bad was averaged away - the dots cover about 1.5% of it, which "
        f"is under any quantile worth using: {[describe(m) for m in measured]}")
    assert min(f["ratio"] for f in failures) < 4.2, [describe(f) for f in failures]


@pytest.mark.browser
def test_large_text_is_allowed_three_to_one_and_the_size_is_measured_not_claimed(browser):
    """`#8a8a8a` on white is about 3.45:1: legible as large text, not as body text. The four cases below
    differ only in computed size and weight, so they prove the branch is taken from what the browser
    computed rather than from the tag, the class or the element's own word for it."""
    pair = "background:#ffffff;color:#8a8a8a;"
    body = "".join(
        f'<p style="{pair}font-size:{size}px;font-weight:{weight}" data-case="{name}">{name} {WORDS}</p>'
        for name, size, weight in (("huge", 30, 400), ("bold-large", 19, 700),
                                   ("small", 16, 400), ("plain-19", 19, 400)))
    failures, measured, _unmeasured = _control(browser, 900, body)

    scored = {m["text"].split()[0]: m for m in measured}
    assert set(scored) == {"huge", "bold-large", "small", "plain-19"}, sorted(scored)
    for name in ("huge", "bold-large"):
        assert scored[name]["floor"] == AA_LARGE, describe(scored[name])
        assert scored[name]["ratio"] >= AA_LARGE, describe(scored[name])
    for name in ("small", "plain-19"):
        assert scored[name]["floor"] == AA, describe(scored[name])
        assert scored[name]["ratio"] < AA, describe(scored[name])
    failed = {f["text"].split()[0] for f in failures}
    assert failed == {"small", "plain-19"}, f"{failed}: {[describe(f) for f in failures]}"


# A missing glyph is still a shape: Chromium draws a box for it, the box has ink, and the ink has perfectly
# good contrast against the page. So a Devanagari measurement on a machine with no Devanagari font is green
# for a reason that has nothing to do with Devanagari - the exact failure this whole file exists to stop.
# Tofu is detectable with certainty rather than by eye: every missing glyph is drawn at the SAME width, so a
# tofu-rendered string is exactly as wide as the same number of private-use characters (which no font has).
# Real Devanagari shapes matras and conjuncts into fewer, narrower clusters and comes out decidedly shorter.
_TOFU_JS = """(text) => {
  const probe = document.createElement('span');
  probe.style.cssText = 'position:absolute;white-space:pre;font-size:14px;visibility:hidden';
  document.body.appendChild(probe);
  probe.textContent = text;
  const real = probe.getBoundingClientRect().width;
  probe.textContent = '\\uE123'.repeat(text.length);
  const missing = probe.getBoundingClientRect().width;
  probe.remove();
  return [real, missing];
}"""


@pytest.fixture(scope="module")
def devanagari(browser):
    page = browser.new_page()
    try:
        page.set_content("<!DOCTYPE html><meta charset='utf-8'><body></body>", wait_until="load")
        return page.evaluate(_TOFU_JS, DEVANAGARI.replace(" ", ""))
    finally:
        page.close()


@pytest.mark.browser
def test_devanagari_is_really_drawn_before_any_of_it_is_believed(devanagari):
    """Measured here: 324px of real Marathi against 400px of missing-glyph boxes. Equal widths mean boxes."""
    real, missing = devanagari
    assert real < missing * 0.97, (
        f"Devanagari is rendering as missing-glyph boxes ({real:.0f}px against {missing:.0f}px of boxes), so "
        "every contrast number for the hi and mr trees in this file would be a number about boxes. Point "
        "XDG_DATA_HOME at the directory the Noto packages were unpacked into - see UNPACKED_SHARE above.")


@pytest.mark.browser
@pytest.mark.parametrize("lang, words", [("en", WORDS), ("mr", DEVANAGARI)])
def test_hairline_script_is_not_penalised_for_being_thin(browser, devanagari, lang, words):
    """Devanagari sets thinner strokes and denser conjuncts than Latin at the same size, so a measurement
    that averaged antialiased edge pixels into the foreground would report it as low-contrast while the
    colours are perfect - a false failure on two of the three language trees. Ink on cream at 14px must pass
    in BOTH scripts, and grey-on-cream must fail in both: the detector has to be neither blind nor jumpy
    about stroke weight.

    Measured, there is no script difference at all: Latin, Marathi and Hindi all reproduce the declared
    ratio exactly at 14px. An earlier version of this comment reported Devanagari as measuring several
    percent CLOSER to the arithmetic than Latin and explained it by the shirorekha rasterising to fuller
    pixels than thin Latin stems. That was subpixel antialiasing, not the script, and the explanation was
    a plausible story fitted to an artefact. The real Devanagari hazard here was never the measurement -
    it was the font: with no Devanagari font installed every glyph becomes a box, which has perfectly good
    contrast and would have made two language trees look checked. That is what the test above refuses to let happen."""
    if lang == "mr" and not devanagari[0] < devanagari[1] * 0.97:
        pytest.fail("this control would be measuring missing-glyph boxes, not Devanagari")
    good = "background:var(--color-bg);color:var(--color-ink);font-size:14px;padding:12px;"
    bad = "background:var(--color-bg);color:#b3b0c4;font-size:14px;padding:12px;"
    ok_failures, ok_measured, ok_unmeasured = _control(
        browser, 700, f'<p style="{good}">{words} {words}</p>', lang=lang)
    assert ok_measured, f"{lang}: nothing measurable at 14px"
    assert not ok_unmeasured, f"{lang}: {[u['unmeasured'] for u in ok_unmeasured]}"
    assert not ok_failures, f"{lang}: ink on cream at 14px reported as a failure: " \
                            f"{[describe(f) for f in ok_failures]}"
    assert min(m["ratio"] for m in ok_measured) > 10, (
        f"{lang}: ink on cream is 15.8:1 declared; measured {min(m['ratio'] for m in ok_measured):.1f}:1 - "
        "the measurement is being dragged down by stroke width")

    bad_failures, _bad_measured, _ = _control(browser, 700, f'<p style="{bad}">{words} {words}</p>', lang=lang)
    assert bad_failures, f"{lang}: the detector cannot see low contrast in this script"


# ---------------------------------------------------------------- the real pages


@pytest.mark.browser
@pytest.mark.parametrize("lang", i18n.LANGS)
def test_no_text_on_any_page_is_illegible_on_the_pixels_it_is_painted_on(live_site, browser, lang):
    """The gate. Every text run on a real page, at a phone width and a desktop width, scored on the pixels
    behind it rather than on the colours the stylesheet declares.

    READ THE GREEN NARROWLY. The population here is every text run the page has, but which GROUND each run
    gets is the page's business, not this test's. Measured with the decorative field behind 640 of 1573
    runs, the number of caption-register runs whose sampled ground contained any of it was zero: caption
    text sits inside opaque cards, tinted panels and the footer, and the field is behind those rather than
    through them. So a pass here means "no caption happened to land on the field" and not "caption text on
    the field is legible". The second claim is made deterministically by
    `test_caption_text_sitting_on_the_field_is_measured_deterministically`, which puts it there on purpose,
    and that is what the design should be read as resting on until frosted surfaces make it the common
    case on real pages."""
    failures = []
    for width in WIDTHS:
        page = browser.new_page(viewport={"width": width, "height": 900}, device_scale_factor=DEVICE_SCALE)
        try:
            for key, params in PAGES:
                page.goto(live_site + i18n.url_for(key, lang, **params), wait_until="networkidle")
                found, _measured, _unmeasured = page_report(page)
                failures += [describe(item, where=f"{key}/{lang} @{width}px ") for item in found]
        finally:
            page.close()
    assert not failures, ("text is illegible on the pixels it is actually painted on:\n    "
                          + "\n    ".join(failures))


# The controls above are built pages. This one is the real site with a frosted-surface system dropped onto
# it: translucent panels, a patterned ground, and the body ink left exactly as the stylesheet declares it.
# Every declared pair on the page is untouched and still passes a declared-colour reader; what changes is
# only what is behind the words.
GLASS_PREVIEW = """
  html { background-color: #141033 !important; }
  body { background-color: transparent !important;
         background-image: radial-gradient(#cfd6ff 1.2px, transparent 1.3px),
                           radial-gradient(#9aa6ff 1px, transparent 1.1px) !important;
         background-size: 23px 19px, 37px 31px !important;
         background-repeat: repeat, repeat !important; }
  .card, .cta, .step, .panel, .chart-download, main section, article {
         background-color: rgba(255, 255, 255, .12) !important;
         -webkit-backdrop-filter: blur(8px); backdrop-filter: blur(8px); }
"""


@pytest.mark.browser
def test_the_gate_goes_red_when_a_frosted_surface_is_put_under_real_text(live_site, browser):
    """The control that matters most, because it is the gate itself rather than a model of it: the same real
    page, measured twice, differing only in what sits behind the words.

    Clean, it passes. With translucent panels over a patterned ground it fails in quantity - and note what
    was NOT changed to make it fail: not one text colour, not one declared foreground/background pair. A
    reader of declarations would report the second page exactly as legible as the first."""
    assert brand._rgb("rgba(255, 255, 255, .12)") is None, "the declared-colour reader now resolves this"

    page = browser.new_page(viewport={"width": 390, "height": 900}, device_scale_factor=DEVICE_SCALE)
    try:
        page.goto(live_site + i18n.url_for("home", "en"), wait_until="networkidle")
        clean, clean_measured, _ = page_report(page)
        page.add_style_tag(content=GLASS_PREVIEW)
        page.wait_for_timeout(150)
        frosted, frosted_measured, _ = page_report(page)
    finally:
        page.close()

    assert not clean, ["the page is not clean to start with:", *[describe(f) for f in clean]]
    assert len(clean_measured) >= 40 and len(frosted_measured) >= 40, (len(clean_measured), len(frosted_measured))
    assert len(frosted) >= 20, (
        f"only {len(frosted)} of {len(frosted_measured)} runs failed once the surfaces went translucent over "
        "a patterned ground - the gate cannot see the thing it is being put in place to stop")
    assert min(f["ratio"] for f in frosted) < 2.0, [describe(f) for f in frosted[:5]]


# The densest small text on the site is not on any page at load: the planet table, the dated dasha rows and
# the dosha verdicts only exist after somebody submits the form. Much of it is set in the caption register,
# which `test_a_faint_wash_over_cream_takes_caption_text_under_aa_before_body_text_notices` shows has about
# a third of a point of headroom - so it is the worst thing on the site to be unable to measure, and it is
# named as a surface the frosted system is meant to cover.
#
# The chart fixture is the one the PDF tests already use: a documented public figure, chosen for this repo
# precisely so that no real customer's and no operator's birth details are ever committed.
CHART_FIXTURE = {"date": "1931-10-15", "time": "06:30", "city": "Miraj"}


def render_a_chart(page, live_site, lang):
    """Drive the tool form until a chart is on screen. Raises rather than skips if it never arrives.

    A gate that quietly skips is the failure this file exists to prevent, and this is the one check here
    that depends on more than a page load - the form's JavaScript, the city list and the chart API all have
    to work. If any of them stops working, the right outcome is a red test naming the step that died, not a
    silently smaller population."""
    page.goto(live_site + i18n.url_for("kundali", lang), wait_until="networkidle")
    page.fill("#self-date", CHART_FIXTURE["date"])
    page.click("[data-step-next]")
    page.fill("#self-time", CHART_FIXTURE["time"])
    page.click("[data-step-next]")
    page.fill("#self-city", CHART_FIXTURE["city"])
    page.wait_for_timeout(400)          # the combobox filters from the city list app.js already fetched
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")
    assert page.locator("#submit-btn").is_visible(), f"{lang}: the form never reached its last step"
    page.click("#submit-btn")
    page.wait_for_selector("#result:not([hidden])", timeout=30000)
    page.wait_for_timeout(400)          # let the chart and the tables finish painting
    blocks = page.locator("#result-body .block, #result-body table").count()
    assert blocks >= 2, f"{lang}: the result appeared but rendered {blocks} blocks - nothing to measure"


@pytest.mark.browser
@pytest.mark.parametrize("lang", i18n.LANGS)
def test_the_rendered_chart_is_legible_on_the_pixels_it_is_painted_on(live_site, browser, lang):
    """The gate, extended to the state that only exists after somebody types something.

    Everything above measures pages as they load. This measures the free chart result - birth facts, the
    chart itself, the planet positions, the dasha timeline and any dosha verdict - at a phone width and a
    desktop one, in all three trees, because the result markup is language-dependent and the Devanagari
    table rows are where a caption token on a tinted ground would go wrong first."""
    failures, measured_total, skipped = [], 0, []
    for width in WIDTHS:
        page = browser.new_page(viewport={"width": width, "height": 900}, device_scale_factor=DEVICE_SCALE)
        try:
            render_a_chart(page, live_site, lang)
            found, measured, unmeasured = page_report(page)
            measured_total += len(measured)
            skipped += [f"@{width}px {item['where']} {item['unmeasured']} - {item['text']!r}"
                        for item in unmeasured]
            failures += [describe(item, where=f"chart/{lang} @{width}px ") for item in found]
        finally:
            page.close()
    # A floor on the result itself, not on the page it sits in: the chart state has to contribute a real
    # number of runs of its own, or this test has quietly become the load-state test run twice.
    assert measured_total >= 600, f"{lang}: only {measured_total} runs measured across the chart pages"
    # And a ceiling on what it gives up on, which is the half that actually bites. Before the document was
    # realised before capture (_REALISE_JS), this state measured 266 runs and shrugged at 277 - and a floor
    # on the measured count sails straight through that, because 266 looks perfectly healthy. What is left
    # is the far side of a horizontally scrollable table, whose cells lie outside the captured page.
    assert len(skipped) <= measured_total // 20, (
        f"{lang}: {len(skipped)} of {measured_total + len(skipped)} runs in the chart could not be "
        "measured:\n    " + "\n    ".join(skipped[:20]))
    assert not failures, ("text in the rendered chart is illegible on the pixels it is painted on:\n    "
                          + "\n    ".join(failures))


@pytest.mark.browser
def test_the_checker_can_still_see(live_site, browser):
    """A checker that quietly stops finding text passes forever. This pins the two ways that happens: it
    measures a real number of real runs, and the share it gives up on stays small. If a redesign paints text
    in a way this cannot read - as a background, under an opaque overlay - this goes red and says so, rather
    than letting the gate above turn into a no-op."""
    measured_total, unmeasured = 0, []
    page = browser.new_page(viewport={"width": 390, "height": 900}, device_scale_factor=DEVICE_SCALE)
    try:
        for key, params in PAGES:
            page.goto(live_site + i18n.url_for(key, "mr", **params), wait_until="networkidle")
            _failures, measured, skipped = page_report(page)
            assert len(measured) >= 20, f"{key}: only {len(measured)} text runs measured"
            measured_total += len(measured)
            unmeasured += [f"{key}: {item['where']} {item['unmeasured']} - {item['text']!r}" for item in skipped]
    finally:
        page.close()
    assert measured_total >= 200, f"only {measured_total} text runs measured across {len(PAGES)} pages"
    assert len(unmeasured) <= measured_total // 20, (
        f"{len(unmeasured)} of {measured_total + len(unmeasured)} text runs could not be measured:\n    "
        + "\n    ".join(unmeasured[:20]))


# The tile, and the breakpoint it turns on at, read out of the RULES - never out of the prose beside them.
_TILE = re.search(r"""url\("(data:image/svg\+xml,[^"]+)"\)""", CSS_RULES)
_NO_TILE = "body { background-image: none !important; }"

# The grounds the decorative field can sit behind. The budget is derived against the TIGHTEST of them, not
# against the page background: --color-tint and --color-quiet-bg are surfaces INSIDE the reading column, and
# a ceiling derived from cream alone is 17.4% where quiet-bg only tolerates 12.7%. Deriving it from the
# palette rather than writing the number down means a token moving re-derives the budget instead of
# silently invalidating it.
FIELD_GROUNDS = ("--color-bg", "--color-tint", "--color-quiet-bg", "--color-surface",
                 "--color-warning-bg", "--color-success-bg")


def _over(ink, ground, alpha):
    return tuple(round(alpha * a + (1 - alpha) * b) for a, b in zip(ink, ground))


def _field_budget():
    """The largest channel shift the field may impose on a ground behind text, in 0-255 units.

    Caption text is the binding constraint everywhere in this file, so: for each ground the field can be
    behind, the largest veil that still leaves caption text above AA; the shift that veil makes to the
    channel that moves most; and then the smallest of those across every ground."""
    indigo = brand._rgb(brand.ROOT_TOKENS["--color-primary"])
    caption = brand._rgb(brand.ROOT_TOKENS["--color-muted"])
    budgets = []
    for token in FIELD_GROUNDS:
        ground = brand._rgb(brand.ROOT_TOKENS[token])
        alpha = 0.0
        while alpha < 1.0 and brand.contrast(caption, _over(indigo, ground, alpha + 0.001)) >= AA:
            alpha += 0.001
        budgets.append((alpha * max(abs(a - b) for a, b in zip(indigo, ground)), token))
    return min(budgets)


FIELD_BUDGET, FIELD_TIGHTEST_GROUND = _field_budget()   # ~26/255 on --color-quiet-bg at this palette


def field_shift_behind_text(page, scale=DEVICE_SCALE):
    """How far the decorative field moves the pixels inside each text run's box. -> (shifts, total).

    `shifts` is [(delta, description)] for every run the field touches at all, worst first; delta is the
    largest single-channel move, 0-255, between the page with the field and the page without it.

    There is no selection step here, and that is the whole point. The population is every text run on the
    page, taken by geometry - a run is in it because it has a box, not because of anything measured about
    its colours. An earlier version picked out the runs whose ground looked like cream and then asked
    whether it was cream; that reads better than it behaves, because a run sitting squarely on the field
    has no cream near it, so it failed the SEARCH rather than the test and left the population silently.

    Note what this deliberately does NOT do: it applies no hairline erosion. The contrast gate erodes, so
    that a table's 1px rule is not mistaken for the ground a glyph sits on - and that erosion also discards
    the field's own constellation lines, which are a 1px stroke. A raw delta has no such blind spot, so this
    is the check that covers the part of the field the contrast measurement cannot see.

    AND IT ANSWERS A DIFFERENT QUESTION FROM `measure_run`, which is easy to miss because both produce a
    number about the ground. This one isolates what the FIELD contributes, by removing the field and
    differencing; `measure_run` reports what colour is behind the glyphs, whatever put it there. So a dark
    ground from `measure_run` is not evidence the field caused it, and the two must not be read across.
    That mistake has been made here: a worst ground of #cbc7ce on a real page, 48/255 from cream, was
    attributed to the field - whose largest contribution to any run measured 22/255, so it could not have
    been. Something else in those line boxes was. Reach for this function when the question is "what is
    this layer costing", and for `measure_run` when it is "can this text be read"."""
    from PIL import Image, ImageChops

    runs, painted = _shoot(page)
    handle = page.add_style_tag(content=_NO_TILE)
    page.wait_for_timeout(120)
    plain = Image.open(io.BytesIO(page.screenshot(full_page=True))).convert("RGB")
    handle.evaluate("node => node.remove()")
    assert painted.size == plain.size, f"removing the field changed the layout ({painted.size} vs {plain.size})"

    shifts = []
    for run in runs:
        box = crop_box(painted, run, scale)
        if box is None:
            continue
        difference = ImageChops.difference(painted.crop(box), plain.crop(box))
        delta = max(high for _low, high in difference.getextrema())
        if delta:
            shifts.append((delta, f"{run['where']} {run['text']!r} at ({run['x']:.0f},{run['y']:.0f}) "
                                  f"moves by {delta}/255"))
    return sorted(shifts, reverse=True), len(runs)


@pytest.mark.browser
def test_the_field_never_darkens_the_ground_behind_text_beyond_its_budget(live_site, browser):
    """What the decorative field is allowed to cost the text it sits behind.

    This replaces an assertion that it sits behind no text at all, which was true while an opaque cream
    column was painted over it and stopped being the design. The question is no longer whether the field
    reaches the words - it does - but whether it darkens their ground by more than legibility can absorb.

    The budget is derived, not written down: the largest veil that keeps caption text above AA on the
    TIGHTEST ground the field can sit behind. That is --color-quiet-bg rather than the page cream, which
    matters more than it sounds - cream tolerates 17.4% and quiet-bg only 12.7%, so a budget derived
    against the page background would be a third too generous on a surface the field is also behind.

    And it is measured from PIXELS rather than from the opacity attributes in the field's own source, which
    is the same trap as every other one in this file: twelve of the thirteen stars sit on a constellation
    vertex, so the declared .07 line and .19 dot composite to about 25% at the darkest point on the page.
    An assertion derived from the attributes would have been exactly right about a number that is not what
    is on screen."""
    # The budget's currency is a single-channel delta, and converting the alpha ceiling into one assumes the
    # field darkens toward --color-primary. That holds because the tile is drawn in it; if it were ever
    # redrawn in another colour the same delta would mean a different luminance shift, so the assumption is
    # asserted rather than left for someone to discover.
    primary = brand._hex(brand._rgb(brand.ROOT_TOKENS["--color-primary"])).lstrip("#")
    assert _TILE and primary in _TILE.group(1).lower(), (
        f"the field is no longer drawn in --color-primary (#{primary}), so the budget's conversion from a "
        "contrast ceiling to a channel delta no longer describes it")

    page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=DEVICE_SCALE)
    try:
        over_budget, touched, total = [], 0, 0
        for lang in i18n.LANGS:
            for key, params in PAGES:
                page.goto(live_site + i18n.url_for(key, lang, **params), wait_until="networkidle")
                shifts, count = field_shift_behind_text(page)
                touched += len(shifts)
                total += count
                over_budget += [f"{key}/{lang}: {what}" for delta, what in shifts if delta > FIELD_BUDGET]
    finally:
        page.close()
    assert total >= 1000, f"only {total} text runs on twelve pages at 1440px - this is checking almost nothing"
    # Which runs the field lands behind is the page's business. Today it lands behind headings, links and
    # body copy and behind no caption text at all, so this green is about the runs the layout happens to
    # put there - the budget it checks against is derived for caption text regardless, so it keeps its
    # meaning when frosted surfaces change which runs those are.
    assert not over_budget, (
        f"the field darkens the ground behind this text by more than {FIELD_BUDGET:.0f}/255, which is what "
        f"caption text can absorb on {FIELD_TIGHTEST_GROUND} before it drops under AA:\n    "
        + "\n    ".join(over_budget[:20]))


@pytest.mark.browser
@pytest.mark.parametrize("alpha, expected", [(0.05, "within"), (0.30, "over")])
def test_that_budget_check_can_tell_a_field_within_budget_from_one_over_it(live_site, browser, alpha, expected):
    """Two-sided, because a budget that has only ever been shown to pass is a number nobody has tested.

    A flat veil of the field's own ink is laid over the page at a known strength and the same check is run
    over the same unfiltered population. At 5% it has to stay quiet and at 30% it has to name the runs -
    proving both that the check sees the field at all and that it is not simply failing everything."""
    indigo = brand._hex(brand._rgb(brand.ROOT_TOKENS["--color-primary"]))
    veil = ("@media (min-width: 1240px) { body { background-image: linear-gradient(%s%02x, %s%02x)"
            " !important; background-repeat: repeat !important; } }"
            % (indigo, round(alpha * 255), indigo, round(alpha * 255)))

    page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=DEVICE_SCALE)
    try:
        page.goto(live_site + i18n.url_for("kundali", "en"), wait_until="networkidle")
        page.add_style_tag(content=veil)
        page.wait_for_timeout(150)
        painted = page.evaluate("() => getComputedStyle(document.body).backgroundImage")
        assert "gradient" in painted, f"the veil did not take: body paints {painted[:90]!r}"
        shifts, total = field_shift_behind_text(page)
    finally:
        page.close()
    assert total >= 100, f"only {total} runs on the page with the veil applied"
    assert shifts, "the veil changed nothing at all, so this proves nothing either way"
    over = [what for delta, what in shifts if delta > FIELD_BUDGET]
    if expected == "over":
        assert len(over) >= 20, (
            f"a {alpha:.0%} veil is well past the {FIELD_BUDGET:.0f}/255 budget and only {len(over)} of "
            f"{len(shifts)} touched runs were named. A green from the budget check would mean nothing.")
    else:
        assert not over, (
            f"a {alpha:.0%} veil is inside the {FIELD_BUDGET:.0f}/255 budget and was reported anyway - the "
            f"check fails anything it can see: {over[:5]}")


# The gutter the decorative layers occupy, taken from the rules: the reading band is centred and reaches
# COLUMN_HALF either side of the middle, so anything outside that is gutter.
_COLUMN_HALF = re.search(r"calc\(50% - (\d+)px\)", CSS_RULES)
# Above the breakpoint only; the layers do not exist below it.
GUTTER_WIDTHS = (1240, 1280, 1440, 1600, 1920, 2560)


def text_in_the_gutter(page, width):
    """Every text run whose box reaches outside the centred reading band. -> list of descriptions."""
    half = int(_COLUMN_HALF.group(1))
    edge = width / 2 - half
    return [f"{run['where'][:30]} x={run['x']:.0f}..{run['x'] + run['w']:.0f} "
            f"(gutter is <{edge:.0f} or >{width - edge:.0f}) {run['text'][:24]!r}"
            for run in page.evaluate(_RUNS_JS)
            if run["x"] < edge - 0.5 or run["x"] + run["w"] > width - edge + 0.5]


@pytest.mark.browser
def test_no_text_ever_enters_the_gutter_the_decorative_layers_occupy(live_site, browser):
    """The gutters carry decoration that respects no contrast budget, on the grounds that they hold no text.

    That is a claim about every element on every page at every width, not about the ones anybody looked at -
    and the elements that could falsify it are the ones that exceed the reading band while carrying a
    transparent background. It is the same shape as the caption-on-field question: either no text can be
    there, or some is and nobody checked which. So it is checked, at six widths from the breakpoint to
    2560px, in all three trees, and in the state that holds the widest content on the site - a rendered
    chart, whose tables are far wider than any prose on the page.

    This is a geometric test, deliberately. It needs no screenshot and makes no claim about contrast: if
    nothing is there, the decoration behind it cannot matter, and if something IS there this fails and the
    question becomes a contrast one."""
    assert _COLUMN_HALF, "the reading band is no longer defined as calc(50% - Npx) - re-derive the gutter"
    offenders = []
    for width in GUTTER_WIDTHS:
        page = browser.new_page(viewport={"width": width, "height": 900}, device_scale_factor=1)
        try:
            for lang in i18n.LANGS:
                for key, params in PAGES:
                    page.goto(live_site + i18n.url_for(key, lang, **params), wait_until="networkidle")
                    page.add_style_tag(content=_FREEZE_CSS)
                    page.evaluate(_REALISE_JS)
                    page.wait_for_timeout(60)
                    offenders += [f"{width}px {key}/{lang}: {item}" for item in text_in_the_gutter(page, width)]
        finally:
            page.close()
    assert not offenders, ("text reaches into the gutter, where the decorative layers are drawn without a "
                           "contrast budget:\n    " + "\n    ".join(offenders[:20]))


@pytest.mark.browser
@pytest.mark.parametrize("lang", i18n.LANGS)
def test_the_widest_state_on_the_site_stays_out_of_the_gutter_too(live_site, browser, lang):
    """The load state is not the widest state. A rendered chart's tables are, and they are the thing most
    likely to reach past the reading band."""
    offenders = []
    for width in (1240, 1440, 1920):
        page = browser.new_page(viewport={"width": width, "height": 900}, device_scale_factor=1)
        try:
            render_a_chart(page, live_site, lang)
            page.add_style_tag(content=_FREEZE_CSS)
            page.evaluate(_REALISE_JS)
            page.wait_for_timeout(60)
            offenders += [f"{width}px chart/{lang}: {item}" for item in text_in_the_gutter(page, width)]
        finally:
            page.close()
    assert not offenders, ("a rendered chart puts text in the gutter:\n    " + "\n    ".join(offenders[:20]))


@pytest.mark.browser
def test_that_gutter_check_would_notice_text_in_the_gutter(live_site, browser):
    """The control, because the two tests above assert that nothing is somewhere.

    The reading band's cap is lifted so the prose runs the full width of the viewport, which is what any
    future full-bleed section would do, and the same check over the same population has to name it."""
    page = browser.new_page(viewport={"width": 1600, "height": 900}, device_scale_factor=1)
    try:
        page.goto(live_site + i18n.url_for("home", "en"), wait_until="networkidle")
        clean = text_in_the_gutter(page, 1600)
        page.add_style_tag(content=".wrap, .wrap > * { max-width: none !important; width: auto !important; }")
        page.wait_for_timeout(120)
        widened = text_in_the_gutter(page, 1600)
    finally:
        page.close()
    assert not clean, f"the page is not clean to start with: {clean[:5]}"
    assert len(widened) >= 10, (
        f"the reading band was uncapped so prose spans the whole viewport, and only {len(widened)} runs "
        "were reported - this check cannot see text in the gutter, so its green means nothing")


def test_the_page_set_covers_the_shared_chrome_and_both_sides_of_the_field_breakpoint():
    """Cheap, no browser: the coverage claims this file makes are checked rather than assumed."""
    assert {key for key, _ in PAGES} <= set(i18n.PAGES), [key for key, _ in PAGES]
    for key, params in PAGES:
        for lang in i18n.LANGS:
            assert i18n.url_for(key, lang, **params).startswith("/")
    # The @media the tile actually lives in. Read from the rules, so that rewording a comment beside it -
    # in a file that belongs to someone else - cannot break a test in this one.
    assert _TILE, "no decorative tile in the stylesheet rules - has it moved, or gone?"
    queries = list(re.finditer(r"@media\s*\(min-width:\s*(\d+)px\)", CSS_RULES[:CSS_RULES.index(_TILE.group(1))]))
    assert queries, "the decorative tile is no longer inside a min-width media query"
    breakpoint_px = int(queries[-1].group(1))
    assert min(WIDTHS) < breakpoint_px <= max(WIDTHS), (
        f"the field turns on at {breakpoint_px}px and the widths measured are {WIDTHS}")
