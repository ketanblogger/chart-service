"""The panchang accuracy gate: our engine against two published panchangs, on the days that can differ.

HOW THESE CASES WERE CHOSEN. Not thirty arbitrary days - an ordinary day agrees with everybody, because
the limbs change once in roughly a day and any reading taken hours from a boundary is the same
everywhere. What separates a correct engine from a nearly-correct one is the boundary, so the set is
built from:

  a tithi ending WITHIN MINUTES OF SUNRISE, where "the tithi at sunrise" differs either side of a
  four-minute sunrise convention;
  a nakshatra changing near MIDNIGHT, where the end time belongs to the next calendar date;
  Amavasya and Purnima, where the paksha flips and the amanta and purnimanta month names separate;
  a day the Moon DOES NOT RISE AT ALL, which happens about once a month.

THE SUNRISE CONVENTION IS A REAL, KNOWN DIFFERENCE AND IS NOT A FAILURE. We compute sunrise as the
centre of the Sun's disc at the horizon with no refraction - swisseph's BIT_HINDU_RISING, the classical
panchang method - and so does ProKerala: both give 06:29:23 at Delhi on 21 October 2026 where Drik
Panchang gives 06:25. Drik uses the upper limb with refraction; computing with that flag reproduces
Drik's figure to the minute (06:25:18). So sunrise is compared against ProKerala and every sunrise-derived
window inherits the same four minutes against Drik, deliberately.

Everything that does NOT depend on sunrise - the end times of the five limbs - agrees with Drik to within
two minutes on every case below.
"""
from __future__ import annotations

import datetime as dt

import pytest

from app.engine.panchang import full_panchang

CITIES = {
    "Delhi": {"lat": 28.6139, "lon": 77.2090},
    "Pune": {"lat": 18.5204, "lon": 73.8567},
    "Mumbai": {"lat": 19.0728, "lon": 72.8826},
    "Kolkata": {"lat": 22.5726, "lon": 88.3639},
    "Chennai": {"lat": 13.0827, "lon": 80.2707},
    "Bengaluru": {"lat": 12.9716, "lon": 77.5946},
}
#: Minutes we accept against a published panchang for a limb's end time. They round differently and
#: compute from slightly different ephemerides; two minutes is agreement, ten would be hiding something.
TOLERANCE_MINUTES = 2


def place(name):
    return dict(CITIES[name], name=name, tz="Asia/Kolkata")


def _at(stamp: str) -> dt.datetime:
    return dt.datetime.fromisoformat(stamp)


def _minutes_apart(stamp: str, published: str, on: dt.date) -> float:
    """`published` is "HH:MM" or "HH:MM+1" for a time on the following date."""
    clock, _, next_day = published.partition("+")
    hour, minute = (int(part) for part in clock.split(":"))
    when = dt.datetime.combine(on + dt.timedelta(days=1 if next_day else 0), dt.time(hour, minute),
                               tzinfo=_at(stamp).tzinfo)
    return abs((_at(stamp) - when).total_seconds()) / 60


# (date, city, source, field, published value). Read from drikpanchang.com and prokerala.com on
# 21 October 2026. Every one of these was fetched, not remembered.
PUBLISHED = [
    # the four sunrise-edge days
    ("2026-11-18", "Delhi", "drik", "nakshatra_ends", "06:10+1"),
    ("2026-11-19", "Mumbai", "drik", "tithi_ends", "07:05"),
    ("2026-11-20", "Kolkata", "drik", "tithi_ends", "07:15"),
    ("2026-11-20", "Kolkata", "drik", "nakshatra_ends", "06:56"),
    ("2027-01-09", "Pune", "drik", "tithi_ends", "07:07+1"),
    ("2027-01-09", "Pune", "drik", "nakshatra_ends", "12:15"),
    ("2027-01-09", "Pune", "prokerala", "tithi_ends", "07:07+1"),
    # the nakshatra that changes seven minutes after midnight
    ("2027-01-26", "Mumbai", "drik", "tithi_ends", "04:33+1"),
    ("2027-01-26", "Mumbai", "drik", "nakshatra_ends", "00:06+1"),
    # a day the Moon does not rise
    ("2026-11-02", "Kolkata", "drik", "tithi_ends", "13:10"),
    ("2026-11-02", "Kolkata", "drik", "nakshatra_ends", "03:46+1"),
    # the first case checked, against both sources
    ("2026-10-21", "Delhi", "drik", "tithi_ends", "14:11"),
    ("2026-10-21", "Delhi", "prokerala", "tithi_ends", "14:12"),
    ("2026-10-21", "Delhi", "drik", "nakshatra_ends", "19:47"),
    ("2026-10-21", "Delhi", "prokerala", "nakshatra_ends", "19:47"),
    # the southern cities, where the sun crosses the horizon at a steeper angle
    ("2026-12-08", "Chennai", "drik", "nakshatra_ends", "18:16"),
    ("2026-12-30", "Bengaluru", "drik", "tithi_ends", "12:36"),
    ("2026-12-30", "Bengaluru", "drik", "nakshatra_ends", "15:36"),
    # an ordinary day read from BOTH sources: they agree with each other and with us, which is what
    # makes the edge cases above the interesting ones
    ("2026-12-27", "Delhi", "drik", "tithi_ends", "17:12"),
    ("2026-12-27", "Delhi", "prokerala", "tithi_ends", "17:13"),
    ("2026-12-27", "Delhi", "drik", "nakshatra_ends", "18:04"),
    ("2026-12-27", "Delhi", "prokerala", "nakshatra_ends", "18:04"),
]


@pytest.mark.parametrize("day, city, source, field, published", PUBLISHED)
def test_the_limbs_agree_with_a_published_panchang(day, city, source, field, published):
    on = dt.date.fromisoformat(day)
    panchang = full_panchang(on, place(city))
    ours = {"tithi_ends": panchang["tithi"]["ends_at"],
            "nakshatra_ends": panchang["nakshatra"]["ends_at"]}[field]
    apart = _minutes_apart(ours, published, on)
    assert apart <= TOLERANCE_MINUTES, (
        f"{day} {city}: our {field} is {ours}, {source} publishes {published} - {apart:.0f} minutes apart")


@pytest.mark.parametrize("day, city, published_sunrise", [
    # ProKerala shares our convention, so these are exact-to-the-minute comparisons rather than tolerant
    # ones. Drik's figure is four minutes earlier on each and that is the convention, not an error.
    ("2026-10-21", "Delhi", "06:29"),
    ("2027-01-09", "Pune", "07:12"),
    ("2026-12-27", "Delhi", "07:16"),
])
def test_sunrise_matches_the_panchang_that_shares_our_convention(day, city, published_sunrise):
    on = dt.date.fromisoformat(day)
    sunrise = full_panchang(on, place(city))["sunrise"]
    apart = _minutes_apart(sunrise, published_sunrise, on)
    assert apart <= 1, f"{day} {city}: our sunrise {sunrise} vs ProKerala {published_sunrise}"


def test_the_moon_that_does_not_rise_is_reported_as_not_rising():
    """2 November 2026 at Kolkata: the next moonrise is 00:07 on the 3rd, so there is none on the 2nd.
    Drik shows it as "12:07 AM, Nov 03" for the same reason. Printing a time anyway - or borrowing the
    next day's - is wrong on about one day a month, and silently."""
    panchang = full_panchang(dt.date(2026, 11, 2), place("Kolkata"))
    assert panchang["moonrise"] is None
    assert panchang["moonset"] is not None, "it still SETS that day, at 12:28 by Drik"
    assert _minutes_apart(panchang["moonset"], "12:28", dt.date(2026, 11, 2)) <= TOLERANCE_MINUTES


def test_a_moonset_always_follows_its_own_moonrise():
    """The bug this catches shipped once: moonset was searched from midnight and returned a setting that
    had happened BEFORE that day's moonrise - 01:26 against a moonrise of 14:50 - which is incoherent as
    a pair and disagreed with both published panchangs."""
    for offset in range(40):
        day = dt.date(2026, 10, 21) + dt.timedelta(days=offset)
        panchang = full_panchang(day, place("Delhi"))
        if panchang["moonrise"] and panchang["moonset"]:
            assert _at(panchang["moonset"]) > _at(panchang["moonrise"]), (
                f"{day}: moonset {panchang['moonset']} precedes moonrise {panchang['moonrise']}")


def test_the_two_month_systems_separate_in_the_dark_half_and_agree_in_the_bright():
    """Amanta and purnimanta name the same fortnight differently, and Maharashtra and Delhi genuinely
    disagree. The Diwali Amavasya of 2026 is Ashwina in Pune and Kartika in the north."""
    bright = full_panchang(dt.date(2026, 10, 26), place("Pune"))
    assert bright["tithi"]["name"] == "Purnima"
    assert bright["masa"]["differ"] is False

    dark = full_panchang(dt.date(2026, 11, 9), place("Pune"))
    assert dark["tithi"]["name"] == "Amavasya"
    assert dark["masa"]["amanta"] == "Ashwina"
    assert dark["masa"]["purnimanta"] == "Kartika"
    assert dark["masa"]["differ"] is True


def test_the_samvat_years_turn_at_chaitra_and_not_in_january():
    """A panchang that adds a constant to the Gregorian year is wrong for a quarter of every year."""
    cases = {dt.date(2026, 10, 21): (2083, 1948), dt.date(2026, 2, 1): (2082, 1947),
             dt.date(2026, 3, 10): (2082, 1947), dt.date(2026, 5, 1): (2083, 1948),
             dt.date(2027, 1, 15): (2083, 1948)}
    for day, (vikram, shaka) in cases.items():
        samvat = full_panchang(day, place("Delhi"))["samvat"]
        assert (samvat["vikram"], samvat["shaka"]) == (vikram, shaka), day


def test_a_karana_ends_with_or_halfway_through_its_tithi():
    """A karana is half a tithi by definition, so this is arithmetic rather than opinion - and it is the
    cheapest check that the karana index is keyed to the same origin as the tithi index."""
    for offset in range(0, 30, 3):
        day = dt.date(2026, 10, 21) + dt.timedelta(days=offset)
        panchang = full_panchang(day, place("Delhi"))
        karana_end, tithi_end = _at(panchang["karana"]["ends_at"]), _at(panchang["tithi"]["ends_at"])
        assert karana_end <= tithi_end + dt.timedelta(minutes=1), day


def test_the_moon_inherits_the_same_sunrise_convention_and_that_is_deliberate():
    """Moonrise and moonset are computed the same classical way as sunrise - disc centre, no refraction -
    so they carry the same difference against a panchang that uses the upper limb with refraction, and
    MORE of it: the Moon's parallax is about a degree, where the Sun's is negligible.

    Measured: at Delhi on 21 October 2026 our moonrise 14:50 is ProKerala's 14:50 exactly and Drik's
    14:55; our moonset 02:22 is ProKerala's 02:22 and Drik's 02:19. At Bengaluru on 30 December the gap
    against Drik reaches twelve minutes. This is pinned so that the day somebody changes the flag, the
    reason it was this way is in front of them rather than lost.
    """
    delhi = full_panchang(dt.date(2026, 10, 21), place("Delhi"))
    assert _minutes_apart(delhi["moonrise"], "14:50", dt.date(2026, 10, 21)) <= 1, "ProKerala: 14:50"
    assert _minutes_apart(delhi["moonset"], "02:22+1", dt.date(2026, 10, 21)) <= 1, "ProKerala: 02:22"


def test_sunrise_sits_four_minutes_after_the_upper_limb_with_refraction():
    """The convention difference itself, measured rather than asserted in prose - and in the direction
    the page's explanatory line claims. If somebody switches the flag, this says so."""
    import swisseph as swe

    from app.engine import swe as engine_swe
    from app.engine.core import from_julian_day, julian_day, parse_tz

    tz = parse_tz("Asia/Kolkata")
    jd0 = julian_day(dt.datetime(2026, 10, 21, 0, 0, tzinfo=tz))
    _result, times = engine_swe.rise_trans(jd0, swe.SUN, swe.CALC_RISE, (77.2090, 28.6139, 0.0),
                                           0.0, 0.0, swe.FLG_SWIEPH)
    upper_limb = from_julian_day(times[0]).astimezone(tz)
    ours = _at(full_panchang(dt.date(2026, 10, 21), place("Delhi"))["sunrise"])
    minutes = (ours - upper_limb).total_seconds() / 60
    assert 3 <= minutes <= 5, (
        f"ours is {minutes:.1f} min after the upper-limb-with-refraction sunrise; the pages say about four")
