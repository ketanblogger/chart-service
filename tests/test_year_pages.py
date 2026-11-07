"""/horoscope/aries/2027 - a permanent address for one year, which the rolling yearly page has not got.

WHY THESE EXIST. /horoscope/{rashi}/yearly is always "this year", so no link and no search result can
point at 2027, and every January its content quietly becomes a different year's. People start searching
"rashifal 2027" in the autumn before it, which is now.

WHAT IS ON THEM is the part that is true before anybody writes a word: where Guru and Shani stand through
the year, as HOUSES counted from that rashi, and the days they move - so the same sky is a different year
for each of the twelve. Every date is a sidereal ingress or station from the same scan the charts use;
these tests check the pages against that scan, not against dates typed into a test.
"""
from __future__ import annotations

import datetime as dt
import re

import pytest
from fastapi.testclient import TestClient

from app.engine import transits
from app.main import app
from app.rashifal import year_facts
from app.rashifal.i18n import format_date
from app.web import i18n

client = TestClient(app, raise_server_exceptions=False)

PATHS = [(path, lang, params["rashi"], int(params["year"]))
         for path, key, lang, params in i18n.all_paths() if key == "rashifal-year"]
YEAR = i18n.YEAR_PAGES[0]


def test_there_is_one_for_every_rashi_in_every_tree_for_every_year():
    # The multiplication is 0 == 0 when YEAR_PAGES is empty, so emptying that one constant would delete
    # all 36 pages and leave this green. The constant is asserted non-empty first.
    assert i18n.YEAR_PAGES, "no years are published; these pages do not exist"
    assert len(PATHS) == 12 * 3 * len(i18n.YEAR_PAGES), len(PATHS)


@pytest.mark.parametrize("path, lang, rashi, year", PATHS)
def test_every_one_of_them_answers(path, lang, rashi, year):
    assert client.get(path).status_code == 200, path


@pytest.mark.parametrize("path, lang, rashi, year", PATHS)
def test_the_year_is_in_the_title_and_the_heading(path, lang, rashi, year):
    """A permanent page whose title does not name its year is indistinguishable, in a result list, from
    the rolling page it exists to replace."""
    html = client.get(path).text
    title = re.search(r"<title>(.*?)</title>", html, re.S)
    h1 = re.search(r"<h1>(.*?)</h1>", html, re.S)
    assert title and str(year) in title.group(1), (path, title.group(1) if title else None)
    assert h1 and str(year) in h1.group(1), (path, h1.group(1) if h1 else None)


@pytest.mark.parametrize("path, lang, rashi, year", PATHS)
def test_the_title_fits_a_search_result(path, lang, rashi, year):
    title = re.search(r"<title>(.*?)</title>", client.get(path).text, re.S)
    assert title and len(title.group(1).strip()) <= 60, (path, len(title.group(1).strip()))


# ---- the two route families must not shadow each other -----------------------------------------------

@pytest.mark.parametrize("lang", list(i18n.LANGS))
def test_a_period_slug_is_still_a_period_and_a_year_is_still_a_year(lang):
    """"/horoscope/aries/2027" and "/horoscope/aries/today" are the same shape. The year route is typed
    as an int and registered first, so neither can be read as the other - rather than relying on an
    unknown period happening to 404, which would make the families depend on registration order."""
    for period in i18n.PERIOD_KEYS:
        path = i18n.url_for("rashifal-reading", lang, rashi="mesha", period=period)
        assert client.get(path).status_code == 200, path
    assert client.get(i18n.url_for("rashifal-year", lang, rashi="mesha", year=YEAR)).status_code == 200


@pytest.mark.parametrize("lang", list(i18n.LANGS))
def test_a_year_without_a_page_is_not_served(lang):
    """Only the years in the registry. A page for 2099 would be an empty promise with a real URL."""
    root = i18n.PAGES["rashifal-year"][lang].split("/{rashi}")[0]
    slug = i18n.rashi_slug("mesha", lang)
    assert client.get(f"{root}/{slug}/2099").status_code == 404


# ---- the dates are the ephemeris's ------------------------------------------------------------------

@pytest.mark.parametrize("rashi", list(i18n.RASHI_KEYS))
def test_every_turn_on_the_page_is_a_real_ingress_or_station(rashi):
    index = i18n.RASHI_KEYS.index(rashi) + 1
    facts = year_facts.for_rashi(index, YEAR)
    events = transits.transit_events(dt.datetime(YEAR, 1, 1), dt.datetime(YEAR + 1, 1, 1),
                                     grahas=list(year_facts.SLOW))
    real = {dt.datetime.fromisoformat(e["datetime"]).date() for e in events}
    assert facts["turns"], rashi
    for turn in facts["turns"]:
        assert turn["date"] in real, (rashi, turn["date"])


@pytest.mark.parametrize("rashi", list(i18n.RASHI_KEYS))
def test_the_houses_are_counted_from_this_rashi_and_differ_between_signs(rashi):
    """The same transit is a different year for each of the twelve. If the houses came out the same for
    every sign, they would be being read from the sign itself rather than from the reader's rashi."""
    index = i18n.RASHI_KEYS.index(rashi) + 1
    mine = year_facts.for_rashi(index, YEAR)
    other = year_facts.for_rashi((index % 12) + 1, YEAR)
    assert [s["house"] for s in mine["stays"]] != [s["house"] for s in other["stays"]], rashi
    for stay in mine["stays"]:
        assert 1 <= stay["house"] <= 12, stay


@pytest.mark.parametrize("rashi", list(i18n.RASHI_KEYS))
def test_the_stays_cover_the_whole_year_with_no_gap(rashi):
    """A year with a hole in it means a graha vanished for a while."""
    index = i18n.RASHI_KEYS.index(rashi) + 1
    facts = year_facts.for_rashi(index, YEAR)
    for graha in year_facts.SLOW:
        spans = [s for s in facts["stays"] if s["graha"]["key"] == graha or s["graha"].get("name")]
    for graha_name in {s["graha"]["name"] for s in facts["stays"]}:
        spans = sorted((s for s in facts["stays"] if s["graha"]["name"] == graha_name),
                       key=lambda s: s["start"])
        assert spans[0]["start"] == dt.date(YEAR, 1, 1), (rashi, graha_name, spans[0])
        assert spans[-1]["end"] == dt.date(YEAR, 12, 31), (rashi, graha_name, spans[-1])
        for before, after in zip(spans, spans[1:]):
            assert before["end"] == after["start"], (rashi, graha_name, before, after)


@pytest.mark.parametrize("path, lang, rashi, year", PATHS)
def test_the_dates_on_the_page_are_the_dates_the_engine_gave(path, lang, rashi, year):
    index = i18n.RASHI_KEYS.index(rashi) + 1
    facts = year_facts.for_rashi(index, year)
    html = client.get(path).text
    for turn in facts["turns"][:4]:
        assert format_date(turn["date"].isoformat(), lang) in html, (path, turn["date"])


@pytest.mark.parametrize("path, lang, rashi, year", PATHS)
def test_no_iso_date_is_shown_to_a_reader(path, lang, rashi, year):
    body = re.search(r"<main.*?</main>", client.get(path).text, re.S)
    assert body and not re.search(r"\b\d{4}-\d{2}-\d{2}\b", body.group(0)), path


@pytest.mark.parametrize("path, lang, rashi, year", [p for p in PATHS if p[1] in ("hi", "mr")])
def test_a_devanagari_page_names_the_grahas_in_devanagari(path, lang, rashi, year):
    """The engine returns "Jupiter", "Guru" and "गुरु", and the first version printed the middle one
    everywhere - so a Hindi page read "Guru Simha" in Latin letters inside a Devanagari table."""
    html = client.get(path).text
    table = re.search(r'<table class="copy-table">(.*?)</table>', html, re.S)
    assert table, path
    assert not re.search(r"<td>(Guru|Shani|Rahu|Simha|Karka|Mesha|Meena)</td>", table.group(1)), path


# ---- what the reader gets ---------------------------------------------------------------------------

@pytest.mark.parametrize("path, lang, rashi, year", PATHS)
def test_it_says_whether_sade_sati_touches_this_sign_in_this_year(path, lang, rashi, year):
    html = client.get(path).text
    assert 'id="sade"' in html, path
    assert i18n.url_for("sade-sati-rashi", lang, rashi=rashi) in html, path


@pytest.mark.parametrize("path, lang, rashi, year", PATHS)
def test_it_does_not_pretend_the_written_reading_exists_yet(path, lang, rashi, year):
    """The dates are final and the prose is not written. Saying which is which is the difference between
    an honest early page and a stub pretending to be a reading."""
    html = client.get(path).text
    assert "Swiss Ephemeris" in html, path


@pytest.mark.parametrize("path, lang, rashi, year", PATHS)
def test_it_offers_the_chart_and_the_astrologer(path, lang, rashi, year):
    html = client.get(path).text
    assert i18n.url_for("kundali", lang) in html, path
    assert i18n.url_for("consultation", lang) in html, path


@pytest.mark.parametrize("lang", list(i18n.LANGS))
def test_the_rolling_yearly_page_links_the_permanent_one(lang):
    """A page nothing links to is one the crawler reaches late or never, and the reader of "this year" is
    the likeliest reader of next year."""
    for rashi in i18n.RASHI_KEYS:
        html = client.get(i18n.url_for("rashifal-reading", lang, rashi=rashi, period="yearly")).text
        for year in i18n.YEAR_PAGES:
            assert i18n.url_for("rashifal-year", lang, rashi=rashi, year=year) in html, (lang, rashi)


@pytest.mark.parametrize("lang", list(i18n.LANGS))
def test_the_other_reading_pages_are_not_cluttered_with_it(lang):
    html = client.get(i18n.url_for("rashifal-reading", lang, rashi="mesha", period="monthly")).text
    assert i18n.url_for("rashifal-year", lang, rashi="mesha", year=YEAR) not in html


def test_they_are_in_the_sitemap():
    sitemap = client.get("/sitemap.xml").text
    for path, _lang, _rashi, _year in PATHS:
        assert path in sitemap, path


def test_adding_a_year_is_one_line():
    """YEAR_PAGES is the whole switch: the pages, the sitemap entries, the hreflang and the links from the
    rolling page all follow from it. A second year must not need a second route or a second template."""
    # Same vacuity: sorted(()) == () and all(... for ... in ()) is True.
    assert i18n.YEAR_PAGES, "no years are published"
    assert i18n.YEAR_PAGES == tuple(sorted(i18n.YEAR_PAGES))
    assert all(isinstance(year, int) for year in i18n.YEAR_PAGES)
    refs = [ref for ref in i18n.all_pages() if ref.key == "rashifal-year"]
    assert len(refs) == 12 * len(i18n.YEAR_PAGES) and refs
