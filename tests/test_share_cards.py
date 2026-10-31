"""The picture a shared link arrives with, and the directives that let search engines show it.

THERE WAS NO og:image ON THIS SITE AT ALL. Every link sent on WhatsApp showed as a bare blue line -
the one moment somebody's friend decides whether to tap, spent on nothing. These tests are mostly
about the ways that can silently come back: a card that 404s, a dated card served from yesterday's
cache, a page that quietly loses its picture because a file was renamed.
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.web import i18n, share_cards

client = TestClient(app)
CARDS = Path("app/static/img/cards")
SAMPLE = ["/", "/hi/", "/mr/", "/birth-chart", "/hi/kundli", "/mr/kundali", "/horoscope-matching",
          "/hi/rashifal/tula/aaj", "/mr/rashi-bhavishya/mesh/saptahik", "/horoscope/libra",
          "/panchang", "/blog", "/pricing", "/about"]


@pytest.mark.parametrize("path", SAMPLE)
def test_every_page_declares_a_card_that_exists(path):
    """A MISSING CARD IS WORSE THAN A GENERIC ONE. The crawler that fetches it will not come back."""
    html = client.get(path).text
    found = re.search(r'<meta property="og:image" content="([^"]+)">', html)
    assert found, f"{path} has no og:image"
    url = found.group(1)
    assert url.startswith("http"), "a crawler has no page to resolve a relative URL against"
    assert client.get(url[url.index("/", 8):]).status_code == 200, f"{path} points at a card that 404s"
    assert '<meta property="og:image:width" content="1200">' in html
    assert re.search(r'<meta property="og:image:alt" content="[^"]+">', html), path


def test_the_right_card_for_the_right_page():
    assert "tool-kundali-mr" in client.get("/mr/kundali").text
    assert "rashi-tula-" in client.get("/horoscope/libra").text
    assert "default.png" in client.get("/pricing").text


def test_a_today_page_uses_a_card_with_todays_date_in_its_name():
    """THE DATE IS IN THE FILENAME on purpose. A card saying "23 October" served from a URL that never
    changes is yesterday's picture in every cache that kept it - and the caches that matter belong to
    WhatsApp and Facebook, not to us. A new name each day is the only invalidation they respect."""
    html = client.get("/hi/rashifal/tula/aaj").text
    found = re.search(r'og:image" content="[^"]*/cards/([^"]+)"', html)
    if not found:
        pytest.skip("today's cards have not been built in this working copy")
    # THE SITE'S CLOCK, NOT THE MACHINE'S. Cards are named by the IST date, and this asserted against
    # dt.date.today() - the local one. On a machine behind IST that is a different day for part of
    # every night, so the test was wrong twice a day on a developer's laptop and would have been
    # wrong on any build box outside India. The same helper the code names the file with.
    assert share_cards._today() in found.group(1), found.group(1)


def test_a_page_falls_back_rather_than_pointing_at_nothing():
    """Every branch of the resolver ends at a file that exists."""
    for key, lang, params in [("rashifal-reading", "hi", {"rashi": "tula", "period": "today"}),
                              ("rashifal-reading", "en", {"rashi": "nonesuch", "period": "weekly"}),
                              ("no-such-page", "mr", {}), (None, "en", {})]:
        path = share_cards.card_path(key, lang, params)
        if path.startswith("/static/"):
            assert Path("app" + path[len("/static") - 7:]).is_file() or \
                Path("app/static" + path[len("/static"):]).is_file(), (key, path)
        assert client.get(path).status_code == 200, (key, path)


def test_the_card_route_refuses_anything_that_is_not_a_card_name():
    """The name comes off the URL and is read as a filename, so it is matched exactly or refused."""
    for name in ("../../../etc/passwd", "today-tula-hi-2026-13-45.png", "today-tula-xx-2026-01-01.png",
                 "../cards/default.png", "today-tula-hi.png", "anything.png"):
        assert share_cards.serve(name) is None, name


def test_every_sign_and_tool_has_a_committed_card():
    for lang in i18n.LANGS:
        for rashi in i18n.RASHI_KEYS:
            assert (CARDS / f"rashi-{rashi}-{lang}.png").is_file(), f"rashi-{rashi}-{lang}"
    assert (CARDS / "default.png").is_file()


def test_the_cards_are_png_and_the_right_size():
    """PNG because WhatsApp's preview fetcher is the least forgiving crawler there is, and 1200x630
    because that is the size every one of them crops to."""
    import struct

    for name in ("default.png", "rashi-tula-hi.png", "tool-kundali-mr.png"):
        data = (CARDS / name).read_bytes()
        assert data[:8] == b"\x89PNG\r\n\x1a\n", f"{name} is not a PNG"
        width, height = struct.unpack(">II", data[16:24])
        assert (width, height) == (1200, 630), (name, width, height)
        assert len(data) < 120_000, f"{name} is {len(data) // 1024} KB - too heavy to commit"


def test_max_image_preview_is_set_and_never_doubled():
    """Two robots metas on one page is a rule nobody can read off the page. A page that must not be
    indexed overrides the block instead of adding a second tag."""
    for path in SAMPLE:
        tags = re.findall(r'<meta name="robots" content="([^"]*)">', client.get(path).text)
        assert len(tags) == 1, (path, tags)
        assert "max-image-preview:large" in tags[0], path

    error = client.get("/no-such-page-at-all").text
    tags = re.findall(r'<meta name="robots" content="([^"]*)">', error)
    assert len(tags) == 1 and "noindex" in tags[0], tags


def test_the_sitemap_declares_an_image_for_every_url():
    xml = client.get("/sitemap.xml").text
    assert 'xmlns:image="http://www.google.com/schemas/sitemap-image/1.1"' in xml
    # One image per URL, counted exactly. The first version of this line had an `or count > 0` in it,
    # which made it true whenever a single image existed anywhere in the file - a check that passes
    # for the wrong reason is the thing this whole batch has been about.
    assert xml.count("<image:loc>") == xml.count("<loc>") > 0
    assert xml.count("<url>") == xml.count("<image:image>"), "a URL in the sitemap has no image"


def test_the_card_the_page_shares_is_the_card_the_sitemap_declares():
    """One picture per page, named the same in the page, the sitemap and the schema - three slightly
    different answers would be three chances to be wrong."""
    from app.web import seo

    entries = {item["loc"]: item["image"] for item in seo.sitemap_entries()}
    for path in ("/birth-chart", "/mr/kundali", "/horoscope/libra"):
        html = client.get(path).text
        page_card = re.search(r'<meta property="og:image" content="([^"]+)">', html).group(1)
        loc = next(url for url in entries if url.endswith(path))
        assert entries[loc] == page_card, path


# ---- item 11b --------------------------------------------------------------------------------------

def test_the_card_foot_is_the_address_and_not_the_engine():
    """A card has one line along its foot. Where the numbers come from is already in the chrome of
    every page; the useful thing to spend a card's last line on is where to go."""
    html = share_cards.card_html(title="x", logo="/l.png")
    assert "rashikundli" in html and ".com" in html
    assert "Swiss Ephemeris" not in html, "the engine line is back on the card foot"
    assert '<img src="/l.png"' in html, "the emblem is missing from the foot"


def test_no_card_says_the_same_thing_twice():
    """The site's own card was headed "RASHIKUNDLI" above its headline, with rashikundli.com along the
    foot - the name three times on one picture. A sign's card had the sign's name directly above
    "<sign> horoscope" for the same reason."""
    import sys
    sys.path.insert(0, "scripts")
    from make_share_cards import build

    for card in build():
        kicker = (card.get("kicker") or "").strip().lower()
        if not kicker:
            continue
        assert kicker not in card["title"].lower(), f"{card['name']} repeats its kicker in the title"
        assert "rashikundli" not in kicker, f"{card['name']} names the site in its kicker"


def test_a_card_with_no_kicker_renders_without_an_empty_slot():
    html = share_cards.card_html(title="A headline on its own")
    assert 'class="kicker"' not in html


def test_the_tool_cards_use_the_benefit_headline_not_the_seo_title():
    """A <title> is written to be matched against a search. A card is read by somebody deciding
    whether to tap a link a friend sent, and it has one line to say what they GET."""
    from app.web import pages as web_pages

    for key in ("kundali", "matching", "sade-sati"):
        for lang in i18n.page_langs(key):
            copy = web_pages.get(key, lang)
            assert copy.og_title, f"{key}/{lang} has no card headline"
            assert copy.og_title != copy.title, f"{key}/{lang} is reusing its SEO title"
            assert len(copy.og_title) <= 60, f"{key}/{lang} headline is too long to read at a glance"


def test_a_page_without_a_card_headline_falls_back_to_its_h1():
    """Most pages will never have one written, and a card is still better than no card."""
    import sys
    sys.path.insert(0, "scripts")
    from make_share_cards import build

    names = {card["name"] for card in build()}
    assert "tool-panchang-en" in names or "tool-kundli-en" in names
    for card in build():
        assert card["title"].strip(), f"{card['name']} has an empty headline"


def test_every_sign_card_carries_its_symbol_and_an_action_line():
    import sys
    sys.path.insert(0, "scripts")
    from make_share_cards import build

    signs = [card for card in build() if card["name"].startswith("rashi-")]
    assert len(signs) == 36, len(signs)
    for card in signs:
        assert card.get("symbol", "").endswith(".svg"), card["name"]
        assert card.get("action"), f"{card['name']} has no action line"
        assert "→" in card["action"], f"{card['name']} does not point anywhere"


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_the_action_line_is_written_in_each_language(lang):
    from app.web import pages as web_pages

    action = web_pages.ui(lang)["card_rashi_action"]
    assert action.strip() and "→" in action
    if lang != "en":
        assert not re.search(r"[A-Za-z]{4,}", action), f"{lang} action line is in English"
