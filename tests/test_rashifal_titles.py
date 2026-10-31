"""Titles and meta descriptions that fit in what a search result actually shows.

WHAT SEARCH CONSOLE SAID over 28 days: the Hindi and Marathi reading pages rank on page one and take
0.4-0.8% of the clicks. /hi/rashifal/vrishchik/masik had 522 impressions and 4 clicks. A page that ranks
and is not clicked has a title problem, and that one read:

    Vrishchik Rashifal October 2026 – वृश्चिक राशिफल अक्टूबर 2026 | Vrishchik Masik Rashifal | RashiKundli

A hundred characters, opening in the wrong script, saying the same thing three times, and spending the
end of the line on our own name. Google shows about sixty, so a reader scanning saw the Latin half and a
truncation.

THE RULES THIS FILE ENFORCES, each of which that title broke: under 60 characters; the sign name in the
page's own script first; the dated period where there is one; and no brand suffix - somebody searching
वृश्चिक राशिफल is not searching for us.
"""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

#: EVERY sign, not a representative one. The limit is a character count and the names differ in length -
#: वृश्चिक is seven where धनु is three, and राशिभविष्य is four longer than राशिफल - so the only sign that
#: matters is whichever combination happens to be longest, and picking it by hand is how the Marathi
#: six-month title reached 61 unnoticed.
#: FROM THE REGISTRY, not typed out. Hand-written slugs put "simha" in this list where the Hindi tree
#: says something else, and ten pages quietly SKIPPED - which is a test that cannot fail, dressed as a
#: test that passes.
def _paths() -> dict[str, list[str]]:
    from app.web import i18n

    out: dict[str, list[str]] = {}
    for lang in ("en", "hi", "mr"):
        root = i18n.RASHIFAL_ROOT[lang]
        periods = i18n.PERIOD_SLUGS[lang]
        out[lang] = [f"{root}/{i18n.rashi_slug(index, lang)}/{slug}"
                     for index in range(1, 13) for slug in periods.values()]
    return out


PAGES = _paths()
ALL_PAGES = [path for paths in PAGES.values() for path in paths]

#: What a results page shows before it truncates. Not a style preference - a measurement of the medium.
TITLE_LIMIT = 60
META_LIMIT = 160


def head(path: str) -> tuple[str, str]:
    response = client.get(path)
    assert response.status_code == 200, (
        f"{path} does not answer ({response.status_code}) - this file builds its paths from the URL "
        "registry, so a 404 here means a page is missing, not that the test should stand aside")
    html = response.text
    title = re.search(r"<title>(.*?)</title>", html, re.S)
    meta = re.search(r'name="description" content="(.*?)"', html, re.S)
    return (title.group(1).strip() if title else ""), (meta.group(1).strip() if meta else "")


@pytest.mark.parametrize("path", ALL_PAGES)
def test_the_title_fits_in_what_a_search_result_shows(path):
    title, _ = head(path)
    assert title, f"{path} has no title"
    assert len(title) <= TITLE_LIMIT, f"{path}: {len(title)} characters - {title!r}"


@pytest.mark.parametrize("path", ALL_PAGES)
def test_no_title_ends_with_our_own_name(path):
    """Nine characters of brand at the end of a sixty-character line is the hook pushed off the end."""
    title, _ = head(path)
    assert not title.rstrip().endswith("RashiKundli"), f"{path}: {title!r}"


@pytest.mark.parametrize("path", PAGES["hi"] + PAGES["mr"])
def test_a_devanagari_page_opens_in_devanagari(path):
    """The first thing a reader scanning a results page sees must be the word they searched for."""
    title, _ = head(path)
    first = next((c for c in title if c.isalpha()), "")
    assert "ऀ" <= first <= "ॿ", f"{path} opens in Latin: {title!r}"


@pytest.mark.parametrize("path", ALL_PAGES)
def test_the_meta_survives_being_cut(path):
    _, meta = head(path)
    assert meta, f"{path} has no description"
    assert len(meta) <= META_LIMIT, f"{path}: {len(meta)} characters - {meta!r}"


@pytest.mark.parametrize("path", [p for p in ALL_PAGES if p.endswith(("masik", "monthly", "varshik", "yearly"))])
def test_a_dated_page_carries_its_date_in_the_title(path):
    """"This month" is the question somebody is asking; a title that could be any month does not answer
    it, and that is what the 6-month pages were ranking 5-8 with before they were dated."""
    title, _ = head(path)
    assert re.search(r"\b20\d\d\b", title), f"{path} does not say which month: {title!r}"


@pytest.mark.parametrize("path", ALL_PAGES)
def test_the_title_promises_something_concrete(path):
    """Not just the sign and the period - a reason to click. Every title carries at least two of the
    things the page actually contains."""
    title, _ = head(path)
    hooks = ("career", "money", "love", "health",
             "करियर", "धन", "पैसा", "प्रेम", "सेहत", "स्वास्थ्य",
             "करिअर", "आरोग्य", "हफ़्ते", "आठवड्यात")
    dated = bool(re.search(r"\b20\d\d\b", title))
    assert dated or any(hook.lower() in title.lower() for hook in hooks), (
        f"{path} offers nothing beyond the sign and the period: {title!r}")
