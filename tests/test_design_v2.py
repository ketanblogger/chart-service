"""The full-width home page PROTOTYPE (`?design=v2`), and the promises it has to keep while it is one.

A prototype behind a flag is only safe while three things are true: the live page is untouched, the prototype
cannot be indexed, and the SEO signals of `/` do not change because a second rendering of it exists. All three
are asserted here rather than trusted, because the flag lives in the home route - the single most valuable URL
on the site - and "it is only a preview" is exactly the sentence under which a live page gets broken.
"""

import html as html_module
import json
import pathlib
import re

import pytest
from fastapi.testclient import TestClient

from app.ai.language import language_problems
from app.main import app
from app.payments import catalogue
from app.web import design_v2, i18n, sky

client = TestClient(app)
LANGS = ("en", "hi", "mr")
PATHS = {"en": "/", "hi": "/hi/", "mr": "/mr/"}


def get(path: str) -> str:
    response = client.get(path)
    assert response.status_code == 200, (path, response.status_code)
    return response.text


def head_of(html: str) -> str:
    return html.split("</head>", 1)[0]


# ---- the live page is untouched ---------------------------------------------------------------------


@pytest.mark.parametrize("lang", LANGS)
def test_the_previous_design_is_still_reachable_and_unchanged(lang):
    """The full-width design became the default on 3 October (site.DESIGN_V2). What this test guarded before
    - that a visitor with no query string got the OLD page - is now guarded one step along: `?design=v1`
    still renders the previous template, untouched, so the rollback can be checked on the live site before
    it is taken. The templates it renders are still in the tree; nothing was deleted."""
    previous = get(PATHS[lang] + "?design=v1")
    assert "design-v2" not in previous and "design-v2.css" not in previous
    assert "v2-hero" not in previous and "v2-sky" not in previous
    assert design_v2.LABELS[lang]["sky_heading"] not in previous
    # an unknown value for the flag is not an escape hatch - it falls through to the default, which is v2
    assert "design-v2" in get(PATHS[lang] + "?design=v3")
    assert "design-v2" in get(PATHS[lang] + "?design=")


# ---- the prototype cannot be indexed, and cannot take the real page's place --------------------------


@pytest.mark.parametrize("lang", LANGS)
def test_the_page_the_site_serves_is_indexable_and_self_canonical(lang):
    """THE NOINDEX HAD TO COME OFF WITH THE FLIP, and that is the single most expensive thing that could have
    been left behind: a `noindex` on the home page of a site that lives on search. It is conditional on
    `v2_is_default` in all five v2 templates.

    Both query spellings still answer, and NEITHER may be a second indexable copy: the canonical is built
    from the PATH, so `?design=v1` and `?design=v2` both nominate the clean URL rather than themselves."""
    for suffix in ("", "?design=v2", "?design=v1"):
        head = head_of(get(PATHS[lang] + suffix))
        assert "noindex" not in head, f"{PATHS[lang] + suffix} is noindex"
        canonical = re.search(r'<link rel="canonical" href="([^"]+)"', head).group(1)
        assert canonical.endswith(i18n.url_for("home", lang)), (suffix, canonical)
        assert "design" not in canonical, (suffix, canonical)


@pytest.mark.parametrize("lang", LANGS)
def test_every_seo_signal_is_the_one_the_live_page_carries(lang):
    """The prototype re-uses the live page's words rather than rewriting them, so a comparison between the
    two is about LAYOUT and nothing else. If the H1 or the JSON-LD differed, the screenshots would be
    comparing two pages instead of two designs, and an approval would be approving the wrong thing."""
    live, preview = get(PATHS[lang]), get(PATHS[lang] + "?design=v2")

    def signals(html):
        head = head_of(html)
        return {
            "title": re.search(r"<title>(.*?)</title>", head, re.S).group(1),
            "description": re.search(r'name="description" content="([^"]*)"', head).group(1),
            "canonical": re.search(r'rel="canonical" href="([^"]+)"', head).group(1),
            "alternates": sorted(re.findall(r'rel="alternate" hreflang="([^"]+)" href="([^"]+)"', head)),
            "h1": [re.sub(r"<[^>]+>", "", h).strip() for h in re.findall(r"<h1[^>]*>(.*?)</h1>", html, re.S)],
            "json_ld": sorted(json.dumps(json.loads(b), sort_keys=True)
                              for b in re.findall(r'type="application/ld\+json">(.*?)</script>', html, re.S)),
        }

    assert signals(live) == signals(preview)


@pytest.mark.parametrize("lang", LANGS)
def test_the_prototype_keeps_the_internal_links_the_live_page_has(lang):
    """A redesign that quietly drops links is an SEO regression that no screenshot shows. Every internal
    path the live page links to must still be linked from the prototype."""
    def paths(html):
        return {href for href in re.findall(r'href="(/[^"#?]*)"', html)
                if not href.startswith("/static/") and not href.startswith("/api/")}

    missing = paths(get(PATHS[lang])) - paths(get(PATHS[lang] + "?design=v2"))
    assert not missing, f"the prototype drops these links: {sorted(missing)}"


# ---- the prototype itself ----------------------------------------------------------------------------


@pytest.mark.parametrize("lang", LANGS)
def test_the_prototype_renders_its_own_words_in_every_language(lang):
    html = get(PATHS[lang] + "?design=v2")
    words = design_v2.LABELS[lang]
    for key in ("form_heading", "tools_heading", "signs_heading", "ai_heading", "trust_heading",
                "sky_heading", "picker_heading", "sell_cta", "bar_kundali"):
        assert words[key] in html, (lang, key)
    # the form is the real one, wired the way app.js expects, not a picture of a form
    assert 'id="tool-form"' in html and 'data-endpoint="/api/chart"' in html
    assert 'id="submit-btn"' in html and 'id="self-name"' in html and 'id="result"' in html


def test_the_prototypes_own_copy_is_not_a_language_defect_waiting_to_ship():
    """A prototype is exactly where a Hindi spelling slips into Marathi unnoticed - nobody reviews a preview
    as carefully as a live page, and this copy moves into the content modules if phase 2 is approved. Checked
    with the same checker the paid reports go through."""
    for lang in ("hi", "mr"):
        for key, value in design_v2.LABELS[lang].items():
            for text in (value if isinstance(value, list) else [value]):
                problems = [p for p in language_problems(text, lang)
                            if not ("Latin-script" in p and any(w in text for w in ("AI", "PDF")))]
                assert not problems, (lang, key, problems)


@pytest.mark.parametrize("lang", LANGS)
def test_the_price_on_the_prototype_comes_from_the_catalogue(lang):
    """Never typed into a template. Same rule as the pricing page: a price written into copy is wrong the
    first time a price moves."""
    html = get(PATHS[lang] + "?design=v2")
    assert f"₹{catalogue.item('kundali-report').price_inr}" in html


def test_every_sign_and_every_tool_has_a_glyph():
    """Twelve signs and every nav key, or a card renders an empty <path> and reads as a missing icon."""
    assert set(design_v2.SIGN_GLYPHS) == set(i18n.RASHI_KEYS)
    for key in design_v2.SIGN_GLYPHS.values():
        assert key.startswith("M") and len(key) > 20
    html = get("/?design=v2")
    assert html.count('<path d="M') >= 12 + 6
    assert '<path d=""' not in html, "a glyph lookup missed and rendered an empty path"


def test_the_prototype_adds_no_inline_style_and_no_third_party_asset():
    """CSP is `self` only, and the prototype must not be the page that needs it relaxed. One extra
    stylesheet from our own origin, no <style> block, no external host."""
    html = get("/?design=v2")
    body = html.split("</head>", 1)[1]
    assert "<style" not in body
    assert "/static/css/design-v2.css" in html
    # Absolute URLs to our OWN origin are the canonical, the hreflang set and og:url - not third parties.
    # The analytics loader is the site's one allowed external host and is named in the CSP.
    from app.web import site

    external = [src for src in re.findall(r'(?:href|src)="(https?://[^"]+)"', html)
                if "googletagmanager" not in src and not src.startswith(site.base_url())]
    assert not external, external


# ---- the second round of feedback --------------------------------------------------------------------


@pytest.mark.parametrize("lang", LANGS)
def test_the_twelve_are_in_zodiac_order_in_the_picker_and_demand_order_in_the_card_list(lang):
    """A PICKER is scanned by position - a reader knows where their own sign falls in the twelve - so the
    prototype runs Mesha to Meena. The LIVE page keeps demand order, where the sequence is crawl priority on
    the most linked-to page of the site. Both are deliberate, and the difference is the point of the test."""
    from app.web import i18n as registry

    preview = get(PATHS[lang])
    names = re.findall(r'class="v2-sign__name">([^<]+)<', preview)
    expected = [preview_label(key, lang) for key in registry.RASHI_KEYS]
    assert names == expected, names
    # the rail picker uses the same order, from the same list
    picker = re.search(r'<div class="v2-picker">(.*?)</div>', preview, re.S).group(1)
    assert re.findall(r">([^<]+)</a>", picker) == expected

    # The card list on the previous design keeps DEMAND order, where the sequence is crawl priority on the
    # most linked-to page of the site. Read from ?design=v1, which is where that template now renders.
    previous = get(PATHS[lang] + "?design=v1")
    first = re.search(r'<ul class="link-grid">\s*<li><a[^>]*>([^<]+)', previous).group(1).strip()
    assert first != expected[0], "the previous design must still lead with its highest-demand rashi"


def preview_label(key: str, lang: str) -> str:
    from app.web import i18n as registry
    from app.web import pages

    names = registry.rashi_names(key, lang)
    return pages.fill(pages.get("rashifal-hub", lang).extra["rashi_label"], **names)


@pytest.mark.parametrize("lang", LANGS)
def test_the_sky_panel_says_when_it_was_computed(lang):
    """"Updated every few minutes" is not a time. A panel that claims to be live has to say how live."""
    html = get(PATHS[lang] + "?design=v2")
    when = re.search(r'class="v2-card__when">([^<]*)', html).group(1)
    assert re.match(r"\d{2}:\d{2} IST", when), when


def test_nothing_on_the_page_depends_on_a_glyph_the_devanagari_font_lacks():
    """`html[lang=hi|mr]` puts Noto Sans Devanagari FIRST, and that face has no U+2192 arrow, no U+2713 tick
    and no zodiac block. Every one of those fell through to whatever the device happened to have - and on a
    machine with a thin font set, to a box, which is how the first screenshot set came back full of tofu.
    They are all drawn as SVG now. The arrow is the one that got as far as a review."""
    for lang in LANGS:
        html = get(PATHS[lang] + "?design=v2")
        body = html.split("</head>", 1)[1]
        for ch, name in (("\u2192", "arrow"), ("\u2713", "tick"), ("\u2714", "heavy tick")):
            assert ch not in body, f"{lang}: a bare {name} character is in the page"
        for code in range(0x2648, 0x2654):               # the zodiac block
            assert chr(code) not in body, f"{lang}: a zodiac character U+{code:04X} is in the page"
        assert body.count("v2-arrow") >= 3 and "icon tick" in body


@pytest.mark.parametrize("lang", LANGS)
def test_every_inline_icon_carries_its_own_size(lang):
    """An <svg> with a viewBox and no width scales to its CONTAINER. An arrow meant to be 15px rendered 571px
    square inside every tool card, in every language, and went out in a screenshot set - because the rule that
    would have sized it was lost when the script adding it aborted on an assertion between two files.

    So the size is an ATTRIBUTE, checked here without a browser, as well as a stylesheet rule. A missing
    stylesheet, a renamed class or another half-applied edit cannot make an icon fill a card again.
    `scripts/design_shots.py` measures the rendered boxes as well, which is the half this cannot see."""
    html = get(PATHS[lang] + "?design=v2")
    body = html.split("</head>", 1)[1]
    tags = re.findall(r"<svg\b[^>]*>", body)
    assert len(tags) >= 20, len(tags)
    for tag in tags:
        assert 'width="' in tag and 'height="' in tag, tag[:90]
        assert 'class="icon' in tag, f"an icon outside the sized class: {tag[:90]}"


def test_the_prototype_does_not_touch_the_font_stack():
    """v2 adds a layout, not a typeface. If it ever declares its own font-family the Devanagari face stops
    being first on the Hindi and Marathi trees and the whole site's script handling changes under it."""
    css = (pathlib.Path(__file__).resolve().parents[1] / "app/static/css/design-v2.css").read_text(encoding="utf-8")
    assert "font-family" not in css and "@font-face" not in css
    site_css = (pathlib.Path(__file__).resolve().parents[1] / "app/static/css/site.css").read_text(encoding="utf-8")
    devanagari = re.search(r'html\[lang="hi"\], html\[lang="mr"\] \{\s*--font:\s*([^;]+);', site_css, re.S)
    assert devanagari and '"Noto Sans Devanagari"' in devanagari.group(1).split(",")[0]


@pytest.mark.parametrize("lang", LANGS)
def test_each_of_the_four_needs_is_a_card_that_links_to_its_own_tool(lang):
    """The mapping from bullet to tool is POSITIONAL, so the position is what has to be checked: four bullets
    in every language, in one order, each card linking to the tool its sentence names. All three languages
    were written from one outline - but an order that is true today and unchecked is how a card quietly
    starts sending people to the wrong page."""
    from app.web import i18n as registry
    from app.web import pages

    needs = pages.get("home", lang).sections[2]
    bullets = [block for block in needs.blocks if not isinstance(block, str)]
    assert len(bullets) == 1 and len(bullets[0]) == len(design_v2.NEED_TOOLS) == 4

    html = get(PATHS[lang] + "?design=v2")
    cards = re.findall(r'<li class="v2-need">(.*?)</li>', html, re.S)
    assert len(cards) == 4
    for card, sentence, key in zip(cards, bullets[0], design_v2.NEED_TOOLS):
        # unescaped, because an apostrophe in the copy is &#39; in the page
        assert sentence[:40] in html_module.unescape(card)
        assert f'href="{registry.url_for(key, lang)}"' in card, (lang, key)


@pytest.mark.parametrize("lang", LANGS)
def test_the_long_sections_are_open_in_the_markup_and_closed_only_on_a_phone(lang):
    """A crawler, a reader with JavaScript off and every desktop see the whole page: the disclosures ship
    `open` and one five-line script closes them below 700px. Collapsed-by-default in the MARKUP would be a
    page whose content a search engine has to be trusted to expand."""
    html = get(PATHS[lang] + "?design=v2")
    # FIVE: the four long prose sections, plus the nine-row sky panel, which is a screenful on a phone of
    # something the reader did not come for and uses the identical mechanism.
    assert html.count('class="v2-readmore" open') == 5
    assert 'class="v2-readmore">' not in html, "a section shipped collapsed"
    # and the heading is OUTSIDE the disclosure, so a collapsed section still says what it is
    for heading in [section.heading for section in __import__("app.web.pages", fromlist=["x"]).get("home", lang).sections]:
        assert heading in html, heading


def test_the_body_carries_the_design_class_and_the_previous_design_does_not():
    """`{% block body_class %}` emits a whole attribute or nothing, so a page rendered from an old template
    still gives a bare `<body>` rather than `<body class="">`."""
    for path in PATHS.values():
        assert '<body class="design-v2">' in get(path), path
        assert "<body>" in get(path + "?design=v1"), path


# ---- the sky panel ------------------------------------------------------------------------------------


def test_the_sky_panel_is_the_engines_answer_in_the_readers_language():
    """Nine grahas, from the ephemeris, named the way each tree names them - so Marathi says मंगळ and शनी
    rather than the engine's stored Hindi, which is the defect that reached the paid book on 2026-09-29."""
    sky.reset_cache()
    rows = sky.snapshot("mr")["rows"]
    assert len(rows) == 9
    assert {row["key"] for row in rows} == {"Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn",
                                            "Rahu", "Ketu"}
    by_key = {row["key"]: row for row in rows}
    assert by_key["Mars"]["graha"] == "मंगळ" and by_key["Saturn"]["graha"] == "शनी"
    assert {r["key"]: r["graha"] for r in sky.snapshot("hi")["rows"]}["Mars"] == "मंगल"
    # English keeps the site's own convention - the planet a reader knows, with the Sanskrit name beside it.
    assert {r["key"]: r["graha"] for r in sky.snapshot("en")["rows"]}["Mars"] == "Mars (Mangal)"
    for row in rows:
        assert 0 <= row["degree"] <= 29, row          # a whole degree WITHIN the sign, never a longitude
        assert isinstance(row["retrograde"], bool)
    # Rahu and Ketu are always retrograde; if they ever read direct the source is wrong, not the panel
    assert by_key["Rahu"]["retrograde"] and by_key["Ketu"]["retrograde"]


def test_the_sky_panel_is_cached_and_costs_nothing_to_serve(monkeypatch):
    """It sits on the busiest page of the site. Every view recomputing nine positions is the thing the cache
    exists to stop, and all three languages come from ONE computation - the positions are identical and only
    the names differ."""
    sky.reset_cache()
    calls = []
    real = sky._rows

    def counted(language):
        calls.append(language)
        return real(language)

    monkeypatch.setattr(sky, "_rows", counted)
    for _ in range(5):
        for lang in LANGS:
            assert sky.snapshot(lang) is not None
    assert calls == ["en", "hi", "mr"], f"expected one computation per language, got {calls}"


def test_an_ephemeris_failure_drops_the_panel_and_not_the_page(monkeypatch):
    """Decoration on a page whose job is the kundali form. It must never be the reason the home page 500s."""
    sky.reset_cache()
    monkeypatch.setattr(sky, "_rows", lambda language: (_ for _ in ()).throw(RuntimeError("no ephemeris")))
    assert sky.snapshot("en") is None
    sky.reset_cache()

    monkeypatch.setattr(sky, "snapshot", lambda language: None)
    html = get("/?design=v2")
    assert "v2-sky" not in html                  # the panel is gone
    assert design_v2.LABELS["en"]["picker_heading"] in html   # the rest of the rail is not
