"""Build the committed share cards: the site default, one per tool, one per sign per language.

Run from the repository root:  uv run python scripts/make_share_cards.py

THESE ARE THE UNDATED ONES and they are committed, because they never change. The dated "today" cards
are built by the 00:05 refresh instead - a card claiming today's date has to be today's, and a
committed one would be wrong by breakfast. See app/web/share_cards.py for why they are PNG.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.web import i18n, pages, share_cards     # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / share_cards.STATIC_DIR


def symbol(rashi: str) -> str:
    return (ROOT / "app" / "static" / "img" / "rashi" / f"{rashi}.svg").as_uri()


def build() -> list[dict]:
    cards = [{"name": "default",
              # NO KICKER HERE. A card headed "RASHIKUNDLI" above a line of text, with
              # rashikundli.com along its foot, says the name twice and tells the reader nothing the
              # second time. The headline does the work instead.
              "title": pages.ui("en")["card_site_title"]}]

    # One per sign per language, undated: these serve the weekly, monthly and yearly pages and the
    # sign's hub. The symbol carries the right half - it is what a reader recognises before they read
    # anything - and the action line says what tapping gets them.
    for lang in i18n.LANGS:
        ui = pages.ui(lang)
        for rashi in i18n.RASHI_KEYS:
            names = i18n.rashi_names(rashi, lang)
            # NO KICKER, for the reason the site card has none: it was the sign's name directly
            # above "<sign> horoscope", saying the same word twice and spending the card's best line
            # on a repeat. The symbol beside it already says which sign this is.
            cards.append({"name": f"rashi-{rashi}-{lang}",
                          "title": ui["card_rashi_title"].format(rashi=names["rashi"]),
                          "action": ui["card_rashi_action"], "symbol": symbol(rashi)})

    # One per tool per language. The headline is the page's og_title - what the reader GETS - and
    # falls back to its h1 where nobody has written one.
    for key in pages.TOOLS:
        for lang in i18n.page_langs(key):
            copy = pages.get(key, lang)
            cards.append({"name": f"tool-{key}-{lang}",
                          "kicker": pages.ui(lang)["card_free_tool"],
                          "title": copy.og_title or copy.h1})
    return cards


if __name__ == "__main__":
    cards = build()
    written = share_cards.render(cards, OUT)
    total = sum(p.stat().st_size for p in written)
    print(f"  {len(written)} cards, {total // 1024} KB total, into {OUT}")
