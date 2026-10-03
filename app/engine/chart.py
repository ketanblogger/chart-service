"""Birth chart: the single entry point that assembles everything the pages and the AI need."""

from datetime import date, datetime, time

from .core import (
    DEFAULT_TZ,
    as_utc,
    ascendant,
    ayanamsa,
    ephemeris_in_use,
    julian_day,
    parse_tz,
    placement,
    to_utc,
)
from .accuracy import accuracy
from .constants import sign_info
from .dasha import vimshottari
from .dosha import chart_signs, mangal_dosha
from .sadesati import sade_sati
from .transits import graha_positions


def compute_chart(
    birth_date: date,
    birth_time: time,
    lat: float,
    lon: float,
    tz: str | None = None,
    as_of: datetime | None = None,
    detail: str = "basic",
) -> dict:
    """Sidereal (Lahiri) birth chart as a JSON-serialisable dict.

    `tz` is the timezone of the birth time: IANA name or UTC offset, default Asia/Kolkata.
    `as_of` (default now) is the moment "current dasha" and sade-sati are evaluated for.
    Every chart carries an `accuracy` block: whether the lagna is close enough to a sign boundary
    that the choice of city could have changed it, and whether the birth was on a non-standard civil
    clock. `detail="full"` adds exactly one key, `report` - every fact the paid Kundali report needs
    (navamsa, dignity, aspects, yogas, highlights, gemstone, dhaiya, timeline). See engine/facts.py.
    """
    if detail not in ("basic", "full"):
        raise ValueError('detail must be "basic" or "full"')
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError("lat must be within ±90 and lon within ±180")
    tz = tz or DEFAULT_TZ
    zone = parse_tz(tz)
    birth_utc = to_utc(birth_date, birth_time, tz)
    as_of_utc = as_utc(as_of)
    jd = julian_day(birth_utc)

    lagna = placement(ascendant(jd, lat, lon))
    lagna_sign = lagna["sign"]["index"]
    grahas = graha_positions(jd, reference_sign=lagna_sign)
    moon = grahas["Moon"]

    chart = {
        "input": {
            "date": birth_date.isoformat(),
            "time": birth_time.isoformat(timespec="seconds"),
            "lat": lat,
            "lon": lon,
            "timezone": tz,
            "datetime_utc": birth_utc.isoformat(timespec="seconds"),
        },
        "meta": {
            "zodiac": "sidereal",
            "ayanamsa": {"name": "Lahiri", "degrees": round(ayanamsa(jd), 6)},
            "house_system": "whole_sign",
            "lunar_node": "mean",
            "ephemeris": ephemeris_in_use(jd),
        },
        "lagna": lagna,
        "grahas": grahas,
        "moon_rashi": moon["sign"],
        "janma_nakshatra": {**moon["nakshatra"], "pada": moon["pada"]},
        "houses": [
            {
                "house": house,
                "sign": sign_info((lagna_sign - 1 + house - 1) % 12),
                "grahas": [key for key, graha in grahas.items() if graha["house"] == house],
            }
            for house in range(1, 13)
        ],
    }
    chart["dasha"] = vimshottari(moon["longitude"], birth_utc, zone, as_of_utc)
    chart["mangal_dosha"] = mangal_dosha(chart_signs(chart))
    chart["sade_sati"] = sade_sati(moon["sign"]["index"], as_of_utc, tz)
    # How far to trust this chart: how close the lagna sits to a sign boundary (so a birthplace a
    # few tens of kilometres out could change it) and which civil clock the birth time was on.
    # Data only - the web and report layers write the wording. See app/engine/accuracy.py.
    chart["accuracy"] = accuracy(jd, lat, lon, lagna["longitude"], zone, birth_utc)
    if detail == "full":
        from .facts import report_facts  # imported here: facts pulls in the whole engine
        chart["report"] = report_facts(chart, as_of_utc)
    return chart
