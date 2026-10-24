"""Festival muhurta windows, computed per city from the same ephemeris as everything else.

WHAT A FESTIVAL DATE ACTUALLY IS. A tithi is not a day: it begins and ends at a moment, and which calendar
day a festival falls on depends on whether its tithi is present at the time of day the observance needs.
Dhanteras needs Trayodashi during pradosh (the stretch after sunset); Lakshmi Puja needs Amavasya present
at sunset. That is why the date cannot be read off a tithi table and why two panchangs can print different
days for the same sky.

WHAT IS VERIFIED. The Lakshmi Puja muhurat is the overlap of pradosh kaal with Vrishabha lagna, the fixed
sign that classically carries the puja. Computed here for Delhi on 8 November 2026 it runs 17:54:44 to
19:50:19; two published panchangs give 17:54 to 19:50. The same minute at both ends, which is why these
windows are published per city rather than left to a note telling the reader to look elsewhere.

WHAT IS NOT HERE. Bhai Dooj. Our Dwitiya times agree with the published ones to the minute - it starts
14:01 on 10 November 2026 and ends 15:54 on the 11th - but published panchangs disagree about which day
that makes the festival, because on the 10th Dwitiya covers only part of aparahna. The disagreement is
about convention, not arithmetic, and a family acts on this date. So it is reported and not published.
"""
from __future__ import annotations

import datetime as dt
from functools import lru_cache

from app.engine import cities
from app.engine.core import ascendant, julian_day
from app.engine.muhurta import day_facts

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))

#: Pradosh kaal: the stretch after sunset when an evening observance is done. Two hours and twenty-four
#: minutes is the figure the widely used panchangs print, and it is what reproduced their muhurat above.
PRADOSH_MINUTES = 144

#: The eight cities the pages carry by name. Everywhere else is reachable through the picker, which uses
#: the same ~124-city table the birth form does, so no city list is invented here.
MAJOR_CITIES = ("Delhi", "Mumbai", "Bengaluru", "Hyderabad", "Chennai", "Kolkata", "Pune", "Ahmedabad")

#: Each festival: the tithi it needs, and WHEN that tithi has to be present. "pradosh" means during the
#: stretch after sunset; "sunset" means at the moment of sunset itself.
#: WHICH MONTH'S TITHI. There is a Krishna Trayodashi and an Amavasya in every lunar month, and the first
#: version of this scan took the first one it met in October - so it published Ashwin's, a full lunar month
#: before Diwali. The lunar month is pinned by the SUN'S SIGN: Kartik's Amavasya, the Diwali one, is the
#: new moon with the Sun in Tula, and the whole festival run sits in that same fortnight. Nothing here is
#: anchored to a Gregorian month, because the lunar month drifts three weeks against it.
FESTIVALS = {
    "dhanteras": {"paksha": "krishna", "tithi": 13, "needs": "pradosh", "lagna": None, "sun_sign": 7},
    "lakshmi-puja": {"paksha": "krishna", "tithi": 15, "needs": "sunset", "lagna": 2, "sun_sign": 7},
}


def _place(city: str) -> dict:
    found = cities.find_city(city)
    if not found:
        raise KeyError(f"unknown city: {city}")
    return {"lat": found["lat"], "lon": found["lon"], "tz": found.get("tz", "Asia/Kolkata"),
            "name": found["name"], "state": found.get("state", "")}


def _rising_sign(when: dt.datetime, lat: float, lon: float) -> int:
    """The sign rising at a moment (1-12)."""
    return int(ascendant(julian_day(when.astimezone(dt.timezone.utc)), lat, lon) // 30) + 1


def _lagna_window(day: dt.date, sign: int, lat: float, lon: float,
                  search_from: dt.datetime, search_to: dt.datetime) -> tuple[dt.datetime, dt.datetime] | None:
    """When `sign` is the rising sign, to the second, inside the search range.

    Bisected rather than stepped: a two-minute scan put the Delhi window two minutes late at both ends,
    and two minutes is visible to somebody who has been told to start a puja at a particular time.
    """
    def first_at_or_after(lo: dt.datetime, hi: dt.datetime, target: int) -> dt.datetime | None:
        if _rising_sign(hi, lat, lon) < target:
            return None
        for _ in range(42):
            mid = lo + (hi - lo) / 2
            if _rising_sign(mid, lat, lon) >= target:
                hi = mid
            else:
                lo = mid
        return hi

    start = first_at_or_after(search_from, search_to, sign)
    if start is None:
        return None
    end = first_at_or_after(start, search_to, sign + 1)
    return (start, end or search_to)


@lru_cache(maxsize=256)
def windows(festival: str, year: int, city: str) -> dict:
    """The festival's date and its windows in one city, or `None` dates when the year holds no such tithi.

    The date is found by asking, for each candidate day, whether the needed tithi is present at the time
    of day the observance needs - not by looking up which day the tithi "is on", which is the step that
    makes a date wrong by one.
    """
    rule = FESTIVALS[festival]
    place = _place(city)
    found = _find_day(rule, year, place)
    if not found:
        return {"festival": festival, "year": year, "city": place, "date": None}

    day, facts = found
    sunset = dt.datetime.fromisoformat(facts["sunset"])
    pradosh = (sunset, sunset + dt.timedelta(minutes=PRADOSH_MINUTES))
    out = {
        "festival": festival, "year": year, "city": place, "date": day,
        # BOTH tithis, deliberately. "tithi" is the one the day is named after, which is what a reader
        # comparing against a printed calendar will see; "tithi_at_observance" is the one actually running
        # when the puja is done, which is what decided the date. They differ on most of these days, and
        # showing only one of them is how a reader concludes the page is wrong.
        "tithi": facts["tithi"], "nakshatra": facts.get("nakshatra"),
        "tithi_at_observance": facts["tithi_at_observance"],
        "sunrise": dt.datetime.fromisoformat(facts["sunrise"]),
        "sunset": sunset,
        "pradosh": {"start": pradosh[0], "end": pradosh[1]},
        "muhurta": None,
    }
    if rule["lagna"]:
        # THE MUHURAT IS THE FIXED SIGN'S OWN WINDOW, not its overlap with pradosh kaal. Checked against a
        # published panchang in two cities: Delhi 17:54-19:50 and Mumbai 18:27-20:27, and the Vrishabha
        # lagna computed here is 17:54:44-19:50:19 and 18:27:55-20:27:49 - the same minute at all four
        # ends. The first version intersected it with pradosh, which happened to be invisible in Delhi,
        # where the lagna sits inside pradosh, and cut five minutes off the end in Mumbai, where it does
        # not. Two cities, because one city cannot tell these two rules apart.
        lagna = _lagna_window(day, rule["lagna"], place["lat"], place["lon"],
                              sunset - dt.timedelta(hours=2), sunset + dt.timedelta(hours=5))
        if lagna:
            out["muhurta"] = {"start": lagna[0], "end": lagna[1], "lagna": rule["lagna"]}
    return out


def _find_day(rule: dict, year: int, place: dict) -> tuple[dt.date, dict] | None:
    """The day in `year` whose needed tithi is present AT THE MOMENT the observance needs it.

    THIS IS THE WHOLE DIFFICULTY, and the first version got it wrong. A panchang names a day after the
    tithi running at SUNRISE, but these observances are done in the evening, and a tithi lasts about
    23 hours 37 minutes - so the tithi at sunset is routinely the next one. Trayodashi in 2026 runs from
    10:31 on 6 November to 10:48 on the 7th: the 7th is the day *named* Trayodashi, and the 6th is the
    evening that HAS it. Asking which day is named for the tithi gives Dhanteras a day late; asking what
    the tithi is at pradosh gives 6 November, which is what two published panchangs print.

    Kartik Krishna paksha falls in October or November, so the scan covers both; the lunar month is pinned
    by the Sun's sign rather than by a Gregorian month.
    """
    for day in _candidate_days(year):
        facts = day_facts(day, place)
        sunset = dt.datetime.fromisoformat(facts["sunset"])
        # The moment that decides it: sunset itself, or the middle of pradosh kaal.
        at = sunset if rule["needs"] == "sunset" else sunset + dt.timedelta(minutes=PRADOSH_MINUTES // 2)
        tithi = _tithi_at(at)
        if tithi["paksha"]["key"] != rule["paksha"] or tithi["day"] != rule["tithi"]:
            continue
        if rule.get("sun_sign") and _sun_sign(day, place) != rule["sun_sign"]:
            continue  # the right tithi of the wrong lunar month
        return day, {**facts, "tithi_at_observance": tithi}
    return None


def _tithi_at(moment: dt.datetime) -> dict:
    """The tithi running at an instant, which is not always the one the day is named after."""
    from app.engine.panchang import tithi_index, tithi_info

    return tithi_info(tithi_index(julian_day(moment.astimezone(dt.timezone.utc))))


def _sun_sign(day: dt.date, place: dict) -> int:
    """The Sun's sidereal sign at midday (1-12) - the marker that says which lunar month a tithi belongs to."""
    from app.engine.core import longitude_and_speed

    noon = dt.datetime.combine(day, dt.time(12), tzinfo=IST)
    longitude, _ = longitude_and_speed(julian_day(noon.astimezone(dt.timezone.utc)), "Sun")
    return int(longitude // 30) + 1


def _candidate_days(year: int) -> list[dt.date]:
    """Every day of October and November. Diwali has fallen as early as 12 October and as late as
    15 November, so a window narrower than this would silently find nothing in some years."""
    start = dt.date(year, 10, 1)
    return [start + dt.timedelta(days=n) for n in range((dt.date(year, 12, 1) - start).days)]


def _tithi_day(tithi: dict) -> int:
    """Tithi number within its paksha (1-15), from the engine's own field."""
    return int(tithi["day"])


def all_cities(festival: str, year: int) -> list[dict]:
    """The festival in each of the eight named cities, in that order."""
    return [windows(festival, year, city) for city in MAJOR_CITIES]
