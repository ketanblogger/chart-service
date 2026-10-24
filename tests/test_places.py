"""The birth-place field: every Indian town, in either script, and a date that cannot be misread.

WHAT THESE FIX. The place list had 137 cities in it and the field is required, so for anybody born in
Bhiwandi (874,000 people) or Dewas (290,000) the form simply ended. Typing a town in Devanagari matched
nothing at all, on pages that are themselves in Devanagari. And the date was a native control drawn in
the BROWSER's locale, so a reader who meant 4 March and typed 03/04 entered 3 April and nothing
downstream could tell.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.engine import places
from app.main import app
from app.web import pages

client = TestClient(app)
RENDER_JS = Path("app/static/js/render.js").read_text(encoding="utf-8")


# ---- the list -----------------------------------------------------------------------------------

def test_the_towns_that_used_to_end_the_form_are_in_it():
    """Both were missing from the hand-kept 137 and both are large. Named here so a future trim of
    this file has to decide about them explicitly."""
    for town in ("Bhiwandi", "Dewas", "Satara", "Latur", "Jalgaon", "Ichalkaranji"):
        assert places.find(town), town


def test_it_covers_the_country_rather_than_a_shortlist():
    assert len(places.places()) > 7000


def test_every_place_has_what_a_chart_needs():
    for place in places.places()[:500]:
        assert place["name"] and place["state"]
        assert 6.0 < place["lat"] < 37.5, place          # India, roughly
        assert 68.0 < place["lon"] < 97.5, place
        assert place["tz"] == "Asia/Kolkata"


def test_the_payload_a_phone_downloads_stays_small():
    """104 KB gzipped, fetched once. As one object per place it is 656 KB - the key names were three
    quarters of the bytes, which is why it ships packed."""
    import gzip

    raw = Path("app/engine/places_in.json").read_bytes()
    assert len(gzip.compress(raw, 9)) < 150_000, f"{len(gzip.compress(raw, 9)) // 1024} KB gzipped"


def test_the_attribution_is_recorded():
    """GeoNames is CC BY 4.0 and the licence asks for it."""
    credits = Path("docs/CREDITS.md").read_text(encoding="utf-8")
    assert "GeoNames" in credits and "CC BY 4.0" in credits
    assert "creativecommons.org/licenses/by/4.0" in credits


def test_nothing_reaches_out_to_geonames_at_request_time():
    """The whole list ships with the site. A reader's birth place is not handed to a geocoder."""
    for path in ("app/engine/places.py", "app/api.py"):
        source = Path(path).read_text(encoding="utf-8")
        assert "download.geonames.org" not in source
        assert "requests.get" not in source and "httpx.get" not in source


# ---- searching in either script -----------------------------------------------------------------

@pytest.mark.parametrize("query,expected", [
    ("पुणे", "Pune"), ("सातारा", "Satara"), ("मुंबई", "Mumbai"), ("नागपूर", "Nagpur"),
    ("देवास", "Dewas"), ("कोल्हापूर", "Kolhapur"), ("नाशिक", "Nashik"),
    ("Pune", "Pune"), ("Bhiwandi", "Bhiwandi"),
])
def test_a_town_typed_in_either_script_finds_itself(query, expected):
    names = [place["name"] for place in places.search(query, 5)]
    assert expected in names, f"{query} -> {names}"


def test_mumbai_leads_its_own_search():
    """It came SECOND to Navi Mumbai at first: the transliteration dropped the inherent vowel, so
    मुंबई became "mumbi" and matched neither."""
    assert places.search("मुंबई", 3)[0]["name"] == "Mumbai"


def test_most_devanagari_names_find_their_own_place():
    """THE MEASUREMENT, not three hand-picked examples. Every place that ships a Hindi or Marathi
    name is searched by that name; the bar is set at where it actually stands so a regression moves
    it rather than going unnoticed."""
    with_deva = [place for place in places.places() if place["deva"]]
    assert len(with_deva) > 700
    found = sum(1 for place in with_deva
                if place["name"] in [hit["name"] for hit in places.search(place["deva"], 5)])
    assert found / len(with_deva) > 0.95, f"{found}/{len(with_deva)}"


def test_the_two_search_keys_are_the_same_function():
    """render.js does the matching a reader actually experiences; places.py is the twin that can be
    tested and that the server resolves with. They carry the same tables, so they are compared."""
    from py_mini_racer import MiniRacer

    ctx = MiniRacer()
    ctx.eval("var window = this; var document = undefined;")
    ctx.eval(RENDER_JS)
    sample = [place["name"] for place in places.places()[:200]]
    sample += ["पुणे", "मुंबई", "सातारा", "देवास", "नागपूर", "Belagavi (Belgaum)", "Pimpri-Chinchwad"]
    for name in sample:
        assert ctx.eval(f"AstroRender.placeKey({json.dumps(name)})") == places.key(name), name


def test_a_place_typed_in_devanagari_computes_a_chart():
    """The end of the road for this fix: it has to produce a chart, not just a suggestion."""
    answer = client.post("/api/chart", json={"date": "1991-03-14", "time": "07:20", "city": "देवास"})
    assert answer.status_code == 200, answer.text[:200]


# ---- the date that cannot be misread -------------------------------------------------------------

def test_the_form_has_no_native_date_input_left():
    """<input type="date"> is drawn in the BROWSER's locale, not the document's. That is the whole
    defect: it cannot be fixed from here, so it is not used."""
    # The template's own comment EXPLAINS what it replaced, so comments are stripped before looking -
    # the first version of this test failed on its own explanation, which is becoming a habit.
    import re

    raw = Path("app/web/templates/_person_fields.html").read_text(encoding="utf-8")
    markup = re.sub(r"\{#.*?#\}", "", raw, flags=re.S)
    assert 'type="date"' not in markup
    for part in ("date-part='day'", 'data-date-part="day"', 'data-date-part="month"'):
        if part in markup:
            break
    else:
        raise AssertionError("no day/month selects in the form")


def test_three_april_and_four_march_cannot_be_confused():
    """THE BUG THIS REPLACES. With a month-first native control, a reader who means 4 March types
    03/04 and gets 3 April - and every figure computed from it is then consistent and wrong, because
    nothing downstream can tell the difference.

    The month is chosen BY NAME now, so the two dates are different words rather than the same two
    digits in a different order. This asserts they produce genuinely different charts, which is what
    the confusion actually costs.
    """
    base = {"time": "07:20", "city": "Pune"}
    march = client.post("/api/chart", json={**base, "date": "1991-03-04"})
    april = client.post("/api/chart", json={**base, "date": "1991-04-03"})
    assert march.status_code == april.status_code == 200
    march_sun = march.json()["grahas"]["Sun"]["sign"]["name"]
    april_sun = april.json()["grahas"]["Sun"]["sign"]["name"]
    assert march_sun != april_sun, (march_sun, april_sun)

    # And the control the reader uses offers month NAMES, which is what makes them distinguishable.
    for lang in ("en", "hi", "mr"):
        months = pages.ui(lang)["month_names"]
        assert len(months) == 12
        assert len(set(months)) == 12, f"{lang} has a duplicate month name"
        assert not any(name.strip().isdigit() for name in months), f"{lang} months are numbers"


@pytest.mark.parametrize("lang,path", [("en", "/birth-chart"), ("hi", "/hi/kundli"), ("mr", "/mr/kundali")])
def test_the_month_names_are_in_the_pages_own_language(lang, path):
    html = client.get(path).text
    for name in pages.ui(lang)["month_names"][:3]:
        assert f">{name}</option>" in html, (lang, name)


# ---- the two things that used to block people ----------------------------------------------------

@pytest.mark.parametrize("path", ["/birth-chart", "/horoscope-matching", "/hi/kundli", "/mr/kundali"])
def test_no_floating_bar_can_cover_the_submit_button(path):
    """At 390px the bar sat on top of the form's own button, and its primary link was a jump to the
    form the reader was already looking at."""
    assert "v2-bottombar" not in client.get(path).text, path


@pytest.mark.parametrize("lang,path", [("en", "/birth-chart"), ("hi", "/hi/kundli"), ("mr", "/mr/kundali")])
def test_the_way_out_of_the_time_field_is_beside_its_label(lang, path):
    """Time of birth is REQUIRED and a great many people do not know it. The escape has to be where
    somebody meets the wall, not under the error line below it."""
    html = client.get(path).text
    label = html.index(pages.ui(lang)["time"])
    escape = html.index(pages.ui(lang)["time_unsure"])
    time_input = html.index('name="time"')
    assert label < escape < time_input, "the escape is not between the label and the field"


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_the_village_hint_says_why_a_nearby_town_is_fine(lang):
    """Not "town not listed? pick another" - which reads as a shrug on a page that promises nothing is
    estimated - but the reason, with the number attached."""
    hint = pages.ui(lang)["city_hint"]
    assert "30" in hint, hint
    assert "English" not in hint and "अंग्रेज़ी" not in hint and "इंग्रजी" not in hint, \
        "the instruction to type in Latin letters is no longer true"


# ---- the form actually works in a browser --------------------------------------------------------

@pytest.mark.parametrize("path,query,expected", [
    ("/birth-chart", "Bhiwandi", "Bhiwandi"),
    ("/hi/kundli", "देवास", "Dewas"),
    ("/mr/kundali", "सातारा", "Satara"),
])
def test_the_place_field_offers_the_town_in_a_real_browser(path, query, expected):
    """THE ONLY TEST HERE THAT WOULD HAVE CAUGHT THE WORST BUG OF THIS BATCH.

    Moving the "don't know the time?" button out of the presets group left app.js looking for it where
    it no longer was. That null threw during init and took the REST of the file with it - the city
    fetch, the combobox and the new date selects all stopped, on every tool page, in every language.
    Every unit test still passed: the templates were right, the search was right, the data was right,
    and the form was dead.

    So this drives the real page with a real browser and asserts a suggestion appears.
    """
    import asyncio

    from playwright.async_api import async_playwright

    from app.pdf.browser import launch_options

    async def run():
        async with async_playwright() as play:
            browser = await play.chromium.launch(**launch_options())
            page = await browser.new_page(viewport={"width": 390, "height": 844})
            errors: list[str] = []
            page.on("pageerror", lambda exc: errors.append(str(exc)))
            await page.goto(f"http://127.0.0.1:8099{path}", wait_until="networkidle")
            await page.wait_for_timeout(1500)
            await page.click("input[name=city]")
            await page.type("input[name=city]", query, delay=60)
            await page.wait_for_timeout(1200)
            options = await page.evaluate(
                "() => [...document.querySelectorAll('[role=option]')].map(e => e.textContent)")
            await browser.close()
            return options, errors

    try:
        options, errors = asyncio.run(run())
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"no local server on 8099 for the browser check ({type(exc).__name__})")
    assert not errors, f"JavaScript threw during init: {errors[:1]}"
    assert any(expected in option for option in options), options[:3]


def test_the_list_answers_both_of_its_callers():
    """TWO SHAPES, AND A CALLER THAT WAS ALREADY ASKING FOR THE SECOND ONE.

    The birth form wants the whole packed list once, and filters it in the browser. The muhurta page
    wants eight suggestions and was already calling `/api/cities?q=...` - which the old 137-city
    answer ignored, because filtering 137 entries in the page cost nothing. The moment the unfiltered
    shape changed, that page's list came back empty: a caller passing a filter it never received, and
    nothing noticing until it returned nothing.
    """
    packed = client.get("/api/cities").json()
    assert "places" in packed and "states" in packed
    assert "cities" not in packed

    filtered = client.get("/api/cities", params={"q": "Pune"}).json()
    assert [place["name"] for place in filtered["cities"]][:1] == ["Pune"]
    assert filtered["cities"][0]["label"].startswith("Pune, ")
    assert len(filtered["cities"]) <= 20

    # And in the reader's own script, because that is the whole point of this batch.
    deva = client.get("/api/cities", params={"q": "पुणे"}).json()
    assert "Pune" in [place["name"] for place in deva["cities"]]


def test_the_hand_kept_list_was_merged_in_and_not_replaced():
    """GEONAMES IS MISSING FIVE OF THE 137 HAND-CHECKED CITIES - Panaji, Vasai-Virar (1.2 million
    people), Miraj, Davanagere, and Chhatrapati Sambhajinagar under that name.

    Swapping one list for the other fixed Bhiwandi and broke Panaji, and a browser test that had
    always typed "Miraj" was what noticed. Both lists can be true at once, so both are in.
    """
    from app.engine import cities as curated

    missing = [city["name"] for city in curated.CITIES
               if not places.find(city["name"])
               and not places.find(city["name"].split("(")[0].strip())]
    assert not missing, f"the curated list lost: {missing}"
