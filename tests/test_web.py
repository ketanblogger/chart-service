"""Phase 2: public tool pages - now in three language trees (SEO map §2; URLs from app/web/i18n.py).

Two layers:
1. The server-rendered pages: status, SEO tags, form wiring, FAQ JSON-LD - for every tool page x language.
2. The "shows a result on submit" path without a browser: static/js/render.js is pure, so it is
   executed in an embedded V8 (mini-racer) - build the request body exactly as the page does,
   POST it to the real API, and feed the real response to the page's renderer.
Site-wide checks (uniqueness, hreflang, switcher, legacy 301s, prices) are in tests/test_pages_i18n.py; the Hindi /
Marathi result rendering is in tests/test_render_i18n.py.
"""

import json
import re
from collections import Counter
from html.parser import HTMLParser

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.web import STATIC_DIR, i18n, pages, site
from tests.reference_charts import CITY_REFERENCES, NEHRU, PRIMARY

client = TestClient(app)

TOOLS = list(i18n.TOOL_KEYS)  # kundali, matching, mangal-dosha, sade-sati
TOOL_PAGES = [(key, lang) for key in TOOLS for lang in i18n.LANGS]

# Two ways in, because the page has two, and both carry published charts (tests/reference_charts.py).
# * The FORM path (`_submit`) can only say what the form can say: a city from the combobox, which accepts
#   one of the ~124 public cities in app/engine/cities.py. Just one published chart can be expressed that
#   way (reference_charts.CITY_REFERENCES), so a PAIR needs a second birth, and that one is arbitrary -
#   it exists to exercise validation and error mapping, and nothing is ever asserted from it.
# * The API path (`_draw`) takes a birth the API accepts directly, which is how a chart given as
#   coordinates gets in. Every value asserted about a rendered result is read back out of the chart the
#   API returned, so changing the chart changes the expectations with it.
PERSON = {"name": "Test <b>User</b>", **CITY_REFERENCES[0].city_request()}
PARTNER = {"name": "", "date": "1986-11-03", "time": "21:40", "city": "Nagpur"}  # arbitrary, never a real person

# How render.js labels the grahas in the chart SVG - a display convention, not chart data.
GRAHA_CODES = {"Sun": "Su", "Moon": "Mo", "Mars": "Ma", "Mercury": "Me", "Jupiter": "Ju",
               "Venus": "Ve", "Saturn": "Sa", "Rahu": "Ra", "Ketu": "Ke"}


def _ordinal(number: int) -> str:
    return f"{number}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(number % 10 if number % 100 not in (11, 12, 13) else 0, 'th') }"


def _birth_line(echoed: dict) -> tuple[str, str, str]:
    """What the page must print for a birth: date, clock and place, formatted as render.js does (no-break
    spaces inside the date and before the meridiem; a birth given as coordinates has no city to name).

    THIS MIRROR IS DELIBERATE. Restating the formatter by hand is what makes the two going out of step turn
    the suite RED. When it fails, the fix is to update this to match render.js - not to loosen the
    assertion, which would remove the only thing connecting them."""
    from datetime import date as _date

    born = _date.fromisoformat(echoed["date"])
    hour, minute = (int(part) for part in echoed["time"].split(":")[:2])
    # No-break space between the clock and its meridiem, as render.js writes it and for the same reason the
    # date carries them: half of "1:15 AM" is a complete and different time.
    clock = f"{hour % 12 or 12}:{minute:02d}\u00a0{'AM' if hour < 12 else 'PM'}"
    place = echoed["city"] or f"{echoed['lat']}, {echoed['lon']}"
    return f"{born.day}\u00a0{born:%b}\u00a0{born.year}", clock, place


class _Page(HTMLParser):
    """Collects the bits of a page the tests look at."""

    def __init__(self, html: str):
        super().__init__()
        self.title = ""
        self.meta: dict[str, str] = {}
        self.links: dict[str, str] = {}
        self.ids: dict[str, dict] = {}
        self.json_ld: list[dict] = []
        self.h1: list[str] = []
        self.products: list[dict] = []
        self.scripts: list[str] = []
        self._capture: str | None = None
        self._buffer = ""
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta" and (a.get("name") or a.get("property")):
            self.meta[a.get("name") or a.get("property")] = a.get("content", "")
        elif tag == "link" and a.get("rel"):
            self.links[a["rel"]] = a.get("href", "")
        elif tag == "script" and a.get("src"):
            self.scripts.append(a["src"])
        if a.get("id"):
            self.ids[a["id"]] = {"tag": tag, **a}
        if "data-product" in a:
            self.products.append(a)
        if tag in ("title", "h1") or (tag == "script" and a.get("type") == "application/ld+json"):
            self._capture, self._buffer = ("json_ld" if tag == "script" else tag), ""

    def handle_data(self, data):
        if self._capture:
            self._buffer += data

    def handle_endtag(self, tag):
        if self._capture == "title" and tag == "title":
            self.title = self._buffer.strip()
        elif self._capture == "h1" and tag == "h1":
            self.h1.append(self._buffer.strip())
        elif self._capture == "json_ld" and tag == "script":
            self.json_ld.append(json.loads(self._buffer))
        else:
            return
        self._capture = None


def _get(path: str) -> _Page:
    response = client.get(path)
    assert response.status_code == 200, path
    assert response.headers["content-type"].startswith("text/html")
    return _Page(response.text)


# ---------- pages ----------


def test_configured_pages_are_the_mvp_tools():
    # TOOLS is the nav set: the four calculators every tree has. pages.TOOLS also carries the calculators that
    # exist in one tree only, which are deliberately absent from the navigation - hence the two are not equal.
    assert TOOLS == ["kundali", "matching", "mangal-dosha", "sade-sati"] == list(i18n.TOOL_KEYS)
    assert list(pages.TOOLS) == TOOLS + ["sidereal"]
    assert {key: spec.endpoint for key, spec in pages.TOOLS.items()} == {
        "kundali": "/api/chart", "matching": "/api/matching", "mangal-dosha": "/api/mangal-dosha",
        "sade-sati": "/api/sade-sati", "sidereal": "/api/chart"}  # the sidereal page IS the birth chart


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_home_links_to_every_tool_in_its_own_language(lang):
    response = client.get(i18n.url_for("home", lang))
    assert response.status_code == 200
    for key in (*TOOLS, "consultation", "rashifal-hub", "rashifal-weekly"):
        assert f'href="{i18n.url_for(key, lang)}"' in response.text, key
    for rashi in i18n.RASHI_KEYS:  # today's reading of all 12 rashis, one click from the home page
        assert f'href="{i18n.url_for("rashifal-reading", lang, rashi=rashi, period="today")}"' in response.text
    strip = response.text.split('id="rashi-strip-heading"', 1)[1]
    first = re.search(r'href="([^"]+)"', strip).group(1)  # highest-demand rashi first (SEO map §4)
    assert first == i18n.url_for("rashifal-reading", lang, rashi=i18n.rashis_by_demand(lang)[0], period="today")
    page = _Page(response.text)
    assert page.links["canonical"] == "http://localhost:8000" + i18n.url_for("home", lang)
    assert len(page.h1) == 1 and page.h1 == [pages.get("home", lang).h1]


@pytest.mark.parametrize("key, lang", TOOL_PAGES)
def test_tool_page_seo_and_structure(key, lang):
    config, spec, path = pages.get(key, lang), pages.TOOLS[key], i18n.url_for(key, lang)
    page = _get(path)

    assert page.title == f"{config.title} | {site.SITE_NAME}"
    assert page.meta["description"] == config.meta_description
    assert 70 <= len(config.meta_description) <= 220
    assert page.links["canonical"] == f"http://localhost:8000{path}"
    assert page.meta["og:url"] == page.links["canonical"]
    assert page.meta["og:title"] == page.title
    assert page.meta["og:description"] == config.meta_description
    assert page.meta["viewport"]
    assert page.h1 == [config.h1]

    # form wired to the right API route, renderer and LANGUAGE
    form = page.ids["tool-form"]
    assert form["tag"] == "form"
    assert form["data-endpoint"] == spec.endpoint
    assert form["data-renderer"] == spec.renderer
    assert form["data-lang"] == lang
    people = ["boy", "girl"] if spec.form == "pair" else ["self"]
    for person in people:
        for field in ("name", "date", "time", "city"):
            assert f"{person}-{field}" in page.ids
        assert page.ids[f"{person}-date"]["type"] == "date"
        assert page.ids[f"{person}-time"]["type"] == "time"
        assert page.ids[f"{person}-city"]["role"] == "combobox"
    assert "result" in page.ids and "result-body" in page.ids
    assert any(src.startswith("/static/js/render.js") for src in page.scripts)
    assert any(src.startswith("/static/js/app.js") for src in page.scripts)

    # paid-product hook: one button per tier the page sells, in that order, each priced by the catalogue
    offered = pages.purchase_options(key)
    assert [p["data-product"] for p in page.products] == [option["product"] for option in offered]
    for button, option in zip(page.products, offered):
        assert button["data-price-inr"] == str(pages.prices()[option["product"]])
    assert spec.product in [option["product"] for option in offered]  # the page's headline product is one of them

    # FAQ JSON-LD mirrors the visible FAQ
    assert 4 <= len(config.faqs) <= 8
    faq = next(block for block in page.json_ld if block["@type"] == "FAQPage")
    assert [q["name"] for q in faq["mainEntity"]] == [question for question, _ in config.faqs]
    assert all(q["acceptedAnswer"]["text"] for q in faq["mainEntity"])
    html = client.get(path).text
    for question, _ in config.faqs:
        assert f"<summary>{question}</summary>".replace("'", "&#39;").replace('"', "&#34;") in html

    # form labels and footer disclaimer in the page language
    ui = pages.ui(lang)
    for label in ("date", "time", "city", "city_hint", "form_note", "faq_heading", "more_heading"):
        assert ui[label] in html, label
    assert ui["disclaimer"] in html
    if lang == "en":
        assert "faith-based" in html and "health, legal or financial" in html


def test_form_labels_differ_per_language():
    labels = {lang: pages.ui(lang) for lang in i18n.LANGS}
    for key in ("date", "time", "city", "form_note", "faq_heading", "disclaimer", "home"):
        assert len({labels[lang][key] for lang in i18n.LANGS}) == 3, key
    assert "जन्म" in labels["hi"]["date"] and "जन्म" in labels["mr"]["date"]


def test_each_page_prices_its_own_product_from_the_catalogue():
    """What every page charges is its own product's catalogue price - the kundali page quotes the book, which is
    the headline of its two tiers. The launch prices themselves are pinned once, in tests/test_pages_i18n.py."""
    prices = pages.prices()
    assert {key: pages.product_price(key) for key in pages.TOOLS} == \
           {key: prices[spec.product] for key, spec in pages.TOOLS.items()}
    assert pages.product_price("kundali") == prices["kundali-report"] > prices["kundali-report-simple"]
    offer = pages.chat_offer()
    assert offer == {"price_inr": prices[pages.CONSULTATION_PRODUCT], "pack_messages": 10, "free_messages": 2}


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_the_kundali_page_offers_both_report_tiers_and_the_others_one_button(lang):
    """Two tiers of the same reading: the concise report and the book, cheapest first, each with its own one-line
    promise. Every other tool page still renders exactly one button, as it did when there was one price."""
    page = _get(i18n.url_for("kundali", lang))
    prices = pages.prices()
    assert [(p["data-product"], p["data-price-inr"]) for p in page.products] == \
        [(product, str(prices[product])) for product in ("kundali-report-simple", "kundali-report")]
    assert prices["kundali-report-simple"] < prices["kundali-report"], "cheapest tier first"
    copy = pages.get("kundali", lang)
    for key in ("simple", "detailed"):
        assert copy.extra[f"buy_{key}"] and copy.extra[f"gets_{key}"]
    labels = [option["label"] for option in pages.purchase_offers("kundali", copy)]
    assert labels == [copy.extra["buy_simple"], copy.extra["buy_detailed"]] and len(set(labels)) == 2
    for key in ("matching", "mangal-dosha", "sade-sati"):
        single = _get(i18n.url_for(key, lang))
        assert [p["data-product"] for p in single.products] == [pages.TOOLS[key].product]
        assert pages.purchase_offers(key, pages.get(key, lang))[0]["label"] == pages.get(key, lang).product.button


def test_a_retired_product_is_never_offered(monkeypatch):
    """`consultation-pack` is honoured for the people who bought one and refused for everyone else: the pages read
    `catalogue.sellable`, so a retired tier stops being offered without a line of page code changing."""
    from app.payments import catalogue

    assert catalogue.PACK not in [option["product"] for option in pages.purchase_options("consultation")]
    price, report, _ = catalogue._PACKS[catalogue.PREMIUM_PACK]  # retire it at whatever it costs today
    monkeypatch.setitem(catalogue._PACKS, catalogue.PREMIUM_PACK, (price, report, False))
    offered = pages.purchase_options("consultation")
    assert [option["product"] for option in offered] == [catalogue.BASIC_PACK]
    page = _get(i18n.url_for("consultation", "en"))
    assert [p["data-product"] for p in page.products] == [catalogue.BASIC_PACK]


def test_canonical_uses_base_url_env(monkeypatch):
    monkeypatch.setenv("BASE_URL", "https://example.test/")
    page = _get("/hi/sade-sati")
    assert page.links["canonical"] == "https://example.test/hi/sade-sati"
    assert page.meta["og:url"] == "https://example.test/hi/sade-sati"
    alternates = dict(re.findall(r'hreflang="([^"]+)" href="([^"]+)"', client.get("/hi/sade-sati").text))
    assert alternates["mr"] == "https://example.test/mr/sade-sati" and alternates["x-default"] == "https://example.test/sade-sati"


def test_static_assets_and_other_routes_still_work():
    for path in ("/static/css/site.css", "/static/js/render.js", "/static/js/app.js", "/static/favicon.svg"):
        assert client.get(path).status_code == 200, path
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/no-such-page").status_code == 404


def test_pages_have_no_external_assets_or_ai_calls():
    """No CDN / third-party requests, and the free tools only ever talk to the calculation API."""
    # One named exception, an allowlist of a single URL prefix rather than a match on "google": Google
    # Analytics' loader, in base.html, whose host is allowed in the CSP. Anything else external still fails.
    analytics = "https://www.googletagmanager.com/gtag/js?id="
    for path in [i18n.url_for(key, lang) for key in ("home", *TOOLS) for lang in i18n.LANGS]:
        html = client.get(path).text
        for url in re.findall(r'(?:src|href)="([^"]+)"', html):
            if url.startswith(analytics):
                continue
            assert url.startswith(("/", "#")) or url.startswith(site.base_url()), url
    app_js = (STATIC_DIR / "js" / "app.js").read_text(encoding="utf-8")
    # An allowlist, not a count: every fetch the tool pages make has to be named here on purpose. All three are
    # first-party and none reaches a model - /api/chart/pdf is the free Basic Chart PDF, which app/pdf/basic.py
    # renders from engine values only (tests/test_pdf.py makes every ClaudeClient raise and still expects 200).
    assert set(re.findall(r"fetch\(([^,)]+)", app_js)) == {"endpoint", '"/api/cities"', '"/api/chart/pdf"'}
    assert "fetch(" not in (STATIC_DIR / "js" / "render.js").read_text(encoding="utf-8")
    # On every page. The nav used to be a horizontal scroller and this asserted it moved only its OWN scroll;
    # it is a wrapping list with a disclosure now, so what has to stay true is that nav.js still never fetches
    # anything and never moves the PAGE - not by scrollIntoView, not by window.scroll.
    nav_js = (STATIC_DIR / "js" / "nav.js").read_text(encoding="utf-8")
    assert "fetch(" not in nav_js and "scrollIntoView" not in nav_js
    assert "window.scroll" not in nav_js and "scrollTo(" not in nav_js and "scrollTop" not in nav_js
    assert all("/static/js/nav.js" in client.get(i18n.url_for(key, "mr")).text for key in ("home", "rashifal-hub", "kundali"))


# ---------- submit -> result, with the page's own JavaScript ----------


@pytest.fixture(scope="module")
def js():
    mini_racer = pytest.importorskip("py_mini_racer")
    ctx = mini_racer.MiniRacer()
    ctx.eval((STATIC_DIR / "js" / "render.js").read_text(encoding="utf-8"))

    def call(expression: str, **variables):
        """Evaluate a JS expression with JSON-able variables in scope; returns the JSON-decoded value."""
        names = ", ".join(variables)
        args = ", ".join(json.dumps(value, ensure_ascii=False) for value in variables.values())
        return json.loads(ctx.eval(f"JSON.stringify((function({names}) {{ return {expression}; }})({args}))"))

    return call


def _draw(js, key: str, body: dict, ctx: dict) -> tuple[dict, str]:
    """POST a birth the API accepts and render the response with the page's own renderer."""
    config = pages.TOOLS[key]
    response = client.post(config.endpoint, json=body)
    assert response.status_code == 200, response.text
    html = js(f"AstroRender.renderers[{json.dumps(config.renderer)}](data, ctx)", data=response.json(), ctx=ctx)
    assert "undefined" not in html and "NaN" not in html and "[object" not in html and ">null<" not in html
    return response.json(), html


def _submit(js, key: str, values: dict, ctx: dict) -> tuple[dict, str]:
    """What the browser does on submit: validate, build the body, POST, render. Returns (response, html)."""
    config = pages.TOOLS[key]
    assert js("AstroRender.validate(formType, values, '2026-01-01')", formType=config.form, values=values) == []
    return _draw(js, key, js("AstroRender.buildPayload(formType, values)", formType=config.form, values=values), ctx)


def test_every_page_renderer_exists(js):
    # the four tool pages, plus the chart header of /consultation (Phase 5, tests/test_consultation_web.py)
    assert sorted(js("Object.keys(AstroRender.renderers)")) == sorted({spec.renderer for spec in pages.TOOLS.values()} | {"consultation"})


def test_janam_kundali_result(js):
    """The reference chart goes in through the API; every expectation comes back out of it."""
    data, html = _draw(js, "kundali", PRIMARY.request(), {"name": PERSON["name"]})
    assert "Test &lt;b&gt;User&lt;/b&gt;" in html and "<b>User" not in html  # name is escaped
    lagna, moon, nakshatra = data["lagna"], data["grahas"]["Moon"]["sign"], data["janma_nakshatra"]
    for expected in (lagna["sign"]["name"], lagna["sign"]["devanagari"], moon["name"], moon["devanagari"],
                     nakshatra["name"], nakshatra["devanagari"],
                     lagna["degree_dms"].split("'")[0],  # degrees and minutes, before the escaped quote
                     *_birth_line(data["input"]),
                     "Current mahadasha", "Mahadasha timeline", "Graha positions", "<svg"):
        assert expected in html, expected
    current = data["dasha"]["current"]["mahadasha"]["lord"]["name"]
    assert current in html
    assert html.count('class="timeline__item') == 9
    assert html.count('class="timeline__item is-current"') == 1
    for position in data["grahas"].values():  # every graha row: degree + nakshatra present
        assert position["degree_dms"].replace('"', "&quot;").replace("'", "&#39;") in html
        assert position["nakshatra"]["devanagari"] in html


def test_north_indian_chart_places_signs_and_grahas(js):
    """Whatever the chart says, the diamond must show: the lagna sign number in the top-centre house, every
    graha in the house the chart puts it in, and the retrograde mark on exactly the retrograde ones."""
    chart = client.post("/api/chart", json=PRIMARY.request()).json()
    svg = js("AstroRender.chartSvg(chart, 'en')", chart=chart)
    texts = re.findall(r'<text class="([^"]+)" x="([\d.]+)" y="([\d.]+)">([^<]*)', svg)
    signs = [(float(x), float(y), t) for cls, x, y, t in texts if cls == "kundali__sign"]
    grahas = {t: (float(x), float(y)) for cls, x, y, t in texts if cls.startswith("kundali__graha")}

    assert len(signs) == 12
    assert sorted(int(t) for _, _, t in signs) == list(range(1, 13))
    assert set(grahas) == {"Lg", *GRAHA_CODES.values()}
    # house 1 = top-centre diamond, and it carries this chart's own lagna sign number
    lagna_sign = chart["lagna"]["sign"]["index"]
    top = min(signs, key=lambda s: abs(s[0] - 200) + abs(s[1] - 100))
    assert top[2] == str(lagna_sign)
    assert abs(grahas["Lg"][0] - 200) < 40 and grahas["Lg"][1] < 200  # the lagna marker is in that house

    # Each sign number is drawn inside its own house, so the twelve of them locate the twelve houses: a
    # graha must land nearer to its own house's number than to any other's.
    at = {int(text): (x, y) for x, y, text in signs}
    house_at = {house: at[(lagna_sign - 1 + house - 1) % 12 + 1] for house in range(1, 13)}
    for graha, code in GRAHA_CODES.items():
        x, y = grahas[code]
        nearest = min(house_at, key=lambda h: (x - house_at[h][0]) ** 2 + (y - house_at[h][1]) ** 2)
        assert nearest == chart["grahas"][graha]["house"], (graha, nearest)
        # the R mark follows the chart, except on the shadow grahas, which are always retrograde
        retro = chart["grahas"][graha]["retrograde"] and graha not in ("Rahu", "Ketu")
        assert (f'{code}<tspan class="kundali__retro"' in svg) == retro, graha

    deva = js("AstroRender.chartSvg(chart, 'deva')", chart=chart)
    assert ">चं" in deva and ">सू" in deva and ">Mo" not in deva



# Births the engine flags on `chart.accuracy`. The flags are the engine's, so the tests assert what the engine
# says rather than pinning the numbers: only ~6% of charts trip either one, and a caveat on every chart would be
# the boilerplate people learn to skip.
NEAR_A_BOUNDARY = {"date": "1889-11-14", "time": "23:30", "city": "Allahabad"}   # both flags: 25 km, Madras time
WARTIME = {"date": "1944-05-04", "time": "06:10", "city": "Mumbai"}              # clock only: India ran +06:30
ORDINARY = {"date": "1990-05-04", "time": "06:10", "city": "Mumbai"}            # neither: 990 km from a sign change


def test_the_chart_says_what_would_change_the_rising_sign(js):
    """The place caveat names the distance and the sign it would become, both read from the chart."""
    data, html = _draw(js, "kundali", NEAR_A_BOUNDARY, {})
    boundary = data["accuracy"]["lagna_boundary"]
    assert boundary["sensitive"], "this birth is the fixture for the sensitive branch"
    note = html.split('class="block accuracy"', 1)[1].split("</section>", 1)[0]
    assert f"{round(boundary['km_to_change_sign'])}&nbsp;km" in note
    assert boundary["adjacent_sign"]["name"] in note and data["lagna"]["sign"]["name"] in note
    assert data["input"]["city"] in note  # the place they picked, named
    assert "Moon sign, nakshatra and dasha dates do not depend on the birthplace" in note


def test_the_chart_names_the_clock_a_historical_birth_was_converted_on(js):
    """The clock caveat names the era and how far it ran from today's IST - not "pre-1906", which would miss the
    1942-45 wartime hour, the case with living customers."""
    data, html = _draw(js, "kundali", WARTIME, {})
    clock = data["accuracy"]["clock"]
    assert clock["non_standard"] and clock["era"] == "wartime"
    note = html.split('class="block accuracy"', 1)[1].split("</section>", 1)[0]
    drift = round(abs(clock["offset_seconds"] - 19800) / 60)
    assert f"{drift} minutes ahead of today's Indian Standard Time" in note
    assert "1942-45" in note and "1906" not in note
    assert "boundary" not in note, "this chart is not near a sign boundary, so only the clock note belongs"


def test_both_caveats_can_appear_and_an_ordinary_chart_gets_none(js):
    both = _draw(js, "kundali", NEAR_A_BOUNDARY, {})[1].split('class="block accuracy"', 1)[1].split("</section>", 1)[0]
    assert both.count("<p>") == 2, "a birth can trip the place and the clock caveat at once"
    data, html = _draw(js, "kundali", ORDINARY, {})
    assert not data["accuracy"]["lagna_boundary"]["sensitive"] and not data["accuracy"]["clock"]["non_standard"]
    assert "block accuracy" not in html, "no caveat on a chart the engine does not flag"


def test_chart_handles_a_crowded_house(js):
    chart = client.post("/api/chart", json={"date": "2000-05-04", "time": "06:10", "city": "Mumbai"}).json()
    assert max(len(h["grahas"]) for h in chart["houses"]) >= 5  # the May 2000 stellium
    svg = js("AstroRender.chartSvg(chart, 'en')", chart=chart)
    ys = [float(y) for y in re.findall(r'class="kundali__graha[^"]*" x="[\d.]+" y="([\d.]+)"', svg)]
    assert svg.count('class="kundali__graha') == 10 and all(0 < y < 400 for y in ys)


def test_kundali_matching_result(js):
    """Two published charts (reference_charts.MATCH notes say why these): score, every koota row, the
    verdict label and the dosha blocks, each checked against what the API returned for this pair."""
    data, html = _draw(js, "matching", {"boy": PRIMARY.request(), "girl": NEHRU.request()},
                       {"names": {"boy": "A", "girl": "B"}})
    assert f'<span class="score__total">{data["total"]:g}</span> / 36' in html
    assert f'{data["percentage"]:g}%' in html
    for label in ("Varna", "Vashya", "Tara", "Yoni", "Graha Maitri", "Gana", "Bhakoot", "Nadi"):
        assert label in html
    for koota in data["kootas"]:
        assert f'<strong>{koota["score"]:g}</strong> / {koota["max"]}' in html
        assert koota["boy"] in html and koota["girl"] in html
    # the verdict is a translated label for the API's verdict key, not the key itself
    verdict = html.split('class="score__verdict"><strong>', 1)[1].split("</strong>", 1)[0]
    assert verdict.startswith(f'{data["percentage"]:g}% &middot; ') and data["verdict"] not in verdict
    # dosha blocks appear exactly when this pair has them
    assert "Mangal dosha comparison" in html
    assert ("Mangal dosha: compatible" in html) == data["mangal_dosha"]["compatible"]
    # both doshas are always named; the badge states what this pair actually has
    for label, dosha in (("Nadi dosha", data["doshas"]["nadi_dosha"]),
                         ("Bhakoot dosha", data["doshas"]["bhakoot_dosha"])):
        badge = ("Not present" if not dosha["present"]
                 else "Present, cancelled by classical exception" if dosha["cancellation_applies"] else "Present")
        assert f"<strong>{label}</strong> " in html
        assert re.search(rf"<strong>{label}</strong> <span[^>]*>{badge}</span>", html), (label, badge)
    for side in ("boy", "girl"):  # each side's Moon sign and nakshatra, in Devanagari, from the response
        assert data[side]["moon_sign"]["devanagari"] in html
        assert data[side]["moon_nakshatra"]["devanagari"] in html



def test_mangal_dosha_result(js):
    """PRIMARY is the chart with a dosha AND a classical cancellation (see tests/reference_charts.py), so
    the "present, with mitigating factors" branch is exercised by a published chart rather than a pinned one."""
    data, html = _draw(js, "mangal-dosha", PRIMARY.request(), {"name": ""})
    dosha = data["mangal_dosha"]
    assert dosha["present"] and dosha["cancellation_applies"]
    assert "Mangal dosha present, with mitigating factors" in html
    assert dosha["intensity"].capitalize() in html
    # every vantage point's house is named, as often as the chart names it
    houses = Counter(dosha[f"from_{point}"]["mars_house"] for point in ("lagna", "moon", "venus"))
    for house, times in houses.items():
        assert html.count(f"{_ordinal(house)} house") == times, (house, times)
    assert html.count("Applies to your chart") == sum(rule["applies"] for rule in dosha["cancellations"])
    for rule in dosha["cancellations"]:
        assert rule["description"].split(",")[0].split("(")[0].strip() in html
    for note in dosha["notes"]:
        assert note in html

    # the other two states, through the form: no dosha, and a dosha with no cancellation. These births are
    # arbitrary - only the branch they land in matters.
    clear, clear_html = _submit(js, "mangal-dosha", {"self": {"name": "", "date": "1988-01-10", "time": "08:00", "city": "Pune"}}, {})
    assert not clear["mangal_dosha"]["present"]
    assert "No Mangal dosha" in clear_html and "Not manglik" in clear_html and "Applies to your chart" not in clear_html

    plain, plain_html = _submit(js, "mangal-dosha", {"self": {"name": "", "date": "1988-10-10", "time": "08:00", "city": "Pune"}}, {})
    assert plain["mangal_dosha"]["present"] and not plain["mangal_dosha"]["cancellation_applies"]
    assert '<p class="banner__title">Mangal dosha present</p>' in plain_html
    assert plain["mangal_dosha"]["intensity"].capitalize() in plain_html



def test_sade_sati_result_all_states(js):
    data, html = _draw(js, "sade-sati", PRIMARY.request(), {"name": "K"})
    sade_sati = data["sade_sati"]
    cycle = sade_sati["cycle"]
    assert html.count("<tr") == len(cycle["periods"]) + 1
    assert ("Sade sati is active" in html) == sade_sati["active"]
    assert sade_sati["moon_sign"]["name"] in html and sade_sati["moon_sign"]["devanagari"] in html

    # Sweep the Moon through the zodiac (2.3-day steps) so active and not-active states both render.
    seen = set()
    for step in range(12):
        values = {"self": {"name": "", "date": f"1990-01-{1 + step * 2:02d}", "time": "12:00", "city": "Nagpur"}}
        result, result_html = _submit(js, "sade-sati", values, {})
        ss = result["sade_sati"]
        seen.add(ss["phase"])
        if ss["active"]:
            assert "Sade sati is active" in result_html and "Your current sade sati" in result_html
            assert result_html.count('<tr class="is-current"') == 1
        elif ss["cycle"]["which"] == "next":
            assert "Sade sati is not active" in result_html and "Your next sade sati" in result_html
    assert None in seen and seen & {"rising", "peak", "setting"}


def test_validation_and_api_error_mapping(js):
    empty = {"self": {"name": "", "date": "", "time": "", "city": " "}}
    assert [e["field"] for e in js("AstroRender.validate('single', v, '2026-01-01')", v=empty)] == ["date", "time", "city"]
    future = {"self": {"date": "2030-01-01", "time": "10:00", "city": "Pune"}}
    assert "future" in js("AstroRender.validate('single', v, '2026-01-01')", v=future)[0]["message"]
    pair = js("AstroRender.validate('pair', v, '2026-01-01')", v={"boy": PERSON, "girl": {**PARTNER, "time": ""}})
    assert pair == [{"person": "girl", "field": "time", "message": pair[0]["message"]}]

    # real 422 bodies from the API land on the right field
    bad_city = client.post("/api/chart", json={**{k: v for k, v in PERSON.items() if k != "name"}, "city": "Atlantis"})
    assert bad_city.status_code == 422
    errors = js("AstroRender.parseApiError(422, body, 'single')", body=bad_city.json())
    assert [(e["person"], e["field"]) for e in errors] == [("self", "city")]

    bad_pair = client.post("/api/matching", json={"boy": {**PERSON, "date": "1917-11-31"},  # a date that does not exist
                                                  "girl": {**PARTNER, "city": "Atlantis"}})
    assert bad_pair.status_code == 422
    errors = js("AstroRender.parseApiError(422, body, 'pair')", body=bad_pair.json())
    assert sorted((e["person"], e["field"]) for e in errors) == [("boy", "date"), ("girl", "city")]

    assert js("AstroRender.parseApiError(500, body, 'single')", body=None)[0]["field"] is None
    assert js("AstroRender.parseApiError(422, body, 'single')", body={"detail": "bad timezone"})[0]["message"] == "bad timezone"


def test_city_filter_uses_the_api_city_list(js):
    cities = client.get("/api/cities").json()["cities"]
    names = lambda query: [c["name"] for c in js("AstroRender.filterCities(cities, q, 5)", cities=cities, q=query)]  # noqa: E731
    first = cities[0]["name"]  # the list is app/engine/cities.py, public geography
    assert first in names(first[:3].lower())
    assert names("pun")[0] == "Pune"
    assert names("zzzz") == []
    assert len(names("")) == 5
