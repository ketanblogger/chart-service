"""The self-hosted Devanagari subset: how it is wired, and the trap that made it cost double.

It is the LAST fallback in the stack, behind the six system families, declared under a family name no
device ships so that no browser has to decide anything. A device with any Devanagari font of its own
never draws a glyph from this face and never asks for the file.

What these tests exist for is the WIRING, which looked right and was not: a preload whose URL did not
match the stylesheet's, so the subset was fetched twice and the preload satisfied nothing.
"""
from __future__ import annotations

import re
from pathlib import Path


def test_the_preload_url_matches_the_stylesheet_exactly():
    """A PRELOAD ONLY COUNTS IF THE URL MATCHES. This one carried ?v={{ static_version }} while
    fonts-devanagari.css asked for the same file with no query - two URLs, two cache entries, so the
    61 KB subset was fetched TWICE on every Hindi and Marathi page and the preload satisfied nothing.
    Chromium had been saying so in the console ("preloaded using link preload but not used") since the
    day it shipped, and the measurements that chose swap+preload were taken on the double-downloading
    page. A browser check counting woff2 requests found it.

    The consequence of the fix: neither URL carries a version, so a CHANGED SUBSET NEEDS A NEW FILENAME.
    """
    base = Path("app/web/templates/base.html").read_text(encoding="utf-8")
    css = Path("app/static/css/fonts-devanagari.css").read_text(encoding="utf-8")

    preloads = re.findall(r'<link rel="preload"[^>]*href="([^"]+)"', base)
    fonts = [url for url in preloads if ".woff2" in url]
    assert fonts, "the Devanagari preload is gone"
    for url in fonts:
        assert "?" not in url, f"the preload carries a query the stylesheet cannot match: {url}"
        assert f'url("{url}")' in css, f"the preload asks for a URL the stylesheet never requests: {url}"


def test_the_stylesheet_asks_for_no_versioned_font_url():
    """The other half of the same trap: a version added to the CSS src would break the match from the
    other side. The subset is cache-busted by FILENAME."""
    css = Path("app/static/css/fonts-devanagari.css").read_text(encoding="utf-8")
    for url in re.findall(r'url\("([^"]+)"\)', css):
        assert "?" not in url, f"a versioned font URL in the stylesheet: {url}"


def test_the_metrics_fallback_is_derived_from_the_subset_it_stands_in_for():
    """THE OVERRIDES ARE NOT TASTE. They come from the subset's own tables - unitsPerEm 1000, hhea
    ascent 896, descent -408, lineGap 0 - so the stand-in occupies the same vertical space as the face
    that replaces it. A number typed from memory here would reintroduce the shift it exists to remove.
    """
    css = Path("app/static/css/fonts-devanagari.css").read_text(encoding="utf-8")
    face = css[css.index('font-family: "RK Devanagari Metrics"'):]
    face = face[:face.index("}")]
    assert "ascent-override: 89.6%" in face      # 896 / 1000
    assert "descent-override: 40.8%" in face     # 408 / 1000
    assert "line-gap-override: 0%" in face
    assert "size-adjust:" in face

    try:
        from fontTools.ttLib import TTFont
    except ImportError:  # pragma: no cover - fontTools is not a runtime dependency
        pytest.skip("fontTools is not installed")
    font = TTFont("app/static/fonts/NotoSansDevanagari-Regular.subset.woff2")
    assert font["head"].unitsPerEm == 1000
    assert (font["hhea"].ascent, font["hhea"].descent, font["hhea"].lineGap) == (896, -408, 0)


def test_the_real_face_carries_no_overrides_so_the_final_rendering_is_unchanged():
    """THE CONDITION THE WHOLE CHANGE WAS ACCEPTED UNDER. The overrides belong to the stand-in used
    while the subset downloads; the subset itself is untouched, so what a reader ends up looking at is
    exactly what they looked at before. Proved by screenshot: six pages, pixel-identical apart from the
    live clock in `.v2-card__when`, and the two pages with no clock byte-identical."""
    css = Path("app/static/css/fonts-devanagari.css").read_text(encoding="utf-8")
    for face in re.findall(r"@font-face\s*\{[^}]*\}", css):
        if '"RK Devanagari Fallback"' in face:
            for override in ("ascent-override", "descent-override", "line-gap-override", "size-adjust"):
                assert override not in face, f"the served face carries {override}; rendering would change"


def test_the_stand_in_sits_after_the_real_face_and_before_the_latin_families():
    """Order is the whole mechanism. A device with a Devanagari font of its own reaches neither face; a
    device without one draws this while the subset downloads and then the subset. Ahead of the subset it
    would be what readers see; behind the Latin families it would never be reached at all."""
    css = Path("app/static/css/site.css").read_text(encoding="utf-8")
    stack = css[css.index('html[lang="hi"], html[lang="mr"]'):]
    stack = stack[:stack.index("}")]
    real, standin = stack.index('"RK Devanagari Fallback"'), stack.index('"RK Devanagari Metrics"')
    assert real < standin, "the stand-in is ahead of the face it stands in for"
    assert standin < stack.index("system-ui"), "the stand-in is behind the Latin families"
