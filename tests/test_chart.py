"""Phase 1 "done when": the engine reproduces published charts.

The accuracy proof here is EXTERNAL. The planetary positions asserted below are the ones an astrology
publisher prints, not ones this engine produced - see tests/reference_charts.py for each source and
the date it was fetched. A few structural facts (house tables, JSON round-tripping, thread safety)
are regression pins and say so.
"""

import json
import threading
from datetime import datetime

import pytest

from app.engine import compute_chart
from tests.reference_charts import AS_OF, INDIRA, KALAM, NEHRU, VIVEKANANDA


@pytest.fixture(scope="module")
def nehru():
    return NEHRU.chart()


@pytest.fixture(scope="module")
def kalam():
    return KALAM.chart()


# --- external accuracy: published positions -------------------------------------------------------

def test_nehru_planets_match_the_published_chart(nehru):
    """14 Nov 1889, 23:30, Allahabad. AstroSage prints sign and degree for the seven classical
    grahas (rated "Accurate (A)", source Kundli Sangraha); every one agrees to under 1.2
    arc-minutes.

    The tolerance is deliberately tight. It was 4.2' for a while, and 4.2' is wide enough to swallow
    an 8m50s error in the clock - which is exactly what was happening, unnoticed, because the
    reference said `Asia/Kolkata` (Madras time in 1889) while its comment claimed +05:30. A
    tolerance that can absorb a whole timezone convention has stopped testing the ephemeris.
    """
    for graha, (sign, degree) in NEHRU.published.items():
        actual = nehru["grahas"][graha]
        assert actual["sign"]["name"] == sign, graha
        assert abs(actual["degree"] - degree) * 60 < 1.2, graha
    assert nehru["moon_rashi"]["name"] == "Karka"
    assert nehru["janma_nakshatra"]["name"] == "Ashlesha"
    assert nehru["janma_nakshatra"]["pada"] == 1


def test_nehru_ascendant_agrees_once_both_clocks_are_the_same(nehru):
    """There is no dispute about this ascendant, and the one this suite used to document was an
    artefact of our own timezone choice. On the source's own convention it prints Karka 28°24'55"
    and this engine gives Karka 28°17'17" - 7.6 arc-minutes, same sign."""
    assert nehru["lagna"]["sign"]["name"] == "Karka"
    arcminutes = abs(nehru["lagna"]["degree"] - 28.41528) * 60
    assert arcminutes < 8, f"{arcminutes:.2f} arc-minutes from the published ascendant"
    assert NEHRU.lagna_dispute is None


def test_the_timezone_convention_is_what_moves_this_ascendant_across_a_sign():
    """The finding behind the two tests above, pinned so it cannot be forgotten again.

    India had no standard time until 1906. `zoneinfo` knows this: Asia/Kolkata resolves to Madras
    time (+05:21:10) for an 1889 birth, not to IST. That is historically RIGHT and it is what the
    engine should do for a user who names the zone - but it is 8m50s away from the modern +05:30
    the published source applied, and 8m50s is enough to carry this ascendant over the Karka/Simha
    boundary and pull the Moon four arc-minutes with it.
    """
    theirs = compute_chart(NEHRU.born, NEHRU.at, NEHRU.lat, NEHRU.lon, "+05:30")
    historical = compute_chart(NEHRU.born, NEHRU.at, NEHRU.lat, NEHRU.lon, "Asia/Kolkata")

    assert theirs["input"]["datetime_utc"] == "1889-11-14T18:00:00+00:00"
    assert historical["input"]["datetime_utc"] == "1889-11-14T18:08:50+00:00"   # Madras time

    assert theirs["lagna"]["sign"]["name"] == "Karka"
    assert historical["lagna"]["sign"]["name"] == "Simha"       # a different sign, from 8m50s
    moon_apart = abs(theirs["grahas"]["Moon"]["longitude"] - historical["grahas"]["Moon"]["longitude"]) * 60
    assert 3 < moon_apart < 5

    # What does NOT move: the Moon's sign and nakshatra, which is why the health check asserts those
    # and not the ascendant.
    assert theirs["moon_rashi"]["name"] == historical["moon_rashi"]["name"] == "Karka"
    assert theirs["janma_nakshatra"]["name"] == historical["janma_nakshatra"]["name"] == "Ashlesha"


@pytest.mark.parametrize("when,offset,era", [
    ((1863, 6), "5:53:20", "Calcutta local mean time"),
    ((1869, 6), "5:53:20", "Calcutta local mean time"),
    ((1870, 6), "5:21:10", "Madras time, the railway standard from 1802"),
    ((1889, 6), "5:21:10", "Madras time, the railway standard from 1802"),
    ((1905, 6), "5:21:10", "Madras time, the railway standard from 1802"),
    ((1906, 6), "5:30:00", "IST, adopted 1 January 1906"),
    ((1931, 6), "5:30:00", "IST"),
    ((1942, 6), "5:30:00", "IST, before the wartime shift"),
    ((1943, 6), "6:30:00", "WARTIME: India ran an hour ahead, 1942-1945"),
    ((1944, 6), "6:30:00", "WARTIME: India ran an hour ahead, 1942-1945"),
    ((1945, 6), "6:30:00", "WARTIME: India ran an hour ahead, 1942-1945"),
    ((1946, 6), "5:30:00", "IST again"),
    ((2026, 6), "5:30:00", "IST"),
])
def test_indian_births_resolve_to_their_historical_offset(when, offset, era):
    """A real accuracy property of the product, and one worth having a test of its own.

    An Indian birth before 1906 was not on IST, and a chart that assumes +05:30 for one is wrong by
    up to nine minutes - which, as the test above shows, is a whole sign of ascendant when the birth
    falls near a cusp. `zoneinfo` carries the transitions and the engine gets them for free by
    naming the zone rather than hardcoding an offset.

    READ THIS ROW FIRST, AND DO NOT SIMPLIFY IT AWAY: Sep 1942 - Oct 1945, India ran an hour ahead.

    This is not a historical curiosity and it is not about the ephemeris. Someone born in 1944 is
    eighty-two. Their daughter ordering them a Rs 249 book is an ordinary Tuesday, not an edge case.
    Get this wrong - by reaching for the fixed +05:30 that sits in four other files because it is
    there and looks like *the* Indian offset - and her mother's ascendant is out by fifteen degrees.
    That is half a sign to a sign and a half: every house statement in the book moves, every dasha
    date shifts, and the mangal dosha verdict can flip. She is also the customer most likely to
    notice, because she is ordering for someone whose chart the family may already have.

    We get it right only because the engine is passed a zone NAME and `zoneinfo` carries the
    transitions - which is as much luck as design, since nobody chose that for this reason. Hence
    this test. The pre-1906 rows below matter far less: they reach ancestors' charts and our own
    fixtures, not a living customer's own chart.
    """
    from zoneinfo import ZoneInfo
    year, month = when
    assert str(datetime(year, month, 1, 12, tzinfo=ZoneInfo("Asia/Kolkata")).utcoffset()) == offset, era


def test_kalam_matches_every_claim_the_published_analysis_makes(kalam):
    """15 Oct 1931, 01:15, Rameswaram. The published analysis is prose, so each statement it makes
    is checked separately. All six hold."""
    said = KALAM.published
    grahas = kalam["grahas"]
    assert kalam["lagna"]["sign"]["name"] == said["lagna_sign"]
    assert kalam["janma_nakshatra"]["name"] == said["janma_nakshatra"]
    assert kalam["moon_rashi"]["name"] == said["moon_sign"]
    assert grahas["Moon"]["dignity"] == said["moon_dignity"]
    assert grahas["Moon"]["house"] == said["moon_house"]
    assert grahas["Jupiter"]["dignity"] == said["jupiter_dignity"]
    assert grahas["Jupiter"]["house"] == said["jupiter_house"]
    assert grahas["Mercury"]["dignity"] == said["mercury_dignity"]
    assert grahas["Mercury"]["house"] == said["mercury_house"]
    assert grahas["Sun"]["house"] == said["sun_house"]
    assert grahas["Saturn"]["house"] == said["saturn_house"]
    rules = {graha: [h["house"] for h in kalam["houses"] if h["sign"]["lord"] == graha]
             for graha in ("Jupiter", "Saturn")}
    assert rules["Jupiter"] == said["jupiter_rules"]
    assert rules["Saturn"] == said["saturn_rules"]


def test_vivekananda_matches_where_the_ayanamsa_does_not_come_into_it():
    """12 Jan 1863, 06:33:33 LMT, Calcutta. VedAstro gives the lagna, the Moon's sign, its nakshatra
    and its PADA; all four agree exactly."""
    chart = VIVEKANANDA.chart()
    said = VIVEKANANDA.published
    assert chart["lagna"]["sign"]["name"] == said["lagna_sign"]
    assert chart["moon_rashi"]["name"] == said["moon_sign"]
    assert chart["janma_nakshatra"]["name"] == said["janma_nakshatra"]
    assert chart["janma_nakshatra"]["pada"] == said["janma_pada"]


def test_vivekananda_sun_differs_from_that_source_because_of_the_ayanamsa():
    """The one disagreement in the suite, and it is fully accounted for. VedAstro states Surya in
    Makara; we compute Dhanu 29°25', thirty-five arc-minutes short of the cusp. That page uses the
    RAMAN ayanamsa, which is about 1.1° smaller than the Lahiri this platform uses; a smaller
    ayanamsa gives a larger sidereal longitude, so the same Surya lands at roughly Makara 0°30'
    under Raman. Surya simply falls inside the gap between the two ayanamsas that day."""
    chart = VIVEKANANDA.chart()
    sun = chart["grahas"]["Sun"]
    assert sun["sign"]["name"] == "Dhanu"
    assert sun["degree"] == pytest.approx(29.42, abs=0.02)
    assert 30 - sun["degree"] < 1.1, "the gap to the cusp must be inside the Lahiri/Raman difference"
    ayanamsa = chart["meta"]["ayanamsa"]
    assert ayanamsa["name"] == "Lahiri"
    assert sun["degree"] + 1.1 > 30, "under Raman the same Surya would already be in Makara"


def test_indira_gandhi_matches_a_fully_published_table():
    """The best-documented chart in the set: that source prints sign, degree, nakshatra AND pada for
    all nine grahas, plus which are combust and which retrograde.

    All nine agree on sign, nakshatra and pada. On the degree, seven agree to under an arc-minute;
    Guru is 2.1' out and Shani 6.2'. Those two are the slow outer grahas, where ephemerides differ
    most and where a disagreement cannot be a birth-time difference - Shani moves about 2' a day, so
    6' would be three days, which is absurd. It is an ephemeris difference and it is recorded here
    rather than absorbed into a loose tolerance."""
    chart = INDIRA.chart()
    said = INDIRA.published
    within_an_arcminute, wider = [], {}
    for graha in ("Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu"):
        sign, degree, nakshatra, pada = said[graha]
        actual = chart["grahas"][graha]
        assert actual["sign"]["name"] == sign, graha
        assert actual["nakshatra"]["name"] == nakshatra, graha
        assert actual["pada"] == pada, graha
        arcminutes = abs(actual["degree"] - degree) * 60
        (within_an_arcminute.append(graha) if arcminutes < 1 else wider.__setitem__(graha, arcminutes))

    assert within_an_arcminute == ["Sun", "Moon", "Mars", "Mercury", "Venus", "Rahu", "Ketu"]
    assert sorted(wider) == ["Jupiter", "Saturn"]
    assert wider["Jupiter"] < 3 and wider["Saturn"] < 7
    assert [k for k, g in chart["grahas"].items() if g["combust"]] == said["combust"]
    assert [k for k, g in chart["grahas"].items() if g["retrograde"]] == said["retrograde"]


def test_indira_gandhi_ascendant_matches_to_sixteen_arcseconds():
    """THE ascendant test. Nehru's and Gandhi's ascendants are both disputed, so without this chart
    nothing in the suite proved the engine computes a LAGNA correctly against a published source -
    only grahas, which are insensitive to the minute of birth and so prove much less about the
    house calculation. Using the coordinates the source itself prints, the two agree to sixteen
    arc-seconds, which is about one second of clock time. Asserted at twenty to leave the published
    value's own rounding - it is printed to the second - some room."""
    chart = INDIRA.chart()
    assert chart["lagna"]["sign"]["name"] == INDIRA.published["lagna_sign"]
    published = INDIRA.published["lagna_degree"]
    arcseconds = abs(chart["lagna"]["degree"] - published) * 3600
    assert arcseconds < 20, f"{arcseconds:.1f} arc-seconds apart"
    assert INDIRA.lagna_dispute is None, "this is the one ascendant nobody disputes"


# --- the conventions every chart is computed under -------------------------------------------------

def test_uses_lahiri_and_the_swiss_ephemeris_data_files(nehru, kalam):
    assert nehru["meta"]["ayanamsa"]["name"] == "Lahiri"
    # Lahiri moves about 50.3" a year and was 0 at its zero-point epoch; these are the values for
    # the two dates, and they are what makes the published positions above reproducible at all.
    assert nehru["meta"]["ayanamsa"]["degrees"] == pytest.approx(22.319, abs=0.002)  # Nov 1889
    assert kalam["meta"]["ayanamsa"]["degrees"] == pytest.approx(22.905, abs=0.002)  # Oct 1931
    for chart in (nehru, kalam):
        assert chart["meta"]["ephemeris"] == "swiss_ephemeris"
        assert chart["meta"]["zodiac"] == "sidereal"
        assert chart["meta"]["house_system"] == "whole_sign"
        assert chart["meta"]["lunar_node"] == "mean"


def test_ketu_is_always_opposite_rahu(nehru, kalam):
    for chart in (nehru, kalam, VIVEKANANDA.chart(), INDIRA.chart()):
        ketu, rahu = chart["grahas"]["Ketu"]["longitude"], chart["grahas"]["Rahu"]["longitude"]
        assert (ketu - rahu) % 360 == pytest.approx(180)
        assert chart["grahas"]["Rahu"]["retrograde"] and chart["grahas"]["Ketu"]["retrograde"]


def test_houses_are_whole_sign_from_the_lagna(kalam):
    houses = kalam["houses"]
    assert [h["house"] for h in houses] == list(range(1, 13))
    assert houses[0]["sign"]["name"] == kalam["lagna"]["sign"]["name"]
    assert houses[2]["grahas"] == ["Sun", "Mercury", "Ketu"]   # Kanya, the 3rd from Karka
    assert sorted(g for h in houses for g in h["grahas"]) == sorted(kalam["grahas"])
    for graha in kalam["grahas"].values():
        house = houses[graha["house"] - 1]
        assert house["sign"]["name"] == graha["sign"]["name"]


def test_every_graha_carries_the_fields_the_pages_render(kalam):
    for key, graha in kalam["grahas"].items():
        assert set(graha) >= {"graha", "longitude", "sign", "degree", "degree_dms", "nakshatra",
                              "pada", "house", "retrograde", "speed", "combust", "dignity"}
        assert 1 <= graha["pada"] <= 4
        assert 0 <= graha["degree"] < 30
        assert graha["graha"]["key"] == key


# --- regression pins (engine-generated, not external proof) -----------------------------------------

def test_chart_is_json_serialisable(kalam):
    assert json.loads(json.dumps(kalam)) == kalam


def test_utc_offset_equals_the_iana_timezone(kalam):
    """Regression pin: "+05:30" and "Asia/Kolkata" must give byte-identical positions."""
    other = compute_chart(KALAM.born, KALAM.at, KALAM.lat, KALAM.lon, "+05:30", as_of=AS_OF)
    assert other["lagna"] == kalam["lagna"]
    assert other["grahas"] == kalam["grahas"]


def test_same_result_from_a_worker_thread(kalam):
    """swisseph settings are thread-local; a fresh thread must still get Lahiri + the .se1 files.
    Regression pin for app/engine/core.py's per-thread configuration."""
    results = []
    thread = threading.Thread(target=lambda: results.append(compute_chart(*KALAM.args, as_of=AS_OF)))
    thread.start()
    thread.join()
    assert results[0]["grahas"] == kalam["grahas"]
    assert results[0]["meta"] == kalam["meta"]


def test_bad_input_is_rejected():
    with pytest.raises(ValueError):
        compute_chart(KALAM.born, KALAM.at, KALAM.lat, KALAM.lon, "Mars/Olympus")
    with pytest.raises(ValueError):
        compute_chart(KALAM.born, KALAM.at, 116.83, KALAM.lon)
