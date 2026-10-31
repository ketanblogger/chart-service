"""The "shaadi kab hogi" tool: supportive periods, and never a date.

THE MOST IMPORTANT TEST IN THIS FILE IS THE ONE THAT CHECKS WHAT THE PAGE DOES NOT SAY. "meri shadi kab
hogi" is asked 50,000 times a month by people who want a date, and a chart has none to give. The page is
built so that the honest sentence is the first thing above the form rather than a footnote under the
result - somebody should read that there is no date before they type their birth details in.
"""
from __future__ import annotations

import datetime as dt
import re

import pytest
from fastapi.testclient import TestClient

from app.engine.chart import compute_chart
from app.engine.timing import TOPICS, indications, supportive_lords, transit_openings, windows
from app.main import app
from app.web import i18n
from app.web.marriage_timing import COPY, view

client = TestClient(app)
PAGES = [("en", "/when-will-i-get-married"), ("hi", "/hi/shadi-kab-hogi"), ("mr", "/mr/lagna-kadhi-hoil")]
TODAY = dt.date(2026, 10, 22)


def chart_at(hour: int = 7, minute: int = 30):
    """An invented person, as every test on this site uses."""
    return compute_chart(dt.date(1990, 5, 14), dt.time(hour, minute), 18.52, 73.86, "Asia/Kolkata")


@pytest.mark.parametrize("lang, path", PAGES)
def test_the_page_never_promises_that_it_will_happen(lang, path):
    """No future-tense claim about the reader's life, in any of the three languages."""
    html = client.get(path).text
    body = re.sub(r"<[^>]+>", " ", html.split("<main", 1)[1].split("</main>", 1)[0])
    forbidden = {
        "en": ["you will marry", "will get married in", "guaranteed", "certain to", "definitely"],
        "hi": ["निश्चित रूप से", "गारंटी", "पक्का होगा"],
        "mr": ["नक्कीच होईल", "हमी", "खात्रीने होईल"],
    }[lang]
    for phrase in forbidden:
        assert phrase.lower() not in body.lower(), f"{path} promises: {phrase!r}"


@pytest.mark.parametrize("lang, path", PAGES)
def test_the_honest_line_sits_above_the_form(lang, path):
    """Not in a footnote. Somebody who came for a date should read that there isn't one BEFORE they type
    their birth details in."""
    html = client.get(path).text
    main = html.split("<main", 1)[1]
    honest = main.index(COPY[lang]["honest"])
    form = main.index("marriage-form")
    assert honest < form, f"{path}: the caveat comes after the form"


@pytest.mark.parametrize("lang, path", PAGES)
def test_the_page_offers_the_astrologer_with_the_topic(lang, path):
    html = client.get(path).text
    assert f'href="{i18n.url_for("consultation", lang)}?topic=marriage"' in html


def test_the_windows_are_periods_and_carry_their_reason():
    """A window with no reason is an assertion; with one it is a reading somebody can check."""
    found = windows(chart_at(), today=TODAY)
    assert found, "this chart has supportive periods in the next three years"
    for w in found:
        assert w.start < w.end
        assert w.reasons, "a window with no reason is just an assertion"
        assert w.strength in ("strong", "supportive")
        assert (w.end - w.start).days >= 1


def test_no_window_runs_past_the_horizon_or_starts_in_the_past():
    for w in windows(chart_at(), years=3, today=TODAY):
        assert w.start >= TODAY
        assert w.end <= TODAY + dt.timedelta(days=int(365.25 * 3)) + dt.timedelta(days=1)


def test_strong_means_both_levels_agree():
    """"Strong" is not a feeling: it means the mahadasha AND the antardasha lord are both on the
    supportive list. Anything looser would be a number dressed as tradition."""
    for w in windows(chart_at(), today=TODAY):
        assert (w.strength == "strong") == (len(w.reasons) == 2), w


def test_the_supportive_lords_are_the_classical_ones():
    chart = chart_at()
    lords = supportive_lords(chart)
    facts = indications(chart)
    assert facts["lord"] in lords, "the seventh lord must be on the list"
    for karaka in TOPICS["marriage"].karakas:
        assert karaka in lords, f"{karaka} is a karaka for marriage"


def test_a_jupiter_transit_over_the_house_is_found_when_there_is_one():
    """The guard must be able to FIRE, or "no openings" would be the answer for every chart.

    A Simha lagna has Jupiter arriving on 31 October 2026 - the same ingress verified against the
    ephemeris for the Marathi examples - so this chart must produce an opening.
    """
    simha = chart_at(hour=13)
    assert simha["lagna"]["sign"]["name"] == "Simha"
    openings = transit_openings(simha, today=TODAY)
    assert openings, "Jupiter enters Simha on 31 Oct 2026; this chart must see it"
    assert any(o["sign"] == "Simha" for o in openings)


def test_a_chart_jupiter_does_not_reach_gets_an_empty_list_not_a_guess():
    mithuna = chart_at(hour=9)
    assert transit_openings(mithuna, today=TODAY) == []


def test_one_opening_per_sign_even_when_jupiter_retrogrades_back_into_it():
    """Jupiter can enter a sign, retrograde out and return, which produced three "openings" for one
    arrival and read as three separate chances."""
    rendered = view(chart_at(hour=13), "en", today=TODAY)
    signs = [o["text"] for o in rendered["openings"]]
    assert len(signs) == len(set(signs))
    assert len(rendered["openings"]) == 1, rendered["openings"]


def test_the_copy_is_complete_in_every_language():
    keys = {lang: set(words) for lang, words in COPY.items()}
    assert keys["en"] == keys["hi"] == keys["mr"]
    for lang, words in COPY.items():
        assert all(str(v).strip() for v in words.values()), lang


def test_the_engine_takes_the_question_as_data():
    """"naukri kab lagegi" must be a TOPICS entry and its copy, not a second engine - which is only true
    if nothing in the engine hardcodes the seventh house."""
    import inspect

    from app.engine import timing

    source = inspect.getsource(timing)
    body = "\n".join(line for line in source.splitlines() if not line.strip().startswith("#"))
    functions = body.split("TOPICS = {", 1)[1].split("}", 1)[1]
    assert "== 7" not in functions and "house = 7" not in functions, (
        "the seventh house is hardcoded in the engine rather than coming from the topic")


SUBMISSION = {"name": "Asha", "date": "1990-05-14", "time": "07:30", "city": "Pune"}


@pytest.mark.parametrize("lang, path", PAGES)
def test_the_result_comes_back_in_the_pages_own_language(lang, path):
    """The engine speaks in keys - "Mars", "mahadasha of Mars" - and a Hindi page must not. This caught
    a result that read "भावेश Mars — भाव में 10" and "क्योंकि mahadasha of Mars"."""
    html = client.post(path, data=SUBMISSION).text
    assert 'id="result"' in html, f"{path}: no result for a valid submission"
    result = re.sub(r"<[^>]+>", " ", html.split('id="result"', 1)[1])
    if lang in ("hi", "mr"):
        for english in ("mahadasha of", "antardasha of", "Mars", "Venus", "Jupiter"):
            assert english not in result, f"{path}: result still says {english!r}"
        assert "मंगल" in result or "शुक्र" in result or "गुरु" in result


@pytest.mark.parametrize("lang, path", PAGES)
def test_birth_details_are_posted_and_never_put_in_the_url(lang, path):
    """A birth date, a time and a city in a query string reach the server log, the browser history and
    the Referer header of the next link the reader clicks. The panchang picker is a GET form because a
    city and a date are not a person; together with a birth time they are."""
    html = client.get(path).text
    form = html.split('id="marriage-form"', 1)[1].split("</form>", 1)[0]
    opening = html.split('id="marriage-form"', 1)[0][-200:] + html.split('id="marriage-form"', 1)[1][:200]
    assert 'method="post"' in opening, f"{path}: the birth-details form is not a POST"
    assert "data-endpoint" not in form


@pytest.mark.parametrize("lang, path", PAGES)
def test_unusable_details_show_no_result_rather_than_an_error(lang, path):
    for bad in ({**SUBMISSION, "date": "not-a-date"}, {**SUBMISSION, "city": "Nowhere-at-all"}):
        response = client.post(path, data=bad)
        assert response.status_code == 200, (path, bad)
        assert 'id="result"' not in response.text


@pytest.mark.parametrize("lang, path", PAGES)
def test_a_missing_birth_time_still_answers(lang, path):
    """"समय नहीं पता" is the commonest case on this site. A dasha needs the Moon, which moves slowly
    enough that noon is a usable stand-in for this question - unlike the lagna."""
    response = client.post(path, data={**SUBMISSION, "time": ""})
    assert response.status_code == 200 and 'id="result"' in response.text


# ---- what a chart can say without a birth time -------------------------------------------------------

def test_every_graha_is_checked_for_an_ingress_on_the_birth_day():
    """NOT JUST THE SUN AND MOON. A birth on any graha's ingress day has that graha in doubt too.

    Jupiter enters Simha on 31 October 2026 at 12:02 IST - the same ingress verified against the
    ephemeris for the Marathi style examples - so a birth on that date is Karka or Simha for Jupiter
    depending on the hour, and the honest answer names both.
    """
    from app.engine.without_time import _OTHERS, what_is_known

    assert set(_OTHERS) == {"Sun", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu"}
    known = what_is_known(dt.date(2026, 10, 31))
    jupiter = [e for e in known["unsettled"] if e["graha"] == "Jupiter"]
    assert jupiter, "Jupiter changes sign on this date and must be reported as undecided"
    assert [s["name"] for s in jupiter[0]["signs"]] == ["Karka", "Simha"]
    assert jupiter[0]["depends_on_time"] is True


def test_a_sankranti_birth_has_even_the_sun_in_doubt():
    from app.engine.without_time import what_is_known

    known = what_is_known(dt.date(2026, 10, 17))
    sun = [e for e in known["unsettled"] if e["graha"] == "Sun"]
    assert sun and [s["name"] for s in sun[0]["signs"]] == ["Kanya", "Tula"]


def test_the_things_a_missing_time_destroys_are_named_not_approximated():
    """An hour's doubt moves every dasha date by months, and "probably about right" is exactly what
    somebody plans around."""
    from app.engine.without_time import what_is_known

    known = what_is_known(dt.date(1990, 5, 14))
    assert set(known["needs_birth_time"]) >= {"lagna", "houses", "dasha", "mangal_dosha"}
    for entry in known["settled"] + known["unsettled"]:
        assert entry["graha"] != "lagna"


def test_the_moon_is_undecided_often_enough_to_matter():
    """About two days in five. If this ever reports zero the check has stopped working."""
    from app.engine.without_time import moon_sign_is_safe

    days = [dt.date(2026, 10, 1) + dt.timedelta(days=n) for n in range(30)]
    ambiguous = sum(1 for day in days if not moon_sign_is_safe(day))
    assert 8 <= ambiguous <= 18, f"{ambiguous} of 30 - the Moon crosses a sign about every 2.3 days"
