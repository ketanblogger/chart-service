"""The page JavaScript speaks English, Hindi and Marathi: static/js/render.js (results, validation, API errors,
matching by name) and static/js/chat.js (chat UI strings). Both are pure, so they run here in an embedded V8
(mini-racer) against REAL API responses, exactly as tests/test_web.py does for English.

Language rules checked: Hindi uses मंगल / शनि / तुला (and भाव), Marathi uses मंगळ / शनी / तूळ (and स्थान); a hi / mr
result contains no leftover English UI words.
"""

import json
import re
from collections import Counter

import pytest

from tests.reference_charts import NEHRU, PRIMARY

LANGS = ("en", "hi", "mr")
# The published reference charts (tests/reference_charts.py) go in as coordinates, which the API takes
# directly; PRIMARY is the one with the richest features - a mangal dosha at "high" WITH a classical
# cancellation, which is the branch this file checks in three languages.
PERSON, PARTNER = PRIMARY.request(), NEHRU.request()
LIBRA_MOON = {"date": "1990-01-19", "time": "12:00", "city": "Nagpur"}  # Moon in Tula: तुला (hi) vs तूळ (mr)
# A birth the engine flags on both accuracy counts (25 km from a sign change, and Madras time). Given as
# coordinates, so no city name is echoed into the note and the whole of it must be Devanagari on a hi / mr page.
FLAGGED = {"date": "1889-11-14", "time": "23:30", "lat": 25.4358, "lon": 81.8463, "timezone": "Asia/Kolkata"}

# The renderer's own vocabulary (render.js: MONTHS_L, VERDICTS, ORDINALS, INTENSITY), keyed by what the
# API returns. Translations have to be spelled out somewhere - this is a test about words - but they are
# looked up by the chart's own values, so a different chart moves the expectation with it.
MONTH_WORD = {"hi": ["जनवरी", "फरवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर"],
              "mr": ["जानेवारी", "फेब्रुवारी", "मार्च", "एप्रिल", "मे", "जून", "जुलै", "ऑगस्ट", "सप्टेंबर", "ऑक्टोबर", "नोव्हेंबर", "डिसेंबर"]}
ORDINAL_WORD = {"hi": ["पहला", "दूसरा", "तीसरा", "चौथा", "पाँचवाँ", "छठा", "सातवाँ", "आठवाँ", "नौवाँ", "दसवाँ", "ग्यारहवाँ", "बारहवाँ"],
                "mr": ["पहिले", "दुसरे", "तिसरे", "चौथे", "पाचवे", "सहावे", "सातवे", "आठवे", "नववे", "दहावे", "अकरावे", "बारावे"]}
INTENSITY_WORD = {"en": {"none": "None", "low": "Low", "medium": "Medium", "high": "High"},
                  "hi": {"none": "नहीं", "low": "कम", "medium": "मध्यम", "high": "अधिक"},
                  "mr": {"none": "नाही", "low": "कमी", "medium": "मध्यम", "high": "अधिक"}}
GRAHA_WORD = {"hi": {"Sun": "सूर्य", "Moon": "चंद्र", "Mars": "मंगल", "Mercury": "बुध", "Jupiter": "गुरु",
                     "Venus": "शुक्र", "Saturn": "शनि", "Rahu": "राहु", "Ketu": "केतु"},
              "mr": {"Sun": "सूर्य", "Moon": "चंद्र", "Mars": "मंगळ", "Mercury": "बुध", "Jupiter": "गुरू",
                     "Venus": "शुक्र", "Saturn": "शनी", "Rahu": "राहू", "Ketu": "केतू"}}
VERDICT_WORD = {"en": {"below_average": "Below average match", "average": "Average match", "good": "Good match",
                       "excellent": "Excellent match"},
                "hi": {"below_average": "औसत से कम मिलान", "average": "मध्यम मिलान", "good": "अच्छा मिलान",
                       "excellent": "उत्तम मिलान"},
                "mr": {"below_average": "सरासरीपेक्षा कमी गुणमेलन", "average": "मध्यम गुणमेलन",
                       "good": "चांगले गुणमेलन", "excellent": "उत्तम गुणमेलन"}}


# What hi and mr call each part of the day: [hour the part STARTS, the word], last row wrapping midnight.
# Mirrors DAY_PARTS in static/js/render.js. The two hold the same hours today and that is NOT an invariant -
# see the tables there for the two boundaries under native-speaker review.
DAY_PARTS = {
    "hi": [(4, "\u0938\u0941\u092c\u0939"), (12, "\u0926\u094b\u092a\u0939\u0930"), (16, "\u0936\u093e\u092e"), (20, "\u0930\u093e\u0924")],
    "mr": [(4, "\u0938\u0915\u093e\u0933\u0940"), (12, "\u0926\u0941\u092a\u093e\u0930\u0940"), (16, "\u0938\u0902\u0927\u094d\u092f\u093e\u0915\u093e\u0933\u0940"), (20, "\u0930\u093e\u0924\u094d\u0930\u0940")],
}


def day_part_word(lang: str, hour: int) -> str:
    word = DAY_PARTS[lang][-1][1]          # before the first boundary is the small hours: night wraps
    for start, name in DAY_PARTS[lang]:
        if hour >= start:
            word = name
    return word


def born_words(echoed: dict, lang: str) -> tuple[str, str]:
    """How the page must print this birth's date and clock in `lang`.

    render.js joins a date with no-break spaces, and joins a clock to its qualifier the same way, for the
    same reason: half of "1:15 AM" or of "\u0936\u093e\u092e 7:30" is a complete and DIFFERENT time, so neither pair may
    be split across a line. English says AM/PM; hi and mr say the part of the day, which is what those
    languages use in place of a meridiem - a 24-hour clock was printed here until it turned out that a
    reader who means \u0936\u093e\u092e 7:30 and types 07:30 reads "07:30" back without noticing.

    THIS MIRROR IS DELIBERATE. It restates render.js's formatting by hand so that the two going out of step
    turns the suite RED - which is how the day-part change was caught in the first place. When it fails with
    something like "expected 01:15, got \u0930\u093e\u0924\u094d\u0930\u0940 1:15" it is reporting a real divergence and the fix is to
    update this function to match the formatter. It is NOT an over-strict assertion to be relaxed; relaxing
    it removes the only thing connecting the two."""
    from datetime import date as _date

    born = _date.fromisoformat(echoed["date"])
    hour, minute = (int(part) for part in echoed["time"].split(":")[:2])
    twelve = f"{hour % 12 or 12}:{minute:02d}"
    if lang == "en":
        return f"{born.day}\u00a0{born:%b}\u00a0{born.year}", f"{twelve}\u00a0{'AM' if hour < 12 else 'PM'}"
    return (f"{born.day}\u00a0{MONTH_WORD[lang][born.month - 1]}\u00a0{born.year}",
            f"{day_part_word(lang, hour)}\u00a0{twelve}")


def _chart_words(chart: dict) -> tuple[str, str, str]:
    """This chart's lagna sign, Moon sign and janma nakshatra in Devanagari, as the API states them. Hindi
    and Marathi spell all of these the same way except Tula (तुला / तूळ), which no reference chart has in
    these three places - LIBRA_MOON exists to cover that difference deliberately."""
    return (chart["lagna"]["sign"]["devanagari"], chart["grahas"]["Moon"]["sign"]["devanagari"],
            chart["janma_nakshatra"]["devanagari"])


def dosha_houses(dosha: dict) -> list[int]:
    """The houses this chart's mangal dosha is counted in, from the three vantage points."""
    return [dosha[f"from_{point}"]["mars_house"] for point in ("lagna", "moon", "venus")]

# Forms one language must never show on the other's page. (भाव / स्थान are checked on the house cells themselves:
# as substrings they also occur in ordinary words of the other language - स्वभाव, प्रभाव, जन्म स्थान.)
HINDI_ONLY = ("मंगल", "शनि", "तुला", "गुरु ", "राहु ", "केतु ", " है", " और ")
MARATHI_ONLY = ("मंगळ", "शनी", "तूळ", "गुरू", "राहू", "केतू", "आहे", " आणि ")
ENGLISH_UI = ("Boy", "Girl", "Points", "Total", "house", "House", "Applies", "apply", "Phase", "phase", "From", "retrograde",
              "Retrograde", "Lagna", "Rashi", "Nakshatra", "Moon", "Mars", "Saturn", "Venus", "Koota", "gunas", "match",
              "Status", "Intensity", "Manglik", "Current", "Now", "Born", "Lord", "pada", "until", "dosha", "Dosha",
              "Yes", "No", "Degree", "Sign")


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


@pytest.fixture(scope="module")
def js():
    mini_racer = pytest.importorskip("py_mini_racer")
    from app.web import STATIC_DIR

    ctx = mini_racer.MiniRacer()
    for name in ("render.js", "chat.js"):
        ctx.eval((STATIC_DIR / "js" / name).read_text(encoding="utf-8"))

    def call(expression: str, **variables):
        names = ", ".join(variables)
        args = ", ".join(json.dumps(value, ensure_ascii=False) for value in variables.values())
        return json.loads(ctx.eval(f"JSON.stringify((function({names}) {{ return {expression}; }})({args}))"))

    return call


@pytest.fixture(scope="module")
def api(client):
    def post(path, body):
        response = client.post(path, json=body)
        assert response.status_code == 200, response.text
        return response.json()

    chart = post("/api/chart", PERSON)
    dasha = chart["dasha"]["current"]
    return {
        "kundali": chart,
        "matching": post("/api/matching", {"boy": PERSON, "girl": PARTNER}),
        "mangalDosha": post("/api/mangal-dosha", PERSON),
        "sadeSati": post("/api/sade-sati", PERSON),
        "sadeSatiLibra": post("/api/sade-sati", LIBRA_MOON),
        "flagged": post("/api/chart", FLAGGED),
        # the session view of POST /api/consultation/start, built from the same chart (no chat session needed here)
        "consultation": {"session_id": "s", "name": None, "language": "en", "summary": {
            "as_of": chart["dasha"]["as_of"], "input": chart["input"], "lagna": chart["lagna"],
            "moon_rashi": chart["moon_rashi"], "janma_nakshatra": chart["janma_nakshatra"],
            "dasha": {"mahadasha": dasha["mahadasha"], "antardasha": dasha["antardasha"]}}},
    }


def _render(js, renderer: str, data: dict, lang: str | None, **ctx) -> str:
    if lang:
        ctx["lang"] = lang
    html = js(f"AstroRender.renderers[{json.dumps(renderer)}](data, ctx)", data=data, ctx=ctx)
    for junk in ("undefined", "NaN", "[object", ">null<"):
        assert junk not in html, (renderer, lang, junk)
    return html


def _visible(html: str) -> str:
    """Text a reader sees, without the SVG chart (its Latin graha codes are a user choice) and without entities."""
    text = re.sub(r"<svg.*?</svg>", " ", html, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"&[a-z#0-9]+;", " ", text)


def _all_results(js, api, lang):
    return {
        "kundali": _render(js, "kundali", api["kundali"], lang, name="K"),
        "matching": _render(js, "matching", api["matching"], lang, names={"boy": "A", "girl": "B"}),
        "mangalDosha": _render(js, "mangalDosha", api["mangalDosha"], lang, name="K"),
        "sadeSati": _render(js, "sadeSati", api["sadeSati"], lang, name="K"),
        "sadeSatiLibra": _render(js, "sadeSati", api["sadeSatiLibra"], lang),
        "consultation": _render(js, "consultation", api["consultation"], lang, name="K"),
    }


# ---------- results ----------


@pytest.mark.parametrize("lang", LANGS)
def test_the_accuracy_caveats_are_written_in_the_page_language(js, api, lang):
    """The place and clock caveats carry engine values into prose, so they are the easiest place for an English
    clause to leak into a Devanagari page - `era_label` is English, which is why the renderer translates `era`."""
    chart = api["flagged"]
    boundary, clock = chart["accuracy"]["lagna_boundary"], chart["accuracy"]["clock"]
    assert boundary["sensitive"] and clock["non_standard"], "the fixture must trip both flags"
    html = _render(js, "kundali", chart, lang)
    note = html.split('class="block accuracy"', 1)[1].split("</section>", 1)[0]
    assert note.count("<p>") == 2
    assert str(round(boundary["km_to_change_sign"])) in note and str(round(abs(clock["offset_seconds"] - 19800) / 60)) in note
    if lang == "en":
        assert "km" in note and clock["era"] == "madras_time" and "Madras time" in note
        return
    text = _visible(note)
    assert not re.search(r"[A-Za-z]", text), (lang, text)  # no city here, so not a Latin letter anywhere
    assert re.search(r"[ऀ-ॿ]", text)
    for form in (MARATHI_ONLY if lang == "hi" else HINDI_ONLY):
        assert form not in text, (lang, form)
    other = _render(js, "kundali", chart, "mr" if lang == "hi" else "hi")
    assert note != other.split('class="block accuracy"', 1)[1].split("</section>", 1)[0]


def test_english_is_the_default_and_unchanged(js, api):
    for renderer in ("kundali", "matching", "mangalDosha", "sadeSati", "consultation"):
        assert _render(js, renderer, api[renderer], None) == _render(js, renderer, api[renderer], "en")
        assert _render(js, renderer, api[renderer], "xx") == _render(js, renderer, api[renderer], "en")  # unknown -> English
    html = _all_results(js, api, "en")
    date, clock = born_words(api["kundali"]["input"], "en")
    assert "Graha positions" in html["kundali"] and date in html["kundali"] and clock in html["kundali"]
    assert "Ashtakoota guna milan" in html["matching"]
    assert VERDICT_WORD["en"][api["matching"]["verdict"]] in html["matching"]
    dosha = api["mangalDosha"]["mangal_dosha"]
    assert dosha["present"] and dosha["cancellation_applies"]  # why PRIMARY: it exercises this branch
    assert "Mangal dosha present, with mitigating factors" in html["mangalDosha"]
    assert INTENSITY_WORD["en"][dosha["intensity"]] in html["mangalDosha"]
    for house, times in Counter(dosha_houses(dosha)).items():
        ordinal = f"{house}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(house % 10 if house % 100 not in (11, 12, 13) else 0, 'th') }"
        assert html["mangalDosha"].count(f"{ordinal} house") == times, (house, times)
    assert "Rule used: Mars in house 1, 2, 4, 7, 8 or 12" in html["mangalDosha"]
    assert "The three phases" in html["sadeSati"] and "Rising phase" in html["sadeSati"]
    assert "Mahadasha" in html["consultation"] and "until " in html["consultation"]


@pytest.mark.parametrize("lang", ["hi", "mr"])
def test_results_are_fully_in_the_page_language(js, api, lang):
    results = _all_results(js, api, lang)
    for name, html in results.items():
        text = _visible(html)
        words = set(re.findall(r"[A-Za-z]+", text))
        assert not words & set(ENGLISH_UI), (lang, name, sorted(words & set(ENGLISH_UI)))
        # the only Latin left: the timezone and any city echoed from the input, the user's name, the "R"
        # retrograde key (a birth given as coordinates echoes digits, which are not letters)
        assert words <= {"Pune", "Nagpur", "Asia", "Kolkata", "K", "A", "B", "R"}, (lang, name, sorted(words))
        for form in (MARATHI_ONLY if lang == "hi" else HINDI_ONLY):
            assert form not in text, (lang, name, form)


def test_hindi_names_and_labels(js, api):
    r = _all_results(js, api, "hi")
    date, clock = born_words(api["kundali"]["input"], "hi")
    assert date in r["kundali"] and clock in r["kundali"] and "PM" not in _visible(r["kundali"])
    for expected in ("ग्रह स्थिति", "वर्तमान महादशा", "महादशाओं का क्रम", "मंगल", "शनि", "गुरु", "राहु", "केतु",
                     *_chart_words(api["kundali"])):
        assert expected in r["kundali"], expected
    assert ">चं" in r["kundali"] and ">Mo" not in r["kundali"]  # Devanagari chart by default
    assert VERDICT_WORD["hi"][api["matching"]["verdict"]] in r["matching"]
    assert "अष्टकूट गुण मिलान" in r["matching"] and "नाड़ी दोष" in r["matching"]
    dosha = api["mangalDosha"]["mangal_dosha"]
    assert "मंगल दोष है, पर उसे कम करने वाले कारक मौजूद हैं" in r["mangalDosha"]
    for house, times in Counter(dosha_houses(dosha)).items():
        assert r["mangalDosha"].count(f"{ORDINAL_WORD['hi'][house - 1]} भाव") == times, house
    assert f"तीव्रता: {INTENSITY_WORD['hi'][dosha['intensity']]}" in r["mangalDosha"] and "मांगलिक" in r["mangalDosha"]
    assert "तुला" in r["sadeSatiLibra"] and "साढ़ेसाती के तीन चरण" in r["sadeSati"]
    assert "शनि अभी इस राशि में है" in r["sadeSati"]  # the label of the "where Saturn is now" fact row
    assert "महादशा" in r["consultation"] and " तक</span>" in r["consultation"]


def test_marathi_names_and_labels(js, api):
    r = _all_results(js, api, "mr")
    date, clock = born_words(api["kundali"]["input"], "mr")
    assert date in r["kundali"] and clock in r["kundali"]
    for expected in ("ग्रहस्थिती", "सध्याची महादशा", "महादशांचा क्रम", "मंगळ", "शनी", "गुरू", "राहू", "केतू",
                     *_chart_words(api["kundali"])):
        assert expected in r["kundali"], expected
    assert VERDICT_WORD["mr"][api["matching"]["verdict"]] in r["matching"]
    assert "अष्टकूट गुणमेलन" in r["matching"] and "नाडी दोष" in r["matching"]
    dosha = api["mangalDosha"]["mangal_dosha"]
    assert "मंगळ दोष आहे, परंतु तो सौम्य करणारे घटक आहेत" in r["mangalDosha"]
    for house, times in Counter(dosha_houses(dosha)).items():
        assert r["mangalDosha"].count(f"{ORDINAL_WORD['mr'][house - 1]} स्थान") == times, house
    assert f"तीव्रता: {INTENSITY_WORD['mr'][dosha['intensity']]}" in r["mangalDosha"] and "मांगलिक" in r["mangalDosha"]
    assert "तूळ" in r["sadeSatiLibra"] and "साडेसातीचे तीन टप्पे" in r["sadeSati"]
    assert "शनी सध्या या राशीत आहे" in r["sadeSati"]  # the label of the "where Saturn is now" fact row
    assert "महादशा" in r["consultation"] and " पर्यंत</span>" in r["consultation"]


@pytest.mark.parametrize("lang", ["hi", "mr"])
def test_matching_values_and_doshas_are_translated(js, api, lang):
    data, html = api["matching"], _render(js, "matching", api["matching"], lang, names={"boy": "A", "girl": "B"})
    assert f'<span class="score__total">{data["total"]:g}</span> / 36' in html and f'{data["percentage"]:g}%' in html
    for koota in data["kootas"]:
        assert f'<strong>{koota["score"]:g}</strong> / {koota["max"]}' in html
        assert f'<td>{koota["boy"]}</td>' not in html and f'<td>{koota["girl"]}</td>' not in html  # no English cell values
    # Tara row = nakshatras, Bhakoot row = signs, and both come back Devanagari for this pair
    for side in ("boy", "girl"):
        assert f'<td>{data[side]["moon_nakshatra"]["devanagari"]}</td>' in html
        assert f'<td>{data[side]["moon_sign"]["devanagari"]}</td>' in html
    # Graha Maitri = the sign lords, spelled the way this language spells them (गुरु / गुरू, मंगल / मंगळ)
    for side in ("boy", "girl"):
        assert f'<td>{GRAHA_WORD[lang][data[side]["sign_lord"]]}</td>' in html
    # no koota cell keeps its English value
    cells = re.findall(r"<td>([^<]*)</td>", html)
    assert cells and not [cell for cell in cells if re.fullmatch(r"[A-Za-z][A-Za-z ]*", cell)], cells
    compatible = {"hi": "मंगल दोष: अनुकूल", "mr": "मंगळ दोष: अनुरूप"}[lang]
    assert (compatible in html) == data["mangal_dosha"]["compatible"]
    assert html.count('class="person-card"') == 4  # two summaries + two mangal dosha cards


@pytest.mark.parametrize("lang", LANGS)
def test_mangal_dosha_rules_by_key_and_other_states(js, client, api, lang):
    dosha = api["mangalDosha"]["mangal_dosha"]
    html = _render(js, "mangalDosha", api["mangalDosha"], lang)
    applies = {"en": "Applies to your chart", "hi": "आपकी कुंडली पर लागू", "mr": "तुमच्या कुंडलीला लागू"}[lang]
    assert html.count(applies) == sum(rule["applies"] for rule in dosha["cancellations"])
    assert html.count('class="check ') == len(dosha["cancellations"]) == 4
    assert html.count("<li>") == len(dosha["notes"]) == 3  # three notes in every language (rules are <li class=...>)
    if lang == "en":
        assert all(note in html for note in dosha["notes"])
    else:
        assert not any(note in html for note in dosha["notes"]) and "28" in html
        assert ("योगकारक" in html) and "yogakaraka" not in html

    clear = client.post("/api/mangal-dosha", json={"date": "1988-01-10", "time": "08:00", "city": "Pune"}).json()
    assert not clear["mangal_dosha"]["present"]
    clear_html = _render(js, "mangalDosha", clear, lang)
    assert {"en": "No Mangal dosha", "hi": "मंगल दोष नहीं है", "mr": "मंगळ दोष नाही"}[lang] in clear_html
    assert applies not in clear_html

    plain = client.post("/api/mangal-dosha", json={"date": "1988-10-10", "time": "08:00", "city": "Pune"}).json()
    title = {"en": "Mangal dosha present", "hi": "मंगल दोष है", "mr": "मंगळ दोष आहे"}[lang]
    assert f'<p class="banner__title">{title}</p>' in _render(js, "mangalDosha", plain, lang)


@pytest.mark.parametrize("lang", LANGS)
def test_sade_sati_states(js, client, lang):
    active = {"en": "Sade sati is active", "hi": "साढ़ेसाती चल रही है", "mr": "साडेसाती सुरू आहे:"}[lang]
    inactive = {"en": "Sade sati is not active", "hi": "अभी साढ़ेसाती नहीं है", "mr": "सध्या साडेसाती नाही"}[lang]
    seen = set()
    for step in range(12):
        body = {"date": f"1990-01-{1 + step * 2:02d}", "time": "12:00", "city": "Nagpur"}
        data = client.post("/api/sade-sati", json=body).json()
        html = _render(js, "sadeSati", data, lang)
        ss = data["sade_sati"]
        seen.add(ss["active"])
        assert html.count("<tr") == len(ss["cycle"]["periods"]) + 1
        if ss["active"]:
            assert active in html and html.count('<tr class="is-current"') == 1
        elif ss["cycle"]["which"] == "next":
            assert inactive in html
    assert seen == {True, False}


def test_chart_legend_and_aria_per_language(js, api):
    assert "Mangal" not in js("AstroRender.chartLegend('deva', 'hi')") and "मंगल" in js("AstroRender.chartLegend('deva', 'hi')")
    assert "मंगळ" in js("AstroRender.chartLegend('deva', 'mr')") and "Mars" in js("AstroRender.chartLegend('en', 'en')")
    lagna = api["kundali"]["lagna"]["sign"]["devanagari"]
    assert f'aria-label="उत्तर भारतीय शैली की कुंडली। लग्न {lagna}।' in _render(js, "kundali", api["kundali"], "hi")
    assert js("AstroRender.langOf(v)", v="hi") == "hi" and js("AstroRender.langOf(v)", v="de") == "en"
    assert js("AstroRender.langOf(v)", v=None) == "en"


# ---------- validation + API errors ----------


@pytest.mark.parametrize("lang, date_missing, city_unknown", [
    ("en", "Please enter the date of birth.", "We could not find this city"),
    ("hi", "कृपया जन्म तिथि भरें।", "यह शहर नहीं मिला"),
    ("mr", "कृपया जन्मतारीख भरा.", "हे शहर सापडले नाही"),
])
def test_validation_and_api_errors_per_language(js, client, lang, date_missing, city_unknown):
    empty = {"self": {"name": "", "date": "", "time": "", "city": " "}}
    errors = js("AstroRender.validate('single', v, '2026-01-01', lang)", v=empty, lang=lang)
    assert [e["field"] for e in errors] == ["date", "time", "city"] and errors[0]["message"] == date_missing
    assert len({e["message"] for e in errors}) == 3

    bad_city = client.post("/api/chart", json={**PERSON, "city": "Atlantis", "lat": None, "lon": None})
    assert bad_city.status_code == 422
    mapped = js("AstroRender.parseApiError(422, body, 'single', lang)", body=bad_city.json(), lang=lang)
    assert [(e["person"], e["field"]) for e in mapped] == [("self", "city")] and city_unknown in mapped[0]["message"]

    bad_pair = client.post("/api/matching", json={"boy": {**PERSON, "date": "1931-10-32"},  # a date that does not exist
                                                  "girl": {**PARTNER, "city": "Atlantis", "lat": None, "lon": None}})
    mapped = js("AstroRender.parseApiError(422, body, 'pair', lang)", body=bad_pair.json(), lang=lang)
    assert sorted((e["person"], e["field"]) for e in mapped) == [("boy", "date"), ("girl", "city")]

    # general errors: English pages show the API's wording, hi / mr pages never show English
    general = [js("AstroRender.parseApiError(s, b, 'single', lang)", s=status, b=body, lang=lang)[0]["message"]
               for status, body in [(422, {"detail": "bad timezone"}), (429, {"detail": {"code": "rate_limited", "message": "Slow down."}}),
                                    (500, None)]]
    if lang == "en":
        assert general[:2] == ["bad timezone", "Slow down."] and "Something went wrong" in general[2]
    else:
        assert not re.search(r"[A-Za-z]{3,}", " ".join(general)) and len(set(general)) == 3
    messages = js("AstroRender.messages(lang)", lang=lang)
    assert set(messages) == set(js("AstroRender.messages('en')")) and all(messages.values())


# ---------- matching by name ----------


def _name_response(api) -> dict:
    """A name-mode response shaped like the birth-details one, minus everything a name cannot give."""
    data = json.loads(json.dumps(api["matching"]))
    data["mode"] = "name"
    data.pop("mangal_dosha")
    for who, syllable in (("boy", "भू"), ("girl", "नो")):
        person = data[who]
        person.pop("input")
        person.update(name="Test <i>" + who, syllable=syllable, pada=3)
    return data


def test_name_payload_and_validation(js):
    values = {"boy": {"name": "  Rahul "}, "girl": {"name": "नेहा"}}
    assert js("AstroRender.buildNamePayload(v)", v=values) == {"mode": "name", "boy": {"name": "Rahul"}, "girl": {"name": "नेहा"}}
    assert js("AstroRender.validateNames(v, 'en')", v=values) == []
    for lang, missing in (("en", "Please enter the name."), ("hi", "कृपया नाम लिखें।"), ("mr", "कृपया नाव लिहा.")):
        errors = js("AstroRender.validateNames(v, lang)", v={"boy": {"name": " "}, "girl": {"name": "x" * 61}}, lang=lang)
        assert [(e["person"], e["field"]) for e in errors] == [("boy", "name"), ("girl", "name")]
        assert errors[0]["message"] == missing and errors[1]["message"] != missing and "60" in errors[1]["message"]
    assert [e["person"] for e in js("AstroRender.validateNames(v)", v={})] == ["boy", "girl"]
    # a 422 on a name lands on the name field
    body = {"detail": [{"loc": ["body", "girl", "name"], "msg": "Value error, no syllable found"}]}
    assert js("AstroRender.parseApiError(422, b, 'pair', 'hi')", b=body) == [
        {"person": "girl", "field": "name", "message": "यह नाम पढ़ा नहीं जा सका। कृपया वर्तनी जाँच लें।"}]


@pytest.mark.parametrize("lang, note, derived", [
    ("en", "Matching by birth details is more accurate", "Derived from the name"),
    ("hi", "जन्म विवरण से किया गया कुंडली मिलान अधिक सटीक", "नाम से निकाला गया"),
    ("mr", "जन्मतपशिलांवरून केलेली पत्रिका जुळवणी अधिक अचूक", "नावावरून काढलेले"),
])
def test_matching_renders_a_name_mode_response(js, api, lang, note, derived):
    data = _name_response(api)
    html = _render(js, "matching", data, lang)
    assert note in html and html.count(derived) == 2
    assert "Test &lt;i&gt;boy" in html and "<i>" not in html  # names from the response are escaped
    assert "<strong>भू</strong>" in html and "<strong>नो</strong>" in html
    assert f'<span class="score__total">{data["total"]:g}</span>' in html and html.count("<tr") == 10
    assert 'class="birth-line"' not in html  # no birth details in name mode
    heading = {"en": "Mangal dosha comparison", "hi": "मंगल दोष की तुलना", "mr": "मंगळ दोषाची तुलना"}[lang]
    assert f"<h3>{heading}</h3>" not in html and f"<h3>{heading}</h3>" in _render(js, "matching", api["matching"], lang)
    # a birth-details response never carries the name note
    assert note not in _render(js, "matching", api["matching"], lang)
    # and the barest possible response still renders
    bare = {"mode": "name", "boy": {}, "girl": {}, "kootas": [], "total": 20, "max_total": 36, "percentage": 55.6, "verdict": "average"}
    assert "55.6%" in _render(js, "matching", bare, lang)


def test_name_candidate_picker(js, api):
    boy = api["matching"]["boy"]
    candidates = [{"syllable": "भू", "nakshatra": boy["moon_nakshatra"], "pada": 3, "sign": boy["moon_sign"]},
                  {"syllable": "<b>", "nakshatra": None}, {}]
    for lang, prompt in (("en", "Boy: this name can start"), ("hi", "वर: इस नाम की शुरुआत"), ("mr", "वर: या नावाची सुरुवात")):
        html = js("AstroRender.candidatesHtml('boy', c, lang)", c=candidates, lang=lang)
        sign = boy["moon_sign"]["name"] if lang == "en" else boy["moon_sign"]["devanagari"]
        assert prompt in html and sign in html and boy["moon_nakshatra"]["devanagari"] in html
        assert html.count("data-name-candidate") == 3 and html.count('data-person="boy"') == 4
        assert [int(i) for i in re.findall(r'data-index="(\d)"', html)] == [0, 1, 2]
        assert "<b>" not in html and "&lt;b&gt;" in html and "undefined" not in html
    assert "वधू:" in js("AstroRender.candidatesHtml('girl', [], 'mr')")
    assert 'class="chip-list"></ul>' in js("AstroRender.candidatesHtml('girl', null)")


# ---------- chat.js ----------


def test_chat_strings_per_language(js):
    state = {"sessionId": "s", "messages": [], "quota": {"free_left": 2, "paid_left": 0, "messages_left": 2},
             "paywall": None, "pending": False, "error": None}
    english = js("AstroChat.strings('en')")
    for lang in ("hi", "mr"):
        strings = js("AstroChat.strings(lang)", lang=lang)
        assert set(strings) == set(english) and all(strings.values())
        for key, text in strings.items():
            assert not re.search(r"[A-Za-z]{3,}", re.sub(r"\{\w+\}|English", "", text)), (lang, key)
    assert js("AstroChat.strings('xx')") == english and js("AstroChat.langOf('mr-IN')") == "mr"

    expected = {
        "en": ("2 free questions left", "1 free question left", "1 question left", "1 free + 10 paid questions left",
               "Please type a question.", "Your free questions are used.", "Namaste", "You: "),
        "hi": ("2 मुफ़्त सवाल बाकी", "1 मुफ़्त सवाल बाकी", "1 सवाल बाकी", "1 मुफ़्त + 10 खरीदे हुए सवाल बाकी",
               "कृपया अपना सवाल लिखें।", "आपके मुफ़्त सवाल पूरे हो गए हैं।", "नमस्ते", "आप: "),
        "mr": ("2 मोफत प्रश्न शिल्लक", "1 मोफत प्रश्न शिल्लक", "1 प्रश्न शिल्लक", "1 मोफत + 10 सशुल्क प्रश्न शिल्लक",
               "कृपया तुमचा प्रश्न लिहा.", "तुमचे मोफत प्रश्न संपले आहेत.", "नमस्कार", "तुम्ही: "),
    }
    for lang, (two_free, one_free, one_paid, mixed, empty, used, hint, you) in expected.items():
        quota = lambda free, paid: js("AstroChat.quotaLabel(s, lang)", lang=lang,  # noqa: E731
                                      s=dict(state, quota={"free_left": free, "paid_left": paid, "messages_left": free + paid}))
        assert (quota(2, 0), quota(1, 0), quota(0, 1), quota(1, 10)) == (two_free, one_free, one_paid, mixed)
        assert js("AstroChat.quotaLabel(s, lang)", s=dict(state, paywall={}), lang=lang) == ""
        assert js("AstroChat.validateMessage(s, ' ', lang)", s=state, lang=lang) == empty
        assert js("AstroChat.validateMessage(s, 'q', lang)", s=dict(state, paywall={}), lang=lang) == used
        assert js("AstroChat.validateMessage(s, 'q', lang)", s=state, lang=lang) is None
        assert "1000" in js("AstroChat.validateMessage(s, t, lang)", s=state, t="x" * 1001, lang=lang)
        assert hint in js("AstroChat.messagesHtml(s, lang)", s=state, lang=lang)
        talk = dict(state, messages=[{"role": "user", "content": "<b>hi</b>", "kind": "ai"}, {"role": "assistant", "content": "ok", "kind": "ai"}])
        html = js("AstroChat.messagesHtml(s, lang)", s=talk, lang=lang)
        assert f'<span class="visually-hidden">{you}</span>' in html and "&lt;b&gt;hi" in html


@pytest.mark.parametrize("lang", ["hi", "mr"])
def test_chat_errors_never_show_english_on_hindi_and_marathi_pages(js, lang):
    pending = {"sessionId": "s", "messages": [{"role": "user", "content": "q", "kind": "pending"}], "draft": "q",
               "quota": {"free_left": 2, "paid_left": 0, "messages_left": 2}, "paywall": None, "pending": True, "error": None}
    seen = set()
    for status, body in [(503, {"detail": {"code": "ai_unavailable", "message": "The astrologer is unavailable right now."}}),
                         (429, {"detail": {"code": "rate_limited", "message": "Please wait a moment."}}),
                         (409, {"detail": {"code": "busy", "message": "Still answering."}}), (0, None), (500, None),
                         (404, {"detail": {}})]:
        after = js("AstroChat.applyResponse(s, status, body, lang)", s=pending, status=status, body=body, lang=lang)
        assert after["error"] and not re.search(r"[A-Za-z]{3,}", after["error"]), (status, after["error"])
        assert after["messages"] == [] and not after["pending"]
        seen.add(after["error"])
    assert len(seen) == 6
    paywall = js("AstroChat.applyResponse(s, 402, b, lang)", s=pending, lang=lang,
                 b={"detail": {"code": "payment_required", "price_inr": 99, "messages": 10}})
    assert paywall["paywall"]["price_inr"] == 99 and paywall["error"] is None


# ---------------------------------------------------------------- how a birth time is put into words
# The ten values are the boundaries themselves and the minute either side of them, not a sample. Noon and
# midnight are the two that matter most: an off-by-one in a range check is invisible in review there and
# catastrophic in meaning, because midnight printed as noon is the twelve-hour error this whole read-back
# exists to catch, produced by the read-back itself.

CLOCK_WORDS = {
    #            en            hi                mr
    "00:00": ("12:00 AM", "\u0930\u093e\u0924 12:00", "\u0930\u093e\u0924\u094d\u0930\u0940 12:00"),
    "03:59": ("3:59 AM", "\u0930\u093e\u0924 3:59", "\u0930\u093e\u0924\u094d\u0930\u0940 3:59"),
    "04:00": ("4:00 AM", "\u0938\u0941\u092c\u0939 4:00", "\u0938\u0915\u093e\u0933\u0940 4:00"),
    "11:59": ("11:59 AM", "\u0938\u0941\u092c\u0939 11:59", "\u0938\u0915\u093e\u0933\u0940 11:59"),
    "12:00": ("12:00 PM", "\u0926\u094b\u092a\u0939\u0930 12:00", "\u0926\u0941\u092a\u093e\u0930\u0940 12:00"),
    "15:59": ("3:59 PM", "\u0926\u094b\u092a\u0939\u0930 3:59", "\u0926\u0941\u092a\u093e\u0930\u0940 3:59"),
    "16:00": ("4:00 PM", "\u0936\u093e\u092e 4:00", "\u0938\u0902\u0927\u094d\u092f\u093e\u0915\u093e\u0933\u0940 4:00"),
    # 19:00 to 19:59 is the hour whose answer is least settled: \u0930\u093e\u0924\u094d\u0930\u0940 \u0938\u093e\u0921\u0947\u0938\u093e\u0924 and \u0938\u0902\u0927\u094d\u092f\u093e\u0915\u093e\u0933\u0940 \u0938\u093e\u0921\u0947\u0938\u093e\u0924 are
    # both ordinary Marathi, so these two rows record a choice under review rather than a settled fact.
    "19:00": ("7:00 PM", "\u0936\u093e\u092e 7:00", "\u0938\u0902\u0927\u094d\u092f\u093e\u0915\u093e\u0933\u0940 7:00"),
    "19:59": ("7:59 PM", "\u0936\u093e\u092e 7:59", "\u0938\u0902\u0927\u094d\u092f\u093e\u0915\u093e\u0933\u0940 7:59"),
    "20:00": ("8:00 PM", "\u0930\u093e\u0924 8:00", "\u0930\u093e\u0924\u094d\u0930\u0940 8:00"),
}


@pytest.mark.parametrize("clock", list(CLOCK_WORDS))
@pytest.mark.parametrize("index, lang", list(enumerate(("en", "hi", "mr"))))
def test_every_day_part_boundary_is_said_the_way_the_language_says_it(js, index, lang, clock):
    """Exact strings, not "contains the word". The formatter is the only thing standing between a customer
    who mistyped their birth time and a chart that is confidently wrong, so what it produces at each
    boundary is pinned rather than sampled."""
    shown = js(f'AstroRender.withLang("{lang}", function () {{ return AstroRender.fmtTime("{clock}"); }})')
    assert shown.replace("\u00a0", " ") == CLOCK_WORDS[clock][index], (
        f"{lang} renders {clock} as {shown!r}, not {CLOCK_WORDS[clock][index]!r}")


def test_each_language_owns_its_own_table_of_day_parts():
    """The two tables hold identical hours today, so no assertion about their VALUES can protect the thing
    that matters. What is pinned is the shape: each language has its own table.

    It is worth pinning precisely because the redundancy is what invites the tidy-up. `fmtTime` printed one
    24-hour clock for both trees on the reasoning that there is no AM/PM to translate, and that reasoning
    was wrong in the same way - it treated two languages as one case. Two tables whose values coincide let a
    reviewer move one language without touching the other, which is what the open boundary questions need."""
    from app.web import STATIC_DIR

    source = (STATIC_DIR / "js" / "render.js").read_text(encoding="utf-8")
    table = re.search(r"var DAY_PARTS = \{(.*?)\n  \};", source, re.S)
    assert table, "the day-part tables have moved or been renamed"
    for lang in ("hi", "mr"):
        assert re.search(rf"\b{lang}:\s*\[", table.group(1)), (
            f"{lang} no longer has a table of its own - if the two were merged because their hours matched, "
            "that is the merge this test exists to stop")
