"""Festival muhurta pages: the date, and the puja window in the reader's own city.

A FAMILY ACTS ON THESE NUMBERS, so they were checked against published panchangs before being published,
and the checks below are against the ephemeris rather than against dates typed into a test.

THE TWO THINGS THAT MAKE A FESTIVAL DATE WRONG, both of which the first implementation did:

1. THE WRONG LUNAR MONTH. There is a Krishna Trayodashi and an Amavasya every lunar month, and a scan
   that takes the first one in October finds Ashwin's - a full month before Diwali. The month is pinned by
   the Sun's sign: Diwali's Amavasya is the new moon with the Sun in Tula.

2. THE TITHI AT SUNRISE INSTEAD OF AT THE PUJA. A panchang names a day after the tithi running at sunrise,
   but a tithi lasts about 23h37m, so the tithi at sunset is routinely the next one. Trayodashi 2026 runs
   10:31 on 6 November to 10:48 on the 7th: the 7th is the day NAMED Trayodashi, and the 6th is the evening
   that HAS it. Asking which day is named for the tithi puts Dhanteras a day late.

And the one that makes a window wrong: intersecting the fixed-sign window with pradosh kaal. That is
invisible in Delhi, where the lagna sits inside pradosh, and cuts five minutes off the end in Mumbai.
"""
from __future__ import annotations

import datetime as dt
import re

import pytest
from fastapi.testclient import TestClient

from app.engine import festivals
from app.main import app
from app.web import i18n, site

client = TestClient(app, raise_server_exceptions=False)

PATHS = [(path, lang, params["festival"], int(params["year"]))
         for path, key, lang, params in i18n.all_paths() if key == "festival"]

#: What two published panchangs give for 2026. These are the OUTSIDE check: everything else in this file
#: is computed, and these four numbers are the ones that caught the two date bugs and the window bug.
PUBLISHED = {
    ("dhanteras", 2026): {"date": dt.date(2026, 11, 6)},
    ("lakshmi-puja", 2026): {"date": dt.date(2026, 11, 8),
                             "windows": {"Delhi": ("17:54", "19:50"), "Mumbai": ("18:27", "20:27")}},
}


def test_there_is_a_page_for_each_festival_in_each_tree():
    assert len(PATHS) == len(i18n.FESTIVAL_PAGES) * 3, len(PATHS)


@pytest.mark.parametrize("path, lang, festival, year", PATHS)
def test_every_one_of_them_answers(path, lang, festival, year):
    assert client.get(path).status_code == 200, path


def test_bhai_dooj_is_not_published():
    """Our Dwitiya times agree with the published ones to the minute, but the panchangs disagree about
    which DAY that makes the festival: on 10 November 2026 Dwitiya covers only part of aparahna. The
    disagreement is about convention, not arithmetic, so it is reported and not published."""
    assert not any(f == "bhai-dooj" for f, _ in i18n.FESTIVAL_PAGES)
    for lang in i18n.LANGS:
        prefix = i18n.PAGES["festival"][lang].split("/{festival}")[0]
        assert client.get(f"{prefix}/bhai-dooj-2026").status_code == 404


def test_the_dwitiya_times_that_caused_that_are_still_what_we_compute():
    """If a later change moved these, the reason Bhai Dooj is withheld would have changed with it, and
    the decision would need revisiting rather than inheriting."""
    from app.engine.festivals import _tithi_at

    IST = festivals.IST
    before = _tithi_at(dt.datetime(2026, 11, 10, 13, 55, tzinfo=IST))
    after = _tithi_at(dt.datetime(2026, 11, 10, 14, 5, tzinfo=IST))
    assert before["day"] == 1 and after["day"] == 2, (before["name"], after["name"])
    still = _tithi_at(dt.datetime(2026, 11, 11, 15, 50, tzinfo=IST))
    gone = _tithi_at(dt.datetime(2026, 11, 11, 16, 0, tzinfo=IST))
    assert still["day"] == 2 and gone["day"] == 3, (still["name"], gone["name"])


# ---- the dates ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("festival, year", list(i18n.FESTIVAL_PAGES))
def test_the_date_matches_the_published_panchangs(festival, year):
    computed = festivals.windows(festival, year, "Delhi")
    assert computed["date"] == PUBLISHED[(festival, year)]["date"], (festival, computed["date"])


@pytest.mark.parametrize("festival, year", list(i18n.FESTIVAL_PAGES))
def test_the_date_is_the_same_in_every_one_of_the_eight_cities(festival, year):
    """These tithi boundaries are far from sunset everywhere in India, so a city whose date differed
    would mean the day was being chosen by something other than the tithi."""
    dates = {row["city"]["name"]: row["date"] for row in festivals.all_cities(festival, year)}
    assert len(set(dates.values())) == 1, dates


@pytest.mark.parametrize("festival, year", list(i18n.FESTIVAL_PAGES))
def test_the_tithi_running_at_the_puja_is_the_one_the_festival_needs(festival, year):
    rule = festivals.FESTIVALS[festival]
    computed = festivals.windows(festival, year, "Delhi")
    assert computed["tithi_at_observance"]["day"] == rule["tithi"], computed["tithi_at_observance"]
    assert computed["tithi_at_observance"]["paksha"]["key"] == rule["paksha"]


@pytest.mark.parametrize("festival, year", list(i18n.FESTIVAL_PAGES))
def test_the_day_is_usually_named_after_a_different_tithi(festival, year):
    """This is the trap, stated as a test. If these two were always equal, reading the tithi at sunrise
    would work and this whole module would be unnecessary - and on both 2026 dates they differ."""
    computed = festivals.windows(festival, year, "Delhi")
    assert computed["tithi"]["day"] != computed["tithi_at_observance"]["day"], computed["tithi"]


@pytest.mark.parametrize("festival, year", list(i18n.FESTIVAL_PAGES))
def test_the_lunar_month_is_pinned_by_the_suns_sign(festival, year):
    """Without this the scan finds Ashwin's Trayodashi and Amavasya, one lunar month early."""
    computed = festivals.windows(festival, year, "Delhi")
    place = festivals._place("Delhi")
    assert festivals._sun_sign(computed["date"], place) == festivals.FESTIVALS[festival]["sun_sign"]


# ---- the windows -------------------------------------------------------------------------------------

@pytest.mark.parametrize("city, expected", list(PUBLISHED[("lakshmi-puja", 2026)]["windows"].items()))
def test_the_puja_window_matches_a_published_panchang_to_the_minute(city, expected):
    """TWO cities, because one cannot tell the two candidate rules apart: in Delhi the fixed-sign window
    sits inside pradosh kaal, so intersecting them changes nothing, and in Mumbai it does not."""
    window = festivals.windows("lakshmi-puja", 2026, city)["muhurta"]
    assert window, city
    assert window["start"].strftime("%H:%M") == expected[0], (city, window["start"])
    assert window["end"].strftime("%H:%M") == expected[1], (city, window["end"])


def test_the_window_is_the_fixed_signs_own_and_not_clipped_by_pradosh():
    """Mumbai's Vrishabha lagna runs past the end of pradosh kaal. The published muhurat follows the
    lagna, so clipping it would publish a window five minutes short of every panchang."""
    mumbai = festivals.windows("lakshmi-puja", 2026, "Mumbai")
    assert mumbai["muhurta"]["end"] > mumbai["pradosh"]["end"], mumbai


def test_the_window_differs_between_cities():
    """Sunset differs by half an hour across these eight. One time for the whole country is wrong for
    almost all of it, which is the reason the table exists."""
    starts = {row["city"]["name"]: row["muhurta"]["start"].strftime("%H:%M")
              for row in festivals.all_cities("lakshmi-puja", 2026) if row["muhurta"]}
    assert len(set(starts.values())) >= 6, starts


def test_dhanteras_has_no_fixed_sign_window_and_does_not_invent_one():
    for row in festivals.all_cities("dhanteras", 2026):
        assert row["muhurta"] is None, row["city"]["name"]
        assert row["pradosh"]["start"] < row["pradosh"]["end"]


# ---- the page ----------------------------------------------------------------------------------------

@pytest.mark.parametrize("path, lang, festival, year", PATHS)
def test_the_date_is_in_the_heading(path, lang, festival, year):
    from app.rashifal.i18n import format_date

    expected = format_date(PUBLISHED[(festival, year)]["date"].isoformat(), lang)
    h1 = re.search(r"<h1>(.*?)</h1>", client.get(path).text, re.S)
    assert h1 and expected in h1.group(1), (path, h1.group(1) if h1 else None)


@pytest.mark.parametrize("path, lang, festival, year", PATHS)
def test_all_eight_cities_are_on_the_page(path, lang, festival, year):
    html = client.get(path).text
    for city in festivals.MAJOR_CITIES:
        assert city in html, (path, city)


@pytest.mark.parametrize("path, lang, festival, year", PATHS)
def test_the_city_picker_needs_no_javascript(path, lang, festival, year):
    """The CSP has no 'unsafe-inline' and this page must work with scripting off: a GET form, and the
    chosen city comes back from the server."""
    html = client.get(path).text
    assert 'method="get"' in html and 'name="city"' in html, path
    assert html.count("<option") > 100, path


@pytest.mark.parametrize("path, lang, festival, year", PATHS)
def test_a_chosen_city_is_shown_first(path, lang, festival, year):
    html = client.get(path + "?city=Mumbai").text
    assert 'id="picked"' in html, path
    window = festivals.windows(festival, year, "Mumbai")
    shown = window["muhurta"] or window["pradosh"]
    assert shown["start"].strftime("%H:%M") in html, path


@pytest.mark.parametrize("path, lang, festival, year", PATHS)
def test_an_unknown_city_still_shows_the_festival(path, lang, festival, year):
    """A stale or mistyped link is not a reason to deny somebody the date."""
    response = client.get(path + "?city=Atlantis")
    assert response.status_code == 200, path
    assert festivals.MAJOR_CITIES[0] in response.text


@pytest.mark.parametrize("path, lang, festival, year", PATHS)
def test_the_page_explains_why_this_date(path, lang, festival, year):
    """A reader whose printed calendar names that day after a different tithi will otherwise conclude the
    page is wrong."""
    assert 'id="why"' in client.get(path).text, path


@pytest.mark.parametrize("path, lang, festival, year", PATHS)
def test_no_second_is_printed_on_a_clock(path, lang, festival, year):
    """The lagna starts at 17:54:44 in Delhi. The second is real, and it is not what anybody acts on, and
    printing it claims a precision the sunset convention does not support."""
    body = re.search(r"<main.*?</main>", client.get(path).text, re.S)
    assert body and not re.search(r"\b\d{1,2}:\d{2}:\d{2}\b", body.group(0)), path


@pytest.mark.parametrize("path, lang, festival, year", PATHS)
def test_the_muhurta_finder_is_linked_only_when_it_is_served(path, lang, festival, year):
    """site.MUHURTA is off by default. A button pointing at a path the app does not route is a 404 we put
    there ourselves, and without this guard it shipped on all six pages."""
    html = client.get(path).text
    if site.MUHURTA:
        assert 'id="cta-muhurta"' in html, path
    else:
        assert 'id="cta-muhurta"' not in html, path


@pytest.mark.parametrize("path, lang, festival, year", PATHS)
def test_it_says_what_computed_the_windows(path, lang, festival, year):
    assert "Swiss Ephemeris" in client.get(path).text, path


def test_they_are_in_the_sitemap():
    sitemap = client.get("/sitemap.xml").text
    for path, _lang, _festival, _year in PATHS:
        assert path in sitemap, path
