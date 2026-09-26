"""Current transits and transit events (sign ingresses, retrograde stations).

Needs no birth data. This is what the rashifal pipeline feeds to the AI, so everything the
AI might be tempted to work out (houses from a rashi, dates of sign changes, when a graha
turns retrograde/direct) is computed here.
"""

from collections.abc import Sequence
from datetime import datetime

from .constants import GRAHA_KEYS, graha_name, resolve_sign, sign_info
from .dignity import combustion, dignity
from .core import (
    DEFAULT_TZ,
    as_utc,
    ayanamsa,
    from_julian_day,
    house_from,
    julian_day,
    longitude_and_speed,
    parse_tz,
    placement,
)

# Sun, Moon and the mean nodes never change direction.
_STATIONING = ["Mars", "Mercury", "Jupiter", "Venus", "Saturn"]
_STEP_DAYS = 1.0  # the fastest graha (Moon) needs ~2.3 days per sign, so no ingress is skipped
_PRECISION_DAYS = 1 / 86400  # bisect to ~1 second
_MOON_DEFAULT_MAX_DAYS = 31


def graha_positions(jd: float, reference_sign: int | None = None) -> dict:
    """All nine grahas at `jd`. `reference_sign` (1-12) adds the whole-sign house from it.

    Every row also carries `combust` and `dignity`, because both are plain lookups once the Sun's
    longitude is known and both are printed in the report's planet table:
      `combust`  bool, and None for Surya and the nodes, where the rule does not apply
      `dignity`  "exalted" | "moolatrikona" | "own_sign" | "friendly_sign" | "neutral_sign" |
                 "enemy_sign" | "debilitated", and None for Rahu/Ketu, whose exaltation is disputed
    The reasoning behind both - orbs, arcs, precedence - is in app/engine/dignity.py, and the full
    working is in `chart["report"]["dignity"]` when the chart is computed with detail="full".
    """
    positions = {}
    sun_longitude = longitude_and_speed(jd, "Sun")[0]
    for key in GRAHA_KEYS:
        longitude, speed = longitude_and_speed(jd, key)
        entry = {"graha": graha_name(key), **placement(longitude)}
        if reference_sign is not None:
            entry["house"] = house_from(reference_sign, entry["sign"]["index"])
        entry["retrograde"] = speed < 0
        entry["speed"] = round(speed, 6)
        entry["combust"] = combustion(key, longitude, sun_longitude, entry["retrograde"])["combust"]
        entry["dignity"] = dignity(key, entry["sign"]["index"], entry["degree"])["label"]
        positions[key] = entry
    return positions


def current_transits(when: datetime | None = None, rashi: int | str | None = None) -> dict:
    """Sidereal positions of all grahas at `when` (default now).

    With `rashi` (moon sign: 1-12, "Leo", "Simha", "simha"), each graha also gets `house`,
    its whole-sign house counted from that rashi.
    """
    when_utc = as_utc(when)
    jd = julian_day(when_utc)
    reference = resolve_sign(rashi) + 1 if rashi is not None else None
    result = {
        "datetime_utc": when_utc.isoformat(timespec="seconds"),
        "ayanamsa": {"name": "Lahiri", "degrees": round(ayanamsa(jd), 6)},
        "grahas": graha_positions(jd, reference),
    }
    if reference is not None:
        result["rashi"] = sign_info(reference - 1)
    return result


def _bisect(jd_low: float, jd_high: float, state) -> float:
    """First instant in (jd_low, jd_high] where state(jd) differs from state(jd_low)."""
    initial = state(jd_low)
    while jd_high - jd_low > _PRECISION_DAYS:
        middle = (jd_low + jd_high) / 2
        if state(middle) == initial:
            jd_low = middle
        else:
            jd_high = middle
    return jd_high


def _sign(jd: float, graha: str) -> int:
    return int(longitude_and_speed(jd, graha)[0] // 30)


def _is_retrograde(jd: float, graha: str) -> bool:
    return longitude_and_speed(jd, graha)[1] < 0


def _state_changes(graha: str, jd_start: float, jd_end: float, state) -> list[float]:
    changes = []
    jd, current = jd_start, state(jd_start, graha)
    while jd < jd_end:
        jd_next = min(jd + _STEP_DAYS, jd_end)
        following = state(jd_next, graha)
        if following != current:
            changes.append(_bisect(jd, jd_next, lambda t: state(t, graha)))
        jd, current = jd_next, following
    return changes


def sign_ingresses(graha: str, jd_start: float, jd_end: float) -> list[tuple[float, int, int]]:
    """(jd, from_sign, to_sign) for each sign change; signs are 0-based here."""
    return [
        (jd, _sign(jd - 2 * _PRECISION_DAYS, graha), _sign(jd, graha))
        for jd in _state_changes(graha, jd_start, jd_end, _sign)
    ]


def transit_events(
    start: datetime,
    end: datetime,
    rashi: int | str | None = None,
    include_moon: bool | None = None,
    tz: str = DEFAULT_TZ,
    grahas: Sequence[str] | None = None,
) -> list[dict]:
    """Sign ingresses and retrograde/direct stations between `start` and `end`, in time order.

    The Moon changes sign every ~2.3 days; by default its ingresses are included only for
    periods up to 31 days. `rashi` adds `house`, the whole-sign house of the event's sign
    counted from that rashi. Event times are given in `tz` (default IST) and in UTC.

    `grahas` restricts the scan to those grahas (default: all nine). Long spans - the paid report's
    timeline scans decades - only want the slow grahas, and skipping the fast ones is most of the cost.
    """
    wanted = GRAHA_KEYS if grahas is None else [k for k in GRAHA_KEYS if k in set(grahas)]
    start_utc, end_utc = as_utc(start), as_utc(end)
    if end_utc <= start_utc:
        raise ValueError("end must be after start")
    jd_start, jd_end = julian_day(start_utc), julian_day(end_utc)
    if include_moon is None:
        include_moon = jd_end - jd_start <= _MOON_DEFAULT_MAX_DAYS
    reference = resolve_sign(rashi) + 1 if rashi is not None else None
    zone = parse_tz(tz)

    def event(jd: float, kind: str, graha: str, details: dict) -> dict:
        moment = from_julian_day(jd)
        return {
            "type": kind,
            "graha": graha_name(graha),
            "datetime": moment.astimezone(zone).isoformat(timespec="minutes"),
            "datetime_utc": moment.isoformat(timespec="minutes"),
            **details,
        }

    def with_house(details: dict, sign: int) -> dict:
        if reference is not None:
            details["house"] = house_from(reference, sign + 1)
        return details

    events = []
    for graha in wanted:
        if graha == "Moon" and not include_moon:
            continue
        for jd, from_sign, to_sign in sign_ingresses(graha, jd_start, jd_end):
            details = {
                "from_sign": sign_info(from_sign),
                "to_sign": sign_info(to_sign),
                # Entering the previous sign means the graha is moving backwards.
                "retrograde": (from_sign - to_sign) % 12 == 1,
            }
            events.append((jd, event(jd, "ingress", graha, with_house(details, to_sign))))
    for graha in _STATIONING:
        if graha not in wanted:
            continue
        for jd in _state_changes(graha, jd_start, jd_end, _is_retrograde):
            longitude, _ = longitude_and_speed(jd, graha)
            position = placement(longitude)
            details = {
                "direction": "retrograde" if _is_retrograde(jd, graha) else "direct",
                "sign": position["sign"],
                "degree": position["degree"],
                "nakshatra": position["nakshatra"],
            }
            sign = position["sign"]["index"] - 1
            events.append((jd, event(jd, "station", graha, with_house(details, sign))))
    events.sort(key=lambda pair: pair[0])
    return [item for _, item in events]
