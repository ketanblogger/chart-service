"""The solar and lunar eclipses of a year, computed rather than looked up.

WHY THIS IS COMPUTED AND NOT A TABLE. An eclipse table typed from a website is wrong the first time
somebody mistypes a digit and stays wrong until a reader notices, which for a date eleven months away
means nobody notices. Swiss Ephemeris already has the search functions; the dates below are whatever
it returns for the year asked for, like every other date on this site.

WHAT A READER ACTUALLY WANTS TO KNOW is whether they will see it. An eclipse invisible from India is
an astronomical fact and nothing else - it is not a grahan anybody observes a fast for - so each one
is checked against a point in India and labelled plainly either way.

WHAT THIS DELIBERATELY DOES NOT DO: say what an eclipse MEANS for a rashi. It returns the dates, the
sign and nakshatra the eclipse falls in, its type, and whether India sees it. The reading is written
from those facts elsewhere, under the same rules as everything else - and "an eclipse in your sign
brings..." is the exact sentence app/blog/safety.py refuses.
"""
from __future__ import annotations

import datetime as dt
from functools import lru_cache

import swisseph as swe

from app.engine.constants import nakshatra_info, sign_info
from app.engine.core import from_julian_day, julian_day

#: UJJAIN, because it is where the Indian prime meridian was drawn and it sits near the middle of the
#: country - so "visible from here" is a fair answer for most of India. A single point cannot speak
#: for a subcontinent and the copy says "in India" rather than "everywhere in India" for that reason.
UJJAIN = (75.7885, 23.1765, 0.0)        # lon, lat, altitude: the order Swiss Ephemeris wants

#: THE CITIES A GRAHAN PAGE GIVES TIMES FOR. One point cannot speak for a subcontinent - the partial
#: phase of 2 August 2027 is 0.43 at Dwarka and 0.17 at Delhi, and it starts and ends at different
#: clock times in each - so an eclipse India can see is listed per city rather than once.
#: Chosen to span the country rather than to rank it: west, south, centre, north, east.
#: Each with its name in all three trees. A Hindi page that says "Delhi" in Latin letters reads as
#: machine-made, and the site's own language check says so: it refuses Latin words in a Devanagari
#: page, which is how this was caught rather than shipped.
CITIES = (
    ("Mumbai", 72.8777, 19.0760, {"hi": "मुंबई", "mr": "मुंबई"}),
    ("Delhi", 77.2090, 28.6139, {"hi": "दिल्ली", "mr": "दिल्ली"}),
    ("Kolkata", 88.3639, 22.5726, {"hi": "कोलकाता", "mr": "कोलकाता"}),
    ("Chennai", 80.2707, 13.0827, {"hi": "चेन्नई", "mr": "चेन्नई"}),
    ("Ahmedabad", 72.5714, 23.0225, {"hi": "अहमदाबाद", "mr": "अहमदाबाद"}),
    ("Bengaluru", 77.5946, 12.9716, {"hi": "बेंगलुरु", "mr": "बेंगळुरू"}),
)


def city_name(city: str, lang: str) -> str:
    """The city's name in one tree, falling back to the Latin one."""
    for name, _lon, _lat, names in CITIES:
        if name == city:
            return names.get(lang, name)
    return city

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))

#: The eclipse kinds Swiss Ephemeris reports, as flags we care to name.
_SOLAR_KINDS = ((swe.ECL_TOTAL, "total"), (swe.ECL_ANNULAR, "annular"),
                (swe.ECL_ANNULAR_TOTAL, "hybrid"), (swe.ECL_PARTIAL, "partial"))
_LUNAR_KINDS = ((swe.ECL_TOTAL, "total"), (swe.ECL_PARTIAL, "partial"),
                (swe.ECL_PENUMBRAL, "penumbral"))


#: WHAT EACH KIND IS CALLED, in the three trees. The penumbral one is named rather than hidden:
#: "उपछाया चंद्र ग्रहण" is what people search for, and a year's list that quietly omits three of its
#: five eclipses is a list a reader cannot check against anywhere else.
KIND_NAMES = {
    "en": {"total": "total", "annular": "annular", "hybrid": "hybrid", "partial": "partial",
           "penumbral": "penumbral"},
    "hi": {"total": "पूर्ण", "annular": "वलयाकार", "hybrid": "संकर", "partial": "आंशिक",
           "penumbral": "उपछाया"},
    "mr": {"total": "खग्रास", "annular": "कंकणाकृती", "hybrid": "संकर", "partial": "खंडग्रास",
           "penumbral": "छायाकल्प"},
}

#: SOLAR OR LUNAR, in each tree. Without this the Hindi page read "उपछाया lunar" - the adjective
#: translated and the noun not, which is worse than either language on its own.
WHAT_NAMES = {
    "en": {"solar": "solar eclipse", "lunar": "lunar eclipse"},
    "hi": {"solar": "सूर्य ग्रहण", "lunar": "चंद्र ग्रहण"},
    "mr": {"solar": "सूर्यग्रहण", "lunar": "चंद्रग्रहण"},
}


def full_name(one: dict, lang: str) -> str:
    """"उपछाया चंद्र ग्रहण (penumbral lunar eclipse)" - the Devanagari name with the Roman one after
    it, because people search both and the Roman phrase is what they type."""
    native = f"{KIND_NAMES[lang][one['kind']]} {WHAT_NAMES[lang][one['what']]}".strip()
    if lang == "en":
        return native
    english = f"{KIND_NAMES['en'][one['kind']]} {WHAT_NAMES['en'][one['what']]}"
    return f"{native} ({english})"


#: WHAT A PENUMBRAL LUNAR ECLIPSE ACTUALLY IS, said plainly, because the honest sentence is also the
#: one that stops somebody worrying. No sutak, nothing to see, and it is still on the list.
PENUMBRAL_NOTE = {
    "en": ("A penumbral lunar eclipse is the Moon passing through the outer shadow. It dims very "
           "slightly and most people looking up would see an ordinary full Moon. Sutak is not "
           "observed for one."),
    "hi": ("उपछाया चंद्र ग्रहण में चंद्रमा पृथ्वी की बाहरी छाया से गुज़रता है। वह बहुत थोड़ा मलिन होता है और "
           "देखने पर सामान्य पूर्णिमा जैसा ही लगता है। इसका सूतक नहीं माना जाता।"),
    "mr": ("छायाकल्प चंद्रग्रहणात चंद्र पृथ्वीच्या बाहेरील छायेतून जातो. तो अगदी थोडा मंद होतो आणि पाहताना "
           "नेहमीच्या पौर्णिमेसारखाच दिसतो. याचे सुतक पाळले जात नाही."),
}


def _kind(flags: int, table) -> str:
    for bit, name in table:
        if flags & bit:
            return name
    return "partial"


def _where(jd: float) -> dict:
    """The sign and nakshatra the eclipse falls in - the Moon's, which is the same point for both."""
    from app.engine.core import longitude_and_speed

    longitude, _ = longitude_and_speed(jd, "Moon")
    sign = sign_info(int(longitude // 30))
    nakshatra = nakshatra_info(int(longitude // (360 / 27)))
    return {"longitude": round(longitude, 4), "sign": sign, "nakshatra": nakshatra}


#: How close a locally-visible eclipse has to be to the global one to be the SAME eclipse. The local
#: search returns the next one visible at the place, which may be a year later; a day and a half is
#: wider than any eclipse and narrower than the gap to the next.
_SAME_ECLIPSE_DAYS = 1.5


def _seen_from_india(jd: float, *, solar: bool) -> dict:
    """What India sees of this eclipse: {visible, magnitude, time_ist} - all of it from Ujjain.

    THE QUESTION IS NOT "IS IT ECLIPSED AT THE INSTANT OF GREATEST ECLIPSE". That instant is when the
    eclipse is largest SOMEWHERE ON EARTH, and a place that sees a partial phase an hour earlier or
    later has a magnitude of zero at that moment. Asking it that way said the total solar eclipse of
    2 August 2027 is not visible from India, when in fact it is a partial across the whole country -
    0.43 at Dwarka, 0.30 at Ujjain, 0.17 at Delhi. That would have gone on a grahan page as a plain
    statement of fact.

    So the LOCAL search is used instead, which finds the next eclipse visible at the place and its
    own contact times, and the result is kept only if it is the same eclipse as the global one.

    The argument order is (jd, geopos, flags) and NOT (jd, flags, geopos), which is what several other
    Swiss Ephemeris calls take. Getting it wrong raised a TypeError that a bare except swallowed, and
    every eclipse of the year reported "not visible from India".
    """
    place = list(UJJAIN)
    search_from = jd - _SAME_ECLIPSE_DAYS
    if solar:
        _, times, attributes = swe.sol_eclipse_when_loc(search_from, place, swe.FLG_SWIEPH, False)
    else:
        _, times, attributes = swe.lun_eclipse_when_loc(search_from, place, swe.FLG_SWIEPH, False)
    local_peak = times[0]
    if abs(local_peak - jd) > _SAME_ECLIPSE_DAYS:
        return _not_seen()
    # FOR A LUNAR ECLIPSE attributes[0] IS THE UMBRAL MAGNITUDE, and it is zero for a penumbral one -
    # so reading only that said the penumbral eclipses of February and July 2027 are not visible from
    # India, when the Moon is 30 and 26 degrees above the horizon at Ujjain while they happen.
    umbral = attributes[0]
    magnitude = umbral if solar else max(umbral, attributes[1])
    if magnitude <= 0:
        return _not_seen()
    when = from_julian_day(local_peak).replace(tzinfo=dt.timezone.utc).astimezone(IST)
    return {
        "visible_in_india": True,
        "india_magnitude": round(magnitude, 3),
        "india_time_ist": when.strftime("%H:%M"),
        # A PENUMBRAL LUNAR ECLIPSE IS NOT A GRAHAN, and this is a statement about practice rather
        # than about the sky. The Moon passes through the outer shadow and dims very slightly; most
        # people looking up would see an ordinary full Moon, and the tradition does not observe
        # sutak for one. So the event is reported - it is real and it is overhead - and this flag
        # says whether it is the thing a reader means when they search for grahan.
        "observed_as_grahan": bool(umbral > 0) if not solar else True,
    }


def _not_seen() -> dict:
    return {"visible_in_india": False, "india_magnitude": 0.0, "india_time_ist": "",
            "observed_as_grahan": False}


@lru_cache(maxsize=8)
def eclipses(year: int) -> tuple[dict, ...]:
    """Every solar and lunar eclipse in one calendar year, in time order.

    Cached per year: the sky is the same for every reader, and only what it means to them differs.
    """
    found: list[dict] = []
    start = julian_day(dt.datetime(year, 1, 1, tzinfo=dt.timezone.utc))
    end = julian_day(dt.datetime(year + 1, 1, 1, tzinfo=dt.timezone.utc))

    jd = start
    while True:
        flags, times = swe.sol_eclipse_when_glob(jd, swe.FLG_SWIEPH, 0, False)
        peak = times[0]
        if peak >= end:
            break
        found.append(_record(peak, flags, _SOLAR_KINDS, solar=True))
        jd = peak + 1

    jd = start
    while True:
        flags, times = swe.lun_eclipse_when(jd, swe.FLG_SWIEPH, 0, False)
        peak = times[0]
        if peak >= end:
            break
        found.append(_record(peak, flags, _LUNAR_KINDS, solar=False))
        jd = peak + 1

    found.sort(key=lambda one: one["jd"])
    return tuple(found)


def _record(jd: float, flags: int, kinds, *, solar: bool) -> dict:
    when = from_julian_day(jd).replace(tzinfo=dt.timezone.utc).astimezone(IST)
    where = _where(jd)
    return {
        "jd": jd,
        "what": "solar" if solar else "lunar",
        "kind": _kind(flags, kinds),
        "date": when.date().isoformat(),
        "time_ist": when.strftime("%H:%M"),
        **_seen_from_india(jd, solar=solar),
        **where,
        # Per-city contact times, but only where there is something to see: a list of six cities all
        # saying "not visible" is noise on a page about an eclipse that is not happening here.
        "cities": city_times(jd, solar=solar) if _seen_from_india(jd, solar=solar)["observed_as_grahan"] else (),
    }


def city_times(jd: float, *, solar: bool) -> tuple[dict, ...]:
    """Start, maximum and end of one eclipse in each of CITIES, for the cities that see it.

    A reader wants to know when to look from where they are, and "16:37 IST at Ujjain" answers that
    for nobody. The contact times come from the LOCAL search, which is the only one that has them:
    times[1] is first contact, times[0] the maximum and times[4] last contact, and a city that does
    not see the eclipse at all is left out rather than listed with blanks.
    """
    out: list[dict] = []
    for name, lon, lat, _names in CITIES:
        place = [lon, lat, 0.0]
        try:
            if solar:
                _, times, attributes = swe.sol_eclipse_when_loc(
                    jd - _SAME_ECLIPSE_DAYS, place, swe.FLG_SWIEPH, False)
            else:
                _, times, attributes = swe.lun_eclipse_when_loc(
                    jd - _SAME_ECLIPSE_DAYS, place, swe.FLG_SWIEPH, False)
        except Exception:
            continue
        if abs(times[0] - jd) > _SAME_ECLIPSE_DAYS:
            continue
        magnitude = attributes[0] if solar else max(attributes[0], attributes[1])
        if magnitude <= 0:
            continue
        out.append({
            "city": name,
            "starts": _ist(times[1]) or _ist(times[2]),
            "maximum": _ist(times[0]),
            "ends": _ist(times[4]) or _ist(times[3]),
            "magnitude": round(magnitude, 3),
        })
    return tuple(out)


def _ist(jd: float | None) -> str:
    """One contact time as HH:MM IST, or "" when Swiss Ephemeris did not fill that contact in."""
    if not jd:
        return ""
    return from_julian_day(jd).replace(tzinfo=dt.timezone.utc).astimezone(IST).strftime("%H:%M")


def for_rashi(year: int, rashi_index: int) -> tuple[dict, ...]:
    """The year's eclipses with the house each falls in, counted from one Moon sign.

    The HOUSE is the part that differs per reader; the eclipse itself is the same sky for everybody.
    """
    from app.engine.core import house_from

    return tuple({**one, "house": house_from(rashi_index, one["sign"]["index"])}
                 for one in eclipses(year))
