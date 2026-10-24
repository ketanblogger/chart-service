"""What one year actually holds for one Moon sign, computed rather than written.

A yearly rashifal page has to say something true before it says anything else, and the true part is where
the slow grahas stand. Guru crosses two or three signs in a year and Shani usually one, and the HOUSE each
occupies counted from the reader's rashi is what the tradition reads - so the same transit is a different
year for each of the twelve.

NOTHING HERE IS WRITTEN AHEAD OF TIME. Every date is a sidereal ingress or station from the same Swiss
Ephemeris scan the charts use, and a year's facts are whatever that scan returns for it. 2027 happens to
be a year where Shani enters Mesha in June and retrogrades back into Meena in October; no table of
hand-typed dates would have had that, and a page that smoothed it away would be wrong for five months.
"""
from __future__ import annotations

import datetime as dt
from functools import lru_cache

from app.engine import transits
from app.engine.constants import graha_name, sign_info
from app.engine.core import house_from
from app.engine.sadesati import cycles

#: The grahas whose movement makes a year different from the one before it. The fast ones change too
#: often to say anything about a year, and the Moon changes sign every two and a half days.
SLOW = ("Jupiter", "Saturn", "Rahu")

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


@lru_cache(maxsize=8)
def _year_events(year: int) -> tuple[dict, ...]:
    """Every ingress and station of the slow grahas inside one calendar year, in time order.

    Cached per year and independent of any rashi: the transits are the same sky for all twelve, and only
    the house they fall in differs.
    """
    events = transits.transit_events(
        dt.datetime(year, 1, 1), dt.datetime(year + 1, 1, 1), grahas=list(SLOW))
    return tuple(events)


@lru_cache(maxsize=1)
def _positions_at(year: int) -> tuple[tuple[str, int], ...]:
    """(graha, sign 1-12) for each slow graha at the first instant of the year, so the year starts with a
    position rather than with its first change."""
    from app.engine.core import julian_day, longitude_and_speed

    jd = julian_day(dt.datetime(year, 1, 1, tzinfo=dt.timezone.utc))
    out = []
    for graha in SLOW:
        longitude, _ = longitude_and_speed(jd, graha)
        out.append((graha, int(longitude // 30) + 1))
    return tuple(out)


def for_rashi(rashi_index: int, year: int) -> dict:
    """`rashi_index` is 1-12. The year's slow transits as houses from that rashi, plus its Sade Sati.

    `stays` is where each graha sits and for how long, in the reader's own houses. `turns` is the ingresses
    and stations as dated events. Both come from one scan; neither is rounded to a month.
    """
    events = _year_events(year)
    start = dt.date(year, 1, 1)
    end = dt.date(year, 12, 31)

    stays: list[dict] = []
    for graha, sign in _positions_at(year):
        opened = start
        current = sign
        for event in events:
            if event["graha"]["key"] != graha or event["type"] != "ingress":
                continue
            at = dt.datetime.fromisoformat(event["datetime"]).date()
            stays.append({"graha": graha_name(graha), "sign": sign_info(current - 1),
                          "house": house_from(rashi_index, current), "start": opened, "end": at})
            current = event["to_sign"]["index"]
            opened = at
        stays.append({"graha": graha_name(graha), "sign": sign_info(current - 1),
                      "house": house_from(rashi_index, current), "start": opened, "end": end})

    turns = []
    for event in events:
        at = dt.datetime.fromisoformat(event["datetime"]).date()
        if event["type"] == "ingress":
            turns.append({"kind": "ingress", "date": at, "graha": event["graha"],
                          "from_sign": event["from_sign"], "sign": event["to_sign"],
                          "from_house": house_from(rashi_index, event["from_sign"]["index"]),
                          "house": house_from(rashi_index, event["to_sign"]["index"])})
        else:
            turns.append({"kind": "station", "date": at, "graha": event["graha"],
                          "direction": event["direction"], "sign": event["sign"],
                          "house": house_from(rashi_index, event["sign"]["index"])})

    sade = cycles(rashi_index, dt.datetime(year, 7, 1, tzinfo=dt.timezone.utc))
    return {
        "year": year,
        "rashi": sign_info(rashi_index - 1),
        "stays": [stay for stay in stays if stay["start"] < stay["end"]],
        "turns": sorted(turns, key=lambda t: t["date"]),
        # Whether Sade Sati touches this sign during the year at all, which is the one question a reader
        # who has heard of it will scan for.
        "sade_sati": _sade_in_year(sade, year),
    }


#: `graha_name` is the engine's own table. The first version of this module searched the year's EVENTS for
#: a graha's spellings and invented `{"name": key, "devanagari": key}` when it found none - and Rahu takes
#: eighteen months to cross a sign, so in a year where it does not move there were no events to find, and
#: a Hindi page printed "Rahu" in Latin letters inside a Devanagari table. A name is never derived from a
#: key: it is looked up where the names live.


def _sade_in_year(sade: dict, year: int) -> dict | None:
    """The Sade Sati cycle overlapping this year, with the phases that fall inside it - or None."""
    first, last = f"{year}-01-01", f"{year}-12-31"
    for which in ("current", "previous", "next"):
        cycle = sade.get(which)
        if cycle and cycle["start"] <= last and cycle["end"] >= first:
            inside = [phase for phase in cycle["phases"]
                      if phase["start"] <= last and phase["end"] >= first]
            return {"which": which, "start": cycle["start"], "end": cycle["end"], "phases": inside}
    return None
