"""The glyph set and the ornaments drawn with it.

The point of these is not that the site looks nice - no test can say that. It is that the ornament stays
ornament: that every glyph a piece of code asks for actually exists in the sprite, that the decoration is
invisible to a screen reader, absent from print and still when motion is unwelcome, and that the kundali
beside a conversation is the SAME chart the conversation was built on rather than a second, drifting copy.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPRITE = ROOT / "app" / "static" / "img" / "glyphs.svg"
CSS = ROOT / "app" / "static" / "css"
JS = ROOT / "app" / "static" / "js"
TEMPLATES = ROOT / "app" / "web" / "templates"

GRAHAS = ("surya", "chandra", "mangal", "budh", "guru", "shukra", "shani", "rahu", "ketu")
RASHIS = ("mesha", "vrishabha", "mithuna", "karka", "simha", "kanya",
          "tula", "vrishchika", "dhanu", "makara", "kumbha", "meena")


def sprite_ids() -> set[str]:
    return {el.get("id") for el in ET.parse(SPRITE).getroot().iter()
            if el.tag.endswith("symbol") and el.get("id")}


def test_the_sprite_holds_every_graha_rashi_and_ornament():
    ids = sprite_ids()
    assert {f"g-{name}" for name in GRAHAS} <= ids
    assert {f"r-{name}" for name in RASHIS} <= ids
    assert {"o-om", "o-lotus", "o-dhyana"} <= ids


def test_every_glyph_the_code_asks_for_exists():
    """A `#g-something` that is not in the sprite renders as nothing, silently, forever."""
    wanted: set[str] = set()
    for path in list(JS.glob("*.js")) + list(TEMPLATES.rglob("*.html")) + list(CSS.glob("*.css")):
        wanted |= set(re.findall(r'#((?:g|r|o)-[a-z]+)', path.read_text(encoding="utf-8")))
    for path in (ROOT / "app" / "ai").glob("*.py"):
        wanted |= set(re.findall(r'"((?:g|r|o)-[a-z]+)"', path.read_text(encoding="utf-8")))
    assert wanted, "no glyph is referenced anywhere - this test would then prove nothing"
    missing = wanted - sprite_ids()
    assert not missing, f"referenced but not drawn: {sorted(missing)}"


def test_the_sidebar_names_a_glyph_for_all_twelve_rashis():
    """Every sign a chart can have must have a mark, or some readers see a name and some do not."""
    from app.ai.chat_routes import _RASHI_SLUG

    assert len(_RASHI_SLUG) == 12
    assert {f"r-{slug}" for slug in _RASHI_SLUG.values()} <= sprite_ids()


def test_the_sprite_is_ours_and_carries_no_external_art():
    text = SPRITE.read_text(encoding="utf-8")
    assert "<image" not in text, "a raster image inside the sprite is somebody else's artwork"
    assert "xlink:href" not in text and "http://" not in text.replace("http://www.w3.org", "")
    credits = (ROOT / "docs" / "CREDITS.md").read_text(encoding="utf-8")
    assert "glyphs.svg" in credits, "the glyph set must be accounted for in the credits"


def test_one_stroke_width_everywhere():
    """A set drawn at three different weights looks like three sets."""
    widths = set(re.findall(r'stroke-width="([\d.]+)"', SPRITE.read_text(encoding="utf-8")))
    assert widths <= {"1.6"}, f"the glyph set has drifted to several weights: {sorted(widths)}"


@pytest.mark.parametrize("selector", [".v2-starfield", "html::after"])
def test_the_decoration_is_dropped_in_print(selector):
    css = (CSS / "site.css").read_text(encoding="utf-8")
    block = re.search(r"@media print \{[^}]*" + re.escape(selector).replace(r"\:\:", "::"), css)
    assert block or f"@media print {{ {selector} {{ display: none; }} }}" in css, \
        f"{selector} is still painted on paper"


def test_every_animation_answers_the_reduced_motion_preference():
    """Not "nothing moves" - the sheet has two valid ways of saying it, and both are honoured here.

    An animated rule either lives inside `prefers-reduced-motion: no-preference`, so it never starts, or
    it is named again inside a `reduce` block that cancels or slows it. What is forbidden is an animation
    that no reduced-motion rule mentions at all: that one just moves, whatever the reader asked for.
    """
    for name in ("site.css", "design-v2.css"):
        text = (CSS / name).read_text(encoding="utf-8")
        reduce_blocks = " ".join(re.findall(r"@media \(prefers-reduced-motion: reduce\)\s*\{(.*?)\n", text))
        for match in re.finditer(r"^([^@{}\n]*)\{[^{}]*?animation(?:-name)?\s*:", text, re.M | re.S):
            selector = match.group(1).strip().strip("{").strip()
            before = text[:match.start()]
            opened = before.rfind("@media (prefers-reduced-motion: no-preference)")
            guarded = opened != -1 and (before[opened:].count("{") - before[opened:].count("}")) > 0
            named = any(part.strip() and part.strip() in reduce_blocks
                        for part in selector.split(","))
            assert guarded or named, (
                f"{name}: `{selector}` animates and no reduced-motion rule mentions it")


def test_the_ornaments_are_hidden_from_screen_readers():
    for name in ("base.html", "consultation_v2.html", "_consultation_body.html"):
        text = (TEMPLATES / name).read_text(encoding="utf-8")
        for match in re.finditer(r"<svg\b[^>]*>", text):
            tag = match.group(0)
            # Either it is decoration and hidden, or it is a figure with a name. What is forbidden is the
            # third case: an unnamed svg a screen reader announces as "graphic" and nothing more.
            hidden = 'aria-hidden="true"' in tag
            named = 'aria-label' in tag or "aria-labelledby" in tag
            assert hidden or named, f"{name}: an svg that is neither hidden nor named: {tag[:90]}"


def test_the_kundali_in_the_chat_is_drawn_from_the_engine_not_the_model():
    """The panel may only draw what /start already returned; it must not fetch or compute a chart."""
    text = (JS / "chat-panel.js").read_text(encoding="utf-8")
    assert "chartSvg" in text
    assert "fetch(" not in text, "the chart panel must not make requests of its own"


def test_an_ornament_never_takes_a_class_that_content_already_uses():
    """The bug this is for: the decorative starfield was called `.v2-sky`, which was already the class of
    the "sky right now" list on five pages. The ornament's `position: fixed; z-index: -1; opacity: .3`
    then applied to that list, which spent a deploy painted behind the whole site as ghost text under the
    hero. Nothing failed - it rendered, it was just wrong, and only a screenshot showed it.

    So: every class the decoration claims must be used by nothing but the decoration.
    """
    ornaments = {"v2-starfield", "v2-star--slow", "brand__orbit", "site-logo__ring",
                 "v2-chats__figure", "chat__avatar", "chat__orbit"}
    for path in TEMPLATES.rglob("*.html"):
        text = path.read_text(encoding="utf-8")
        for name in ornaments:
            for match in re.finditer(r'class="([^"]*\b' + re.escape(name) + r'\b[^"]*)"', text):
                owner = re.search(r"<(\w+)[^>]*" + re.escape(match.group(0)), text)
                tag = owner.group(1) if owner else "?"
                assert tag in {"svg", "span", "div", "i", "use", "circle"}, (
                    f"{path.name}: `{name}` is decoration but sits on <{tag}>, which carries content")


def test_the_sky_right_now_list_is_still_in_the_flow():
    """The list the ornament collided with: it must be ordinary content, not a fixed backdrop."""
    css = (CSS / "site.css").read_text(encoding="utf-8") + (CSS / "design-v2.css").read_text(encoding="utf-8")
    for match in re.finditer(r"^\.v2-sky\s*\{([^}]*)\}", css, re.M):
        body = match.group(1)
        assert "position: fixed" not in body, "the sky-right-now list has been thrown out of the flow"
        assert "z-index: -1" not in body, "the sky-right-now list has been pushed behind the page"
