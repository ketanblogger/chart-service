"""Sade Sati per Moon sign: 12 rashis x 3 trees, with the dates Saturn's own motion gives.

THE THING THAT MAKES THESE PAGES HARD TO GET RIGHT. The obvious implementation adds thirty months to an
ingress three times. Saturn retrogrades: across 1950-2100 the engine finds 128 sign crossings and 66 of
them are Saturn RETURNING to a sign it had already left. So a phase has a first entry and a final exit
with gaps between, published tables disagree about the same cycle, and arithmetic is wrong by months.

Every date on these pages comes from `engine.sadesati.cycles`, which reads real sidereal ingresses. These
tests check the dates against the ingresses rather than against a copy of the answer.
"""
from __future__ import annotations

import datetime as dt
import re

import pytest
from fastapi.testclient import TestClient

from app.engine import sadesati, transits
from app.main import app
from app.web import i18n

client = TestClient(app, raise_server_exceptions=False)

PATHS = [(path, lang, params["rashi"]) for path, key, lang, params in i18n.all_paths()
         if key == "sade-sati-rashi"]
NOW = dt.datetime(2026, 10, 20, 12, tzinfo=dt.timezone.utc)


def test_there_is_one_for_every_rashi_in_every_tree():
    assert len(PATHS) == 36, f"expected 12 rashis x 3 trees, got {len(PATHS)}"


@pytest.mark.parametrize("path, lang, rashi", PATHS)
def test_every_one_of_them_answers(path, lang, rashi):
    assert client.get(path).status_code == 200, path


def test_the_calculator_still_owns_its_own_url():
    """These pages were first registered under the key "sade-sati", which the free calculator already
    had. A dict literal takes a repeated key in silence and keeps the last one, so the calculator's URL
    became a template with {rashi} in it and nothing said a word."""
    assert i18n.PAGES["sade-sati"]["en"] == "/sade-sati"
    for lang in i18n.LANGS:
        assert client.get(i18n.url_for("sade-sati", lang)).status_code == 200


@pytest.mark.parametrize("lang", list(i18n.LANGS))
def test_a_slug_from_another_tree_is_not_a_second_address(lang):
    other = next(l for l in i18n.LANGS if l != lang)
    wrong = i18n.PAGES["sade-sati-rashi"][lang].replace("{rashi}", i18n.rashi_slug("makara", other))
    if wrong != i18n.url_for("sade-sati-rashi", lang, rashi="makara"):
        assert client.get(wrong).status_code == 404, wrong


# ---- the dates ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("rashi", list(i18n.RASHI_KEYS))
def test_a_cycle_begins_on_a_real_saturn_ingress(rashi):
    """Not "about 7.5 years after the last one": the start of a cycle is the day Saturn ENTERS the twelfth
    sign from the Moon sign, and that date must appear in the ephemeris scan."""
    index = i18n.RASHI_KEYS.index(rashi) + 1
    cycles = sadesati.cycles(index, NOW)
    cycle = cycles["current"] or cycles["next"]
    assert cycle, rashi

    span_start = dt.datetime.fromisoformat(cycle["start"]) - dt.timedelta(days=5)
    events = transits.transit_events(span_start, span_start + dt.timedelta(days=10), grahas=["Saturn"])
    ingress_days = {dt.datetime.fromisoformat(e["datetime"]).date().isoformat()
                    for e in events if e["type"] == "ingress"}
    assert cycle["start"] in ingress_days, (rashi, cycle["start"], sorted(ingress_days))


@pytest.mark.parametrize("rashi", list(i18n.RASHI_KEYS))
def test_a_cycle_runs_about_seven_and_a_half_years_never_exactly(rashi):
    """Three signs at ~2.5 years each, plus however long the retrograde returns add. A cycle that came out
    at exactly 2738 days every time would mean the dates were arithmetic and not transits."""
    index = i18n.RASHI_KEYS.index(rashi) + 1
    for key in ("previous", "current", "next"):
        cycle = sadesati.cycles(index, NOW)[key]
        if not cycle:
            continue
        days = (dt.date.fromisoformat(cycle["end"]) - dt.date.fromisoformat(cycle["start"])).days
        # The upper bound is 3300 and not 3100 because of Vrishchika's 2041 cycle, which is 8.85 years
        # and is right: Saturn touches Libra for NINE DAYS in January 2041, retrogrades out, and comes
        # back in September, then wobbles at both later boundaries too. First touch to final exit is the
        # honest span of that cycle. 3100 was my guess at how long Sade Sati can be, and the ephemeris
        # disagreed with it.
        assert 2550 <= days <= 3300, (rashi, key, cycle["start"], cycle["end"], days)


@pytest.mark.parametrize("rashi", list(i18n.RASHI_KEYS))
def test_the_three_phases_are_all_there_and_in_order(rashi):
    index = i18n.RASHI_KEYS.index(rashi) + 1
    for key in ("previous", "current", "next"):
        cycle = sadesati.cycles(index, NOW)[key]
        if not cycle:
            continue
        assert [p["phase"] for p in cycle["phases"]] == ["rising", "peak", "setting"], (rashi, key)
        starts = [p["start"] for p in cycle["phases"]]
        assert starts == sorted(starts), (rashi, key, starts)


@pytest.mark.parametrize("rashi", list(i18n.RASHI_KEYS))
def test_a_previous_cycle_is_about_one_saturn_orbit_before_this_one(rashi):
    """Saturn goes round in about 29.5 years, so consecutive Sade Satis for a sign are that far apart.
    This is what catches a "previous" cycle that is really the current one read twice, or a table whose
    span is too narrow to hold a previous cycle at all."""
    index = i18n.RASHI_KEYS.index(rashi) + 1
    cycles = sadesati.cycles(index, NOW)
    assert cycles["previous"], f"no previous cycle for {rashi} - the span is too narrow"
    later = cycles["current"] or cycles["next"]
    gap = (dt.date.fromisoformat(later["start"]) - dt.date.fromisoformat(cycles["previous"]["start"])).days
    assert 9 * 365 <= gap <= 31 * 365, (rashi, cycles["previous"]["start"], later["start"], gap / 365.25)


def test_a_retrograde_return_is_counted_and_not_smoothed_away():
    """Over the whole zodiac some phase must show a return, because two thirds of Saturn's crossings are
    returns. A build where every `returns` is 0 means the gaps were merged and the dates are no longer
    the transits."""
    total = 0
    for rashi in i18n.RASHI_KEYS:
        index = i18n.RASHI_KEYS.index(rashi) + 1
        for key in ("previous", "current", "next"):
            cycle = sadesati.cycles(index, NOW)[key]
            if cycle:
                total += sum(p["returns"] for p in cycle["phases"])
    assert total >= 12, f"only {total} retrograde returns across 36 cycles - they are being merged away"


def test_the_wide_table_does_not_disturb_the_one_reports_use():
    """A public page asking about a cycle thirty years ago must not change what a paid report computes.
    The two spans are separate cache entries, and this is the check that keeps them that way."""
    before = sadesati.sade_sati(10, NOW)
    sadesati.cycles(10, NOW)
    assert sadesati.sade_sati(10, NOW) == before


# ---- what the reader sees ----------------------------------------------------------------------------

@pytest.mark.parametrize("path, lang, rashi", PATHS)
def test_whether_it_is_running_is_the_first_thing_said(path, lang, rashi):
    html = client.get(path).text
    status = re.search(r'class="lede sadesati__status">(.*?)</p>', html, re.S)
    assert status and status.group(1).strip(), path


@pytest.mark.parametrize("path, lang, rashi", PATHS)
def test_no_iso_date_is_shown_to_a_reader(path, lang, rashi):
    """The engine speaks ISO, which is right for an engine and wrong on a page: "2049-03-06" asks the
    reader to parse a format before reading a date."""
    body = re.search(r"<main.*?</main>", client.get(path).text, re.S)
    assert body, path
    assert not re.search(r"\b\d{4}-\d{2}-\d{2}\b", body.group(0)), path


@pytest.mark.parametrize("path, lang, rashi", PATHS)
def test_the_dates_on_the_page_are_the_dates_the_engine_gave(path, lang, rashi):
    """The page is checked against the engine, not against a list of dates typed into a test - which
    would only prove the two copies match."""
    from app.rashifal.i18n import format_date

    index = i18n.RASHI_KEYS.index(rashi) + 1
    cycles = sadesati.cycles(index, dt.datetime.now(dt.timezone.utc))
    html = client.get(path).text
    for key in ("previous", "current", "next"):
        cycle = cycles[key]
        if not cycle:
            continue
        for field in ("start", "end"):
            assert format_date(cycle[field], lang) in html, (path, key, field, cycle[field])


@pytest.mark.parametrize("path, lang, rashi", PATHS)
def test_it_says_where_the_dates_come_from(path, lang, rashi):
    """A page of dates that does not say what computed them is asking to be trusted for no reason."""
    html = client.get(path).text
    assert "Swiss Ephemeris" in html, path


@pytest.mark.parametrize("path, lang, rashi", PATHS)
def test_it_offers_the_calculator_the_chart_and_the_astrologer(path, lang, rashi):
    html = client.get(path).text
    assert i18n.url_for("sade-sati", lang) in html, path
    assert i18n.url_for("consultation", lang) in html, path
    assert i18n.url_for("rashifal-rashi", lang, rashi=rashi) in html, path


@pytest.mark.parametrize("path, lang, rashi", PATHS)
def test_it_tells_the_reader_the_transit_is_not_a_verdict(path, lang, rashi):
    """Somebody arriving here has usually been told Sade Sati is a disaster, so the page has to say
    plainly what the transit is and what it is not.

    THIS WAS FIRST WRITTEN AS A BLOCKLIST of frightening words, and it failed on the page's own
    reassurance: "demanding rather than ruinous" contains "ruin", and the Marathi "विनाशकारी नाहीत" -
    "not destructive" - contains विनाश. A blocklist cannot tell a word from its negation, so it fails
    exactly where the copy is doing the right thing, and it would pass on a page that frightened the
    reader using any word not on the list. What the page must CONTAIN is the testable thing."""
    html = client.get(path).text
    reassurance = {
        "en": ("transit, not a verdict", "rather than ruinous"),
        "hi": ("कोई फ़ैसला नहीं", "बर्बादी वाले\nनहीं", "बर्बादी वाले नहीं"),
        "mr": ("निकाल नाही", "विनाशकारी नाहीत"),
    }[lang]
    assert any(phrase in html for phrase in reassurance), (path, reassurance)


@pytest.mark.parametrize("path, lang, rashi", PATHS)
def test_the_title_fits_a_search_result(path, lang, rashi):
    title = re.search(r"<title>(.*?)</title>", client.get(path).text, re.S)
    assert title and len(title.group(1).strip()) <= 65, (path, title.group(1) if title else None)


def test_localising_the_dates_does_not_touch_the_engines_own_dict():
    """THE INVARIANT, stated where it can actually fail.

    My first version of this test rendered a Hindi page then an English one and looked for Devanagari
    dates in the English output. IT PASSED EVEN WITH THE BUG DELIBERATELY IN PLACE - cycles() cached AND
    the page rewriting its result - because the cache key includes `as_of_utc`, which is
    datetime.now(timezone.utc) and therefore different on every request, so the cache never hits and the
    mutation never reaches a second reader. A test that cannot fail is worse than no test: it reports the
    hazard as handled.

    What IS testable is the rule itself: the page must not write into the dict the engine handed it. That
    fails immediately for an in-place version, whatever any cache is doing."""
    from app.web.sade_sati_pages import _localise

    original = sadesati.cycles(10, NOW)
    cycle = original["current"] or original["next"]
    before = cycle["start"]
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", before), before

    localised = _localise(original, "hi")

    after = (original["current"] or original["next"])["start"]
    assert after == before, f"the engine's dict was rewritten: {before} became {after}"
    shown = (localised["current"] or localised["next"])["start"]
    assert shown != before and re.search(r"[\u0900-\u097F]", shown), shown


def test_the_engine_still_hands_out_iso_dates():
    """The copy is only correct if the source is untouched: if the engine itself started returning
    localised dates, every other caller - the paid report, the API - would get them too."""
    cycles = sadesati.cycles(10, NOW)
    cycle = cycles["current"] or cycles["next"]
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", cycle["start"]), cycle["start"]
