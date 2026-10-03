"""PHASE 2 of the full-width prototype: tool pages, their result, and the three rashifal page kinds.

Phase 1 put one page behind `?design=v2`. Phase 2 puts the pages that EARN, and the pages that are read more
than anything else on the site, behind the same flag - and it does it by extracting the live pages' markup
into partials that both arrangements include. That extraction is the risk this file exists for, and it has two
distinct failure modes which need two different kinds of assertion:

  THE LIVE PAGE CHANGES. Cutting markup out of tool.html and rashifal_page.html cannot alter what a visitor
  with no query string gets. The extraction was verified once, out of band, by rendering all twenty affected
  URLs from the pre-extraction commit in a git worktree and diffing: all twenty were identical once the asset
  hash (design-v2.css moved, so `?v=` moved with it) and the blank lines left where the include tags now sit
  were normalised away. A one-off diff cannot be a test, so what is asserted here instead is the property
  that diff was checking for: the live pages carry no trace of the prototype, and they still carry every
  structural part the extraction moved.

  THE PROTOTYPE DROPS A HOOK. app.js, pay.js and render.js find the form and the result BY ID. A second
  arrangement of the same page is a second contract with three scripts, and the way it breaks is silent: the
  page renders, and submitting does nothing. So the hooks are not listed here - a hardcoded list goes stale
  and then asserts nothing. They are read out of the scripts themselves and compared as a SET between the two
  arrangements, which is a claim that stays true as the scripts change.
"""

import json
import pathlib
import re

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

STATIC = pathlib.Path("app/static/js")
TEMPLATES = pathlib.Path("app/web/templates")

# THE URL LISTS ARE THE SITEMAP'S, NOT ONES WRITTEN OUT FROM MEMORY. The first version of this file invented
# five paths that 404 - `/sidereal-calculator`, `/mr/kundali-matching`, `/horoscope-weekly` - and the tests
# over them passed the parts that compare live against prototype, because a 404 compared equal to a 404. A
# list of URLs is a population, and a wrong population is a green that means nothing. These were read off
# /sitemap.xml and the counts are asserted below, so a renamed route breaks the test rather than shrinking it.
TOOL_SINGLE = ("/birth-chart", "/hi/kundli", "/mr/kundali",
               "/mangal-dosha", "/hi/mangal-dosha", "/mr/mangal-dosha",
               "/sade-sati", "/hi/sade-sati", "/mr/sade-sati", "/sidereal-birth-chart")
TOOL_PAIR = ("/horoscope-matching", "/hi/kundali-matching", "/mr/patrika-matching")
TOOL_PAGES = TOOL_SINGLE + TOOL_PAIR

# The chat pages (/ai-astrologer and its two translations) also carry `id="tool-form"`, but they are a
# different template with no `_v2` counterpart, so the preview swap falls through to the live page - which is
# the designed behaviour for any page phase 2 has not reached. They are out of scope here, and asserted to be
# so rather than left out silently, because "it is missing from the list" and "it deliberately has no
# prototype" look identical from inside a test that does not mention it.
CHAT_PAGES = ("/ai-astrologer", "/hi/ai-jyotish", "/mr/ai-jyotish")

HUB_PAGES = ("/horoscope", "/hi/rashifal", "/mr/rashi-bhavishya",
             "/horoscope/weekly", "/hi/rashifal/saptahik", "/mr/rashi-bhavishya/saptahik")
RASHI_PAGES = ("/horoscope/libra", "/hi/rashifal/tula", "/mr/rashi-bhavishya/tula",
               "/horoscope/aries", "/hi/rashifal/mesh", "/mr/rashi-bhavishya/mesh")
READING_PAGES = ("/horoscope/libra/today", "/hi/rashifal/tula/aaj", "/mr/rashi-bhavishya/tula/aaj",
                 "/horoscope/aries/weekly", "/hi/rashifal/mesh/saptahik", "/mr/rashi-bhavishya/mesh/saptahik")
ALL_PAGES = TOOL_PAGES + HUB_PAGES + RASHI_PAGES + READING_PAGES

# The four templates phase 2 adds, and the live template each one stands in for.
V2_TEMPLATES = ("tool_v2.html", "rashifal_index_v2.html", "rashifal_rashi_v2.html", "rashifal_page_v2.html")


# THE PREVIOUS DESIGN. Since 3 October the full-width design is what every visitor gets (site.DESIGN_V2),
# so the comparison these tests make - "the two arrangements of this page agree" - is no longer
# live-vs-prototype but previous-vs-current. `?design=v1` renders the old template, which is still in the
# tree and still the rollback.
PREVIOUS = "?design=v1"


def get(path: str) -> str:
    response = client.get(path)
    assert response.status_code == 200, (path, response.status_code)
    return response.text


def head_of(html: str) -> str:
    return html.split("</head>", 1)[0]


def script_hooks() -> set[str]:
    """Every id the three tool scripts look up. Read from the scripts so the set cannot go stale."""
    found = set()
    for name in ("app.js", "pay.js", "render.js"):
        source = (STATIC / name).read_text()
        found |= set(re.findall(r'getElementById\("([^"]+)"\)', source))
        found |= set(re.findall(r'querySelector\("#([A-Za-z0-9_-]+)"\)', source))
    assert len(found) > 10, "the hook scan found almost nothing - the scripts changed shape, fix the scan"
    return found


def ids_in(html: str) -> set[str]:
    return set(re.findall(r'\bid="([A-Za-z0-9_-]+)"', html))


# ---- the live pages are untouched -------------------------------------------------------------------


@pytest.mark.parametrize("path", ALL_PAGES)
def test_the_previous_design_is_still_reachable_and_unchanged(path):
    """`?design=v1` renders the previous template whatever the switch is set to, so the rollback can be
    checked on the live site before it is taken. Nothing was deleted to make the flip."""
    previous = get(path + PREVIOUS)
    assert "design-v2" not in previous, path
    assert "v2-hero" not in previous and "v2-rail" not in previous, path
    assert "noindex" not in previous, path


@pytest.mark.parametrize("path", TOOL_SINGLE)
def test_the_previous_tool_form_still_has_the_numbered_stages_the_extraction_moved(path):
    """`_tool_form.html` takes a `form_stages` flag so the prototype can render the fields unstaged in its
    hero. A default that leaked the other way would silently un-stage the LIVE form on the pages that earn -
    three fields at once instead of one at a time, on a phone, with no test failing. The default is asserted
    from the live page, not from the template's signature."""
    live = get(path + PREVIOUS)
    assert live.count('data-step="') == 3, path
    assert 'class="steps"' in live, path
    assert live.count("step__num") == 3, path


@pytest.mark.parametrize("path", TOOL_PAIR)
def test_the_pair_form_is_staged_by_person_on_both_arrangements(path):
    """A pair form's two steps are the two PEOPLE, not three stages of one person: it is already as compact
    as the single form's unstaged branch, so the prototype leaves it exactly as it is."""
    for url in (path, path + "?design=v2", path + PREVIOUS):
        html = get(url)
        assert html.count('data-step="') == 2, url
        assert html.count("step__num") == 2, url


# ---- the prototype cannot be indexed, and cannot take the real page's place --------------------------


@pytest.mark.parametrize("path", ALL_PAGES)
def test_the_page_the_site_serves_is_indexable_and_keeps_every_seo_signal(path):
    """THE NOINDEX HAD TO COME OFF WITH THE FLIP. It was correct while the design was a preview behind a
    query string and is the most expensive thing that could have been left behind afterwards - a noindex
    across the tool and rashifal pages of a site that lives on search.

    Everything that tells a crawler which page this IS - title, description, canonical, hreflang, JSON-LD -
    must still be what the previous design carried, byte for byte. The design changed; the page did not."""
    live, proto = get(path + PREVIOUS), get(path)
    assert "noindex" not in proto, f"{path} is noindex"
    assert "design-v2" in proto, path

    live_head, proto_head = head_of(live), head_of(proto)
    for tag in ("<title>", 'name="description"', 'rel="canonical"', 'rel="alternate"', 'property="og:title"'):
        assert extract(live_head, tag) == extract(proto_head, tag), (path, tag)

    assert json_blocks(live) == json_blocks(proto), path


def extract(head: str, needle: str) -> list[str]:
    """Every line of <head> carrying `needle`, so a changed title or a dropped hreflang is a failure."""
    return sorted(line.strip() for line in head.splitlines() if needle in line)


def json_blocks(html: str) -> list:
    """Every JSON-LD block, parsed - compared as data so indentation cannot make a difference either way."""
    return sorted(
        (json.dumps(json.loads(m), sort_keys=True) for m in
         re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)),
    )


@pytest.mark.parametrize("path", ALL_PAGES)
def test_the_prototype_keeps_every_h1_and_every_internal_link_the_live_page_has(path):
    """The H1 is the page's promise and the internal links are how the rest of the site is reachable. The
    prototype may ADD a link - the rail is mostly links - but losing one is losing a path a crawler follows."""
    live, proto = get(path + PREVIOUS), get(path)
    assert re.findall(r"<h1[^>]*>(.*?)</h1>", live, re.S) == re.findall(r"<h1[^>]*>(.*?)</h1>", proto, re.S), path

    def internal(html):
        body = html.split("</head>", 1)[1]
        return {h for h in re.findall(r'href="(/[^"#?]*)"', body) if not h.startswith("/static/")}

    missing = internal(live) - internal(proto)
    assert not missing, f"{path} loses internal links: {sorted(missing)}"


# ---- the prototype does not break the three scripts -------------------------------------------------


@pytest.mark.parametrize("path", TOOL_PAGES)
def test_the_prototype_offers_the_scripts_exactly_the_hooks_the_live_page_does(path):
    """THE FAILURE THIS CATCHES IS SILENT. app.js reads the form and writes the result by id; pay.js drives
    the purchase the same way. A rearrangement that drops one renders a page that looks right and does
    nothing when submitted. Set equality, both directions: a hook the prototype lacks is broken, and a hook
    only the prototype has means the two pages have drifted apart."""
    hooks = script_hooks()
    live, proto = ids_in(get(path + PREVIOUS)), ids_in(get(path))
    assert live & hooks == proto & hooks, path


@pytest.mark.parametrize("path", TOOL_SINGLE)
def test_the_prototypes_hero_form_is_the_compact_one(path):
    """Feedback on phase 1's screenshots: the hero form was too tall to see whole at 1366x768. The fields are
    the same fields - this is the unstaged branch, date and time on one row and place across the width, which
    is what the home prototype already renders - so the claim to check is that the stages are GONE from the
    prototype while the live page above still has all three."""
    proto = get(path)
    assert 'data-step="' not in proto, path
    assert "step__num" not in proto, path
    assert 'class="field-row' in proto, path
    # every field is still there, and still where the scripts look for it
    for suffix in ("name", "date", "time", "city"):
        assert f'id="self-{suffix}"' in proto, (path, suffix)


@pytest.mark.parametrize("path", TOOL_PAGES)
def test_the_result_is_one_markup_included_twice_and_not_a_second_copy(path):
    """The result region is the tallest and most intricate thing on the site. Two hand-maintained copies of
    it would drift, so both arrangements include the same partial - asserted by the ids, which is what
    render.js actually depends on."""
    live, proto = get(path + PREVIOUS), get(path)
    for hook in ("result", "result-body", "result-skeleton", "cta", "cta-notice"):
        assert f'id="{hook}"' in live, (path, hook)
        assert f'id="{hook}"' in proto, (path, hook)


# ---- the rashifal pages keep their words -------------------------------------------------------------


@pytest.mark.parametrize("path", READING_PAGES)
def test_the_reading_itself_is_the_same_text_in_the_prototype(path):
    """These are the most-read pages on the site. The prototype moves the blocks AROUND the reading into a
    rail; the reading is the product and not one word of it moves."""
    live, proto = get(path + PREVIOUS), get(path)

    def paragraphs(html):
        body = html.split("</head>", 1)[1]
        return [re.sub(r"<[^>]+>", "", p).strip() for p in re.findall(r"<p[^>]*>(.*?)</p>", body, re.S)]

    live_text, proto_text = paragraphs(live), paragraphs(proto)
    missing = [p for p in live_text if p and p not in proto_text]
    assert not missing, f"{path} drops {len(missing)} paragraph(s), first: {missing[:1]}"


@pytest.mark.parametrize("path", HUB_PAGES)
def test_every_one_of_the_twelve_cards_is_on_the_prototype_hub(path):
    """A hub that lost a sign would lose a reader and an indexed link at the same time."""
    assert get(path).count('class="v2-hubcard"') == 12, path


# ---- the prototype's own markup keeps the rules phase 1 established ---------------------------------


@pytest.mark.parametrize("name", V2_TEMPLATES)
def test_every_inline_icon_in_the_phase_2_templates_carries_its_own_size(name):
    """A regression that shipped once already: an inline <svg> with no width/height fills its container, and
    the arrows in the tool cards rendered at 571px. The CSS rule that fixes it is not enough on its own -
    it is one stylesheet away from being overridden - so every icon states its size on the element too. The
    rendered check that no icon EXCEEDS 32px lives in scripts/design_shots.py; this is the markup half."""
    source = (TEMPLATES / name).read_text()
    for svg in re.findall(r"<svg\b[^>]*>", source, re.S):
        assert 'class="icon' in svg, f"{name}: an inline svg with no icon class: {svg[:70]}"
        assert 'width="1em"' in svg and 'height="1em"' in svg, f"{name}: unsized icon: {svg[:70]}"


@pytest.mark.parametrize("name", V2_TEMPLATES)
def test_the_phase_2_templates_add_no_inline_style_and_no_third_party_asset(name):
    """CSP is self-only and the fonts are self-hosted. A prototype is where a convenient CDN link gets added
    and then quietly promoted to the live page."""
    source = (TEMPLATES / name).read_text()
    assert "http://" not in source and "https://" not in source, name
    assert "<style" not in source, name


@pytest.mark.parametrize("path", ALL_PAGES)
def test_the_body_carries_the_design_class_and_the_previous_design_does_not(path):
    """Every phase 2 rule is scoped under `body.design-v2`, so the class is what actually applies the design
    - and its absence is what makes `?design=v1` a real rollback rather than the same page with old markup."""
    assert 'class="design-v2"' in get(path), path
    assert 'class="design-v2"' not in get(path + PREVIOUS), path


# ---- the population these tests run over is the real one ---------------------------------------------


def test_the_pages_these_tests_cover_are_the_ones_the_sitemap_publishes():
    """Every URL above must exist, and the four kinds must be the four kinds the site actually has. Without
    this, a route rename turns this whole file into assertions about 404 pages - which pass."""
    sitemap = client.get("/sitemap.xml").text
    published = {re.sub(r"^https?://[^/]+", "", u) for u in re.findall(r"<loc>(.*?)</loc>", sitemap)}
    for path in ALL_PAGES + CHAT_PAGES:
        assert path in published, f"{path} is not in the sitemap - the list here is stale"
        assert client.get(path).status_code == 200, path

    # the counts the sitemap had when phase 2 was built, so a new tool or a thirteenth sign is noticed here
    kinds = {"tool": 0, "hub": 0, "reading": 0}
    for path in published:
        html = client.get(path).text
        if 'id="tool-form"' in html:
            kinds["tool"] += 1
        elif 'id="hub-cards"' in html:
            kinds["hub"] += 1
        elif 'id="period-range"' in html:
            kinds["reading"] += 1
    # 19 tool forms, not 16: since the design flip the three home pages carry the kundali form in their
    # hero, so they answer to the same `id="tool-form"` the tool pages do. That is the flip working.
    assert kinds == {"tool": 19, "hub": 6, "reading": 180}, kinds


@pytest.mark.parametrize("path", CHAT_PAGES)
def test_a_page_phase_2_has_not_reached_falls_through_to_the_live_template(path):
    """The preview swap is opt-in per template: it looks for `<name>_v2.html` and uses the live template when
    there is none. So the flag on a page with no prototype is a no-op rather than a 500 or a half-styled
    page - which is what makes it safe to ship the flag before every page has an arrangement."""
    flagged = get(path + "?design=v2")
    assert "design-v2" not in flagged, path
    assert flagged == get(path) == get(path + PREVIOUS), path


# ---- no part of the design may depend on a glyph the fonts do not have ------------------------------


def _bundled_coverage() -> set[int]:
    """Every codepoint the four fonts this site ships can actually draw."""
    from fontTools.ttLib import TTFont

    covered = set()
    for path in sorted(pathlib.Path("app/pdf/fonts").glob("*.ttf")):
        font = TTFont(path, fontNumber=0, lazy=True)
        for table in font["cmap"].tables:
            covered |= set(table.cmap)
    assert len(covered) > 1000, "the font scan found almost nothing - check the path"
    return covered


def test_no_css_rule_draws_a_character_the_fonts_cannot_draw():
    """THIS ONE SHIPPED. The disclosure marker was `content: " \\u25be"`, and U+25BE is in none of the four
    Noto faces this site bundles nor in the Devanagari subset it serves - so every "Read more" on a phone
    ended in a tofu box. The page had ALREADY replaced "\\u2192" and "\\u2713" with inline SVG for that exact
    reason, and the replacement missed the CSS because a template test cannot see a stylesheet.

    A generated marker is now drawn out of borders and depends on no font at all. What this asserts is the
    general rule rather than the one character: nothing in `content:` may be a codepoint the fonts lack."""
    covered = _bundled_coverage()
    css = pathlib.Path("app/static/css/design-v2.css").read_text()
    offenders = []
    for value in re.findall(r"content:\s*([^;]+);", css):
        for char in re.findall(r'["\']([^"\']*)["\']', value):
            offenders += [f"U+{ord(c):04X} {c!r}" for c in char if ord(c) > 0x7F and ord(c) not in covered]
    assert not offenders, f"design-v2.css draws characters no bundled font has: {sorted(set(offenders))}"


def test_the_phase_2_templates_print_no_character_the_fonts_cannot_draw():
    """The template half of the same rule. Devanagari is excluded because those pages are the reason the
    Devanagari faces exist; what this catches is a symbol, arrow or dingbat typed into the markup."""
    covered = _bundled_coverage()
    offenders = {}
    for name in V2_TEMPLATES:
        source = (TEMPLATES / name).read_text()
        # comments explain WHY a character was replaced by an SVG, and must stay able to name it
        source = re.sub(r"\{#.*?#\}", "", source, flags=re.S)
        bad = {f"U+{ord(c):04X} {c!r}" for c in source
               if ord(c) > 0x7F and not 0x900 <= ord(c) <= 0x97F and ord(c) not in covered}
        if bad:
            offenders[name] = sorted(bad)
    assert not offenders, offenders


# ---- the home prototype's form is a real form ------------------------------------------------------


HOME_PAGES = ("/", "/hi/", "/mr/")


@pytest.mark.parametrize("path", HOME_PAGES)
def test_the_home_prototypes_hero_form_is_wired_to_the_same_scripts_as_the_tool_page(path):
    """THIS ONE SHIPPED TOO, and it is the reason this test compares against a page rather than a list.

    The live home page has no birth form at all - it links to /birth-chart - so the home prototype's hero
    form is the one piece of phase 1 with no live counterpart to be checked against. It was added with the
    right markup and the right ids, under a comment saying there was "nothing to wire", and it did not work:
    the page never loaded app.js, so typing a city fired no lookup and the submit button did nothing. It
    photographed perfectly, and screenshots were the only thing looking at it.

    The prototype's hero form IS the kundali tool's form, so the claim that holds it together is that the
    home page offers the scripts exactly what /birth-chart's prototype offers them."""
    hooks = script_hooks()
    home = ids_in(get(path + "?design=v2")) & hooks
    tool = ids_in(get("/birth-chart")) & hooks
    assert home == tool, f"{path} differs from the tool page by {sorted(home ^ tool)}"

    page = get(path + "?design=v2")
    for script in ("app.js", "render.js", "pay.js"):
        assert script in page, f"{path} does not load {script} - the form cannot work"


@pytest.mark.parametrize("path", HOME_PAGES)
def test_the_previous_home_page_still_carries_no_form_and_no_tool_scripts(path):
    """The other half, and the rollback's own guarantee: the previous home template never loaded the tool
    scripts and must not start, or `?design=v1` would stop being the page it is there to restore."""
    live = get(path + PREVIOUS)
    for script in ("app.js", "render.js", "pay.js"):
        assert script not in live, f"{path} now loads {script}"
    assert 'id="tool-form"' not in live, path


@pytest.mark.parametrize("path", TOOL_PAGES + HOME_PAGES)
def test_the_trust_line_is_printed_once(path):
    """It was printed twice in the tool prototype's hero - once in the lead and once at the top of the form
    card, the same three sentences side by side. Easy to write (two templates, one label) and easy to miss
    in a 4000px screenshot."""
    for url in (path, path + "?design=v2"):
        html = get(url)
        ui_trust = re.findall(r'class="(?:v2-hero__trust|trust-line)"[^>]*>(.*?)</p>', html, re.S)
        assert len(ui_trust) == len(set(ui_trust)), f"{url} prints the same trust line more than once"


# ---- the container is fluid, and the rail is not -----------------------------------------------------


def test_the_container_is_fluid_and_the_rail_is_capped():
    """A fixed 1280 left 320px of empty page down each side of a 1920 monitor and 640px on a 2560 - which is
    the thing this redesign exists to stop, and which is invisible at the 1440 the review was done at.

    The lower bound matters as much as the upper one: `clamp(1280px, 94vw, 1600px)` is min(94vw, 1600px) on a
    wide screen and never NARROWER than the 1280 that was reviewed, so no width from the phone to the laptop
    moves. The rendered check - that the page actually takes the width, and that the rail does not - is in
    scripts/design_shots.py, where boxes can be measured; this is the half a stylesheet diff would show."""
    css = pathlib.Path("app/static/css/design-v2.css").read_text()
    assert "max-width: clamp(1280px, 94vw, 1600px)" in css, "the v2 container is not fluid any more"
    assert "max-width: 1280px" not in css, "a fixed 1280 container has come back"

    rail = re.search(r"\.v2-body \{.*?grid-template-columns: ([^;]+);", css, re.S)
    assert rail, "the two-column body rule has moved"
    assert "minmax(260px, 400px)" in rail.group(1), f"the rail is no longer capped: {rail.group(1)}"


# ---- the switch ---------------------------------------------------------------------------------------


def test_one_setting_turns_the_whole_design_off(monkeypatch):
    """THE ROLLBACK, asserted rather than assumed. `DESIGN_V2=off` in /srv/astrology/.env and a restart has
    to put the previous design back on every page, with no deploy and nothing to revert - which is only true
    if the switch is read at request time in the one funnel, and not baked into a template or a route.

    The old templates are all still in the tree; nothing was deleted to make the flip."""
    from app.web import routes, site

    monkeypatch.setattr(site, "DESIGN_V2", False)
    for path in ("/", "/hi/", "/mr/", "/birth-chart", "/horoscope/libra", "/horoscope/libra/today"):
        off = get(path)
        assert "design-v2" not in off, f"{path} still serves the new design with the switch off"
        assert "v2-hero" not in off, path
        # and the query string still overrides, so one page can be compared without moving the setting
        assert "design-v2" in get(path + "?design=v2"), path

    monkeypatch.setattr(site, "DESIGN_V2", True)
    assert "design-v2" in get("/")
    assert "design-v2" not in get("/?design=v1")
    assert routes  # the switch lives in routes._preview, the one funnel every page goes through


def test_nothing_the_switch_turns_off_has_been_deleted():
    """A rollback that needs a deploy is not a rollback. Every template the previous design renders from is
    still here, beside its v2 counterpart."""
    for name in V2_TEMPLATES:
        previous = TEMPLATES / name.replace("_v2.html", ".html")
        assert previous.is_file(), f"{previous.name} is gone - ?design=v1 and DESIGN_V2=off cannot work"
