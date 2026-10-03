"""Panchang basics for one civil day: vara, tithi and the Moon's nakshatra, read at sunrise.

Convention (the one printed panchangs use): the panchang day runs from sunrise to sunrise, and the
day's tithi / nakshatra are the ones current at sunrise. Sunrise depends on the place, so a place is
always stated; the rashifal uses REFERENCE_PLACE for the whole site. `ends_at` is when that tithi /
nakshatra gives way to the next one (it can fall on the next calendar day).
"""

from datetime import date, datetime, time, timedelta

from .constants import NAKSHATRA_SPAN, graha_name, nakshatra_info
from .core import DEFAULT_TZ, from_julian_day, julian_day, longitude_and_speed, parse_tz, sunrise

REFERENCE_PLACE = {"name": "Mumbai", "lat": 19.0728, "lon": 72.8826, "tz": DEFAULT_TZ}

TITHI_SPAN = 12.0  # degrees of Moon-Sun elongation per tithi

# 1-15; the 15th is Purnima in the bright half and Amavasya in the dark half.
_TITHI_NAMES = [
    ("Pratipada", "प्रतिपदा"), ("Dwitiya", "द्वितीया"), ("Tritiya", "तृतीया"), ("Chaturthi", "चतुर्थी"),
    ("Panchami", "पंचमी"), ("Shashthi", "षष्ठी"), ("Saptami", "सप्तमी"), ("Ashtami", "अष्टमी"),
    ("Navami", "नवमी"), ("Dashami", "दशमी"), ("Ekadashi", "एकादशी"), ("Dwadashi", "द्वादशी"),
    ("Trayodashi", "त्रयोदशी"), ("Chaturdashi", "चतुर्दशी"),
]
_PURNIMA, _AMAVASYA = ("Purnima", "पौर्णिमा"), ("Amavasya", "अमावस्या")
_PAKSHA = {"shukla": ("Shukla", "शुक्ल"), "krishna": ("Krishna", "कृष्ण")}

# Monday = 0 (datetime.weekday()). (English, Sanskrit vara, Devanagari, day lord)
_VARAS = [
    ("Monday", "Somavara", "सोमवार", "Moon"),
    ("Tuesday", "Mangalavara", "मंगळवार", "Mars"),
    ("Wednesday", "Budhavara", "बुधवार", "Mercury"),
    ("Thursday", "Guruvara", "गुरुवार", "Jupiter"),
    ("Friday", "Shukravara", "शुक्रवार", "Venus"),
    ("Saturday", "Shanivara", "शनिवार", "Saturn"),
    ("Sunday", "Ravivara", "रविवार", "Sun"),
]

_PRECISION_DAYS = 1 / 86400
_STEP_DAYS = 1 / 8  # a tithi lasts >= ~19h and a nakshatra >= ~20h, so a 3-hour step never skips one


def tithi_index(jd: float) -> int:
    """0-29: 0 = Shukla Pratipada ... 14 = Purnima, 15 = Krishna Pratipada ... 29 = Amavasya."""
    moon, _ = longitude_and_speed(jd, "Moon")
    sun, _ = longitude_and_speed(jd, "Sun")
    return int(((moon - sun) % 360) // TITHI_SPAN)


def tithi_info(index: int) -> dict:
    paksha = "shukla" if index < 15 else "krishna"
    day = index % 15 + 1
    if day == 15:
        name, devanagari = _PURNIMA if paksha == "shukla" else _AMAVASYA
    else:
        name, devanagari = _TITHI_NAMES[day - 1]
    paksha_name, paksha_devanagari = _PAKSHA[paksha]
    return {
        "index": index + 1,  # 1-30
        "day": day,  # 1-15 within the paksha
        "name": name,
        "devanagari": devanagari,
        "paksha": {"key": paksha, "name": paksha_name, "devanagari": paksha_devanagari},
    }


def vara_info(day: date) -> dict:
    english, name, devanagari, lord = _VARAS[day.weekday()]
    return {"key": english, "name": name, "devanagari": devanagari, "lord": graha_name(lord)}


def _nakshatra_index(jd: float) -> int:
    return int(longitude_and_speed(jd, "Moon")[0] // NAKSHATRA_SPAN)


def _next_change(jd: float, state) -> float:
    """First instant after `jd` at which state(jd) changes, to about a second."""
    initial = state(jd)
    low, high = jd, jd + _STEP_DAYS
    while state(high) == initial:
        low, high = high, high + _STEP_DAYS
    while high - low > _PRECISION_DAYS:
        middle = (low + high) / 2
        if state(middle) == initial:
            low = middle
        else:
            high = middle
    return high


def panchang(day: date, lat: float | None = None, lon: float | None = None, tz: str | None = None) -> dict:
    """Vara, sunrise, and the tithi and Moon nakshatra current at sunrise on the civil date `day`.

    Without lat/lon the site's REFERENCE_PLACE is used. Times are given in `tz` (default IST).
    """
    place = dict(REFERENCE_PLACE)
    if lat is not None and lon is not None:
        place = {"name": None, "lat": lat, "lon": lon, "tz": tz or DEFAULT_TZ}
    elif tz:
        place["tz"] = tz
    zone = parse_tz(place["tz"])
    midnight = datetime.combine(day, time(0, 0), tzinfo=zone)
    jd_rise = sunrise(julian_day(midnight), place["lat"], place["lon"])
    rise_local = from_julian_day(jd_rise).astimezone(zone)
    if rise_local.date() != day:  # cannot happen at Indian latitudes; guards polar input
        raise ValueError(f"no sunrise on {day.isoformat()} at lat={place['lat']}, lon={place['lon']}")

    def local(jd: float) -> str:
        moment = from_julian_day(jd).astimezone(zone)
        # round to the nearest minute: panchangs print minutes, and 06:29:58 should read 06:30
        moment = (moment + timedelta(seconds=30)).replace(second=0, microsecond=0)
        return moment.isoformat(timespec="minutes")

    tithi = tithi_info(tithi_index(jd_rise))
    tithi["ends_at"] = local(_next_change(jd_rise, tithi_index))
    nakshatra = nakshatra_info(_nakshatra_index(jd_rise))
    nakshatra["ends_at"] = local(_next_change(jd_rise, _nakshatra_index))
    return {
        "date": day.isoformat(),
        "place": place,
        "convention": "values current at sunrise",
        "sunrise": local(jd_rise),
        "vara": vara_info(day),
        "tithi": tithi,
        "nakshatra": nakshatra,
    }
