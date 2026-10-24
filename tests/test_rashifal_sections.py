"""The sectioned reading: jump chips, the ten-second summary, stable anchors, the per-section ask links.

EVERY TEST HERE TAKES `populated`. Without it the rashifal store under pytest is empty, every page renders
the "being prepared" fallback, and none of this markup exists - so every assertion below would pass by
describing a page that has no reading on it. That is the exact shape of green that has already been caught
twice in this build, once measuring duplication against boilerplate and once measuring chips against a
fallback, so it is stated here rather than left to be rediscovered.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.rashifal import i18n as rashifal_i18n
from app.web import i18n
from app.web.rashifal import JUMP_CHIPS

from .test_rashifal_web import populated  # noqa: F401  (the fixture IS the point)

client = TestClient(app)

#: One reading page per language, across periods, so a chip that only works on `today` is caught.
PAGES = (("mr", "/mr/rashi-bhavishya/mesh/aaj"), ("hi", "/hi/rashifal/tula/saptahik"),
         ("en", "/horoscope/libra/today"), ("hi", "/hi/rashifal/mesh/masik"),
         ("mr", "/mr/rashi-bhavishya/vrishchik/saptahik"), ("en", "/horoscope/capricorn/monthly"))
ANCHORS = ("career", "money", "relationships", "health", "dates", "remedy")
#: The ids these pages used before this item. Somebody's bookmark points at them.
OLD_ANCHORS = ("career-money", "love-family", "health-wellbeing", "key-dates", "tip")


@pytest.mark.parametrize("lang, path", PAGES)
def test_every_anchor_exists_exactly_once(populated, lang, path):  # noqa: F811
    html = client.get(path).text
    for anchor in ANCHORS + OLD_ANCHORS:
        found = len(re.findall(rf'id="{re.escape(anchor)}"', html))
        assert found == 1, f"{path}: id={anchor} appears {found} times, want 1"


@pytest.mark.parametrize("lang, path", PAGES)
def test_each_section_has_its_own_h2(populated, lang, path):  # noqa: F811
    """Google links straight to a section when the section has a heading of its own. These were h3 under
    one h2 for the whole reading, which reads as subordinate."""
    html = client.get(path).text
    article = html.split('class="reading card"', 1)[1].split("</article>", 1)[0]
    for anchor in ("career", "relationships", "health", "dates", "remedy"):
        section = article.split(f'id="{anchor}"', 1)[1].split("</section>", 1)[0]
        assert "<h2>" in section, f"{path}: section #{anchor} has no h2 of its own"


@pytest.mark.parametrize("lang, path", PAGES)
def test_the_chips_are_in_the_pages_language(populated, lang, path):  # noqa: F811
    html = client.get(path).text
    nav = html.split('class="jumps"', 1)[1].split("</nav>", 1)[0]
    assert len(re.findall(r'class="jumps__chip"', nav)) == len(JUMP_CHIPS)
    for key, anchor, _icon in JUMP_CHIPS:
        label = rashifal_i18n.UI[lang][f"jump_{key}"]
        assert label in nav, f"{path}: chip {key} is not labelled {label!r}"
        assert f'href="#{anchor}"' in nav, f"{path}: chip {key} does not link to #{anchor}"


@pytest.mark.parametrize("lang, path", PAGES)
def test_every_chip_lands_on_a_real_anchor(populated, lang, path):  # noqa: F811
    """A chip pointing at an id the page does not have scrolls nowhere, and nothing else would catch it."""
    html = client.get(path).text
    nav = html.split('class="jumps"', 1)[1].split("</nav>", 1)[0]
    for target in re.findall(r'href="#([^"]+)"', nav):
        assert f'id="{target}"' in html, f"{path}: chip points at #{target}, which does not exist"


@pytest.mark.parametrize("lang, path", PAGES)
def test_the_summary_is_shown(populated, lang, path):  # noqa: F811
    """It was generated for every reading from the first version and no template rendered it."""
    html = client.get(path).text
    assert 'class="reading__summary"' in html, path
    summary = html.split('class="reading__summary"', 1)[1].split("</p>", 1)[0]
    assert len(re.sub(r"<[^>]+>", "", summary).split()) >= 5, f"{path}: the summary box is empty"


@pytest.mark.parametrize("lang, path", PAGES)
def test_the_reading_is_never_collapsed(populated, lang, path):  # noqa: F811
    """No accordions: the whole reading stays open, top to bottom. A <details> around any of it would hide
    a section from a reader on a phone AND change what a crawler sees first."""
    html = client.get(path).text
    article = html.split('class="reading card"', 1)[1].split("</article>", 1)[0]
    assert "<details" not in article, f"{path}: part of the reading is inside a <details>"
    assert " hidden" not in article, f"{path}: part of the reading is hidden"


@pytest.mark.parametrize("lang, path", PAGES)
def test_each_section_offers_the_astrologer_in_its_own_language(populated, lang, path):  # noqa: F811
    html = client.get(path).text
    article = html.split('class="reading card"', 1)[1].split("</article>", 1)[0]
    asks = re.findall(r'class="reading__ask"><a href="([^"]+)">([^<]+)<', article)
    assert len(asks) == 4, f"{path}: {len(asks)} ask links, want one under each of the four sections"
    consultation = i18n.url_for("consultation", lang)
    for href, label in asks:
        assert href.startswith(consultation), f"{path}: ask link goes to {href}, not the astrologer"
        assert re.search(r"\?topic=[a-z]+$", href), f"{path}: {href} carries no topic for the funnel"
        assert label.strip(), f"{path}: empty ask label"


@pytest.mark.parametrize("lang, path", PAGES)
def test_the_ask_link_names_the_sign(populated, lang, path):  # noqa: F811
    """"Ask about YOUR Makar career" - the sign is the whole reason this link is worth a tap."""
    html = client.get(path).text
    rashi = i18n.resolve(path)[2].get("rashi")
    names = i18n.rashi_names(rashi, lang)
    article = html.split('class="reading card"', 1)[1].split("</article>", 1)[0]
    labels = re.findall(r'class="reading__ask"><a href="[^"]+">([^<]+)<', article)
    # `names` carries an int index alongside the names, and `7 in "Ask about..."` raises rather than
    # returning False - so the names are filtered to strings before any of them is searched for.
    spellings = [n for n in names.values() if isinstance(n, str) and n]
    named = [l for l in labels if any(n in l for n in spellings)]
    assert len(named) >= 3, f"{path}: only {len(named)} of {len(labels)} ask links name the sign: {labels}"


@pytest.mark.parametrize("lang, path", PAGES)
def test_back_to_top_after_every_section(populated, lang, path):  # noqa: F811
    html = client.get(path).text
    article = html.split('class="reading card"', 1)[1].split("</article>", 1)[0]
    links = re.findall(r'class="reading__totop"><a href="([^"]+)">([^<]+)<', article)
    assert len(links) == 5, f"{path}: {len(links)} back-to-top links, want one after each of five sections"
    for href, label in links:
        assert href == "#jumps", f"{path}: back-to-top goes to {href}"
        assert label.strip() == rashifal_i18n.UI[lang]["back_to_top"], f"{path}: {label!r} is not in {lang}"


def test_the_chip_row_cannot_shift_the_page(populated):  # noqa: F811
    """Everything this item adds sits ABOVE the reading, so anything that changes height after paint moves
    the whole reading down. The row is given a fixed min-height and the icons explicit dimensions for that
    reason; this guards the CSS that does it. Measured CLS on the page itself is 0.0000."""
    css = (client.get("/static/css/site.css").text)
    row = css.split(".jumps {", 1)[1].split("}", 1)[0]
    assert "min-height" in row, "the chip row has no min-height; a webfont landing would reflow it"
    icon = css.split(".jumps__icon {", 1)[1].split("}", 1)[0]
    assert "width" in icon and "height" in icon, "the chip icons have no explicit size"


def test_the_chip_labels_exist_in_every_language():
    """A missing key renders as an empty chip rather than an error, which is why this is checked directly."""
    for lang in i18n.LANGS:
        for key, _anchor, _icon in JUMP_CHIPS:
            assert rashifal_i18n.UI[lang].get(f"jump_{key}"), f"{lang}: no label for chip {key}"
        assert rashifal_i18n.UI[lang].get("back_to_top"), f"{lang}: no back-to-top label"


def test_the_chip_glyphs_are_real_symbols():
    """A chip pointing at a <symbol> the sprite does not define renders as an empty box - the same class of
    bug as the \\25BE triangle that shipped as tofu, and invisible to any template assertion."""
    sprite = client.get("/static/img/glyphs.svg").text
    for key, _anchor, icon in JUMP_CHIPS:
        assert f'id="{icon}"' in sprite, f"chip {key} uses {icon}, which the sprite does not define"


def test_the_ask_topic_reaches_the_funnel():
    """The ask links carry ?topic=career so the funnel can say which section sent the reader.

    IT IS AN EVENT, NOT A VISIT. site_visits stores "path only, never the query string" by design, so the
    topic is recorded on the events table instead of being smuggled past that rule.
    """
    from app import analytics
    from app.web.rashifal import ASK_TOPICS

    path = i18n.url_for("consultation", "hi")
    before = len(analytics.recent_events(200))
    assert client.get(f"{path}?topic=career").status_code == 200
    recorded = [e for e in analytics.recent_events(200) if e.get("action") == "ask-click"]
    assert recorded and recorded[0].get("detail") == "career", recorded[:2]

    # A value from outside the fixed set is not stored, because `detail` is structural and the query
    # string is written by whoever types the URL.
    assert client.get(f"{path}?topic=<script>alert(1)</script>").status_code == 200
    details = {e.get("detail") for e in analytics.recent_events(200) if e.get("action") == "ask-click"}
    assert details <= ASK_TOPICS, f"an unchecked topic reached the table: {details - ASK_TOPICS}"
    assert len(analytics.recent_events(200)) > before


def test_the_devanagari_face_is_the_last_resort():
    """It must be a family of its own, after every system family, or devices that already have Devanagari
    download 61 KB they do not need. It is NOT declared under the name "Noto Sans Devanagari" with a
    local() hint: Safari and Firefox ignore local(), which is why the earlier version of this file was
    measured at 0.27s and never wired in."""
    css = client.get("/static/css/site.css").text
    block = css.split('html[lang="hi"], html[lang="mr"] {', 1)[1].split("}", 1)[0]
    # The comment above the declaration names the family too, so it is stripped before anything is
    # located by position - otherwise this measures the prose and not the font stack.
    stack = re.sub(r"/\*.*?\*/", " ", block, flags=re.S).split("--font:", 1)[1]
    ours = stack.index("RK Devanagari Fallback")
    for system_family in ("Noto Sans Devanagari", "Nirmala UI", "Kohinoor Devanagari", "Mangal"):
        assert stack.index(system_family) < ours, f"{system_family} must come before our own face"
    face = client.get("/static/css/fonts-devanagari.css").text
    # Comments stripped first. The file explains at length why local() is NOT used, and a test that reads
    # the prose instead of the rules fails on the explanation - which is what happened here.
    rules = re.sub(r"/\*.*?\*/", " ", face, flags=re.S)
    # SCOPED TO THE SERVED FACES. The ban on local() is about the faces that DELIVER the subset: a hint
    # Safari and Firefox ignore would have them fetch the file anyway, which is the mistake this file
    # was rewritten to avoid. "RK Devanagari Metrics" serves no file - it is a metrics-matched stand-in
    # drawn from a font the device already has while the subset downloads - and local() is the only way
    # to express that. Where it is ignored the face simply does not apply and the stack falls through,
    # which is the behaviour without it. So the rule holds where it means something and the check now
    # says which faces it means.
    served = [f for f in re.findall(r"@font-face\s*\{[^}]*\}", rules)
              if '"RK Devanagari Fallback"' in f]
    assert len(served) == 2, "expected the regular and bold faces of the served subset"
    for block in served:
        assert "local(" not in block, "a local() hint is ignored by some browsers; the stack order does this job"
        assert "url(" in block, "a served face must name the file it serves"
    assert rules.count("unicode-range") == 3, "every Devanagari face must be limited to Devanagari"
    assert "U+0900-097F" in rules


def test_the_devanagari_font_is_linked_everywhere_but_preloaded_only_where_it_is_the_page():
    """WHAT THIS GUARD IS ACTUALLY FOR: an English visitor must not be made to download a 61 KB
    Devanagari subset before the page can paint.

    It used to say the sheet must not appear on the English tree at all, and that premise was simply
    false - an English page is FULL of Devanagari. The switcher says हिन्दी and मराठी, and every chart
    result prints "Mangal (Mars) मंगल". Those were drawn as empty boxes for every English visitor,
    because the one tree that never linked the face was the tree quietly using it.

    So the rule is narrowed to the cost it exists to control, not relaxed: every tree may LINK the
    sheet, because every tree draws the script; only the Devanagari trees PRELOAD it, because only
    there is it the font the page is set in. An English page fetches it lazily, for a few words, or
    not at all if the system already has a Devanagari face.
    """
    english = client.get("/horoscope/libra/today").text
    assert "fonts-devanagari" in english, "English draws Devanagari and must be able to"
    assert "rel=\"preload\"" not in _devanagari_tags(english), \
        "the English tree must not block on a 61 KB subset it needs for a handful of words"

    for path in ("/hi/rashifal/tula/saptahik", "/mr/rashi-bhavishya/mesh/aaj"):
        page = client.get(path).text
        assert "fonts-devanagari" in page, path
        assert "preload" in _devanagari_tags(page), f"{path} is set in Devanagari and must preload it"


def _devanagari_tags(html: str) -> str:
    """Every <link> in the page that mentions the Devanagari font, as one string."""
    import re

    return "\n".join(tag for tag in re.findall(r"<link [^>]*>", html)
                     if "evanagari" in tag)


def test_indexnow_stays_quiet_off_production():
    """A laptop regenerating two pages was submitting 39 URLs to Bing and Yandex per run, and a 429 is how
    that was noticed. The site's submission quota is for pages that actually changed on the live site."""
    from app.web import indexnow

    result = indexnow.submit(["/horoscope/libra/today"], reason="test")
    assert result["sent"] == 0 and "not production" in result["detail"], result


def test_every_colour_token_the_stylesheets_use_is_defined():
    """A misspelt custom property does not raise - the declaration is simply dropped, and the element
    quietly renders with an inherited value.

    THIS CAUGHT A REAL ONE. The chips and the summary box were written against `--color-gold`, a token
    that does not exist; the real one is `--color-accent`. The icons rendered in body ink instead of gold
    and the summary box lost its left border, and both looked deliberate enough to survive a screenshot
    review. Nothing else in the suite would have said a word.

    A use that supplies a fallback - var(--veil-half, 496px) - is deliberate and is not a finding: the
    fallback IS the value when the token is not set by a parent.
    """
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[1] / "app" / "static" / "css"
    sheets = sorted(root.glob("*.css"))
    assert sheets, "no stylesheets found"
    defined = set()
    for sheet in sheets:
        defined |= set(re.findall(r"(--[\w-]+)\s*:", sheet.read_text()))
    missing = {}
    for sheet in sheets:
        for token in re.findall(r"var\((--[\w-]+)\s*\)", sheet.read_text()):
            if token not in defined:
                missing.setdefault(sheet.name, set()).add(token)
    assert not missing, f"undefined custom properties: {missing}"


# ---------------------------------------------------------------------------------------------------
# 3c: the bridge from a sign reading to the reader's own chart.


def test_the_bridge_sits_above_the_jump_chips_in_every_tree():
    """WHY IT EXISTS AT ALL: the rail already carries a proper CTA card with a button, and on a 390px
    phone it measures about two thirds of the way down a 6,000-pixel page - after the entire reading.
    The sentence belongs where the reader has just been told what their sign's day looks like."""
    body = Path("app/web/templates/_rashifal_reading_body.html").read_text(encoding="utf-8")
    assert "reading__bridge" in body
    assert body.index("reading__bridge") < body.index('id="jumps"'), "the bridge is below the chip row"
    assert body.index('class="reading__summary"') < body.index("reading__bridge")


def test_the_bridge_copy_exists_in_all_three_languages_and_names_the_sign():
    """It states the limitation of the reading in front of the person - one sign is one of twelve
    readings - so it has to name their sign, in their language."""
    from app.rashifal import i18n as rashifal_i18n

    for lang in ("en", "hi", "mr"):
        words = rashifal_i18n.UI[lang]
        assert "{rashi}" in words["bridge_text"], f"{lang} bridge does not name the sign"
        assert words["bridge_link"].strip(), f"{lang} has no link text"


def test_the_bridge_is_quieter_than_the_rail_card():
    """Two identical asks on one page read as a site that wants something. The rail sells, with a button;
    this is a sentence in the prose."""
    body = Path("app/web/templates/_rashifal_reading_body.html").read_text(encoding="utf-8")
    bridge = body[body.index('class="reading__bridge"'):]
    bridge = bridge[:bridge.index("</p>")]
    assert "btn" not in bridge, "the bridge is styled as a button"
    css = Path("app/static/css/site.css").read_text(encoding="utf-8")
    rule = css[css.index(".reading__bridge {"):]
    rule = rule[:rule.index("}")]
    assert "var(--color-muted)" in rule


def test_every_token_the_bridge_uses_exists():
    """--color-ink-soft was the first spelling, and it does not exist. An undeclared custom property used
    with no fallback resolves to nothing and renders as inherited body ink without failing anything -
    which is how an earlier block lost its border and its icons silently.

    Writing the example literally in the stylesheet's own comment tripped the site-wide version of this
    guard, which reads comments as well as rules. It was right to."""
    css = Path("app/static/css/site.css").read_text(encoding="utf-8")
    declared = set(re.findall(r"(--[a-z0-9-]+)\s*:", css))
    rule = css[css.index(".reading__bridge {"):]
    rule = rule[:rule.index("\n\n")]
    for used in re.findall(r"var\((--[a-z0-9-]+)(?!\s*,)", rule):
        assert used in declared, f"{used} is used by the bridge and declared nowhere"


def test_every_period_card_on_a_rashi_hub_says_something():
    """THE MONTH, SIX-MONTH AND YEAR CARDS SAT WITH A DATE RANGE AND THEN A BLANK while Today and This
    Week beside them carried a sentence - which reads as a card that failed to load rather than one
    with nothing to say. The teaser was only ever built for the two short periods.
    """
    import datetime as dt

    from app.web import rashifal

    now = dt.datetime.now()
    brief = rashifal.build_brief("tula", "today", now)
    for period in ("today", "weekly", "monthly", "6-months", "yearly"):
        line = rashifal._engine_teaser("tula", period, "en", now, brief)
        assert line and line.strip(), f"the {period} card has nothing to say"


def test_two_cards_on_one_hub_never_carry_the_same_sentence():
    """The windows NEST - a month sits inside the six months, which sits inside the year - so the
    first slow-graha event is very often the same event, and two cards side by side carrying one
    identical sentence reads as a bug rather than a coincidence."""
    page = client.get("/horoscope/libra").text
    body = page.split('All Libra horoscopes', 1)[-1].split("</section>", 1)[0]
    lines = re.findall(r"<p[^>]*>([^<]{25,})</p>", body)
    meaningful = [line.strip() for line in lines if " - house " in line or " enters " in line]
    assert len(meaningful) == len(set(meaningful)), f"a line repeats: {meaningful}"


def test_the_moon_is_not_offered_as_a_summary_of_a_year():
    """Where the Moon is right now is a fact about today. On a card covering a year it is a sentence
    that stops being true in two days, which is worse than the date alone."""
    import datetime as dt

    from app.web import rashifal

    now = dt.datetime.now()
    brief = rashifal.build_brief("tula", "today", now)
    for period in ("monthly", "6-months", "yearly"):
        line = rashifal._engine_teaser("tula", period, "en", now, brief, avoid=set())
        assert "Moon (Chandra) enters" not in (line or ""), period
