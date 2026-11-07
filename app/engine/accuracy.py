"""How much to trust this chart: the two things that can be wrong through no fault of the ephemeris.

Both are DATA. Nothing here writes a sentence for a customer - the web and report layers own the
wording, in three languages. The engine's job is to say what it knows and, crucially, to stay quiet
when there is nothing to say: a caveat printed on a chart where it could not have mattered is noise
that teaches people to skip the one that does matter.

1. PLACE. The birth-details form offers a list of cities, so a visitor born somewhere not on the list
   picks the nearest one that is. The engine cannot detect that - whatever city arrives looks like a
   deliberate choice - but it CAN say whether it would have mattered, which is the useful half.
   `lagna_boundary` measures how far the birthplace would have to be wrong, in kilometres, before the
   rising sign changed. On most charts the answer is hundreds of kilometres and no caveat is
   warranted; near a cusp it can be under fifty.

2. CLOCK. India's civil time has moved four times and `zoneinfo` carries all four (see parse_tz in
   core.py). A birth on Madras time or on the 1942-45 wartime offset is computed correctly, but its
   recorded clock was not today's, and a reader comparing against another site - or against a chart
   cast decades ago - deserves to know which system applied. `clock` reports the offset actually
   used and names the era.

Neither block ever blocks or alters a calculation. The chart is computed the same way regardless.
"""

import math
from datetime import datetime, timedelta, timezone, tzinfo

from .constants import sign_info

# How far a birthplace might plausibly be from the city a visitor picked. Measured, not guessed: the
# 124 cities in cities.py have a median nearest-neighbour distance of 81 km and a 90th percentile of
# 138 km, so somebody whose own town is missing is typically within ~40 km of a listed one and, in
# the sparser parts of the country, within ~70 km. 100 km covers that with margin while staying well
# inside "implausible". It fires on roughly 6% of charts - the ascendant is near-uniform within its
# sign, and 100 km is about 0.9 degrees of ascendant, so 2 x 0.9 / 30.
PLACE_UNCERTAINTY_KM = 100.0

_EARTH_KM_PER_DEGREE = 111.32
_PROBE_DEGREES = 0.25  # big enough to be numerically clean, small enough to stay locally linear

# Offsets India's civil clock has actually used, by the value itself rather than by date, so an
# explicitly-passed offset is recognised as readily as a named zone. See core.parse_tz.
_INDIAN_ERAS = {
    "5:53:20": ("calcutta_local_mean_time", "Calcutta local mean time, before any standard"),
    "5:21:10": ("madras_time", "Madras time - the railway standard, fixed by Goldingham in 1802"),
    "6:30:00": ("wartime", "wartime: India ran an hour ahead from September 1942 to October 1945"),
    "5:30:00": ("ist", "Indian Standard Time, adopted 1 January 1906"),
}
IST = timedelta(hours=5, minutes=30)


def _offset_text(offset: timedelta) -> str:
    total = int(offset.total_seconds())
    sign = "+" if total >= 0 else "-"
    total = abs(total)
    return f"{sign}{total // 3600:02d}:{total % 3600 // 60:02d}:{total % 60:02d}"


def lagna_boundary(jd: float, lat: float, lon: float, longitude: float,
                   threshold_km: float = PLACE_UNCERTAINTY_KM) -> dict:
    """How far the birthplace would have to be wrong for the rising sign to change.

    Measured rather than assumed: the ascendant is recomputed at the same instant a quarter-degree
    east and a quarter-degree north, which gives the local gradient in degrees-of-ascendant per
    degree-of-coordinate. Longitude dominates (about 0.9 degrees of ascendant per degree of
    longitude, since the sky turns) and latitude contributes roughly a third as much, but the mix
    depends on the latitude and on which sign is rising - so it is computed per chart, not from a
    rule of thumb.

    `km_to_change_sign` is the distance in the WORST direction, so it never overstates how safe a
    chart is. `sensitive` is the flag a renderer acts on.
    """
    from .core import ascendant  # local: core imports nothing from here

    degree = longitude % 30
    to_boundary = min(degree, 30 - degree)
    per_degree_lon = ((ascendant(jd, lat, lon + _PROBE_DEGREES) - longitude + 180) % 360 - 180) / _PROBE_DEGREES
    per_degree_lat = ((ascendant(jd, lat + _PROBE_DEGREES, lon) - longitude + 180) % 360 - 180) / _PROBE_DEGREES

    km_per_degree_lon = _EARTH_KM_PER_DEGREE * math.cos(math.radians(lat))
    per_km_east = per_degree_lon / km_per_degree_lon if km_per_degree_lon else 0.0
    per_km_north = per_degree_lat / _EARTH_KM_PER_DEGREE
    gradient = math.hypot(per_km_east, per_km_north)   # degrees of ascendant per km, worst direction
    km = to_boundary / gradient if gradient else float("inf")

    sign_index = int(longitude % 360 // 30)
    rising_toward_next = 30 - degree <= degree
    return {
        "degrees_into_sign": round(degree, 6),
        "arcminutes_to_boundary": round(to_boundary * 60, 2),
        "nearer_boundary": "next" if rising_toward_next else "previous",
        "adjacent_sign": sign_info((sign_index + (1 if rising_toward_next else -1)) % 12),
        "km_to_change_sign": round(km, 1),
        "threshold_km": threshold_km,
        "sensitive": km <= threshold_km,
        "basis": ("Distance in the most sensitive direction, from the ascendant's measured gradient "
                  "at this place and instant. The threshold is how far a birthplace might plausibly "
                  "be from the city a visitor picked off the list."),
    }


def clock(zone: tzinfo, birth_utc: datetime) -> dict:
    """Which civil clock the birth time was recorded on, and whether it was today's.

    `non_standard` is the flag: true when the birth was computed on an offset that is not the one
    that place uses now. It is what tells a reader why this chart may differ from one cast by
    software that assumes the modern offset.
    """
    offset = birth_utc.astimezone(zone).utcoffset() or timedelta()
    named = hasattr(zone, "key")
    today = datetime.now(timezone.utc).astimezone(zone).utcoffset() if named else None
    era, era_label = _INDIAN_ERAS.get(str(offset), (None, None))

    differs = None if today is None else offset != today
    # A fixed offset carries no history of its own, so fall back to "is it India's current one?" -
    # which is what makes Gandhi's +04:38 Porbandar local mean time report as non-standard.
    non_standard = bool(differs) if differs is not None else offset != IST

    return {
        "timezone": getattr(zone, "key", None) or _offset_text(offset),
        "timezone_kind": "zone" if named else "fixed_offset",
        "offset": _offset_text(offset),
        "offset_seconds": int(offset.total_seconds()),
        "zone_offset_today": _offset_text(today) if today is not None else None,
        "differs_from_zone_today": differs,
        "non_standard": non_standard,
        "era": era,
        "era_label": era_label,
        "basis": ("The offset the birth time was actually converted on. India's civil clock has used "
                  "four different offsets; `era` names the one that applied when it is recognised."),
    }


def accuracy(jd: float, lat: float, lon: float, lagna_longitude: float,
             zone: tzinfo, birth_utc: datetime, threshold_km: float = PLACE_UNCERTAINTY_KM) -> dict:
    """The `accuracy` block on every chart. The coordinates and city used are already in
    `chart["input"]`; this says what they and the clock imply about how much to trust the result."""
    return {
        "lagna_boundary": lagna_boundary(jd, lat, lon, lagna_longitude, threshold_km),
        "clock": clock(zone, birth_utc),
    }
