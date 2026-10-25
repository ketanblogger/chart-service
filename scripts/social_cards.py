"""Daily social cards: 12 rashis x 3 languages, plus one "today's one to watch", as 1080x1920 PNGs.

    .venv/bin/python scripts/social_cards.py                    # today, all three languages
    .venv/bin/python scripts/social_cards.py --langs mr          # one tree
    .venv/bin/python scripts/social_cards.py --date 2026-10-05   # a day ahead, to schedule posts

Output: var/social/<date>/<lang>/<rashi>.png with <rashi>.txt beside it - the caption, the hashtags and the
UTM-tagged link to that rashi's own page.

EVERY WORD IS THE ENGINE'S. The cards are built from app/rashifal/brief.py: where the grahas are, which house
that is from each rashi, the nakshatra and the tithi. No AI call is made here and no interpretive sentence is
written - a card says where a graha IS, never what it means for you. A card is seen out of context by people
who did not ask for it, so it is the last place to make a claim nobody can click through to check, and
app/social/cards.py refuses outright anything about death, illness or accidents. This script asserts that on
the RENDERED text of every card before it writes a single file.

Chromium is the one the PDF renderer already uses, with the same bundled Noto fonts, so Devanagari on a card
is shaped exactly as it is in the reports that have already been sold.
"""

import argparse
import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jinja2 import Environment, FileSystemLoader, select_autoescape  # noqa: E402

from app.pdf.browser import launch_options  # noqa: E402
from app.social import cards  # noqa: E402
from app.web import i18n, site  # noqa: E402

WIDTH, HEIGHT = 1080, 1920
FONTS = ROOT / "app" / "pdf" / "fonts"
TEMPLATES = ROOT / "app" / "social" / "templates"


def _env() -> Environment:
    return Environment(loader=FileSystemLoader(str(TEMPLATES)),
                       autoescape=select_autoescape(["html"]), undefined=__import__("jinja2").StrictUndefined)


def _fontconfig_env(base: dict | None) -> dict:
    """Point Chromium at the four bundled Noto faces, for this process only.

    The same device scripts/design_shots.py uses, and for the same reason: this machine has no Devanagari
    font installed, and a `file://` @font-face cannot be loaded into a page built with `set_content` because
    that page has an opaque origin. fontconfig sits below CSS, so the family name in the stylesheet simply
    resolves - and it resolves to the SAME files the PDF renderer uses, which is what makes a card's
    Devanagari identical to a sold report's.
    """
    import os

    config = ROOT / "var" / "fontconfig-social.xml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(
        '<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd"><fontconfig>'
        f"<dir>{FONTS}</dir><cachedir>{ROOT / 'var' / 'fontcache'}</cachedir></fontconfig>", encoding="utf-8")
    env = dict(base or os.environ)
    env["FONTCONFIG_FILE"] = str(config)
    return env


def build(when: dt.datetime, langs: tuple[str, ...], out: Path, base_url: str) -> tuple[int, list[str]]:
    """Render every card. Returns (files written, refusals). Writes nothing if anything is refused."""
    from playwright.sync_api import sync_playwright

    template = _env().get_template("card.html")
    date = when.astimezone(dt.timezone(dt.timedelta(hours=5, minutes=30))).date().isoformat()

    # EVERYTHING IS BUILT AND CHECKED BEFORE ANYTHING IS WRITTEN. A half-written folder of cards is a folder
    # somebody posts from without noticing the missing ones.
    planned, refused = [], []
    for lang in langs:
        for rashi in i18n.RASHI_KEYS:
            card = cards.card_for(rashi, lang, when)
            planned.append((lang, rashi, card))
        highlight = cards.highlight_card(lang, when)
        if highlight:
            planned.append((lang, "highlight", highlight))

    # A LINK NOBODY CAN OPEN MAKES THE WHOLE POST WORTHLESS. `site.base_url()` falls back to localhost when
    # BASE_URL is unset, which is right for a development server and useless in a caption: the cards would
    # be generated, look perfect, and carry http://localhost:8000 into Instagram. Checked here, with the
    # rest of the refusals, so it stops the run rather than being noticed afterwards.
    host = (base_url or "").strip()
    if not host.startswith("https://") or "localhost" in host or "127.0.0.1" in host:
        refused.append(f"BASE_URL is {host!r}: a caption built from it would carry a link nobody can open. "
                       f"Set BASE_URL to the live site before generating cards.")

    for lang, name, card in planned:
        caption = cards.caption(card, cards.utm_link(card["rashi"], lang, date, base_url))
        found = cards.unsafe(caption)
        if found:
            refused.append(f"{lang}/{name}: refuses to say {found}")
    if refused:
        return 0, refused

    written = 0
    options = launch_options()
    options["args"] = [*options.get("args", []), "--no-sandbox"]
    options["env"] = _fontconfig_env(options.get("env"))
    with sync_playwright() as play:
        browser = play.chromium.launch(**options)
        try:
            page = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT}, device_scale_factor=1)
            for lang, name, card in planned:
                folder = out / date / lang
                folder.mkdir(parents=True, exist_ok=True)
                page.set_content(template.render(card=card), wait_until="load")
                page.wait_for_timeout(120)                 # the four faces are local files; this is ample
                page.screenshot(path=str(folder / f"{name}.png"), clip={"x": 0, "y": 0,
                                                                       "width": WIDTH, "height": HEIGHT})
                link = cards.utm_link(card["rashi"], lang, date, base_url)
                (folder / f"{name}.txt").write_text(cards.caption(card, link), encoding="utf-8")
                written += 2
            page.close()
        finally:
            browser.close()
    return written, []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Daily social cards from engine facts.")
    parser.add_argument("--date", help="YYYY-MM-DD in IST (default: today)")
    parser.add_argument("--langs", nargs="*", default=list(cards.LANGS))
    parser.add_argument("--out", type=Path, default=ROOT / "var" / "social")
    args = parser.parse_args(argv)

    when = dt.datetime.now(dt.timezone.utc)
    if args.date:
        day = dt.date.fromisoformat(args.date)
        when = dt.datetime(day.year, day.month, day.day, 6, 30, tzinfo=dt.timezone.utc)   # noon IST

    written, refused = build(when, tuple(args.langs), args.out, site.base_url())
    if refused:
        print("REFUSED - nothing written:")
        for line in refused:
            print("  " + line)
        return 1
    print(f"{written} file(s) in {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
