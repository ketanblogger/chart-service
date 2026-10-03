"""Swiss Ephemeris access. Every swisseph call in the engine goes through this module.

Conventions (fixed for the whole platform):
- Sidereal zodiac, Lahiri (Chitrapaksha) ayanamsa.
- Swiss Ephemeris data files in ./ephe (sepl_18 / semo_18, valid 1800-2399 CE). Outside that
  range, or if the files are missing, swisseph silently falls back to its built-in Moshier
  ephemeris; `ephemeris_in_use` reports which one actually answered.
- Rahu = MEAN lunar node, Ketu = Rahu + 180°. The mean node is the traditional default in
  Indian panchang software; it is always retrograde, so it has no station events.
- Whole-sign houses counted from the lagna sign.
"""

import re
import threading
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import swisseph as swe

from .constants import NAKSHATRA_SPAN, PADA_SPAN, nakshatra_info, sign_info

EPHE_PATH = Path(__file__).parent / "ephe"
DEFAULT_TZ = "Asia/Kolkata"

_FLAGS = swe.FLG_SWIEPH | swe.FLG_SIDEREAL | swe.FLG_SPEED
_BODIES = {
    "Sun": swe.SUN,
    "Moon": swe.MOON,
    "Mars": swe.MARS,
    "Mercury": swe.MERCURY,
    "Jupiter": swe.JUPITER,
    "Venus": swe.VENUS,
    "Saturn": swe.SATURN,
    "Rahu": swe.MEAN_NODE,
}
_J2000 = datetime(2000, 1, 1, 12, tzinfo=timezone.utc)
_J2000_JD = 2451545.0

# The swisseph C library keeps its settings (ephemeris path, sidereal mode) in THREAD-LOCAL
# storage. FastAPI runs sync endpoints in worker threads, so configuring swisseph once at
# import would leave those threads on the default Fagan-Bradley ayanamsa + Moshier - a chart
# that is wrong by ~0.9° with no error. Hence: configure once per thread, before every use.
_thread = threading.local()


def _swe():
    if not getattr(_thread, "configured", False):
        swe.set_ephe_path(str(EPHE_PATH))
        swe.set_sid_mode(swe.SIDM_LAHIRI)
        _thread.configured = True
    return swe


# --- time -----------------------------------------------------------------------------

_OFFSET_RE = re.compile(r"^(?:UTC)?([+-])(\d{1,2})(?::?(\d{2}))?$")


def parse_tz(value: str | None) -> tzinfo:
    """IANA name ("Asia/Kolkata") or UTC offset ("+05:30", "UTC+5:30", "-0800").

    THE ZONE NAME IS LOAD-BEARING. Do not "simplify" a named zone into a fixed +05:30 for Indian
    births: India's clock has moved four times and `zoneinfo` knows all four, so passing the name is
    what makes a historical chart right.

        before 1870        +05:53:20   Calcutta local mean time
        1870 - 1905        +05:21:10   Madras time (the railway standard)
        1906 - Aug 1942    +05:30      IST
        Sep 1942 - Oct 1945 +06:30     wartime: India ran an hour ahead
        1946 onwards       +05:30      IST

    The wartime window is the one with living customers: someone born in 1944 is in their eighties,
    and a fixed +05:30 puts their ascendant out by fifteen degrees - half a sign to a sign and a
    half, so every house statement in their report moves. Elsewhere in the codebase a fixed
    `timedelta(hours=5, minutes=30)` appears a few times; every one of those is a "now" (an as_of, a
    payment timestamp), never a birth. Birth times reach the ephemeris only through this function.

    ONE LIMIT OF THE NAME, for completeness: before 1870 `Asia/Kolkata` is *Calcutta's* local mean
    time, not a national standard, so it is right for Bengal and wrong further west - by 75 minutes
    for Porbandar in Gujarat, which is a whole sign of ascendant. A pre-1870 birth outside Bengal
    wants its own longitude-derived offset passed explicitly rather than the zone name.
    """
    if not value:
        value = DEFAULT_TZ
    match = _OFFSET_RE.match(value.strip())
    if match:
        sign, hours, minutes = match.groups()
        offset = timedelta(hours=int(hours), minutes=int(minutes or 0))
        if offset > timedelta(hours=14):
            raise ValueError(f"UTC offset out of range: {value!r}")
        return timezone(offset if sign == "+" else -offset)
    try:
        return ZoneInfo(value.strip())
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"unknown timezone: {value!r}") from exc


def to_utc(local_date: date, local_time: time, tz: str | None = None) -> datetime:
    local = datetime.combine(local_date, local_time.replace(tzinfo=None), tzinfo=parse_tz(tz))
    return local.astimezone(timezone.utc)


def as_utc(when: datetime | None) -> datetime:
    """None -> now. Naive datetimes are taken as IST, the platform's home timezone."""
    if when is None:
        return datetime.now(timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=parse_tz(DEFAULT_TZ))
    return when.astimezone(timezone.utc)


def julian_day(when_utc: datetime) -> float:
    return _J2000_JD + (when_utc - _J2000).total_seconds() / 86400


def from_julian_day(jd: float) -> datetime:
    return _J2000 + timedelta(days=jd - _J2000_JD)


# --- positions ------------------------------------------------------------------------

def longitude_and_speed(jd: float, graha: str) -> tuple[float, float]:
    """Sidereal longitude (0-360) and daily speed in degrees; negative speed = retrograde."""
    if graha == "Ketu":
        longitude, speed = longitude_and_speed(jd, "Rahu")
        return (longitude + 180) % 360, speed
    values, _ = _swe().calc_ut(jd, _BODIES[graha], _FLAGS)
    return values[0], values[3]


def ascendant(jd: float, lat: float, lon: float) -> float:
    _, ascmc = _swe().houses_ex(jd, lat, lon, b"W", swe.FLG_SIDEREAL)
    return ascmc[0]


def ayanamsa(jd: float) -> float:
    return _swe().get_ayanamsa_ut(jd)


def sunrise(jd_from: float, lat: float, lon: float) -> float:
    """Julian day (UT) of the first sunrise at or after `jd_from`, by the Hindu-panchang convention
    (centre of the disc on the horizon, no refraction). Raises ValueError where the Sun does not rise."""
    rsmi = swe.CALC_RISE | swe.BIT_HINDU_RISING
    result, times = _swe().rise_trans(jd_from, swe.SUN, rsmi, (lon, lat, 0.0), 0.0, 0.0, swe.FLG_SWIEPH)
    if result != 0:
        raise ValueError(f"no sunrise found at lat={lat}, lon={lon}")
    return times[0]


def ephemeris_in_use(jd: float) -> str:
    """"swiss_ephemeris" when the .se1 data files answered, "moshier" on fallback."""
    for body in (swe.MOON, swe.SATURN):  # one body from each data file
        _, flags = _swe().calc_ut(jd, body, _FLAGS)
        if not flags & swe.FLG_SWIEPH:
            return "moshier"
    return "swiss_ephemeris"


def _dms(degrees: float) -> str:
    seconds = int(degrees * 3600)
    return f"{seconds // 3600}°{seconds % 3600 // 60:02d}'{seconds % 60:02d}\""


def placement(longitude: float) -> dict:
    """Break a sidereal longitude into sign, degree within sign, nakshatra and pada."""
    longitude %= 360
    if longitude >= 360:  # -1e-15 % 360 == 360.0
        longitude = 0.0
    degree = longitude % 30
    return {
        "longitude": round(longitude, 6),
        "sign": sign_info(int(longitude // 30)),
        "degree": round(degree, 6),
        "degree_dms": _dms(degree),
        "nakshatra": nakshatra_info(int(longitude // NAKSHATRA_SPAN)),
        "pada": int(longitude % NAKSHATRA_SPAN // PADA_SPAN) + 1,
    }


def house_from(reference_sign: int, sign: int) -> int:
    """Whole-sign house (1-12) of `sign` counted from `reference_sign`. Both are 1-12."""
    return (sign - reference_sign) % 12 + 1
