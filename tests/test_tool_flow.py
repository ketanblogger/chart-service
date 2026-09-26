"""The staged tool-page flow: steps, time presets, "use my location", the caveat, and the links around them.

The flow patterns are a redesign of the four calculator pages, and almost all of the risk in them is the same
risk: a nicer-looking form that quietly makes the product less accurate or less usable.

* The steps are progressive enhancement, never a gate. Every input is in the DOM on first render, all steps
  are visible until app.js takes over, and the `<noscript>` promise - that the whole form is there and works -
  still holds. `test_every_field_is_in_the_dom_on_first_render` is the one that fails if a step is ever built
  by JavaScript instead of merely shown by it.
* The time presets are up to three hours wide and the lagna turns over about every two hours. Choosing one
  therefore has to say WHICH conclusions survive that and which do not, and it has to say it in the result,
  not only beside the button. That distinction is the whole point of the caveat, so it is asserted literally.
* "Use my location" must never send coordinates anywhere. The proof is structural: the page has no endpoint to
  send them to, and the nearest city is chosen from the list app.js already fetched.

The interactive halves (stepping, tapping a preset, a denied location) run in a real browser and are marked
`browser`, so they skip where Chromium cannot launch rather than failing.
"""

import json
import re
import time
from html import unescape as html_unescape

import pytest

from app.pdf import browser as pdf_browser
from app.web import STATIC_DIR, i18n, pages
from tests.test_web import client

TOOLS = list(i18n.TOOL_KEYS)
SINGLE = [key for key in TOOLS if pages.TOOLS[key].form == "single"]
# Every three hours, so the furthest anyone can be from the nearest is ninety minutes. The gap this list
# used to have between midnight and 6 am was six hours wide, which forced the caveat to be written for a
# three-hour error - correct for a quarter of the clock and roughly double the truth for the other three.
PRESET_TIMES = ("00:00", "03:00", "06:00", "09:00", "12:00", "15:00", "18:00", "21:00")
PRESET_KEYS = ("preset_midnight", "preset_small_hours", "preset_early", "preset_morning", "preset_noon",
               "preset_afternoon", "preset_evening", "preset_night")
# What the caveat has to distinguish, and why these items and not others. 150 random births were re-run
# across a full three-hour preset bucket; the share of charts whose answer changed:
#
#     ascendant (lagna)      76%           mahadasha lord          5.3%  (1 in 19)
#     mangal dosha verdict    9.2% (1 in 11) Moon sign              2.6%  (1 in 40)
#     janma nakshatra         5.7% (1 in 18) sade sati status       0.5%  (1 in 200)
#     mahadasha START DATE   over a year on 44%; over TWO years on none, and that is a bound rather than a
#                            sample: at 1.5 h the Moon covers at most 0.95 degrees, 0.071 of a nakshatra, so
#                            against the 20-year Venus period no boundary can move more than 1.42 years.
#
# The worst case is the honest basis: somebody who taps a preset because they do not know their birth time
# cannot know they are near the middle of the bucket. Adding the 03:00 preset roughly halved every one of
# these, which is why the copy could be softened without becoming less honest - the uncertainty really did
# shrink. Change the preset list and these numbers stop describing the product.
#
# NOTHING ON THAT LIST IS ZERO. Sade sati is the steadiest item and it still flips for about one chart in a
# hundred, because it is read from the Moon sign and the Moon sign itself moves for one in eighteen. Copy
# that called it "unaffected" shipped here and in the PDF before it was measured, so
# `test_no_copy_claims_anything_is_immune_to_the_birth_time` bans the absolute phrasing outright.
#
# DASHA DATES ARE THE TRAP. They read as safe - the lord usually holds - and the dates underneath move by a
# median of fifteen months, on the one product that promises real calendar ranges. A caveat that lists them
# as reliable is worse than no caveat, so `test_the_caveat_does_not_put_the_dasha_dates_back_on_the_safe_side`
# asserts the measured claim itself rather than the word "dasha", which appears on either side of the line.
AT_RISK = {"en": ("ascendant", "house", "mangal dosha"),
           "hi": ("लग्न", "भाव", "मंगल दोष"),
           "mr": ("लग्न", "स्थान", "मंगळ दोष")}
# The steadiest item, stated as steady rather than as immune.
SAFE_CLAIM = {"en": "steadiest", "hi": "सबसे टिकाऊ", "mr": "सर्वात स्थिर"}
STILL_MOVES = {"en": "one chart in two hundred", "hi": "दो सौ में से एक कुंडली",
               "mr": "दोनशेतल्या एका कुंडलीत"}
DASHA_MOVES = {"en": "a little under half of all charts shift by more than a year",
               "hi": "आधी से कुछ कम कुंडलियों में", "mr": "निम्म्याहून थोड्या कमी कुंडल्यांत"}
# The width the whole caveat is calibrated to. If the preset list changes, this has to change with it.
WINDOW = {"en": "ninety minutes", "hi": "डेढ़ घंटे", "mr": "दीड तास"}
# Phrases that would put something back beyond the reach of the birth time. None may appear anywhere.
ABSOLUTE = {"en": ("sade sati is unaffected", "cannot move it", "is not affected by the birth time"),
            "hi": ("साढ़ेसाती पर कोई फ़र्क़ नहीं", "साढ़ेसाती पर फ़र्क़ नहीं पड़ता", "वह हिलता नहीं"),
            "mr": ("साडेसातीवर काहीच फरक पडत नाही", "साडेसातीवर फरक पडत नाही", "तो हलत नाही")}
# Only these two may be described as holding up. Anything else on the safe side is a regression.
USUALLY_SAFE = {"en": ("Moon sign", "nakshatra"), "hi": ("चंद्र राशि", "नक्षत्र"), "mr": ("चंद्ररास", "नक्षत्र")}


def _page(key: str, lang: str) -> str:
    response = client.get(i18n.url_for(key, lang))
    assert response.status_code == 200
    return response.text


def _form(html: str) -> str:
    return html.split('<form id="tool-form"', 1)[1].split("</form>", 1)[0]


# ---------------------------------------------------------------- the form is still the whole form


@pytest.mark.parametrize("lang", i18n.LANGS)
@pytest.mark.parametrize("key", TOOLS)
def test_every_field_is_in_the_dom_on_first_render(key, lang):
    """Staging shows steps; it must never be what builds them. 4 tools x 3 languages."""
    html = _page(key, lang)
    form = _form(html)
    people = ("boy", "girl") if pages.TOOLS[key].form == "pair" else ("self",)
    for person in people:
        for field in ("name", "date", "time", "city"):
            assert f'id="{person}-{field}"' in form, (key, lang, person, field)
            assert f'name="{field}"' in form
    # the wiring tests/test_web.py and the renderers depend on
    for attribute in ('id="tool-form"', 'data-endpoint=', 'data-renderer=', 'data-lang=', 'data-form='):
        assert attribute in html, (key, lang, attribute)
    assert "<noscript>" in html


@pytest.mark.parametrize("lang", i18n.LANGS)
@pytest.mark.parametrize("key", TOOLS)
def test_no_step_is_hidden_before_javascript_runs(key, lang):
    """Server-rendered, every step visible: that is the no-JavaScript path, and it is also what a crawler
    reads. app.js hides the inactive ones itself."""
    steps = re.findall(r"<fieldset[^>]*\sdata-step=\"\d+\"[^>]*>", _form(_page(key, lang)))
    expected = 2 if pages.TOOLS[key].form == "pair" else 3
    assert len(steps) == expected, (key, lang, steps)
    for step in steps:
        assert "hidden" not in step, (key, lang, step)
    assert 'data-step-nav' in _form(_page(key, lang))


@pytest.mark.parametrize("key", TOOLS)
def test_matching_groups_by_person_and_the_rest_by_input(key):
    """Six steps to compare two charts would be worse than the single form it replaces."""
    steps = re.findall(r'data-step="(\d+)"', _form(_page(key, "en")))
    assert steps == ["1", "2"] if key == "matching" else steps == ["1", "2", "3"]


# ---------------------------------------------------------------- the presets, and what they cost


@pytest.mark.parametrize("lang", i18n.LANGS)
@pytest.mark.parametrize("key", TOOLS)
def test_seven_time_presets_per_form_in_the_page_language(key, lang):
    form = _form(_page(key, lang))
    ui = pages.ui(lang)
    people = 2 if pages.TOOLS[key].form == "pair" else 1
    values = re.findall(r'data-preset="([\d:]+)"', form)
    assert values == list(PRESET_TIMES) * people, (key, lang, values)
    for preset_key in PRESET_KEYS:
        assert ui[preset_key] and ui[preset_key] in form, (key, lang, preset_key)
    assert ui["time_unsure"] in form and ui["time_approx_note"] in form


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_the_preset_labels_are_written_for_their_own_language(lang):
    ui = pages.ui(lang)
    labels = [ui[key] for key in PRESET_KEYS]
    assert len(set(labels)) == len(PRESET_KEYS)
    if lang != "en":
        for label in labels:
            assert re.search(r"[ऀ-ॿ]", label), (lang, label)
    english = pages.ui("en")
    if lang != "en":
        assert not set(labels) & {english[key] for key in PRESET_KEYS}, "labels look translated, not written"


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_an_approximate_time_produces_the_caveat_that_says_what_survives_it(js, lang):
    """The one that matters. A preset moves the ascendant on effectively every chart, so the result has to
    name what holds up and what does not - and be right about which is which."""
    data = client.post("/api/chart", json={"date": "1984-02-19", "time": "09:05", "city": "Pune"}).json()

    exact = js("AstroRender.renderers.kundali(data, ctx)", data=data, ctx={"lang": lang})
    approx = js("AstroRender.renderers.kundali(data, ctx)", data=data, ctx={"lang": lang, "approxTime": True})
    assert 'class="block accuracy"' in approx, "no caveat for an approximate time"
    note = approx.split('class="block accuracy"', 1)[1].split("</section>", 1)[0]
    assert SAFE_CLAIM[lang] in note, f"{lang}: the caveat no longer names sade sati as the steadiest item"
    assert STILL_MOVES[lang] in note, f"{lang}: the caveat does not admit sade sati can still flip"
    assert WINDOW[lang] in note, f"{lang}: the caveat does not name the ninety-minute window it is measured on"
    for term in USUALLY_SAFE[lang]:
        assert term in note, f"{lang}: the caveat does not mention {term}"
    for term in AT_RISK[lang]:
        assert term in note, f"{lang}: the caveat does not warn that {term} may change"
    assert len(approx) > len(exact), "the caveat added nothing"


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_the_caveat_does_not_put_the_dasha_dates_back_on_the_safe_side(js, lang):
    """Dasha dates move by a median of fifteen months across a preset bucket, and more than half of all
    charts shift by over a year. They were on the safe list once; this is what stops them going back."""
    data = client.post("/api/chart", json={"date": "1984-02-19", "time": "09:05", "city": "Pune"}).json()
    note = js("AstroRender.renderers.kundali(data, ctx)", data=data,
              ctx={"lang": lang, "approxTime": True}).split('class="block accuracy"', 1)[1]
    assert DASHA_MOVES[lang] in note, (
        f"{lang}: the caveat no longer says the dasha dates move by more than a year")


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_the_preset_note_beside_the_buttons_says_the_same_thing(lang):
    """The reader should learn the cost before tapping, not only afterwards in the result. This note is the
    short form - it says "everything counted from it" where the result names the house placements - so what
    it must carry is the three items a reader would otherwise assume are safe."""
    note = pages.ui(lang)["time_approx_note"]
    dasha = {"en": "dasha dates", "hi": "दशा की तारीख़ें", "mr": "दशांच्या तारखा"}[lang]
    assert dasha in note, f"{lang}: the short note does not warn about the dasha dates"
    assert WINDOW[lang] in note, f"{lang}: the short note does not name the ninety-minute window"
    for term in ({"en": ("lagna", "mangal dosha"), "hi": ("लग्न", "मंगल दोष"),
                  "mr": ("लग्न", "मंगळ दोष")}[lang]):
        assert term in note, (lang, term)
    assert {"en": "Sade sati", "hi": "साढ़ेसाती", "mr": "साडेसाती"}[lang] in note


def test_the_approximate_time_note_comes_first_in_the_caveat_block(js):
    """Same order as the PDF: a three-hour bucket moves the lagna on every chart, where a birthplace rarely
    does, so it is read first. A birth that trips the engine's own two caveats as well."""
    flagged = client.post("/api/chart", json={"date": "1889-11-14", "time": "23:30",
                                              "lat": 25.4358, "lon": 81.8463,
                                              "timezone": "Asia/Kolkata"}).json()
    assert flagged["accuracy"]["lagna_boundary"]["sensitive"] and flagged["accuracy"]["clock"]["non_standard"]
    note = js("AstroRender.renderers.kundali(data, ctx)", data=flagged,
              ctx={"lang": "en", "approxTime": True}).split('class="block accuracy"', 1)[1]
    paragraphs = re.findall(r"<p>(.*?)</p>", note, flags=re.S)
    assert len(paragraphs) == 3, "expected the approximate-time note plus the engine's two"
    assert SAFE_CLAIM["en"] in paragraphs[0], "the engine's notes are being read before the input's"


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_no_copy_claims_anything_is_immune_to_the_birth_time(lang):
    """The error that shipped twice, on the page and in the PDF: calling sade sati unaffected. It is the
    steadiest thing measured and it still flips for about one chart in a hundred, because it is read from a
    Moon sign that moves for one in eighteen. This bans the absolute phrasing everywhere it could come back -
    the renderer's labels, every UI string and every page's copy."""
    haystacks = [(STATIC_DIR / "js" / "render.js").read_text(encoding="utf-8")]
    module = pages.content(lang)
    haystacks += list(module.UI.values())
    for copy in module.PAGES.values():
        haystacks += [copy.intro, copy.meta_description]
        haystacks += [block if isinstance(block, str) else " ".join(block)
                      for section in copy.sections for block in section.blocks]
        haystacks += [question + " " + answer for question, answer in copy.faqs]
        haystacks += [str(value) for value in copy.extra.values()]
    for phrase in ABSOLUTE[lang]:
        for text in haystacks:
            assert phrase.lower() not in str(text).lower(), f"{lang}: absolute claim {phrase!r} in {str(text)[:90]!r}"


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_the_birth_time_faqs_agree_with_the_caveat(lang):
    """A reader who asks "do I need the exact time?" gets the FAQ, not the caveat, so the FAQ is the worse
    place to be wrong. Both the homepage's answer and the chart page's own must put the dasha dates on the
    side that needs the real time."""
    dasha = {"en": "dasha dates", "hi": "दशा की तारीख़ें", "mr": "दशांच्या तारखा"}[lang]
    asked = [answer for page in ("home", "kundali") for question, answer in pages.get(page, lang).faqs
             if any(word in question for word in {"en": ("birth time",), "hi": ("जन्म समय",),
                                                  "mr": ("जन्मवेळ",)}[lang])]
    assert len(asked) == 2, f"{lang}: expected the homepage and chart-page birth-time questions, got {len(asked)}"
    for answer in asked:
        assert dasha in answer, f"{lang}: a birth-time FAQ never mentions the dasha dates: {answer[:80]!r}"
        assert DASHA_MOVES[lang] in answer or {"en": "more than a year", "hi": "साल भर से ज़्यादा",
                                               "mr": "वर्षभरापेक्षा जास्त"}[lang] in answer, answer[:120]


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_the_caveat_is_calibrated_to_the_gaps_the_presets_actually_leave(lang):
    """The warning and the preset list have to move together. Presets every three hours mean a worst case of
    ninety minutes; a list with a wider gap somewhere would make the copy an understatement for whoever falls
    in it, which is how this started - a six-hour hole between midnight and 6 am."""
    minutes = sorted(int(h) * 60 + int(m) for h, m in (value.split(":") for value in PRESET_TIMES))
    gaps = [b - a for a, b in zip(minutes, minutes[1:])] + [minutes[0] + 24 * 60 - minutes[-1]]
    worst = max(gaps) / 2
    assert worst == 90, f"the worst distance to a preset is now {worst:g} minutes, so the copy is wrong"
    for text in (pages.ui(lang)["time_approx_note"], ):
        assert WINDOW[lang] in text, f"{lang}: the note does not state the window it is measured on"


def test_the_caveat_is_a_statement_about_the_input_not_an_engine_finding():
    """chart.accuracy is the engine's verdict about a chart; an approximate time is something only the caller
    knows. Keeping them apart is why the flag rides in ctx and never gets written into the response."""
    data = client.post("/api/chart", json={"date": "1984-02-19", "time": "09:00", "city": "Pune"}).json()
    assert "approximate_time" not in data and "approximate_time" not in data["accuracy"]
    source = (STATIC_DIR / "js" / "render.js").read_text(encoding="utf-8")
    signature = source.split("function accuracyHtml(", 1)[1].split(")", 1)[0]
    assert signature.split(",")[-1].strip() == "approx", "the input-side note is no longer a separate argument"


@pytest.mark.parametrize("lang", i18n.LANGS)
@pytest.mark.parametrize("renderer", ["mangalDosha", "sadeSati"])
def test_the_caveat_reaches_the_tools_whose_verdict_it_changes(js, lang, renderer):
    """Mangal dosha is counted from the lagna, so an approximate time can change the verdict outright. The
    caveat has to appear there too, in the same block a chart uses - not a second caveat surface."""
    endpoint = "/api/mangal-dosha" if renderer == "mangalDosha" else "/api/sade-sati"
    data = client.post(endpoint, json={"date": "1984-02-19", "time": "09:05", "city": "Pune"}).json()
    html = js(f"AstroRender.renderers.{renderer}(data, ctx)", data=data, ctx={"lang": lang, "approxTime": True})
    assert html.count('class="block accuracy"') == 1, (renderer, lang)
    plain = js(f"AstroRender.renderers.{renderer}(data, ctx)", data=data, ctx={"lang": lang})
    assert "accuracy" not in plain, "a caveat with no reason to be there"


def test_the_free_pdf_carries_the_same_flag_rather_than_a_second_mechanism():
    js_source = (STATIC_DIR / "js" / "app.js").read_text(encoding="utf-8")
    assert "approximate_time" in js_source, "the PDF request does not carry the approximate-time flag"
    assert js_source.count('data-approx-time') >= 2, "the flag is not set from the presets and read on submit"


# ---------------------------------------------------------------- location, links, disclaimer


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_the_location_control_is_offered_only_where_it_could_be_true(lang):
    """Your current position is your birth place only if you never moved, so it is a single-person
    convenience and never the dominant control. On a pair form it would be nonsense twice over."""
    for key in SINGLE:
        form = _form(_page(key, lang))
        assert form.count("data-locate-go") == 1, (key, lang)
        assert pages.ui(lang)["location_hint"] in form
    assert "data-locate-go" not in _form(_page("matching", lang))


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_every_location_outcome_has_wording_before_it_is_needed(lang):
    """Permission denied, unavailable and timeout are ordinary outcomes, not errors: each one has to leave
    the reader able to type the city. The strings ship in the markup so the failure path needs no fetch."""
    form = _form(_page(SINGLE[0], lang))
    status = form.split("data-locate-status", 1)[1].split(">", 1)[0]
    ui = pages.ui(lang)
    for attribute, key in (("data-searching", "location_searching"), ("data-denied", "location_denied"),
                           ("data-unavailable", "location_unavailable"), ("data-found", "location_found")):
        assert attribute in status, (lang, attribute)
        assert ui[key] in form, (lang, key)


def test_the_coordinates_have_nowhere_to_go():
    """Structural, not a promise: the only fetches on a tool page are the three allowlisted ones, so a
    latitude read in the browser cannot be sent anywhere even by accident."""
    js_source = (STATIC_DIR / "js" / "app.js").read_text(encoding="utf-8")
    assert set(re.findall(r"fetch\(([^,)]+)", js_source)) == {"endpoint", '"/api/cities"', '"/api/chart/pdf"'}
    body = js_source.split("navigator.geolocation.getCurrentPosition", 1)[1].split("}, {", 1)[0]
    assert "fetch(" not in body and "latitude" in body and "input.value = city.name" in body


CONTEXTUAL = {"kundali": ("matching", "consultation"), "matching": ("kundali",),
              "mangal-dosha": ("kundali", "sade-sati"), "sade-sati": ("mangal-dosha", "consultation")}


@pytest.mark.parametrize("lang", i18n.LANGS)
@pytest.mark.parametrize("key,targets", list(CONTEXTUAL.items()))
def test_the_cross_tool_links_are_in_the_prose(key, targets, lang):
    """In a sentence that gives a reason to follow them, not only in the nav and the "more tools" list."""
    html = _page(key, lang)
    article = html.split('<article class="wrap content"', 1)[1]
    prose = "".join(re.findall(r"<p>(.*?)</p>", article, flags=re.S))
    for target in targets:
        href = i18n.url_for(target, lang)
        assert f'href="{href}"' in prose, (key, lang, target)


@pytest.mark.parametrize("lang", i18n.LANGS)
@pytest.mark.parametrize("key", TOOLS)
def test_the_disclaimer_sits_with_the_offer(key, lang):
    html = _page(key, lang)
    cta = html.split('<aside class="cta"', 1)[1].split("</aside>", 1)[0]
    disclaimer = pages.get(key, lang).extra["cta_disclaimer"]
    shown = re.search(r'class="cta__disclaimer">(.*?)</p>', cta, flags=re.S)
    assert shown, (key, lang, "no disclaimer inside the CTA")
    # Jinja escapes the apostrophe in "Saturn's", so compare the unescaped text.
    assert html_unescape(shown.group(1)).strip() == disclaimer.strip(), (key, lang)
    # it shares a section with copy about an AI-written report, so the engine is named in it
    assert "Swiss Ephemeris" in disclaimer or "स्विस एफेमेरिस" in disclaimer


# ---------------------------------------------------------------- the interactive halves


@pytest.fixture(scope="module")
def chromium():
    ok, reason = pdf_browser.chromium_available()
    if not ok:
        pytest.skip(f"headless Chromium cannot launch here: {reason}")


@pytest.fixture(scope="module")
def live_site(chromium):
    """The real app on a free port, so the browser drives the same page a visitor gets."""
    import socket
    import threading
    import time

    import uvicorn

    from app.main import app

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), 0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True


@pytest.mark.browser
def test_the_form_walks_forward_one_step_at_a_time(live_site):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as play:
        browser = play.chromium.launch(**pdf_browser.launch_options())
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.goto(live_site + i18n.url_for("kundali", "en"), wait_until="networkidle")

        steps = page.locator("#tool-form [data-step]")
        assert steps.count() == 3
        assert steps.nth(0).is_visible() and not steps.nth(1).is_visible()
        assert steps.nth(0).get_attribute("aria-current") == "step"
        assert not page.locator("#submit-btn").is_visible(), "submit belongs on the last step"

        page.click("[data-step-next]")  # empty date: the step must hold
        assert steps.nth(0).is_visible(), "an invalid step let the reader past"
        assert page.locator("#self-date-error").is_visible()

        page.fill("#self-date", "1984-02-19")
        page.click("[data-step-next]")
        assert steps.nth(1).is_visible() and not steps.nth(0).is_visible()
        assert page.evaluate("document.activeElement.id") == "self-time", "focus did not follow the step"

        page.click("[data-step-back]")
        assert steps.nth(0).is_visible(), "back does not go back"
        browser.close()


@pytest.mark.browser
def test_a_preset_fills_the_time_and_the_result_carries_the_caveat(live_site):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as play:
        browser = play.chromium.launch(**pdf_browser.launch_options())
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.goto(live_site + i18n.url_for("kundali", "en"), wait_until="networkidle")

        page.fill("#self-date", "1984-02-19")
        page.click("[data-step-next]")
        page.click("[data-preset-toggle]")
        page.click('[data-preset="09:00"]')
        assert page.input_value("#self-time") == "09:00"
        assert page.get_attribute("#tool-form", "data-approx-time") == "1"

        page.click("[data-step-next]")
        page.fill("#self-city", "Pune")
        page.wait_for_timeout(400)
        page.keyboard.press("ArrowDown")
        page.keyboard.press("Enter")
        page.click("#submit-btn")
        page.wait_for_selector("#result:not([hidden])", timeout=20000)

        caveat = page.locator("#result-body .accuracy")
        assert caveat.count() == 1, "the approximate time produced no caveat"
        text = caveat.inner_text()
        assert SAFE_CLAIM["en"] in text and STILL_MOVES["en"] in text and DASHA_MOVES["en"] in text
        for term in AT_RISK["en"] + USUALLY_SAFE["en"]:
            assert term in text, term
        browser.close()


@pytest.mark.browser
def test_a_denied_location_leaves_the_reader_typing(live_site):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as play:
        browser = play.chromium.launch(**pdf_browser.launch_options())
        context = browser.new_context(viewport={"width": 390, "height": 844})
        context.add_init_script("""
            Object.defineProperty(navigator, 'geolocation', { configurable: true, value: {
              getCurrentPosition: function (ok, fail) { fail({ code: 1, message: "denied" }); }
            }});
        """)
        page = context.new_page()
        page.goto(live_site + i18n.url_for("kundali", "en"), wait_until="networkidle")
        page.fill("#self-date", "1984-02-19")
        page.click("[data-step-next]")
        page.fill("#self-time", "09:05")
        page.click("[data-step-next]")
        page.keyboard.press("Escape")  # focus lands in the city combobox, whose list covers the control
        page.locator("h2#form-heading").click()

        assert page.locator("[data-locate]").is_visible()
        page.click("[data-locate-go]")
        status = page.locator("[data-locate-status]")
        page.wait_for_selector("[data-locate-status]:not([hidden])", timeout=5000)
        assert pages.ui("en")["location_denied"] in status.inner_text()
        assert page.locator("#self-city").is_editable(), "the city field must still be typeable"
        assert page.locator("#submit-btn").is_visible()
        context.close()
        browser.close()


@pytest.mark.browser
def test_a_granted_location_sends_only_a_city_name(live_site):
    """The privacy property, observed rather than asserted: every request the page makes is captured."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as play:
        browser = play.chromium.launch(**pdf_browser.launch_options())
        context = browser.new_context(viewport={"width": 390, "height": 844})
        context.add_init_script("""
            Object.defineProperty(navigator, 'geolocation', { configurable: true, value: {
              getCurrentPosition: function (ok) {
                ok({ coords: { latitude: 18.5204, longitude: 73.8567 } });   // Pune
              }
            }});
        """)
        page = context.new_page()
        sent = []
        page.on("request", lambda request: sent.append((request.url, request.post_data or "")))
        page.goto(live_site + i18n.url_for("kundali", "en"), wait_until="networkidle")
        page.fill("#self-date", "1984-02-19")
        page.click("[data-step-next]")
        page.fill("#self-time", "09:05")
        page.click("[data-step-next]")
        page.keyboard.press("Escape")
        page.locator("h2#form-heading").click()
        page.click("[data-locate-go]")
        # The production CSP forbids 'unsafe-eval', so a string predicate cannot be used to wait here.
        for _ in range(40):
            if page.input_value("#self-city"):
                break
            page.wait_for_timeout(200)

        assert page.input_value("#self-city") == "Pune"
        for url, body in sent:
            assert "18.52" not in url and "73.85" not in url, url
            assert "18.52" not in body and "73.85" not in body, body
            assert "latitude" not in body and "lat=" not in url
        context.close()
        browser.close()


@pytest.fixture(scope="module")
def js():
    mini_racer = pytest.importorskip("py_mini_racer")
    context = mini_racer.MiniRacer()
    context.eval((STATIC_DIR / "js" / "render.js").read_text(encoding="utf-8"))

    def call(expression: str, **variables):
        names = ", ".join(variables)
        args = ", ".join(json.dumps(value, ensure_ascii=False) for value in variables.values())
        return json.loads(context.eval(f"JSON.stringify((function({names}) {{ return {expression}; }})({args}))"))

    return call


# ---------------------------------------------------------------- brand tagline and the philosophy line


CHROME_PAGES = (("home", {}), ("kundali", {}), ("consultation", {}), ("rashifal-rashi", {"rashi": "tula"}))


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_the_poetic_brand_line_is_a_home_hero_flourish_and_never_the_chrome(lang):
    """Two different lines that a glance confuses. `brand_tagline` is identity - a poem, not a claim.
    `tagline` is the claim that the calculation engine is named in the chrome of every page, which the trust
    sweep asserts across all 246 URLs.

    They used to be stacked one above the other in the header on every page, and two subtitles under one
    wordmark read as neither: the poem stole the weight the trust line needs and cost the header a row on a
    phone. So the poem is a flourish the visitor meets once, in the home hero, and the chrome carries the
    trust line alone. This asserts the split in both directions - the poem is in the hero and in NO page's
    header, the trust line is in every page's header - because "removed from the header" is the kind of
    change a later edit reinstates for symmetry.
    """
    ui = pages.ui(lang)
    assert ui["brand_tagline"] != ui["tagline"]
    assert "Swiss Ephemeris" in ui["tagline"] or "स्विस एफेमेरिस" in ui["tagline"]

    for key, params in CHROME_PAGES:
        html = client.get(i18n.url_for(key, lang, **params)).text
        header = html.split("</header>", 1)[0]
        assert ui["tagline"] in header, f"{lang}/{key}: the engine trust line has left the header"
        assert 'class="site-tagline"' in header, f"{lang}/{key}: the trust line lost its own element"
        assert ui["brand_tagline"] not in header, f"{lang}/{key}: the poetic line is back in the chrome"
        assert "brand-tagline" not in header, f"{lang}/{key}: the header tagline element is back"
        if key != "home":
            assert ui["brand_tagline"] not in html, (
                f"{lang}/{key}: the flourish is meant to be met once, on the home page")

    home = client.get(i18n.url_for("home", lang)).text
    hero = home.split('class="hero"', 1)[1].split("</section>", 1)[0]
    assert ui["brand_tagline"] in hero, f"{lang}: no brand tagline in the home hero"
    assert 'class="hero__tagline"' in hero, f"{lang}: the hero flourish lost its own element"


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_the_gita_line_is_quoted_rather_than_paraphrased(lang):
    """Gita 2.47 is about action and its fruits and says nothing about astrology. Printing our reading of it
    straight after the Sanskrit would present it as a translation, which would be false and checkable - the
    same thing the policy pages already refuse to do with the Bhrigu Samhita. So the verse carries its own
    translation and our application is marked as ours, in a separate string."""
    copy = pages.get("consultation", lang)
    verse, gloss = copy.extra["philosophy_verse"], copy.extra["philosophy_gloss"]
    assert "कर्मण्येवाधिकारस्ते" in verse
    # the verse's own translation is about action, and says nothing about astrology
    for word in {"en": ("astrology", "chart", "horoscope"), "hi": ("ज्योतिष", "कुंडली"),
                 "mr": ("ज्योतिष", "कुंडली")}[lang]:
        assert word not in verse, f"{lang}: the verse's translation has been made to mention {word}"
    for claim in {"en": ("right to action",), "hi": ("अधिकार", "कर्म"), "mr": ("अधिकार", "कर्म")}[lang]:
        assert claim in verse, f"{lang}: the verse is quoted without saying what it means"
    # and our reading is marked as ours
    assert any(marker in gloss for marker in {"en": ("We read it",), "hi": ("हम इसे",), "mr": ("आम्ही ते",)}[lang]), \
        f"{lang}: the gloss reads as a translation rather than as our application"

    html = client.get(i18n.url_for("consultation", lang)).text
    shown = re.search(r'class="chat__philosophy">(.*?)</p>', html, flags=re.S)
    assert shown, f"{lang}: the philosophy line is not on the consultation page"
    rendered = re.sub(r"\s+", " ", html_unescape(re.sub(r"<[^>]+>", "", shown.group(1)))).strip()
    assert verse in rendered and gloss in rendered, rendered[:120]
    assert html.index('class="chat__trust"') < html.index('class="chat__philosophy"'), \
        "the philosophy line should close the consultation, not open it"


# ---------------------------------------------------------------- the date, read back in words


@pytest.mark.parametrize("lang", i18n.LANGS)
@pytest.mark.parametrize("key", TOOLS)
def test_every_date_field_reads_its_value_back(key, lang):
    """`<input type="date">` is drawn in the BROWSER's locale, so a Chrome set to en-US shows mm/dd/yyyy to a
    reader in India and `lang="en-IN"` does not reliably change it. The echo is the part that catches the
    resulting mis-entry, so it ships with the field rather than being a nicety."""
    form = _form(_page(key, lang))
    people = ("boy", "girl") if pages.TOOLS[key].form == "pair" else ("self",)
    for person in people:
        echo = re.search(rf'<p class="field-echo" id="{person}-date-echo"[^>]*>', form)
        assert echo, (key, lang, person)
        assert "data-date-echo" in echo.group(0) and 'role="status"' in echo.group(0)
        assert pages.ui(lang)["echo_prefix"] in echo.group(0), f"{lang}: the echo has no label"
        # and the field points at it, so a screen reader hears the read-back with the field
        field = re.search(rf'<input type="date" id="{person}-date"[^>]*>', form)
        assert f"{person}-date-echo" in field.group(0), "the echo is not announced with the field"


@pytest.mark.browser
@pytest.mark.parametrize("lang", i18n.LANGS)
def test_the_date_echo_says_the_date_in_words_in_the_page_language(live_site, lang):
    """The whole point: 2026-03-04 must read back as a month a person recognises, so a day/month swap is
    visible before it becomes a chart."""
    from playwright.sync_api import sync_playwright

    month = {"en": "Mar", "hi": "मार्च", "mr": "मार्च"}[lang]
    with sync_playwright() as play:
        browser = play.chromium.launch(**pdf_browser.launch_options())
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.goto(live_site + i18n.url_for("kundali", lang), wait_until="networkidle")
        assert not page.locator("[data-date-echo]").is_visible(), "an empty field echoes nothing"
        page.fill("#self-date", "1988-03-04")   # 04/03: a day-first and a month-first reading differ
        page.wait_for_selector("[data-date-echo]:not([hidden])", timeout=4000)
        shown = page.locator("[data-date-echo]").inner_text().replace(" ", " ")
        browser.close()
    assert month in shown and "4" in shown and "1988" in shown, shown
    assert pages.ui(lang)["echo_prefix"] in shown


@pytest.mark.parametrize("lang", i18n.LANGS)
@pytest.mark.parametrize("key", TOOLS)
def test_every_time_field_reads_its_value_back(key, lang):
    """The time field ships the same read-back as the date field, and for a worse failure. `<input
    type="time">` is drawn in the BROWSER's locale too - it may offer AM/PM, it may be a 24-hour spinner -
    and a birth time taken as morning when the visitor meant evening moves the lagna by half the zodiac.
    Every number computed after that is consistent with itself and wrong, so this echo is the last place
    the mistake can be seen by anyone."""
    form = _form(_page(key, lang))
    people = ("boy", "girl") if pages.TOOLS[key].form == "pair" else ("self",)
    for person in people:
        echo = re.search(rf'<p class="field-echo" id="{person}-time-echo"[^>]*>', form)
        assert echo, (key, lang, person)
        assert "data-time-echo" in echo.group(0) and 'role="status"' in echo.group(0)
        assert pages.ui(lang)["echo_prefix"] in echo.group(0), f"{lang}: the echo has no label"
        field = re.search(rf'<input type="time" id="{person}-time"[^>]*>', form)
        assert f"{person}-time-echo" in field.group(0), "the echo is not announced with the field"


# What each tree must say about 19:30 and about 07:30, and the point is that the two differ. "19:30" is a
# correct rendering of half past seven at night and a useless one here, because the reader who typed it by
# mistake reads it back exactly as they misread the clock.
#
# Every boundary is pinned in tests/test_render_i18n.py; this only needs the two values to differ.
LATE = {"en": ("7:30", "PM"), "hi": ("7:30", "\u0936\u093e\u092e"), "mr": ("7:30", "\u0938\u0902\u0927\u094d\u092f\u093e\u0915\u093e\u0933\u0940")}
EARLY = {"en": ("7:30", "AM"), "hi": ("7:30", "\u0938\u0941\u092c\u0939"), "mr": ("7:30", "\u0938\u0915\u093e\u0933\u0940")}


@pytest.mark.browser
@pytest.mark.parametrize("lang", i18n.LANGS)
def test_the_time_echo_tells_morning_from_evening_in_every_tree(live_site, lang):
    """The one that matters. 07:30 and 19:30 are the pair this exists to separate, so both are entered and
    the echo has to say something DIFFERENT about each - and say it in a register the reader of that tree
    actually thinks in. Hindi and Marathi used to get a bare 24-hour clock here on the grounds that there is
    no AM/PM to translate; the words those languages use for the part of the day are the translation."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as play:
        browser = play.chromium.launch(**pdf_browser.launch_options())
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.goto(live_site + i18n.url_for("kundali", lang), wait_until="networkidle")
        assert not page.locator("[data-time-echo]").is_visible(), "an empty field echoes nothing"
        # The time lives on step 2 of the staged form, so the date has to be answered to reach it.
        page.fill("#self-date", "1984-02-19")
        page.click("[data-step-next]")
        page.wait_for_selector("#self-time", state="visible", timeout=4000)
        page.fill("#self-time", "19:30")
        page.wait_for_selector("[data-time-echo]:not([hidden])", timeout=4000)
        evening = page.locator("[data-time-echo]").inner_text().replace("\u00a0", " ")
        page.fill("#self-time", "07:30")
        page.wait_for_timeout(200)
        morning = page.locator("[data-time-echo]").inner_text().replace("\u00a0", " ")

        # And the same words on the RESULT, from the same formatter. The echo under the field is only half
        # the promise: a visitor who does not look down at it still meets the birth line on the result, and
        # if those two ever disagree about the same value the echo is worse than useless.
        page.fill("#self-time", "19:30")
        page.click("[data-step-next]")
        page.fill("#self-city", "Pune")
        page.wait_for_timeout(400)
        page.keyboard.press("ArrowDown")
        page.keyboard.press("Enter")
        page.click("#submit-btn")
        page.wait_for_selector("#result:not([hidden])", timeout=30000)
        page.wait_for_selector(".birth-line", timeout=30000)
        birth_line = page.locator(".birth-line").inner_text().replace("\u00a0", " ")
        browser.close()

    clock, late_word = LATE[lang]
    _clock, early_word = EARLY[lang]
    assert pages.ui(lang)["echo_prefix"] in evening, evening
    assert clock in evening, f"{lang}: the evening echo does not say the clock time: {evening!r}"
    assert late_word in evening, f"{lang}: 19:30 echoes as {evening!r} - nothing says what part of the day it is"
    assert early_word in morning, f"{lang}: 07:30 echoes as {morning!r} - nothing says it is the morning"
    assert evening != morning, (
        f"{lang}: 07:30 and 19:30 echo identically as {evening!r}. That is the entire failure this echo "
        "exists to prevent: the reader who typed the wrong one reads back their own mistake.")
    # ONE FORMATTER, asserted as one string rather than as "both mention the evening". The echo strips its
    # own label, so what is left is exactly what fmtTime returned for 19:30 - and that exact run of
    # characters has to appear in the birth line. A field echo and a result echo that can disagree is worse
    # than no field echo at all, because the customer checks the first and buys on the second.
    formatted = evening.replace(pages.ui(lang)["echo_prefix"], "").strip()
    assert formatted, f"{lang}: the echo was only its label: {evening!r}"
    assert late_word in formatted and clock in formatted, f"{lang}: unexpected echo body {formatted!r}"
    assert formatted in birth_line, (
        f"{lang}: the field formatted 19:30 as {formatted!r} and the result's birth line says "
        f"{birth_line!r}. Both are meant to be the same call to the same exported function.")


# ---------------------------------------------------------------- state -> tone, every state, every tree
# This replaces two tests, and the reason one of them had to go is the finding worth keeping.
#
# `test_a_caution_chip_never_appears_without_the_sentence_that_explains_it` iterated the cards and skipped
# any that were not `warn`. Once verdict() gained its refusal - downgrading a warn with no note to `info` -
# that test could no longer fail: a missing note produces an `info` card, the loop skips it, and the run is
# green. A GUARD MADE AN EXISTING ASSERTION TRUE BY CONSTRUCTION. Nothing at the call site looked wrong,
# the guard was correct, the test was correct, and the alarm was gone. That is the third time in one
# afternoon a correct fix rendered a correct test unfalsifiable, and it is the hardest of the vacuous
# classes to see, because there is no bad line to find - the defect is in the relationship between two
# files that do not mention each other.
#
# The other test asserted only that a cancelled dosha is NOT warn, which passes for a cancelled dosha
# rendered as anything at all, including the caution tone's opposite by accident.
#
# So the claim is now the whole mapping, in both directions: each state renders with EXACTLY its own tone.
# That is falsifiable by any tone regression, it is true of nothing by construction, and it says what the
# two tests between them were reaching for.


def _mangal(state):
    def build():
        data = _chart()
        data["mangal_dosha"].update(state)
        return data
    return build


def _sade_sati(state):
    """The five rows set their flags directly, and that is the right instrument for THIS claim.

    The subject here is the MAPPING from state to tone, and three of the five states cannot occur together
    in any one real chart, so a real-payload approach could not reach them deterministically. The engine
    path is covered separately and deliberately: test_a_real_active_mangal_dosha_reaches_the_page_as_a_caution
    and test_a_real_active_sade_sati_reaches_the_page_as_a_caution render payloads the engine actually
    produces. The table pins the mapping; that pair pins that real data reaches it. Searching for a real
    birth five more times here would cost a hundred engine calls and add no claim either of them makes."""
    def build():
        data = _chart()
        data["sade_sati"].update(state)
        return data
    return build


# (label key, how to build a payload in that state, the tone it must render with)
TONE_TABLE = (
    ("not-present", "sumMangal", _mangal({"present": False}), "ok"),
    # `present` is true in THIS row and the next, and the field that separates them is a different one.
    # Reading the first without the second is the mistake that paints a chart which is fine in caution
    # colours - cancellation_applies exists precisely because the dosha does not bite.
    ("cancelled", "sumMangal", _mangal({"present": True, "cancellation_applies": True}), "info"),
    ("active", "sumMangal", _mangal({"present": True, "cancellation_applies": False}), "warn"),
    ("not-running", "sumSadeSati", _sade_sati({"active": False}), "ok"),
    # `phase` is set too because it is what the chip prints; the NOTE comes from the cycle, which the
    # fixture chart carries for real (its "next" cycle has both dates), so the warn tone is not being
    # propped up by an invented note.
    ("running", "sumSadeSati", _sade_sati({"active": True, "phase": "peak"}), "warn"),
)


@pytest.mark.parametrize("lang", i18n.LANGS)
@pytest.mark.parametrize("state, label_key, build, expected", TONE_TABLE, ids=[row[0] for row in TONE_TABLE])
def test_every_verdict_state_renders_with_exactly_its_own_tone(js, lang, state, label_key, build, expected):
    """Exactly, not "not warn". An assertion that a state avoids one tone passes on every other tone there
    is, including by accident - which is how the cancelled case was covered before."""
    data = build()
    summary = js("AstroRender.renderers.kundali(data, ctx)", data=data, ctx={"lang": lang}) \
        .split('class="facts result-summary"', 1)[1].split("</dl>", 1)[0]
    card = verdict_card(summary, lang, label_key)
    tone = card.split('"', 1)[0]
    assert tone == expected, (
        f"{lang}: {label_key} in the {state!r} state renders as {tone!r}, expected {expected!r}")
    assert f"badge--{expected}" in card, f"{lang}: the card tone and its chip tone disagree: {card[:120]!r}"


# ---------------------------------------------------------------- fast year selection
# A 1950s birth is a long crawl backwards through a month-at-a-time picker. The jump exists to skip that,
# and everything asserted here is about it NOT becoming a second way to end up with the wrong date: a chart
# for the wrong year is still a valid chart, and nothing downstream of this form can tell.


@pytest.mark.parametrize("lang", i18n.LANGS)
@pytest.mark.parametrize("key", TOOLS)
def test_the_year_jump_ships_no_options_in_the_document(key, lang):
    """It is an accelerator, so it costs nothing to a reader who never uses it. A birth-year list is ~226
    options; shipped in the markup that is about 7KB per field, two of them on the matching pages, on all
    246 pages. The slot carries a label and nothing else, and app.js fills it."""
    form = _form(_page(key, lang))
    people = ("boy", "girl") if pages.TOOLS[key].form == "pair" else ("self",)
    for person in people:
        slot = re.search(r'<span class="field__jump"[^>]*></span>', form)
        assert slot, (key, lang, person, "no year-jump slot beside the date field")
        assert pages.ui(lang)["year_jump"] in slot.group(0), f"{lang}: the slot carries no label"
    assert "<option" not in form or form.count("<option") == form.count('<option value="'), None
    # the real assertion: no year is enumerated in the document at all
    assert not re.search(r"<option[^>]*>(18|19|20)\d{2}</option>", form), (
        f"{key}/{lang}: the year list has been shipped in the markup - that is ~7KB per field of document "
        "for a control most visitors never touch")


@pytest.mark.browser
@pytest.mark.parametrize("lang", i18n.LANGS)
def test_the_year_jump_writes_through_to_the_field_and_is_echoed(live_site, lang):
    """The three things that make it safe rather than fast.

    It holds no value of its own - it writes the year into the date input and lets the existing echo and
    validation see it as a keystroke. Its range comes from the field, so it can never offer a year the form
    would refuse. And on an empty field it lands on 1 January, which is a day and a month the visitor did
    NOT choose - permissible only because the echo says so in the same instant.
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as play:
        browser = play.chromium.launch(**pdf_browser.launch_options())
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.goto(live_site + i18n.url_for("kundali", lang), wait_until="networkidle")
        jump = page.locator("[data-year-jump] select")
        assert jump.is_visible(), f"{lang}: app.js built no year jump"
        # There is no "does it steal focus on creation" assertion here, and its absence is deliberate.
        # I wrote one, then mutated app.js to call select.focus() on the element it had just built, and the
        # test still passed - twice, once with the check late and once with it at load time. The reason is
        # structural: the control is created DISABLED, because the field starts empty, and disabling an
        # element blurs it. Focus theft is not something this implementation can do, so an assertion about
        # it can only ever be green. If the jump is ever enabled at creation - a date restored from a
        # previous visit would do it - this becomes a real case and needs a real test.

        # its range is the field's range, so it cannot offer a year the validator would reject
        bounds = page.evaluate("""() => {
            const s = document.querySelector("[data-year-jump] select");
            const years = [...s.options].map(o => o.value).filter(Boolean).map(Number);
            const input = document.querySelector("input[type='date']");
            return { min: Math.min(...years), max: Math.max(...years), count: years.length,
                     fieldMin: input.getAttribute("min"), fieldMax: input.getAttribute("max") }; }""")

        # an EMPTY field: the jump writes 1 January, because a native date input has no partial value and
        # the picker opens on whatever the field holds. The day and month are therefore OURS, and the echo
        # has to say so rather than claim the visitor entered them.
        jump.select_option("1955")
        page.wait_for_selector("[data-date-echo]:not([hidden])", timeout=4000)
        empty_start = page.evaluate("() => document.querySelector(\"input[type='date']\").value")
        supplied_echo = page.locator("[data-date-echo]").inner_text()
        # and the ordinary echo returns the moment they touch the field themselves. TYPED, not filled:
        # page.fill sets the value programmatically, which produces an untrusted event - the same kind the
        # jump dispatches - so filling here asks the mechanism to separate two things that are identical.
        # Measured on this page: fill -> isTrusted false, keyboard.type -> isTrusted true.
        page.focus("#self-date")
        page.keyboard.type("03091955")
        page.wait_for_timeout(150)
        own_echo = page.locator("[data-date-echo]").inner_text()
        # read the template from the page's own message table, so the test cannot drift from the copy
        year_set_template = page.evaluate(f"() => AstroRender.messages('{lang}').yearSet")

        # an EXISTING date keeps its day and month
        page.fill("#self-date", "1962-07-23")
        jump.select_option("1958")
        page.wait_for_timeout(150)
        kept = page.evaluate("() => document.querySelector(\"input[type='date']\").value")

        # 29 February carried into a year without one must CLAMP, not roll into March
        page.fill("#self-date", "1960-02-29")
        jump.select_option("1961")
        page.wait_for_timeout(150)
        leap = page.evaluate("() => document.querySelector(\"input[type='date']\").value")
        leap_echo = page.locator("[data-date-echo]").inner_text()

        # and the control follows the field rather than the other way round
        page.fill("#self-date", "1943-11-02")
        page.wait_for_timeout(150)
        followed = jump.input_value()

        # keyboard only: tab off the date field and drive the select with the keyboard
        page.fill("#self-date", "1962-07-23")
        page.focus("#self-date")
        # A date input is segmented - day, month and year each take a Tab of their own before focus leaves
        # it - so "one Tab lands on the select" is not a property any correct implementation has. What is
        # asserted is that tabbing FORWARD from the date field reaches the jump without skipping it.
        reached_by_tab = False
        for _ in range(6):
            page.keyboard.press("Tab")
            if page.evaluate("() => document.activeElement === "
                             "document.querySelector('[data-year-jump] select')"):
                reached_by_tab = True
                break
        jump.select_option("1958")          # select_option drives the element, not the mouse
        page.wait_for_timeout(150)
        keyboard = page.evaluate("() => document.querySelector(\"input[type='date']\").value")
        browser.close()

    assert bounds["fieldMin"] == "1800-01-01", bounds
    assert bounds["min"] == 1800 and str(bounds["max"]) == bounds["fieldMax"][:4], (
        f"{lang}: the jump offers {bounds['min']}-{bounds['max']} but the field accepts "
        f"{bounds['fieldMin']}..{bounds['fieldMax']} - it can offer a year the form will refuse")
    assert empty_start == "1955-01-01", f"{lang}: an empty field jumped to {empty_start!r}"
    # The claim under test is about AUTHORSHIP, not about wording. The echo must not use the sentence it
    # uses for a value the visitor typed, and it must say what is still to be chosen.
    assert pages.ui(lang)["echo_prefix"] not in supplied_echo, (
        f"{lang}: the echo said {supplied_echo!r} about a day and month the APP supplied. Its whole worth "
        "is that it reports what the visitor did; the first time it claims an action they did not take, it "
        "teaches them it is not a faithful mirror - in the cheap case, so that in the expensive one they "
        "have already learned to skim it.")
    assert "1955" in supplied_echo, f"{lang}: the supplied-year echo does not name the year: {supplied_echo!r}"
    expected = year_set_template.replace("{year}", "1955")
    assert supplied_echo.strip() == expected, (
        f"{lang}: expected {expected!r}, got {supplied_echo!r}")
    assert pages.ui(lang)["echo_prefix"] in own_echo, (
        f"{lang}: after the visitor set the date themselves the echo still says {own_echo!r} - the sentence "
        "about the app supplying a date has outlived the moment it was true")
    assert kept == "1958-07-23", f"{lang}: changing the year lost the day and month: {kept!r}"
    assert leap == "1961-02-28", (
        f"{lang}: 29 February carried into 1961 became {leap!r}. Rolling into 1 March would move the birth "
        "date by a day silently, which is the failure class this whole form exists to close.")
    assert "1961" in leap_echo, f"{lang}: the clamped date was not echoed: {leap_echo!r}"
    assert followed == "1943", f"{lang}: the jump did not follow the field, it shows {followed!r}"
    assert keyboard == "1958-07-23", (
        f"{lang}: the year could not be changed from the keyboard - it reached {keyboard!r}. The control is "
        "built by script, so nothing in the markup puts it in the tab order or gives it a name; both have "
        "to be true of the element that is actually created.")
    assert reached_by_tab, (
        f"{lang}: tabbing on from the date field does not reach the year jump. It is inserted adjacent to "
        "that field in DOM order precisely so the tab order follows the reading order.")


# ---------------------------------------------------------------- the result summary
# What a chart result opens with. Two instruments, deliberately kept apart: POSITION says "this is what you
# came for", COLOUR says "this is a finding". The four facts are identity and timing and carry no tone; the
# two items with a verdict carry the only chips on the page.


def _chart(**over):
    body = {"date": "1984-02-19", "time": "09:05", "city": "Pune"}
    body.update(over)
    return client.post("/api/chart", json=body).json()


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_the_summary_chips_only_the_two_things_that_are_findings(js, lang):
    """A chip carries valence, and lagna, rashi, nakshatra and the running dasha have none. Chipping them
    would make the chip mean "here is a thing" rather than "here is a finding" - at exactly the moment the
    dosha line needs it to mean the second. So the count is asserted, not the appearance."""
    data = _chart()
    html = js("AstroRender.renderers.kundali(data, ctx)", data=data, ctx={"lang": lang})
    summary = html.split('class="facts result-summary"', 1)[1].split("</dl>", 1)[0]

    plain = summary.count('class="fact"')
    assert plain == 4, (
        f"{lang}: expected four plain facts - lagna, rashi, nakshatra and the running mahadasha - "
        f"and found {plain}")
    chips = summary.count("badge badge--")
    assert chips == 2, (
        f"{lang}: the summary carries {chips} chips. Only mangal dosha and sade "
        "sati are findings; a chip on a neutral fact asserts something about a value that has nothing to "
        "assert, and it spends the signal the dosha line needs.")
    # the running mahadasha is here by POSITION, not by colour - it used to sit below the chart and the
    # positions table, which is the single thing most visitors come to read
    assert pages_ui_dasha(lang) in summary, f"{lang}: the current mahadasha is not in the summary"


def render_label(lang, key):
    """A label render.js uses, read out of its own table rather than restated here, so these tests cannot
    drift from the copy they assert about."""
    from app.web import STATIC_DIR

    source = (STATIC_DIR / "js" / "render.js").read_text(encoding="utf-8")
    block = source.split("var LABELS = {", 1)[1].split(f"{lang}: {{", 1)[1]
    return re.search(rf'{key}:\s*"([^"]+)"', block).group(1)


def pages_ui_dasha(lang):
    return render_label(lang, "currentMaha")


def verdict_card(summary, lang, key):
    """The ONE verdict card whose label is `key`.

    Asserting over the whole summary is how this went wrong once: the fixture birth is manglik, so
    `badge--warn` is present somewhere no matter what the sade sati card does - and a test written to prove
    the sade sati caution reaches the page passed with that caution removed entirely. Locating the card by
    its label is what makes the assertion about the thing it names."""
    label = render_label(lang, key)
    for card in summary.split('<div class="verdict verdict--')[1:]:
        if label in card:
            return card
    raise AssertionError(f"{lang}: no verdict card labelled {label!r} in the summary")


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_the_summary_never_puts_the_dosha_intensity_in_front_of_the_visitor(js, lang):
    """A gradation on a caution invites the reader to escalate their own anxiety, and nobody reads "high"
    neutrally about their own marriage prospects. It belongs beside the rule that produced it, not in the
    line they meet first."""
    data = _chart()
    data["mangal_dosha"].update(present=True, cancellation_applies=False, intensity="high")
    html = js("AstroRender.renderers.kundali(data, ctx)", data=data, ctx={"lang": lang})
    summary = html.split('class="facts result-summary"', 1)[1].split("</dl>", 1)[0]
    for word in ("high", "\u0909\u091a\u094d\u091a", "\u091c\u093c\u094d\u092f\u093e\u0926\u093e", "\u091c\u093e\u0938\u094d\u0924"):
        assert word.lower() not in summary.lower(), f"{lang}: the intensity {word!r} is in the summary"


# ---------------------------------------------------------------- fast year selection
# A 1950s birth is a long crawl backwards through a month-at-a-time picker. The jump exists to skip that,
# and everything asserted here is about it NOT becoming a second way to end up with the wrong date: a chart
# for the wrong year is still a valid chart, and nothing downstream of this form can tell.


@pytest.mark.parametrize("lang", i18n.LANGS)
@pytest.mark.parametrize("key", TOOLS)
def test_the_year_jump_ships_no_options_in_the_document(key, lang):
    """It is an accelerator, so it costs nothing to a reader who never uses it. A birth-year list is ~226
    options; shipped in the markup that is about 7KB per field, two of them on the matching pages, on all
    246 pages. The slot carries a label and nothing else, and app.js fills it."""
    form = _form(_page(key, lang))
    people = ("boy", "girl") if pages.TOOLS[key].form == "pair" else ("self",)
    for person in people:
        slot = re.search(r'<span class="field__jump"[^>]*></span>', form)
        assert slot, (key, lang, person, "no year-jump slot beside the date field")
        assert pages.ui(lang)["year_jump"] in slot.group(0), f"{lang}: the slot carries no label"
    assert "<option" not in form or form.count("<option") == form.count('<option value="'), None
    # the real assertion: no year is enumerated in the document at all
    assert not re.search(r"<option[^>]*>(18|19|20)\d{2}</option>", form), (
        f"{key}/{lang}: the year list has been shipped in the markup - that is ~7KB per field of document "
        "for a control most visitors never touch")


@pytest.mark.browser
@pytest.mark.parametrize("lang", i18n.LANGS)
def test_the_year_jump_writes_through_to_the_field_and_is_echoed(live_site, lang):
    """The three things that make it safe rather than fast.

    It holds no value of its own - it writes the year into the date input and lets the existing echo and
    validation see it as a keystroke. Its range comes from the field, so it can never offer a year the form
    would refuse. And on an empty field it lands on 1 January, which is a day and a month the visitor did
    NOT choose - permissible only because the echo says so in the same instant.
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as play:
        browser = play.chromium.launch(**pdf_browser.launch_options())
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.goto(live_site + i18n.url_for("kundali", lang), wait_until="networkidle")
        jump = page.locator("[data-year-jump] select")
        assert jump.is_visible(), f"{lang}: app.js built no year jump"
        # There is no "does it steal focus on creation" assertion here, and its absence is deliberate.
        # I wrote one, then mutated app.js to call select.focus() on the element it had just built, and the
        # test still passed - twice, once with the check late and once with it at load time. The reason is
        # structural: the control is created DISABLED, because the field starts empty, and disabling an
        # element blurs it. Focus theft is not something this implementation can do, so an assertion about
        # it can only ever be green. If the jump is ever enabled at creation - a date restored from a
        # previous visit would do it - this becomes a real case and needs a real test.

        # its range is the field's range, so it cannot offer a year the validator would reject
        bounds = page.evaluate("""() => {
            const s = document.querySelector("[data-year-jump] select");
            const years = [...s.options].map(o => o.value).filter(Boolean).map(Number);
            const input = document.querySelector("input[type='date']");
            return { min: Math.min(...years), max: Math.max(...years), count: years.length,
                     fieldMin: input.getAttribute("min"), fieldMax: input.getAttribute("max") }; }""")

        # an EMPTY field: the jump writes 1 January, because a native date input has no partial value and
        # the picker opens on whatever the field holds. The day and month are therefore OURS, and the echo
        # has to say so rather than claim the visitor entered them.
        jump.select_option("1955")
        page.wait_for_selector("[data-date-echo]:not([hidden])", timeout=4000)
        empty_start = page.evaluate("() => document.querySelector(\"input[type='date']\").value")
        supplied_echo = page.locator("[data-date-echo]").inner_text()
        # and the ordinary echo returns the moment they touch the field themselves. TYPED, not filled:
        # page.fill sets the value programmatically, which produces an untrusted event - the same kind the
        # jump dispatches - so filling here asks the mechanism to separate two things that are identical.
        # Measured on this page: fill -> isTrusted false, keyboard.type -> isTrusted true.
        page.focus("#self-date")
        page.keyboard.type("03091955")
        page.wait_for_timeout(150)
        own_echo = page.locator("[data-date-echo]").inner_text()
        # read the template from the page's own message table, so the test cannot drift from the copy
        year_set_template = page.evaluate(f"() => AstroRender.messages('{lang}').yearSet")

        # an EXISTING date keeps its day and month
        page.fill("#self-date", "1962-07-23")
        jump.select_option("1958")
        page.wait_for_timeout(150)
        kept = page.evaluate("() => document.querySelector(\"input[type='date']\").value")

        # 29 February carried into a year without one must CLAMP, not roll into March
        page.fill("#self-date", "1960-02-29")
        jump.select_option("1961")
        page.wait_for_timeout(150)
        leap = page.evaluate("() => document.querySelector(\"input[type='date']\").value")
        leap_echo = page.locator("[data-date-echo]").inner_text()

        # and the control follows the field rather than the other way round
        page.fill("#self-date", "1943-11-02")
        page.wait_for_timeout(150)
        followed = jump.input_value()

        # keyboard only: tab off the date field and drive the select with the keyboard
        page.fill("#self-date", "1962-07-23")
        page.focus("#self-date")
        # A date input is segmented - day, month and year each take a Tab of their own before focus leaves
        # it - so "one Tab lands on the select" is not a property any correct implementation has. What is
        # asserted is that tabbing FORWARD from the date field reaches the jump without skipping it.
        reached_by_tab = False
        for _ in range(6):
            page.keyboard.press("Tab")
            if page.evaluate("() => document.activeElement === "
                             "document.querySelector('[data-year-jump] select')"):
                reached_by_tab = True
                break
        jump.select_option("1958")          # select_option drives the element, not the mouse
        page.wait_for_timeout(150)
        keyboard = page.evaluate("() => document.querySelector(\"input[type='date']\").value")
        browser.close()

    assert bounds["fieldMin"] == "1800-01-01", bounds
    assert bounds["min"] == 1800 and str(bounds["max"]) == bounds["fieldMax"][:4], (
        f"{lang}: the jump offers {bounds['min']}-{bounds['max']} but the field accepts "
        f"{bounds['fieldMin']}..{bounds['fieldMax']} - it can offer a year the form will refuse")
    assert empty_start == "1955-01-01", f"{lang}: an empty field jumped to {empty_start!r}"
    # The claim under test is about AUTHORSHIP, not about wording. The echo must not use the sentence it
    # uses for a value the visitor typed, and it must say what is still to be chosen.
    assert pages.ui(lang)["echo_prefix"] not in supplied_echo, (
        f"{lang}: the echo said {supplied_echo!r} about a day and month the APP supplied. Its whole worth "
        "is that it reports what the visitor did; the first time it claims an action they did not take, it "
        "teaches them it is not a faithful mirror - in the cheap case, so that in the expensive one they "
        "have already learned to skim it.")
    assert "1955" in supplied_echo, f"{lang}: the supplied-year echo does not name the year: {supplied_echo!r}"
    expected = year_set_template.replace("{year}", "1955")
    assert supplied_echo.strip() == expected, (
        f"{lang}: expected {expected!r}, got {supplied_echo!r}")
    assert pages.ui(lang)["echo_prefix"] in own_echo, (
        f"{lang}: after the visitor set the date themselves the echo still says {own_echo!r} - the sentence "
        "about the app supplying a date has outlived the moment it was true")
    assert kept == "1958-07-23", f"{lang}: changing the year lost the day and month: {kept!r}"
    assert leap == "1961-02-28", (
        f"{lang}: 29 February carried into 1961 became {leap!r}. Rolling into 1 March would move the birth "
        "date by a day silently, which is the failure class this whole form exists to close.")
    assert "1961" in leap_echo, f"{lang}: the clamped date was not echoed: {leap_echo!r}"
    assert followed == "1943", f"{lang}: the jump did not follow the field, it shows {followed!r}"
    assert keyboard == "1958-07-23", (
        f"{lang}: the year could not be changed from the keyboard - it reached {keyboard!r}. The control is "
        "built by script, so nothing in the markup puts it in the tab order or gives it a name; both have "
        "to be true of the element that is actually created.")
    assert reached_by_tab, (
        f"{lang}: tabbing on from the date field does not reach the year jump. It is inserted adjacent to "
        "that field in DOM order precisely so the tab order follows the reading order.")


# ---------------------------------------------------------------- the result summary
# What a chart result opens with. Two instruments, deliberately kept apart: POSITION says "this is what you
# came for", COLOUR says "this is a finding". The four facts are identity and timing and carry no tone; the
# two items with a verdict carry the only chips on the page.


def _chart(**over):
    body = {"date": "1984-02-19", "time": "09:05", "city": "Pune"}
    body.update(over)
    return client.post("/api/chart", json=body).json()


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_the_summary_chips_only_the_two_things_that_are_findings(js, lang):
    """A chip carries valence, and lagna, rashi, nakshatra and the running dasha have none. Chipping them
    would make the chip mean "here is a thing" rather than "here is a finding" - at exactly the moment the
    dosha line needs it to mean the second. So the count is asserted, not the appearance."""
    data = _chart()
    html = js("AstroRender.renderers.kundali(data, ctx)", data=data, ctx={"lang": lang})
    summary = html.split('class="facts result-summary"', 1)[1].split("</dl>", 1)[0]

    plain = summary.count('class="fact"')
    assert plain == 4, (
        f"{lang}: expected four plain facts - lagna, rashi, nakshatra and the running mahadasha - "
        f"and found {plain}")
    chips = summary.count("badge badge--")
    assert chips == 2, (
        f"{lang}: the summary carries {chips} chips. Only mangal dosha and sade "
        "sati are findings; a chip on a neutral fact asserts something about a value that has nothing to "
        "assert, and it spends the signal the dosha line needs.")
    # the running mahadasha is here by POSITION, not by colour - it used to sit below the chart and the
    # positions table, which is the single thing most visitors come to read
    assert pages_ui_dasha(lang) in summary, f"{lang}: the current mahadasha is not in the summary"


def render_label(lang, key):
    """A label render.js uses, read out of its own table rather than restated here, so these tests cannot
    drift from the copy they assert about."""
    from app.web import STATIC_DIR

    source = (STATIC_DIR / "js" / "render.js").read_text(encoding="utf-8")
    block = source.split("var LABELS = {", 1)[1].split(f"{lang}: {{", 1)[1]
    return re.search(rf'{key}:\s*"([^"]+)"', block).group(1)


def pages_ui_dasha(lang):
    return render_label(lang, "currentMaha")


def verdict_card(summary, lang, key):
    """The ONE verdict card whose label is `key`.

    Asserting over the whole summary is how this went wrong once: the fixture birth is manglik, so
    `badge--warn` is present somewhere no matter what the sade sati card does - and a test written to prove
    the sade sati caution reaches the page passed with that caution removed entirely. Locating the card by
    its label is what makes the assertion about the thing it names."""
    label = render_label(lang, key)
    for card in summary.split('<div class="verdict verdict--')[1:]:
        if label in card:
            return card
    raise AssertionError(f"{lang}: no verdict card labelled {label!r} in the summary")


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_the_summary_never_puts_the_dosha_intensity_in_front_of_the_visitor(js, lang):
    """A gradation on a caution invites the reader to escalate their own anxiety, and nobody reads "high"
    neutrally about their own marriage prospects. It belongs beside the rule that produced it, not in the
    line they meet first."""
    data = _chart()
    data["mangal_dosha"].update(present=True, cancellation_applies=False, intensity="high")
    html = js("AstroRender.renderers.kundali(data, ctx)", data=data, ctx={"lang": lang})
    summary = html.split('class="facts result-summary"', 1)[1].split("</dl>", 1)[0]
    for word in ("high", "\u0909\u091a\u094d\u091a", "\u091c\u093c\u094d\u092f\u093e\u0926\u093e", "\u091c\u093e\u0938\u094d\u0924"):
        assert word.lower() not in summary.lower(), f"{lang}: the intensity {word!r} is in the summary"


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_a_caution_chip_never_appears_without_the_sentence_that_explains_it(js, lang):
    """The rule that makes this not fear framing. A bare caution badge tells a visitor something is wrong
    and nothing about what it means, which is the whole of what this product does not do. The chip and its
    note are emitted by one function so that a later edit cannot move one and leave the other."""
    data = _chart()
    data["mangal_dosha"].update(present=True, cancellation_applies=False)
    html = js("AstroRender.renderers.kundali(data, ctx)", data=data, ctx={"lang": lang})
    summary = html.split('class="facts result-summary"', 1)[1].split("</dl>", 1)[0]
    for card in summary.split('<div class="verdict verdict--')[1:]:
        tone = card.split('"', 1)[0]
        if tone != "warn":
            continue
        note = card.split('class="verdict__note">', 1)
        assert len(note) == 2 and len(note[1].split("</span>", 1)[0].strip()) > 20, (
            f"{lang}: a warn chip is shown with no sentence beside it: {card[:160]!r}")


def test_the_verdict_emitter_cannot_produce_a_bare_caution(js):
    """The emitter's CONTRACT, called directly rather than through a payload that happens to satisfy it.

    The distinction this closes: one function emitting the chip and its sentence together means no later
    edit can move one and leave the other - but it does not mean a bare caution is impossible, because the
    function would emit whatever note it was handed, including none. Separation and absence are different
    guarantees and the code documented the stronger one.

    Nothing reaches it today: app/engine/sadesati.py always returns a cycle with a start and an end, so the
    only conditional note on the page is never empty. That is a fact about an engine file this renderer does
    not mention, which is exactly why it should not be what the guarantee rests on. Testing through a chart
    payload would pass for that reason and prove nothing about the emitter.
    """
    with_note = js('AstroRender.verdict("warn", "Label", "State", "a sentence explaining what it means")')
    assert "badge--warn" in with_note and "verdict--warn" in with_note, with_note
    assert "verdict__note" in with_note, "the note was dropped when one was supplied"

    bare = js('AstroRender.verdict("warn", "Label", "State", "")')
    assert "badge--warn" not in bare and "verdict--warn" not in bare, (
        "a caution tone was emitted with no sentence beside it. A badge that tells a visitor something is "
        f"wrong and nothing about what it means is the framing this product does not do: {bare!r}")
    assert "State" in bare and "Label" in bare, (
        f"the downgrade dropped the finding itself, which is worse than the tone being wrong: {bare!r}")
    # downgraded rather than thrown: this runs in a customer's browser inside kundaliHtml, so refusing to
    # render is a blank result for someone who has paid, not a loud error beside a chip
    assert "verdict--info" in bare, f"expected a calm tone, got {bare!r}"


# ---------------------------------------------------------------- the caution actually reaches the page
# `verdict()` cannot EMIT a bare caution - the test above proves that against the emitter's contract. These
# two prove the other half: that the real payloads never ask it to. The fallback downgrades a warn with no
# note to a calm tone, which is the right runtime behaviour and would be a silent degradation if nothing
# ever checked that the downgrade is not happening. With these, an upstream change that empties the note
# turns a red run rather than a quiet chart, so the fallback is a fallback and not a hiding place.


def _birth_whose_sade_sati_is_running():
    """A birth the engine says is IN sade sati right now, found by search rather than by a fixed date.

    `active` depends on where Saturn is today, so any hardcoded birth drifts out of sade sati within a
    couple of years and the test quietly stops testing.

    THE SEARCH CANNOT FAIL TO FIND ONE, and that is arithmetic rather than luck. Sade sati covers the 12th,
    the 1st and the 2nd sign from the Moon, so wherever Saturn is, exactly 3 of the 12 rashis are in the
    window at any moment. The Moon moves through all twelve signs in about twenty-seven days, so one month
    of birth dates at a fixed time and place must contain a birth whose Moon sign is one of the three.
    Measured on the day this was written: 7 of 31, which is 23% against an expected 25% - the arithmetic
    agreeing with the observation is what says the mechanism is the one described and not a coincidence of
    this particular month.

    Which is why it RAISES rather than skips when it finds nothing. The only way to find no candidate is
    for the engine to have stopped reporting sade sati at all, and that is precisely the regression worth
    catching - a skip would hide it behind a green run.

    Deliberately NOT done by setting `active` on a response: a flipped flag does not prove the engine still
    returns the cycle the note is built from, and that is exactly the regression these tests exist to catch.
    """
    for day in range(1, 32):
        data = _chart(date=f"1984-01-{day:02d}")
        if data["sade_sati"]["active"]:
            return data
    raise AssertionError(
        "no birth in a whole lunar month is in sade sati today. Saturn is always within three signs of "
        "some Moon sign, so this means the engine has stopped reporting it rather than that none exists.")


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_a_real_active_mangal_dosha_reaches_the_page_as_a_caution(js, lang):
    """End to end, on an unedited chart. The birth this file already uses is manglik with no classical
    cancellation, so the engine's own output has to come out the other side wearing the caution tone."""
    data = _chart()
    assert data["mangal_dosha"]["present"] and not data["mangal_dosha"]["cancellation_applies"], (
        "the fixture birth is no longer an active mangal dosha, so this test is not testing anything - "
        "pick another birth rather than deleting the assertion")
    summary = js("AstroRender.renderers.kundali(data, ctx)", data=data, ctx={"lang": lang}) \
        .split('class="facts result-summary"', 1)[1].split("</dl>", 1)[0]
    card = verdict_card(summary, lang, "sumMangal")
    assert card.startswith("warn") and "badge--warn" in card, (
        f"{lang}: a real active mangal dosha did not reach the summary as a caution. If the note that has "
        "to accompany it went missing upstream, verdict() downgrades the tone on purpose - which is the "
        "right thing at runtime and must never be how a chart ships.")


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_a_real_active_sade_sati_reaches_the_page_as_a_caution(js, lang):
    """The same, for the branch whose note is CONDITIONAL. The sade sati sentence is built from
    `cycle.start` and `cycle.end`; if either stopped being returned the note would be empty, the tone would
    quietly drop to calm, and nothing else in the suite would notice."""
    data = _birth_whose_sade_sati_is_running()
    cycle = data["sade_sati"]["cycle"]
    assert cycle.get("start") and cycle.get("end"), (
        "the engine returned an active sade sati with no cycle dates, so the summary's caution note is "
        "empty and the tone has silently downgraded - this is the upstream change the test guards")
    summary = js("AstroRender.renderers.kundali(data, ctx)", data=data, ctx={"lang": lang}) \
        .split('class="facts result-summary"', 1)[1].split("</dl>", 1)[0]
    # THE SADE SATI CARD, not the summary. The fixture birth is manglik, so `badge--warn` is in this block
    # whatever sade sati does; an earlier version of this assertion passed with the sade sati caution gone.
    card = verdict_card(summary, lang, "sumSadeSati")
    assert card.startswith("warn") and "badge--warn" in card, (
        f"{lang}: a real running sade sati is not shown as a caution: {card[:140]!r}")
    assert "verdict__note" in card, f"{lang}: the caution reached the page with no sentence beside it"


# ---------------------------------------------------------------- a request that never answers
# Entering a state is half of it; LEAVING it is the half that strands a customer. A test that only proves
# the busy state appears would pass on a busy state that never ends, which is precisely the defect this
# found: measured before the fix, a chart request that hangs left the submit button disabled reading
# "Calculating…" with no error and no result, for ever, with a page reload as the only way out. A reset
# connection and an HTTP 500 were both handled and said so - the hang was the single unhandled branch, and
# the worst of the three, because to the customer it looks like a slow site rather than a broken one.
#
# This test is SLOW ON PURPOSE - it waits out the real twenty-second timeout. The alternative was making
# the timeout settable from outside so a test could shorten it, which is application surface that exists
# only for testing, and the whole reachability design here is that nothing outside the harness can reach
# these states. Twenty seconds once is cheaper than that.


@pytest.mark.browser
def test_a_request_that_never_answers_gives_the_form_back(live_site):
    """Three claims, and the middle one is the defect: the busy state is entered, it ENDS, and the customer
    can retry afterwards. The route is held open rather than failed, because a failure was already handled
    correctly and a hang was not - they are different branches and only one of them was broken."""
    from playwright.sync_api import sync_playwright

    def state(page):
        return page.evaluate("""() => {
            const b = document.querySelector("#submit-btn");
            const errors = [...document.querySelectorAll(".form-status, .field-error")]
                .filter(e => !e.hidden && e.offsetParent !== null)
                .map(e => e.innerText.trim()).filter(Boolean);
            return { disabled: b.disabled, busy: document.querySelector("form").getAttribute("aria-busy"),
                     errors: errors, result: !document.querySelector("#result").hidden }; }""")

    with sync_playwright() as play:
        browser = play.chromium.launch(**pdf_browser.launch_options())
        page = browser.new_page(viewport={"width": 390, "height": 844})
        try:
            held = []
            page.route("**/api/chart", lambda route: held.append(route))   # accepted, never answered
            page.goto(live_site + i18n.url_for("kundali", "en"), wait_until="networkidle")
            page.fill("#self-date", "1984-02-19")
            page.click("[data-step-next]")
            page.fill("#self-time", "09:05")
            page.click("[data-step-next]")
            page.fill("#self-city", "Pune")
            page.wait_for_timeout(400)
            page.keyboard.press("ArrowDown")
            page.keyboard.press("Enter")
            page.click("#submit-btn")

            page.wait_for_timeout(1500)
            during = state(page)
            page.wait_for_timeout(21000)      # past the twenty-second timeout
            after = state(page)

            page.unroute("**/api/chart")      # the connection comes back
            page.click("#submit-btn")
            page.wait_for_selector("#result:not([hidden])", timeout=30000)
            retried = state(page)
        finally:
            browser.close()

    assert during["disabled"] and during["busy"] == "true", (
        f"the form does not show it is working while a request is in flight: {during}")
    assert not during["errors"], f"an error was shown while the request was still running: {during}"

    assert not after["disabled"], (
        f"a request that never answers left the form disabled for ever: {after}. The customer sees a dead "
        "button reading 'Calculating…', no error, and no result, and their only way out is a page reload - "
        "which on the path to a paid product means they leave instead.")
    assert after["busy"] == "false", f"aria-busy is still set after the request gave up: {after}"
    assert after["errors"], f"the form came back with no explanation of what happened: {after}"

    assert retried["result"] and not retried["disabled"], (
        f"the form could not be used again after a timeout: {retried}. Coming back disabled-but-silent and "
        "coming back unusable stranded the customer equally.")


# ---------------------------------------------------------------- the two states that already shipped
# Both of these were CORRECT before these tests existed, and neither had ever been exercised. That is the
# same position the request timeout was in an hour ago: the error branch beside it was right, nobody had
# looked at the hang, and nothing in the suite could tell the two apart. Untested working code is one edit
# from untested broken code - and in the timeout's case it was one MISSING edit from broken, which is worse,
# because nothing had to change for it to be wrong.


@pytest.mark.browser
@pytest.mark.parametrize("lang", i18n.LANGS)
def test_the_form_still_works_with_javascript_switched_off(live_site, lang):
    """`<noscript>` was asserted as a TAG - `assert "<noscript>" in html` - which passes on an empty one, on
    one carrying the wrong message, and on a page whose form cannot be used without JavaScript. The file's
    own docstring promises "the whole form is there and works"; the assertion checked that a tag exists.

    So this loads the page with scripting genuinely disabled and uses it. No progressive enhancement, no
    staged steps, no combobox - just the plain form the browser gets, which is the thing a reader with a
    blocked or failed script actually meets."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as play:
        browser = play.chromium.launch(**pdf_browser.launch_options())
        context = browser.new_context(java_script_enabled=False)
        page = context.new_page()
        try:
            page.goto(live_site + i18n.url_for("kundali", lang), wait_until="domcontentloaded")
            fields = {name: page.locator(f"#self-{name}").is_visible() for name in ("date", "time", "city")}
            submit = page.locator("#submit-btn").is_visible()
            notice = page.locator("noscript").inner_text().strip()
            steps_hidden = page.locator("[data-step]:not([hidden])").count()
        finally:
            browser.close()

    for name, shown in fields.items():
        assert shown, (
            f"{lang}: the {name} field is not usable with JavaScript off. Every input is meant to be in the "
            "DOM and visible on first render - the steps are an enhancement that app.js adds, never a gate.")
    assert submit, f"{lang}: there is no way to submit the form without JavaScript"
    assert steps_hidden >= 1, f"{lang}: the form's own steps are hidden before app.js has run"
    assert pages.ui(lang)["noscript"] in notice, (
        f"{lang}: the noscript block does not carry the page's own explanation - it said {notice!r}. A tag "
        "with nothing in it satisfies the old assertion and tells the reader nothing.")


# (how the request fails, the message key the page must show)
BROKEN = (("server-error", lambda route: route.fulfill(status=500, content_type="application/json", body="{}")),
          ("connection-reset", lambda route: route.abort()))


@pytest.mark.browser
@pytest.mark.parametrize("failure, handler", BROKEN, ids=[row[0] for row in BROKEN])
def test_a_failed_calculation_is_visible_and_the_form_comes_back(live_site, failure, handler):
    """`parseApiError` is well covered as a MAPPING - status and body to message, in four files, per tree.
    Nothing asserted that the message reaches the page, that the form is usable afterwards, or that a retry
    works. Same split as the caution chips: the contract was proven and whether anything exercises it was
    not.

    Three claims, and the last is the one that matters. A customer who sees an error and cannot try again
    has been stopped just as completely as one who sees nothing."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as play:
        browser = play.chromium.launch(**pdf_browser.launch_options())
        page = browser.new_page(viewport={"width": 390, "height": 844})
        try:
            page.route("**/api/chart", handler)
            page.goto(live_site + i18n.url_for("kundali", "en"), wait_until="networkidle")
            page.fill("#self-date", "1984-02-19")
            page.click("[data-step-next]")
            page.fill("#self-time", "09:05")
            page.click("[data-step-next]")
            page.fill("#self-city", "Pune")
            page.wait_for_timeout(400)
            page.keyboard.press("ArrowDown")
            page.keyboard.press("Enter")
            page.click("#submit-btn")
            page.wait_for_timeout(2000)

            shown = [e.strip() for e in page.locator(".form-status:visible, .field-error:visible")
                     .all_inner_texts() if e.strip()]
            enabled = not page.locator("#submit-btn").is_disabled()
            result_hidden = page.locator("#result").is_hidden()

            page.unroute("**/api/chart")
            page.click("#submit-btn")
            page.wait_for_selector("#result:not([hidden])", timeout=30000)
            recovered = page.locator("svg.kundali").is_visible()
        finally:
            browser.close()

    assert shown, (
        f"{failure}: the calculation failed and the page said nothing. The mapping from this status to a "
        "message is unit-tested; that it reaches a reader was not.")
    assert result_hidden, f"{failure}: a result was shown for a request that failed: {shown}"
    assert enabled, (
        f"{failure}: the form is still disabled after a failure, so the message tells the customer what "
        "went wrong and gives them no way to act on it")
    assert recovered, f"{failure}: the form could not produce a chart after recovering from a failure"


# ---------------------------------------------------------------- the busy row
# Two-sided like every other state here: it appears while the engine works and it is GONE afterwards, on
# the success path and on the failure path. A busy indicator that never clears is the hung form in a
# different costume - the same defect the request deadline exists to prevent, wearing a spinner.
#
# The trust line is on this row and not on the button on purpose, and the number is why: the submit button
# is width:100% on a phone, so the longer label wraps and the button grows from 48px to 67px - nineteen
# pixels, under the reader's finger, at the instant of the most important click on the page. Revealing the
# row moves what is BELOW it instead, which is expected after a deliberate click and is the acceptable half
# of that trade.


@pytest.mark.browser
@pytest.mark.parametrize("lang", i18n.LANGS)
def test_the_busy_row_says_what_is_being_computed_and_then_goes(live_site, lang):
    from playwright.sync_api import sync_playwright

    engine_line = None
    with sync_playwright() as play:
        browser = play.chromium.launch(**pdf_browser.launch_options())
        page = browser.new_page(viewport={"width": 390, "height": 900})
        try:
            holding = {"on": True}
            page.route("**/api/chart", lambda route: None if holding["on"] else route.continue_())
            page.goto(live_site + i18n.url_for("kundali", lang), wait_until="networkidle")
            engine_line = page.evaluate(f"() => AstroRender.messages('{lang}').calculatingEngine")
            page.fill("#self-date", "1984-02-19")
            page.click("[data-step-next]")
            page.fill("#self-time", "09:05")
            page.click("[data-step-next]")
            page.fill("#self-city", "Pune")
            page.wait_for_timeout(400)
            page.keyboard.press("ArrowDown")
            page.keyboard.press("Enter")

            button_before = page.evaluate(
                "() => Math.round(document.querySelector('#submit-btn').getBoundingClientRect().height)")
            page.click("#submit-btn")
            page.wait_for_timeout(700)
            during = page.evaluate("""() => { const r = document.querySelector("#form-busy");
                return { shown: !r.hidden, text: r.innerText.trim(),
                         spinner: [...r.querySelectorAll(".form-busy__spinner")].filter(e => {
                             const box = e.getBoundingClientRect();
                             return box.width > 4 && box.height > 4 && getComputedStyle(e).display !== "none";
                         }).length,
                         button: Math.round(document.querySelector("#submit-btn").getBoundingClientRect().height) }; }""")

            page.unroute("**/api/chart")
            holding["on"] = False
            page.click("#submit-btn")
            page.wait_for_selector("#result:not([hidden])", timeout=30000)
            after_success = page.evaluate("() => document.querySelector('#form-busy').hidden")
        finally:
            browser.close()

    assert during["shown"], f"{lang}: nothing tells the reader the engine is working"
    # Counted by RENDERED SIZE, not by existence. The first version of this counted elements, and it passed
    # with the spinner set to display:none - and then passed again when the stylesheet rules for it were
    # deleted outright by accident. An element in the DOM is not a spinner anyone can see.
    assert during["spinner"] == 1, (
        f"{lang}: the busy row has no VISIBLE spinner. An element with the class is not enough - it has to "
        "be rendered, which is what a reader waiting on a slow request actually needs.")
    assert engine_line and engine_line in during["text"], (
        f"{lang}: the busy row says {during['text']!r}, not the engine line {engine_line!r}. This is a trust "
        "statement about what is being computed, not a progress label.")
    assert during["button"] == button_before, (
        f"{lang}: the submit button changed height when it went busy, {button_before} -> {during['button']}. "
        "That is the tap target moving under the reader's finger at the moment of the click, which is why "
        "the engine line is on the row below rather than on the button.")
    assert after_success, (
        f"{lang}: the busy row is still showing after a chart was rendered. A busy indicator that never "
        "clears is the hung form in a different costume.")


# ---------------------------------------------------------------- the result skeleton
# Four sides, and the second is the one that makes the feature worth having rather than an annoyance: it
# must NOT appear on a fast response. The endpoint answers in well under a second, so without the threshold
# every visitor would see a placeholder flash and vanish, which is worse than showing nothing at all.
#
# The other three are the same two-sided shape as every state here. A skeleton that never clears is the
# hung form wearing a different costume, and it can be reached by the success path, the error path and the
# abort path independently.


def _skeleton_visible(page):
    return page.evaluate("""() => { const s = document.querySelector("#result-skeleton");
        return !!s && !s.hidden && s.getBoundingClientRect().height > 20; }""")


def _fill_form(page, live_site, lang="en"):
    page.goto(live_site + i18n.url_for("kundali", lang), wait_until="networkidle")
    page.fill("#self-date", "1984-02-19")
    page.click("[data-step-next]")
    page.fill("#self-time", "09:05")
    page.click("[data-step-next]")
    page.fill("#self-city", "Pune")
    page.wait_for_timeout(400)
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")


@pytest.mark.browser
def test_the_skeleton_waits_for_a_slow_request_and_never_outlives_it(live_site):
    """Appears after the threshold on a slow request; gone once the chart arrives."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as play:
        browser = play.chromium.launch(**pdf_browser.launch_options())
        page = browser.new_page(viewport={"width": 390, "height": 900})
        try:
            # The request is HELD rather than slept on. Sleeping inside a route handler blocks
            # Playwright's own driver, so the observations below queue up behind it and report the state
            # after the wait rather than during it - the first version of this test failed for exactly
            # that reason, and the failure looked like the skeleton not appearing.
            held = []
            page.route("**/api/chart", lambda route: held.append(route))
            _fill_form(page, live_site)
            page.click("#submit-btn")
            page.wait_for_timeout(200)
            early = _skeleton_visible(page)       # before the threshold
            page.wait_for_timeout(1000)
            during = _skeleton_visible(page)      # after it, request still in flight
            assert held, "the chart request was never made"
            held[0].continue_()                   # let it through; the real chart comes back
            page.wait_for_selector("#result:not([hidden])", timeout=30000)
            page.wait_for_timeout(200)
            after = _skeleton_visible(page)
        finally:
            browser.close()

    assert not early, "the skeleton appeared immediately - the half-second threshold is not being applied"
    assert during, "a request that took two seconds showed the reader no placeholder at all"
    assert not after, (
        "the skeleton is still on screen after the chart arrived. A placeholder that never clears is the "
        "hung form in a different costume.")


@pytest.mark.browser
def test_the_skeleton_never_appears_for_a_fast_answer(live_site):
    """The side that keeps it from being an annoyance. The endpoint normally answers in well under a
    second; without the threshold every visitor would see a placeholder flash and disappear."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as play:
        browser = play.chromium.launch(**pdf_browser.launch_options())
        page = browser.new_page(viewport={"width": 390, "height": 900})
        try:
            _fill_form(page, live_site)
            page.click("#submit-btn")
            seen = False
            for _ in range(12):               # poll across the whole request
                if _skeleton_visible(page):
                    seen = True
                    break
                page.wait_for_timeout(50)
            page.wait_for_selector("#result:not([hidden])", timeout=30000)
        finally:
            browser.close()

    assert not seen, (
        "the skeleton appeared during a normal, fast response. Below the threshold nobody should ever see "
        "it - a placeholder that flashes and vanishes is worse than showing nothing.")


@pytest.mark.browser
@pytest.mark.parametrize("failure, handler", BROKEN, ids=[row[0] for row in BROKEN])
def test_the_skeleton_is_gone_when_the_calculation_fails(live_site, failure, handler):
    """The error path, independently of the success path. `setBusy(false)` runs on every exit and the
    skeleton's timer is cancelled there, so this is testing that the invariant actually holds rather than
    that somebody remembered to clear it in three places."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as play:
        browser = play.chromium.launch(**pdf_browser.launch_options())
        page = browser.new_page(viewport={"width": 390, "height": 900})
        try:
            page.route("**/api/chart", handler)
            _fill_form(page, live_site)
            page.click("#submit-btn")
            page.wait_for_timeout(2000)
            lingering = _skeleton_visible(page)
            errors = [e.strip() for e in page.locator(".form-status:visible").all_inner_texts() if e.strip()]
        finally:
            browser.close()

    assert errors, f"{failure}: no error was shown, so this is not testing the failure path"
    assert not lingering, (
        f"{failure}: the skeleton is still showing after the calculation failed - the reader is looking at "
        "a placeholder for a chart that is never going to arrive, next to a message saying it failed")


@pytest.mark.browser
def test_a_response_arriving_after_the_skeleton_shows_never_paints_over_the_chart(live_site):
    """The exit path that is easy to miss, and the worst one if it is wrong.

    The 500ms timer and the response can both be legitimately in flight, and the ordering decides what the
    reader sees. If the placeholder is still showing when the chart is written, the page contradicts itself
    in front of somebody who has just waited for that chart - worse than the placeholder never appearing.

    So the request is held until AFTER the threshold has fired and the skeleton is on screen, and only then
    released. The collision is arranged rather than hoped for."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as play:
        browser = play.chromium.launch(**pdf_browser.launch_options())
        page = browser.new_page(viewport={"width": 390, "height": 900})
        try:
            held = []
            page.route("**/api/chart", lambda route: held.append(route))
            _fill_form(page, live_site)
            page.click("#submit-btn")
            page.wait_for_timeout(900)              # let the threshold fire
            assert _skeleton_visible(page), "the skeleton never appeared, so this is not testing the collision"
            assert held, "the chart request was never made"
            held[0].continue_()                     # the answer arrives while the placeholder is up
            page.wait_for_selector("svg.kundali", timeout=30000)
            page.wait_for_timeout(300)
            both = page.evaluate("""() => {
                const s = document.querySelector("#result-skeleton");
                return { skeleton: !!s && !s.hidden && s.getBoundingClientRect().height > 20,
                         chart: !!document.querySelector("svg.kundali") }; }""")
        finally:
            browser.close()

    assert both["chart"], "no chart was rendered"
    assert not both["skeleton"], (
        "the placeholder is still on screen beside the rendered chart. A reader who waited is being told "
        "it is still working and shown the finished result at the same time.")


@pytest.mark.browser
def test_a_second_submit_does_not_leave_the_first_requests_placeholder_behind(live_site):
    """Abort by resubmit, for a request whose timer has ALREADY FIRED.

    WHAT THIS DOES NOT COVER, stated because the name suggests otherwise: it cannot detect a timer that was
    never cancelled. It waits 900ms before resubmitting, so the first request's 500ms has already elapsed
    and there is no pending timer left to leak - removing the cancellation entirely leaves this green. I
    found that by mutating it and watching it pass.

    The pending-timer case needs the second submit to happen INSIDE the threshold, and it is covered by
    test_a_superseded_timer_cannot_paint_a_placeholder_over_a_finished_chart. This one covers the other
    half: a placeholder from a superseded request that is still on screen after a later one finished."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as play:
        browser = play.chromium.launch(**pdf_browser.launch_options())
        page = browser.new_page(viewport={"width": 390, "height": 900})
        try:
            held = []
            page.route("**/api/chart", lambda route: held.append(route))
            _fill_form(page, live_site)
            page.click("#submit-btn")
            page.wait_for_timeout(900)              # first request in flight, threshold fired
            assert _skeleton_visible(page)
            page.unroute("**/api/chart")            # the network recovers
            page.evaluate("() => document.querySelector('#tool-form').requestSubmit()")
            page.wait_for_selector("#result:not([hidden])", timeout=30000)
            page.wait_for_timeout(400)
            leftover = _skeleton_visible(page)
            for route in held:
                try:
                    route.abort()
                except Exception:
                    pass                            # the superseded request; its outcome is irrelevant
        finally:
            browser.close()

    assert not leftover, (
        "a placeholder from an earlier, superseded request is still on screen after a later one finished - "
        "the skeleton outlived the request that showed it")


@pytest.mark.browser
def test_a_superseded_timer_cannot_paint_a_placeholder_over_a_finished_chart(live_site):
    """The leak, arranged so that it is observable.

    The defect needs a PENDING timer to survive a new submit, so the second submit has to happen before the
    first request's 500ms has elapsed and the second has to finish before it too. If the first timer was
    never cancelled it then fires into a page already showing the chart - a placeholder painted over a
    finished result, which is the worst thing this feature can do.

    The sibling test above waits 900ms and therefore cannot see this: by then the first timer has fired and
    there is nothing left to leak. It stays green with the cancellation removed, which is how this gap was
    found - the mutant survived and the mutant was valid, so the test was the problem."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as play:
        browser = play.chromium.launch(**pdf_browser.launch_options())
        page = browser.new_page(viewport={"width": 390, "height": 900})
        try:
            # The FIRST request is held so it is still in flight at the resubmit; the second is let
            # straight through. Without holding it the first answers in about 100ms locally, so it has
            # already finished by the time the second submit happens and there is no pending timer to
            # leak - measured, and it is why an earlier version of this test could not see the defect
            # either. The overlap has to be built, not hoped for.
            held = []

            def first_one_waits(route):
                if not held:
                    held.append(route)          # hold #1
                else:
                    route.continue_()           # #2 goes through

            page.route("**/api/chart", first_one_waits)
            _fill_form(page, live_site)
            page.click("#submit-btn")
            page.wait_for_timeout(150)          # inside the 500ms threshold, request 1 still in flight
            page.evaluate("() => document.querySelector('#tool-form').requestSubmit()")
            page.wait_for_selector("#result:not([hidden])", timeout=30000)
            page.wait_for_timeout(900)          # past when request 1's timer would have fired
            after = _skeleton_visible(page)
            for route in held:
                try:
                    route.abort()
                except Exception:
                    pass
        finally:
            browser.close()

    assert not after, (
        "a placeholder appeared after the chart was already on screen. A timer belonging to a superseded "
        "request survived the submit that replaced it and fired into a finished page.")


# ---------------------------------------------------------------------------
# The echoed date has to be CONFIRMED, not merely shown.
#
# The year jump writes 1 January so the native picker can open in the chosen year, and the echo says so.
# A sentence can be skimmed, and what it guards is not recoverable: a chart cast for a date nobody entered,
# bought and printed. So the invented date cannot be submitted at all until the visitor has touched the
# field themselves.
#
# Four sides, and the fourth is the one that makes the other three mean anything: the jump dispatches
# `input` and `change` itself, so the gate is only real if those synthetic events do NOT count as
# confirmation. That is what `isTrusted` is for, and it is asserted here as behaviour rather than trusted.
#
# WHAT IS NOT DRIVEN HERE: the operating system's calendar widget. It is browser chrome and Playwright
# cannot open it. The arrow-key edit below is the same code path - a trusted `input`/`change` on the field -
# so it covers the mechanism the picker uses, and this comment is here so nobody reads the picker test as
# proof that a calendar was clicked.


def _year_jump_to(page, year):
    """Pick a year with the fast-year control, leaving the day and month as the app's invented 1 January."""
    page.select_option("[data-year-jump] .field__jump-select", str(year))
    page.wait_for_timeout(100)


def _finish_time_and_city(page):
    """Complete the form AFTER the date step, however the date got there."""
    page.click("[data-step-next]")
    page.fill("#self-time", "09:05")
    page.click("[data-step-next]")
    page.fill("#self-city", "Pune")
    page.wait_for_timeout(400)
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")


def _date_error(page):
    return page.evaluate("""() => { const e = document.querySelector("#self-date-error");
        return e && !e.hidden ? e.textContent.trim() : ""; }""")


@pytest.mark.browser
def test_a_year_picked_but_never_confirmed_cannot_be_submitted(live_site):
    """The refusal itself: a date the app invented does not reach the engine."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as play:
        browser = play.chromium.launch(**pdf_browser.launch_options())
        page = browser.new_page(viewport={"width": 390, "height": 900})
        try:
            calls = []
            page.route("**/api/chart", lambda route: (calls.append(1), route.abort()))
            page.goto(live_site + i18n.url_for("kundali", "en"), wait_until="networkidle")
            _year_jump_to(page, 1955)
            _finish_time_and_city(page)
            page.click("#submit-btn")
            page.wait_for_timeout(600)
            message = _date_error(page)
            invalid = page.get_attribute("#self-date", "aria-invalid")
            focused = page.evaluate("() => document.activeElement && document.activeElement.id")
            value = page.input_value("#self-date")
        finally:
            browser.close()

    assert not calls, (
        "a date the visitor never entered was sent to the engine. The year jump invented the day and the "
        "month and the form calculated anyway - this is the failure the whole echo exists to prevent.")
    assert value == "1955-01-01", "precondition failed: the jump did not leave its invented date in the field"
    assert message, "the form refused but said nothing, which is worse than either alternative"
    assert "confirm" in message.lower(), (
        f"the refusal does not ask for a confirmation, it reads as a rejection: {message!r}")
    assert invalid == "true", "the date field was not marked, so a screen reader is not sent to it"
    assert focused == "self-date", f"focus was left on {focused!r} rather than on the field to confirm"


@pytest.mark.browser
def test_a_date_the_visitor_typed_is_submitted_without_a_confirmation_step(live_site):
    """The gate must not fire on the ordinary path - nobody who entered a date is asked to confirm it."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as play:
        browser = play.chromium.launch(**pdf_browser.launch_options())
        page = browser.new_page(viewport={"width": 390, "height": 900})
        try:
            calls = []
            page.route("**/api/chart", lambda route: (calls.append(1), route.continue_()))
            _fill_form(page, live_site)          # fills the date directly; the jump is never used
            page.click("#submit-btn")
            page.wait_for_selector("#result:not([hidden])", timeout=30000)
            message = _date_error(page)
        finally:
            browser.close()

    assert calls, "a plainly entered date was refused - the confirmation gate is firing on the normal path"
    assert not message, f"an ordinary date drew a confirmation demand: {message!r}"


@pytest.mark.browser
def test_touching_the_field_confirms_it_and_keeps_a_genuine_first_of_january(live_site):
    """The way out, and the case that makes the mechanism honest.

    Somebody born on 1 January of the year they picked must be able to submit 1 January. The gate cannot
    therefore be a comparison against that date - it is a question of whether the field was touched. Here
    the touch is an arrow-key edit that moves a segment and moves it back, so the value the engine receives
    is still 1 January and it is now confirmed."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as play:
        browser = play.chromium.launch(**pdf_browser.launch_options())
        page = browser.new_page(viewport={"width": 390, "height": 900})
        try:
            sent = []

            def capture(route):
                sent.append(route.request.post_data)
                route.continue_()

            page.route("**/api/chart", capture)
            page.goto(live_site + i18n.url_for("kundali", "en"), wait_until="networkidle")
            _year_jump_to(page, 1955)
            page.click("#self-date")             # a real click, then real keys: isTrusted is true for both
            page.keyboard.press("ArrowUp")
            page.keyboard.press("ArrowDown")
            page.wait_for_timeout(100)
            value = page.input_value("#self-date")
            _finish_time_and_city(page)
            page.click("#submit-btn")
            page.wait_for_selector("#result:not([hidden])", timeout=30000)
            message = _date_error(page)
        finally:
            browser.close()

    assert value == "1955-01-01", (
        f"the arrow keys did not return the field to its starting date ({value!r}), so this test is no "
        "longer about a genuine 1 January and needs rewriting rather than relaxing")
    assert not message, f"a confirmed date was still refused: {message!r}"
    assert sent, "a confirmed date never reached the engine"
    assert '"date": "1955-01-01"' in sent[0] or '"date":"1955-01-01"' in sent[0], (
        f"1 January was not the date submitted, so confirming it moved it: {sent[0]!r}")


@pytest.mark.browser
def test_the_jumps_own_events_do_not_count_as_the_visitor_confirming(live_site):
    """The discriminator, asserted rather than assumed.

    The jump dispatches `input` and `change` to keep the echo and the validation in step, so the gate is
    worth nothing unless those events are distinguishable from a person's. This test proves they were
    delivered AND did not confirm, in one page: the echo has re-rendered into its year-set sentence, which
    only happens by way of those events, and the submit is still refused."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as play:
        browser = play.chromium.launch(**pdf_browser.launch_options())
        page = browser.new_page(viewport={"width": 390, "height": 900})
        try:
            calls = []
            page.route("**/api/chart", lambda route: (calls.append(1), route.abort()))
            page.goto(live_site + i18n.url_for("kundali", "en"), wait_until="networkidle")
            _year_jump_to(page, 1955)
            echo = page.evaluate("""() => { const e = document.querySelector("[data-date-echo]");
                return e && !e.hidden ? e.textContent.trim() : ""; }""")
            supplied = page.get_attribute("#self-date", "data-supplied-year")
            _finish_time_and_city(page)
            page.click("#submit-btn")
            page.wait_for_timeout(600)
            message = _date_error(page)
        finally:
            browser.close()

    assert "1955" in echo, (
        f"the echo did not react to the jump, so this test cannot show that its events were ignored "
        f"rather than never delivered: {echo!r}")
    assert supplied == "1955", "the field was not marked as carrying an app-supplied day and month"
    assert message, "the jump's own untrusted events satisfied the confirmation gate"
    assert not calls, "the jump's own events were enough to get a chart calculated"


# ---------------------------------------------------------------------------
# /api/cities had no deadline, and the failure was not a missing list.
#
# The promise is AWAITED by the "use my location" button: it says "searching..." and then waits on the
# cities before it asks for a position. The fetch's own .catch settles a network ERROR, so the visible
# failure needed a HANG - a connection that opens and never answers - which nothing settled at all. The
# sentence stayed on screen for good, with no error and nothing to press: the hung-form defect on a
# different control.
#
# THIS TEST COSTS TWENTY SECONDS OF WALL CLOCK, deliberately. The deadline is the product's real constant
# and there is no way to shorten it from outside the page - no debug parameter, no injectable delay, and
# that is a rule rather than an oversight. So it waits. One slow test for a control that could otherwise
# sit dead forever is the right trade; do not "fix" it by making the timeout configurable from a URL.


@pytest.mark.browser
def test_a_hung_city_list_does_not_leave_the_locate_button_searching_for_ever(live_site):
    """The stuck state, observed: the status has to stop saying "searching" on its own."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as play:
        browser = play.chromium.launch(**pdf_browser.launch_options())
        context = browser.new_context(viewport={"width": 390, "height": 900},
                                      permissions=["geolocation"],
                                      geolocation={"latitude": 18.52, "longitude": 73.86})  # Pune
        page = context.new_page()
        try:
            held = []
            page.route("**/api/cities", lambda route: held.append(route))   # opens, never answers
            # NOT networkidle: the held request would keep that wait pending for the whole test.
            page.goto(live_site + i18n.url_for("kundali", "en"), wait_until="domcontentloaded")
            page.fill("#self-date", "1984-02-19")
            page.click("[data-step-next]")
            page.fill("#self-time", "09:05")
            page.click("[data-step-next]")
            page.wait_for_selector("[data-locate-go]", state="visible", timeout=10000)
            searching = page.get_attribute("[data-locate-status]", "data-searching")
            page.click("[data-locate-go]")
            page.wait_for_timeout(300)
            during = page.text_content("[data-locate-status]").strip()
            page.wait_for_timeout(21000)        # past REQUEST_TIMEOUT_MS
            after = page.text_content("[data-locate-status]").strip()
            for route in held:
                try:
                    route.abort()
                except Exception:
                    pass
        finally:
            browser.close()

    assert during == (searching or "").strip(), (
        f"precondition failed: the button did not enter its searching state, so what follows would prove "
        f"nothing ({during!r} vs {searching!r})")
    assert after != during, (
        "the locate button is still saying it is searching twenty seconds after a city list that will "
        "never arrive. It never asked for a position and it never will: the control is dead and the reader "
        "has no error, no result and nothing to press.")
    assert after, "the status went empty rather than reporting an outcome, which tells the reader nothing"


@pytest.mark.browser
def test_a_hung_pdf_request_gives_the_download_button_back(live_site):
    """The third bounded fetch. Without a deadline the button stays disabled for ever on a hung connection.

    Worth being precise about what the deadline is and is not doing here, because the reasoning differs from
    the chart's. The server does not cancel: the route is sync, so Chromium finishes and one unit of the
    IP's hourly render budget is spent whether or not we wait. What the abort buys is that the customer
    stops watching a dead control - and the finished PDF is cached, so the retry the "failed" note invites
    is a cache hit that costs them nothing and charges nothing again.

    Twenty seconds of wall clock, like its sibling, and for the same reason: the constant is the product's
    and there is no way in from outside the page."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as play:
        browser = play.chromium.launch(**pdf_browser.launch_options())
        page = browser.new_page(viewport={"width": 390, "height": 900})
        try:
            _fill_form(page, live_site)
            page.click("#submit-btn")
            page.wait_for_selector("#result:not([hidden])", timeout=30000)
            held = []
            page.route("**/api/chart/pdf", lambda route: held.append(route))
            page.click("#chart-pdf-btn")
            page.wait_for_timeout(300)
            busy = page.is_disabled("#chart-pdf-btn")
            page.wait_for_timeout(21000)            # past REQUEST_TIMEOUT_MS
            still_busy = page.is_disabled("#chart-pdf-btn")
            note = page.evaluate("""() => { const s = document.querySelector("#chart-pdf-status");
                return s && !s.hidden ? s.textContent.trim() : ""; }""")
            for route in held:
                try:
                    route.abort()
                except Exception:
                    pass
        finally:
            browser.close()

    assert busy, "precondition failed: the button never went busy, so what follows would prove nothing"
    assert not still_busy, (
        "the download button is still disabled twenty seconds after a PDF request that will never answer. "
        "There is no error, no spinner that ends and nothing to press: the only way out is a page reload.")
    assert note, "the button came back but said nothing about why the download did not happen"


# ---------- the wiring that calls the recovery, not just the decision ----------
#
# tests/test_consultation_web.py pins the DECISION (recoverFromSession) against real server state, and
# mutants on it die there. But deleting the handler branch that CALLS it leaves every one of those tests
# green - measured, by doing it - because they exercise the function directly. A decision nothing calls is
# not a fix, so the branch needs its own observation, and that has to be in a browser.
#
# The session here is real: /api/consultation/start needs no AI, so the page opens a genuine consultation.
# Only the two calls that follow are controlled - the send is failed at the network, and the re-read is the
# server's own answer with the exchange the server WOULD have recorded spliced in. That is precisely the
# state a lost response leaves behind, and it is the smallest fiction that can produce it without an AI key.


@pytest.mark.browser
def test_a_consultation_answer_lost_on_the_wire_is_recovered_rather_than_resold(live_site):
    """The handler branch: a failed send re-reads the session and shows the answer already paid for."""
    from playwright.sync_api import sync_playwright

    reply = "Recovered reply for the lost response."

    with sync_playwright() as play:
        browser = play.chromium.launch(**pdf_browser.launch_options())
        page = browser.new_page(viewport={"width": 390, "height": 900})
        try:
            page.goto(live_site + i18n.url_for("consultation", "en"), wait_until="networkidle")
            # This page calls person_fields WITHOUT stages, so there is no step nav to click through -
            # every field is visible at once. Measured by the first version of this test timing out on
            # [data-step-next], which does not exist here.
            page.fill("#self-date", "1984-02-19")
            page.fill("#self-time", "09:05")
            page.fill("#self-city", "Pune")
            page.wait_for_timeout(400)
            page.keyboard.press("ArrowDown")
            page.keyboard.press("Enter")
            page.click("#submit-btn")
            page.wait_for_selector("#chat-form:not([hidden])", timeout=30000)

            sends = []

            def lose_the_response(route):
                sends.append(1)
                route.abort()                    # the server's work, if any, is never heard about

            def splice_in_the_exchange(route):
                answer = route.fetch()           # the real session, so nothing else is invented
                view = answer.json()
                view["messages"] = (view.get("messages") or []) + [
                    {"role": "user", "content": "How is my career?", "kind": "ai"},
                    {"role": "assistant", "content": reply, "kind": "ai"}]
                route.fulfill(json=view)

            page.route("**/api/consultation/message", lose_the_response)
            page.route("**/api/consultation/session/**", splice_in_the_exchange)

            page.fill("#chat-input", "How is my career?")
            page.click("#chat-send")
            page.wait_for_timeout(1200)
            log = page.text_content("#chat-log")
            left_in_box = page.input_value("#chat-input")
            error = page.evaluate("""() => { const e = document.querySelector("#chat-error");
                return e && !e.hidden ? e.textContent.trim() : ""; }""")
        finally:
            browser.close()

    assert sends == [1], f"the send did not happen exactly once, so this proves nothing: {sends!r}"
    assert reply in log, (
        "the answer was on the server and the page did not go and get it. The reader has been charged a "
        "message credit for a reply they cannot see.")
    assert left_in_box == "", (
        f"their question was put back in the box next to an answer that already exists ({left_in_box!r}) - "
        "the obvious next action spends a second credit on a question already answered")
    assert not error, f"a recovered answer was shown alongside a failure message: {error!r}"
