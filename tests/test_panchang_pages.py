"""The three panchang pages: what they show, what they index, and what they promise about their method.

The engine's correctness is tested in test_panchang_accuracy.py against two published panchangs. This
file is about the PAGE: that every value reaches it, that only today is indexed, that the city is
remembered, and that the two method notes are present and say the right thing.
"""
from __future__ import annotations

import datetime as dt
import re

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.web import i18n
from app.web.panchang import COPY, DEFAULT_CITY, resolve_city, resolve_date

client = TestClient(app)
PAGES = [("en", "/panchang"), ("hi", "/hi/aaj-ka-panchang"), ("mr", "/mr/aajche-panchang")]


@pytest.mark.parametrize("lang, path", PAGES)
def test_the_page_carries_every_limb_and_window(lang, path):
    html = client.get(path).text
    words = COPY[lang]
    for key in ("vara", "tithi", "nakshatra", "yoga", "karana", "paksha", "masa", "samvat",
                "sunrise", "sunset", "moonrise", "moonset", "moon_sign", "sun_sign",
                "rahu_kaal", "yamaganda", "gulika", "abhijit", "brahma"):
        assert words[key] in html, f"{path}: {key} ({words[key]!r}) is not on the page"


@pytest.mark.parametrize("lang, path", PAGES)
def test_only_today_is_indexed(lang, path):
    """A panchang has a page for every date since the calendar began. Inviting a crawler to all of them
    spends the crawl budget on pages nobody searched for; the query people type is "aaj ka panchang"."""
    assert "noindex" not in client.get(path).text
    other = (dt.date.today() + dt.timedelta(days=9)).isoformat()
    assert 'content="noindex' in client.get(f"{path}?date={other}").text


@pytest.mark.parametrize("lang, path", PAGES)
def test_the_method_notes_are_present_and_point_the_right_way(lang, path):
    """THE DIRECTION OF THIS CLAIM WAS CHECKED BEFORE IT WAS WRITTEN. swisseph's BIT_HINDU_RISING is
    DISC_CENTER | NO_REFRACTION, and 21 October 2026 at Delhi gives 06:29:23 with it against 06:25:18
    with the upper limb and refraction - ProKerala publishes 06:29, Drik 06:25. So the page says WE use
    the disc centre and others the upper limb, which is the opposite of the easy assumption."""
    # UNESCAPED before comparing: the English note contains "Sun's", which Jinja renders as &#39; - so a
    # raw substring check fails on a page that carries the text perfectly well.
    import html as html_module

    page = html_module.unescape(client.get(path).text)
    words = COPY[lang]
    assert words["sunrise_note"] in page
    assert words["brahma_note"] in page
    claim = words["sunrise_note"]
    if lang == "en":
        assert "centre of the Sun's disc" in claim and "without refraction" in claim
        assert "upper edge" in claim, "the note must say what the OTHER convention is"


@pytest.mark.parametrize("lang, path", PAGES)
def test_the_picker_works_without_javascript(lang, path):
    """A plain GET form: bookmarkable, shareable, and working before any script runs."""
    html = client.get(path).text
    form = html.split('class="card panchang__pick"', 1)[1].split("</form>", 1)[0]
    assert 'method="get"' in html.split('panchang__pick', 1)[0][-120:] or 'method="get"' in html
    assert 'name="city"' in form and 'name="date"' in form
    assert 'type="date"' in form and "min=" in form and "max=" in form


def test_the_default_city_follows_the_language_tree():
    """Sunrise at Pune and Delhi differ by about twenty minutes, which on a day when a tithi ends near
    dawn is the difference between two correct answers."""
    assert resolve_city(None, "mr")["name"] == "Pune"
    assert resolve_city(None, "hi")["name"] == "Delhi"
    assert resolve_city(None, "en")["name"] == DEFAULT_CITY["en"]
    assert resolve_city("Kolkata", "mr")["name"] == "Kolkata", "an explicit city wins"


def test_a_chosen_city_is_remembered_and_an_unasked_one_is_not():
    """A city is not a person - it is one of 137 names from a list we ship - but it is only stored when
    the reader actually chose it."""
    from app.web.panchang import CITY_COOKIE

    chosen = client.get("/panchang?city=Chennai")
    assert chosen.cookies.get(CITY_COOKIE) == "Chennai"
    plain = client.get("/panchang")
    assert plain.cookies.get(CITY_COOKIE) is None, "a visit that chose nothing must store nothing"


def test_a_date_that_cannot_be_answered_falls_back_to_today_rather_than_erroring():
    today = dt.date.today()
    assert resolve_date(None, today) == (today, True)
    assert resolve_date("not-a-date", today) == (today, True)
    assert resolve_date("2099-01-01", today) == (today, True)
    assert resolve_date((today + dt.timedelta(days=10)).isoformat(), today)[1] is False


@pytest.mark.parametrize("lang, path", PAGES)
def test_the_page_links_on_to_the_things_that_reader_wants_next(lang, path):
    html = client.get(path).text
    for key in ("rashifal-hub", "kundali", "consultation"):
        assert f'href="{i18n.url_for(key, lang)}"' in html, f"{path} does not link to {key}"


def test_all_three_are_in_the_sitemap_once():
    locs = re.findall(r"<loc>([^<]+)</loc>", client.get("/sitemap.xml").text)
    panchang = [loc for loc in locs if "panchang" in loc]
    assert len(panchang) == 3, panchang
    assert len(set(panchang)) == 3


def test_the_copy_is_complete_in_every_language():
    """A missing key renders as an empty cell rather than an error, which is why this is checked."""
    keys = {lang: set(words) for lang, words in COPY.items()}
    assert keys["en"] == keys["hi"] == keys["mr"], {
        "hi missing": keys["en"] - keys["hi"], "mr missing": keys["en"] - keys["mr"]}
    for lang, words in COPY.items():
        empty = [key for key, value in words.items() if not str(value).strip()]
        assert not empty, f"{lang}: empty copy for {empty}"


@pytest.mark.parametrize("lang, path", PAGES)
def test_a_time_on_another_date_says_so(lang, path):
    """A tithi ending at 06:11 TOMORROW printed as "06:11" reads as this morning - the single most
    misleading thing a panchang can do, because somebody plans a vrat around it."""
    from app.web.panchang import _clock

    today = dt.date(2026, 10, 21)
    assert _clock("2026-10-21T14:12+05:30", today) == "14:12"
    assert "(" in _clock("2026-10-22T06:11+05:30", today)
