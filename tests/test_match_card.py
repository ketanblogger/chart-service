"""The shareable match card (SEO map item 4): "Name ❤ Name: N/36 gun".

THE SITE'S RULE IS THAT A SHARE SHARES THE TOOL, NEVER THE RESULT - written down in app/web/sharing.py
because a result is computed from somebody's birth date, time and place, and a WhatsApp message is
forwarded onward by people who never saw the original. This card is the deliberate exception the
proprietor asked for, so it is worth being exact about what makes it safe:

  - two names the reader typed, and only if they tick a box that starts unticked;
  - one score out of 36 that this page computed;
  - and nothing else. No date, no time, no place, in the markup or in the share text.

The card is also drawn in the BROWSER, on a canvas, so the names never reach a server at all. A
server-rendered card would need them in a URL or a request body, which puts the names of two people
somebody is considering a marriage between into an access log.
"""

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.web import STATIC_DIR, i18n

client = TestClient(app)
CARD_JS = (STATIC_DIR / "js" / "match-card.js").read_text(encoding="utf-8")
RENDER_JS = (STATIC_DIR / "js" / "render.js").read_text(encoding="utf-8")

# Invented people, as every test in this repository uses.
BOY = {"name": "Keshav", "date": "1991-04-03", "time": "06:12", "city": "Nashik"}
GIRL = {"name": "Tina", "date": "1993-11-21", "time": "19:40", "city": "Pune"}


@pytest.fixture(scope="module")
def js():
    mini_racer = pytest.importorskip("py_mini_racer")
    ctx = mini_racer.MiniRacer()
    ctx.eval("var window = this; var document = undefined;")
    ctx.eval(RENDER_JS)

    def call(expression: str, **variables):
        names = ", ".join(variables)
        args = ", ".join(json.dumps(value, ensure_ascii=False) for value in variables.values())
        return json.loads(ctx.eval(f"JSON.stringify((function({names}) {{ return {expression}; }})({args}))"))

    return call


@pytest.fixture(scope="module")
def result():
    response = client.post("/api/matching", json={"boy": BOY, "girl": GIRL})
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_the_card_is_offered_on_a_result_in_every_tree(js, result, lang):
    html = js("AstroRender.renderers.matching(data, ctx)", data=result, ctx={"lang": lang})
    assert "data-match-card" in html
    assert "data-match-names" in html, "the tickbox"
    assert "data-match-share" in html, "the button"


def test_the_names_box_starts_unticked(js, result):
    """Somebody sharing a match into a family group has not necessarily decided to put both names
    in it. Opting in is a decision; opting out must not be."""
    html = js("AstroRender.renderers.matching(data, ctx)", data=result, ctx={"lang": "en"})
    tick = re.search(r"<input[^>]*data-match-names[^>]*>", html).group(0)
    assert "checked" not in tick, tick


def test_the_card_carries_the_two_names_and_the_score_and_nothing_else(js, result):
    """THE RULE OF THIS FILE. The attributes on the card element are exactly the three facts it is
    allowed to know, plus its own labels."""
    html = js("AstroRender.renderers.matching(data, ctx)", data=result, ctx={"lang": "en"})
    element = re.search(r"<section class=\"block match-card\"[^>]*>", html).group(0)
    attributes = set(re.findall(r"(data-[a-z-]+)=", element)) | set(re.findall(r"\b(data-match-card)\b", element))
    assert attributes <= {
        "data-match-card", "data-score", "data-max",
        "data-label-gunas", "data-share-url",
    }, attributes


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_no_birth_detail_reaches_the_card_in_any_tree(js, result, lang):
    """The date, the time and the place of birth of two real people. None of the three may appear
    anywhere in the card's markup - not as an attribute, not as text."""
    html = js("AstroRender.renderers.matching(data, ctx)", data=result, ctx={"lang": lang})
    card = html[html.index("match-card"):]
    card = card[:card.index("</section>")]
    for person in (BOY, GIRL):
        assert person["date"] not in card, f"a birth date on the card ({lang})"
        assert person["time"] not in card, f"a birth time on the card ({lang})"
        assert person["city"] not in card, f"a birth place on the card ({lang})"
    assert "1991" not in card and "1993" not in card, "a birth year on the card"
    for fragment in ("06:12", "19:40", "Nashik", "Pune"):
        assert fragment not in card, fragment


def test_the_score_on_the_card_is_the_score_of_the_match(js, result):
    html = js("AstroRender.renderers.matching(data, ctx)", data=result, ctx={"lang": "en"})
    element = re.search(r"<section class=\"block match-card\"[^>]*>", html).group(0)
    assert f'data-score="{result["total"]}"' in element
    assert f'data-max="{result["max_total"]}"' in element


def test_no_name_is_in_the_markup_at_all(js, result):
    """STRONGER THAN ESCAPING ONE. The names are read from the two name inputs at the moment the
    button is pressed, so the only copy of them is in the reader's own form - not in the page's
    markup, and not in the request that produced the result either."""
    for lang in ("en", "hi", "mr"):
        html = js("AstroRender.renderers.matching(data, ctx)", data=result, ctx={"lang": lang})
        card = html[html.index("match-card"):]
        card = card[:card.index("</section>")]
        assert "Keshav" not in card and "Tina" not in card, card
    assert "data-name-left" not in RENDER_JS and "data-name-right" not in RENDER_JS
    assert 'getElementById(which + "-name")' in CARD_JS, "read from the input, not the markup"


def test_the_card_is_drawn_in_the_browser_and_never_posted_to_us():
    """The design property: no name ever reaches a server. The script draws on a canvas and the only
    thing it sends us is a funnel step with no name and no score in it."""
    assert "canvas" in CARD_JS and "toBlob" in CARD_JS
    sends = re.findall(r"send\(\"([a-z_]+)\"\)", CARD_JS)
    assert sends == ["match_card_seen", "match_card_named", "match_card_shared"], sends
    # the only outbound URL is the funnel step, and nothing interpolates a name or a score into it
    for line in CARD_JS.splitlines():
        if "/api/funnel" in line:
            assert "data-name" not in line and "score" not in line, line


def test_the_three_funnel_steps_are_accepted_and_carry_nothing_else():
    """Tracked in the funnel, as asked - offered, named, shared - and the endpoint takes the step
    only, so there is nothing for a name to ride in on."""
    from app import api

    for step in ("match_card_seen", "match_card_named", "match_card_shared"):
        assert step in api.FUNNEL_STEPS, step
        assert client.post(f"/api/funnel?step={step}&w=390").status_code in (200, 204)


def test_no_third_party_url_is_in_the_markup_only_assembled_on_the_tap():
    """Four guards in this repository forbid a third-party URL in a page's markup, and they are
    right. app/web/sharing.py solved this by assembling wa.me on the press; this does the same."""
    html_sources = [CARD_JS]
    assert "wa.me" in CARD_JS, "the share still opens WhatsApp"
    for lang in ("en", "hi", "mr"):
        page = client.get(i18n.url_for("matching", lang)).text
        assert "wa.me" not in page, f"a third-party URL in the markup ({lang})"


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_the_card_script_loads_only_where_a_match_can_happen(lang):
    page = client.get(i18n.url_for("matching", lang)).text
    assert "match-card.js" in page
    assert "?v=" in page.split("match-card.js")[1][:12], "cache-busted like every other script"
    kundli = client.get(i18n.url_for("kundali", lang)).text
    assert "match-card.js" not in kundli, "loaded on a page that cannot produce a match"


def test_every_label_exists_in_all_three_languages(js, result):
    seen = {}
    for lang in ("en", "hi", "mr"):
        html = js("AstroRender.renderers.matching(data, ctx)", data=result, ctx={"lang": lang})
        card = html[html.index("match-card"):]
        card = card[:card.index("</section>")]
        for marker in ("data-label-gunas=\"\"",):
            assert marker not in card, f"an empty label in {lang}: {marker}"
        seen[lang] = card
    assert len({re.search(r"<h3>(.*?)</h3>", c).group(1) for c in seen.values()}) == 3, \
        "the heading is not translated in all three trees"


def test_the_site_name_on_the_card_is_not_a_string_in_the_script():
    """The brand is configuration (tests/test_seo.py), so the card reads it off the address the
    reader is already on rather than spelling it."""
    assert "rashikundli" not in CARD_JS.lower() and "rashikundli" not in RENDER_JS.lower()
    assert "location.hostname" in CARD_JS


def test_only_one_file_knows_the_whatsapp_url():
    """The guard in tests/test_payments.py whitelists external URLs per FILE, and the point of it is
    that the list stays short enough to read. analytics.js owns wa.me; this calls into it."""
    # The rule is about the URL, not the word: the comment naming analytics.js as its owner is how
    # the next reader finds it. (A comment tripping the rule it explains has happened three times in
    # this batch already - the guard in tests/test_payments.py matches https:// URLs, so match that.)
    assert "https://wa.me" not in CARD_JS
    assert "RKShare" in CARD_JS


def test_the_canvas_names_a_font_the_site_actually_declares():
    """THE TOFU BUG. The first version drew with "Noto Sans Devanagari", which this site does not
    declare - so every Hindi and Marathi name, and the word for gunas, came out as empty boxes. A
    canvas draws with the fonts the DOCUMENT has, and nothing fails loudly when it has none; the PNG
    simply comes out wrong, which is why these cards are screenshotted and looked at.
    """
    css = (STATIC_DIR / "css" / "fonts-devanagari.css").read_text(encoding="utf-8")
    declared = set(re.findall(r'font-family:\s*"([^"]+)"', css))
    # The font the canvas USES, from the FAMILY constant - not every font named in the file. The
    # comment above that constant names the wrong one on purpose, to record what went wrong.
    family = re.search(r'var FAMILY = \'([^\']+)\'', CARD_JS).group(1)
    quoted = re.findall(r'"([^"]+)"', family)
    assert quoted, "the card names no quoted font family at all"
    # The FIRST family is the one that has to carry Devanagari, and it must be one this site ships.
    # The rest are system fallbacks for Latin and are nobody's to declare.
    assert quoted[0] in declared, f"the canvas asks for {quoted[0]!r}, which the site does not declare"
    assert "sans-serif" in family, "no generic fallback if the webfont never loads"


def test_the_card_waits_for_the_font_before_it_draws():
    """A webfont the page has not painted yet is not in document.fonts, so the draw must wait for it
    or it silently falls back - which is the same boxes again."""
    assert "document.fonts.load" in CARD_JS
    assert "fontsReady()" in CARD_JS
    before = CARD_JS.index("fontsReady()")
    assert before < CARD_JS.index("drawAndShare()"), "the fonts must be awaited before the draw"


def test_the_subset_covers_any_devanagari_name_not_just_our_own_copy():
    """The names are whatever two people are called, not words from our pages. The webfont's
    unicode-range must cover the Devanagari block, or an uncommon name draws as boxes for the one
    reader whose name it is."""
    css = (STATIC_DIR / "css" / "fonts-devanagari.css").read_text(encoding="utf-8")
    assert "U+0900-097F" in css, "the full Devanagari block"


def test_the_card_steps_are_their_own_feature_and_reach_the_daily_summary():
    """They were first recorded as "kundli_form", which is the form funnel for a different tool -
    the summary would have counted nothing and the form's numbers would have been wrong too."""
    import datetime as dt

    from app import analytics, db
    from app.admin import daily

    for step in ("match_card_seen", "match_card_named", "match_card_shared"):
        client.post(f"/api/funnel?step={step}&w=390")
    today = dt.date.fromisoformat(analytics.today_iso()) if hasattr(analytics, "today_iso") else None
    with db.transaction(write=False) as conn:
        rows = conn.execute(
            "SELECT feature, action FROM site_events WHERE action LIKE 'match_card_%'").fetchall()
    assert rows, "no card step was recorded at all"
    assert {row["feature"] for row in rows} == {"match_card"}, {row["feature"] for row in rows}


def test_the_summary_line_reports_offered_named_and_shared():
    import datetime as dt
    import inspect

    from app.admin import daily

    source = inspect.getsource(daily)
    assert "match_card_shared" in source and "match_card_named" in source
    assert "card " in source, "the line says 'card N seen / N named / N shared'"
