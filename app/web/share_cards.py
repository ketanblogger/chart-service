"""Share cards - the picture WhatsApp and Facebook show when somebody sends a link.

THERE WAS NO og:image AT ALL. Every share of this site arrived as a bare blue link, which is the one
moment a reader's friend decides whether to tap, and we were spending it on nothing.

A card is 1200x630 of the site's own colours: the sign's symbol, what the page is, and the one line
that says where the numbers come from. NOTHING FIGURATIVE AND NOTHING STOCK, same as everywhere else
here - the symbols are the ones in app/static/img/rashi, drawn in this repository.

PNG, not WebP. The rest of this batch prefers WebP and should, but a share card is read by crawlers
rather than browsers, and WhatsApp's preview fetcher is the least forgiving of them. A card that a
browser would render beautifully and WhatsApp would drop is a card that does not exist, so this one
takes the format every crawler has handled for twenty years.

Rendered by the same headless Chromium that makes the PDFs, so there is no new dependency and no image
library: app/pdf/browser.py. Static cards are built by scripts/make_share_cards.py and committed; the
dated "today" cards are rebuilt by the 00:05 refresh, because a card claiming today's date has to be
today's.
"""

from __future__ import annotations

from pathlib import Path

#: Where committed cards live (served as ordinary static files).
STATIC_DIR = Path("app/static/img/cards")

#: Where the dated cards the 00:05 refresh writes live. NOT in the repository: a deploy replaces the
#: tree, and a card that says "23 October" is worthless the next morning anyway.
DAILY_DIR = Path("var/cards")

WIDTH, HEIGHT = 1200, 630

# THE FOOT IS THE ADDRESS, NOT THE ENGINE. Where the numbers come from is on the page itself, in the
# chrome of every one; a card has a single line of room along its foot and the useful thing to spend it
# on is where to go.
#
# NOTE FOR ANYONE EDITING THE TEMPLATE BELOW: it is a str.format() template, so every literal brace has
# to be doubled. A Jinja-style {# comment #} in here is read as a replacement field and raises KeyError
# at render time - which is exactly how the first version of this footer failed.
TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8">
<style>
  @font-face {{ font-family: "Card Deva"; src: url("{deva_font}") format("woff2");
                unicode-range: U+0900-097F, U+200C-200D, U+25CC; font-weight: 400; }}
  @font-face {{ font-family: "Card Deva"; src: url("{deva_bold}") format("woff2");
                unicode-range: U+0900-097F, U+200C-200D, U+25CC; font-weight: 700; }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ width: {width}px; height: {height}px; background: #2E2660; color: #FFFFFF;
          font-family: "Card Deva", system-ui, -apple-system, "Segoe UI", sans-serif;
          padding: 58px 68px; position: relative; overflow: hidden;
          display: flex; flex-direction: column; justify-content: space-between; }}
  /* FLAT RINGS, NOT A GRADIENT. A smooth gradient is the one thing PNG cannot compress; the first
     version of these cards came out at 110 KB each because of one radial glow. */
  .ring {{ position: absolute; border-radius: 50%; border: 2px solid rgba(224,168,46,.20); }}
  .r1 {{ right: -150px; top: -150px; width: 560px; height: 560px; }}
  .r2 {{ right: -40px; bottom: -220px; width: 420px; height: 420px; border-color: rgba(224,168,46,.13); }}
  .body {{ display: flex; align-items: center; gap: 40px; flex: 1; z-index: 1; }}
  .words {{ flex: 1 1 auto; min-width: 0; }}
  /* The sign's symbol, large, on the right half - it is the thing a reader recognises before they
     read anything, and at this size it carries the card. */
  .art {{ flex: 0 0 {art}px; display: flex; align-items: center; justify-content: center; }}
  .art img {{ width: {art}px; height: {art}px; }}
  .kicker {{ font-size: 30px; color: #E0A82E; font-weight: 700; letter-spacing: .05em;
             margin-bottom: 14px; }}
  h1 {{ font-size: {title_size}px; line-height: 1.14; font-weight: 700; }}
  .when {{ font-size: 32px; color: #B9B2E0; margin-top: 16px; }}
  .action {{ font-size: 30px; color: #E0A82E; margin-top: 20px; font-weight: 700; }}
  .foot {{ display: flex; align-items: center; gap: 16px; z-index: 1;
           border-top: 2px solid rgba(224,168,46,.45); padding-top: 24px; }}
  .foot img {{ width: 40px; height: 40px; }}
  .site {{ font-size: 32px; font-weight: 700; }}
  .site span {{ color: #E0A82E; }}
</style></head>
<body>
  <div class="ring r1"></div><div class="ring r2"></div>
  <div class="body">
    <div class="words">
      {kicker}
      <h1>{title}</h1>
      {when}
      {action}
    </div>
    {art_html}
  </div>
  <div class="foot">
    <img src="{logo}" alt="">
    <div class="site">rashikundli<span>.com</span></div>
  </div>
</body></html>"""


def card_html(*, kicker: str = "", title: str, when: str = "", action: str = "",
              symbol_svg: str = "", logo: str = "", fonts: tuple[str, str] = ("", "")) -> str:
    """The card's markup. Pure string building - nothing here touches a browser or the disk.

    `kicker` is OPTIONAL and the site's own card leaves it out: a card headed "RASHIKUNDLI" above a
    line of text, with rashikundli.com along the foot, says the name twice and tells the reader
    nothing the second time.
    """
    art = 300 if symbol_svg else 0
    # A long title in any script has to stay on the card, and it has less room when a symbol is beside
    # it; the size steps down rather than overflowing.
    room = 30 if symbol_svg else 42
    size = 76 if len(title) <= room else (62 if len(title) <= room * 1.7 else 52)
    return TEMPLATE.format(
        width=WIDTH, height=HEIGHT, title_size=size, art=art,
        deva_font=fonts[0], deva_bold=fonts[1], logo=logo,
        kicker=f'<div class="kicker">{kicker}</div>' if kicker else "",
        title=title,
        when=f'<div class="when">{when}</div>' if when else "",
        action=f'<div class="action">{action}</div>' if action else "",
        art_html=f'<div class="art"><img src="{symbol_svg}" alt=""></div>' if symbol_svg else "")


def render(cards: list[dict], out_dir: Path) -> list[Path]:
    """Render cards to PNG with the headless Chromium the PDFs already use.

    ONE BROWSER FOR THE WHOLE BATCH. Launching Chromium per card costs about a second each, and the
    00:05 refresh draws three dozen of them while nobody is watching but the next request is.

    Each card is {"name", "kicker", "title", "when", "source", "symbol"}.
    """
    import asyncio

    return asyncio.run(_render(cards, out_dir))


async def _render(cards: list[dict], out_dir: Path) -> list[Path]:
    from playwright.async_api import async_playwright

    from app.pdf.browser import launch_options

    out_dir.mkdir(parents=True, exist_ok=True)
    fonts = _font_urls()
    written = []
    async with async_playwright() as play:
        browser = await play.chromium.launch(**launch_options())
        page = await browser.new_page(viewport={"width": WIDTH, "height": HEIGHT})
        # WRITTEN TO A FILE AND NAVIGATED TO, not set_content'd. A page built with set_content has no
        # origin, so it may not fetch file:// resources - the first run of this drew the Devanagari
        # title as boxes and the sign symbol as a broken-image icon, because neither the font nor the
        # SVG was ever allowed to load. A file:// page may read its neighbours.
        scratch = out_dir / "_card.html"
        for card in cards:
            html = card_html(kicker=card.get("kicker", ""), title=card["title"],
                             when=card.get("when", ""), action=card.get("action", ""),
                             symbol_svg=card.get("symbol", ""), logo=_logo_url(), fonts=fonts)
            scratch.write_text(html, encoding="utf-8")
            await page.goto(scratch.resolve().as_uri(), wait_until="load")
            # The webfont has to be IN before the shot: a card screenshotted mid-swap shows the
            # fallback, and a Devanagari title with no Devanagari face shows boxes that no later
            # request will fix - the file is written once and served for a day.
            await page.evaluate("() => document.fonts.ready")
            target = out_dir / f"{card['name']}.png"
            await page.screenshot(path=str(target), type="png")
            written.append(target)
        await browser.close()
    scratch.unlink(missing_ok=True)
    return written


def _logo_url() -> str:
    """The emblem, as a file:// URL. The same mark the site header wears."""
    root = Path(__file__).resolve().parents[2] / "app" / "static" / "brand"
    return (root / "emblem-96.png").as_uri()


def _font_urls() -> tuple[str, str]:
    """file:// URLs for the Devanagari faces, so a card can draw हिन्दी and मराठी.

    The page rendering a card is set_content'd with no origin, so a /static path resolves to nothing;
    these are absolute file URLs into the repository's own fonts.
    """
    root = Path(__file__).resolve().parents[2] / "app" / "static" / "fonts"
    return (f"file://{root / 'NotoSansDevanagari-Regular.subset.woff2'}",
            f"file://{root / 'NotoSansDevanagari-Bold.subset.woff2'}")


# ---- which card a page uses ------------------------------------------------------------------------

#: Pages whose card is the sign's own. The reading pages pass `rashi`, the hubs pass it too.
_SIGN_PAGES = ("rashifal-rashi", "rashifal-reading", "rashi-in-english", "sade-sati-rashi",
               "love-rashifal", "rashifal-year")


def card_path(page_key: str | None, lang: str, params: dict | None = None) -> str:
    """The site-relative path of the card for one page. Always returns something.

    NEVER A MISSING FILE. A share card is read by a crawler that will not come back, so a page whose
    specific card has not been built falls back to the sign's, and then to the site's - a generic card
    is a smaller loss than a broken preview, and a broken preview is what "no og:image" already looked
    like everywhere on this site before this existed.
    """
    params = params or {}
    rashi = params.get("rashi")

    if page_key in _SIGN_PAGES and rashi:
        # The dated card, but only when the 00:05 refresh has actually written today's. Checked on
        # disk rather than assumed: a card that 404s is worse than a correct undated one.
        if params.get("period") in ("today", "aaj") and _daily_exists(rashi, lang):
            return f"/cards/{_daily_name(rashi, lang)}.png"
        if (STATIC_DIR / f"rashi-{rashi}-{lang}.png").is_file():
            return f"/static/img/cards/rashi-{rashi}-{lang}.png"

    if page_key and (STATIC_DIR / f"tool-{page_key}-{lang}.png").is_file():
        return f"/static/img/cards/tool-{page_key}-{lang}.png"

    return "/static/img/cards/default.png"


def _daily_name(rashi: str, lang: str, day: "str | None" = None) -> str:
    """today-<rashi>-<lang>-<YYYY-MM-DD>: THE DATE IS IN THE FILENAME.

    A card that says "23 October" served from a URL that never changes is yesterday's picture in every
    cache that kept it, and the caches that matter here belong to WhatsApp and Facebook rather than to
    us. A new name each day is the only cache invalidation those respect.
    """
    return f"today-{rashi}-{lang}-{day or _today()}"


def _today() -> str:
    import datetime as dt
    import zoneinfo

    return dt.datetime.now(zoneinfo.ZoneInfo("Asia/Kolkata")).date().isoformat()


def _daily_exists(rashi: str, lang: str) -> bool:
    return (DAILY_DIR / f"{_daily_name(rashi, lang)}.png").is_file()


def build_daily(day: str | None = None) -> list[Path]:
    """Build today's dated card for every sign in every language. Called by the 00:05 refresh.

    SELF-CLEANING. Yesterday's cards are deleted as today's are written, so this directory cannot grow
    without bound on a box nobody is watching - 36 files a day is 13,000 a year otherwise.
    """
    from app.web import i18n, pages

    day = day or _today()
    cards = []
    for lang in i18n.LANGS:
        for rashi in i18n.RASHI_KEYS:
            names = i18n.rashi_names(rashi, lang)
            ui = pages.ui(lang)
            cards.append({
                "name": _daily_name(rashi, lang, day),
                "kicker": names["rashi"].upper(),
                "title": ui["card_today_title"].format(rashi=names["rashi"]),
                "when": _spoken_date(day, lang),
                "source": {"en": "Swiss Ephemeris, Lahiri ayanamsa"}.get(
                    lang, "स्विस एफेमेरिस, लाहिरी अयनांश"),
                "symbol": (Path("app/static/img/rashi") / f"{rashi}.svg").resolve().as_uri(),
            })
    written = render(cards, DAILY_DIR)
    keep = {path.name for path in written}
    for stale in DAILY_DIR.glob("today-*.png"):
        if stale.name not in keep:
            stale.unlink()
    return written


def _spoken_date(day: str, lang: str) -> str:
    from app.rashifal.i18n import format_date

    return format_date(day, lang)


# ---- serving ---------------------------------------------------------------------------------------

def serve(name: str) -> "tuple[Path, str] | None":
    """(file, cache-control) for a dated card, or None.

    THE NAME IS VALIDATED, NOT TRUSTED. This reads a file whose name came off the URL, so anything
    that is not exactly one of today's card names is a 404 - no dots, no slashes, no traversal, and
    nothing outside the one directory this function knows about.
    """
    import re

    if not re.fullmatch(r"today-[a-z]+-(en|hi|mr)-\d{4}-\d{2}-\d{2}\.png", name):
        return None
    target = (DAILY_DIR / name).resolve()
    if not target.is_file() or target.parent != DAILY_DIR.resolve():
        return None
    # The date is IN the name, so the file at this URL never changes and may be kept for a year.
    return target, "public, max-age=31536000, immutable"
