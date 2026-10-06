"""Sade-sati: Saturn transiting the 12th, 1st and 2nd sign from the natal Moon sign.

Dates come from Saturn's actual sidereal sign ingresses. Because Saturn retrogrades, it can
slip back over a sign boundary for a few months, so a cycle is a list of `periods`; the
cycle runs from the first entry into the 12th-from-Moon to the final exit from the 2nd.
"""

from datetime import datetime, timezone
from functools import lru_cache

from .constants import sign_info
from .core import DEFAULT_TZ, from_julian_day, house_from, julian_day, parse_tz
from .transits import sign_ingresses

_PHASES = {12: "rising", 1: "peak", 2: "setting"}
_SAME_CYCLE_GAP_DAYS = 3 * 365  # retrograde gaps last months; separate cycles are ~22 years apart
_YEARS_BACK, _YEARS_AHEAD = 10, 33  # enough to hold the whole current cycle, or the whole next one


@lru_cache(maxsize=8)
def _saturn_segments(year: int) -> list[tuple[int, float, float]]:
    """(sign 1-12, jd_start, jd_end) stretches of Saturn in one sign, around `year`.

    Independent of any birth chart, so it is cached per calendar year of the query.
    """
    jd_start = julian_day(datetime(year - _YEARS_BACK, 1, 1, tzinfo=timezone.utc))
    jd_end = julian_day(datetime(year + _YEARS_AHEAD, 1, 1, tzinfo=timezone.utc))
    segments = []
    segment_start = jd_start
    for jd, from_sign, _ in sign_ingresses("Saturn", jd_start, jd_end):
        segments.append((from_sign + 1, segment_start, jd))
        segment_start = jd
    return segments  # the truncated stretch after the last ingress is not needed


def sade_sati(moon_sign: int, as_of_utc: datetime, tz: str = DEFAULT_TZ) -> dict:
    """`moon_sign` is 1-12. Reports the current cycle if one is running, otherwise the next."""
    zone = parse_tz(tz)
    jd_now = julian_day(as_of_utc)

    def iso(jd: float) -> str:
        return from_julian_day(jd).astimezone(zone).date().isoformat()

    cycles: list[list[tuple[str, float, float]]] = []
    saturn_sign = None
    for sign, jd_start, jd_end in _saturn_segments(as_of_utc.year):
        if jd_start <= jd_now < jd_end:
            saturn_sign = sign
        phase = _PHASES.get(house_from(moon_sign, sign))
        if phase is None:
            continue
        if cycles and jd_start - cycles[-1][-1][2] < _SAME_CYCLE_GAP_DAYS:
            cycles[-1].append((phase, jd_start, jd_end))
        else:
            cycles.append([(phase, jd_start, jd_end)])

    cycle = next(c for c in cycles if c[-1][2] > jd_now)
    active_phase = next((phase for phase, start, end in cycle if start <= jd_now < end), None)
    running = cycle[0][1] <= jd_now
    return {
        "moon_sign": sign_info(moon_sign - 1),
        "saturn_sign": sign_info(saturn_sign - 1),
        "saturn_house_from_moon": house_from(moon_sign, saturn_sign),
        "as_of": as_of_utc.astimezone(zone).date().isoformat(),
        "active": active_phase is not None,
        "phase": active_phase,  # "rising" (12th), "peak" (1st, over the Moon), "setting" (2nd) or null
        # A running cycle with active=false means Saturn has temporarily retrograded out of the three signs.
        "cycle": {
            "which": "current" if running else "next",
            "start": iso(cycle[0][1]),
            "end": iso(cycle[-1][2]),
            "periods": [{"phase": phase, "start": iso(start), "end": iso(end)} for phase, start, end in cycle],
        },
    }


_DHAIYA = {4: "fourth", 8: "eighth"}  # Saturn in the 4th (ardhashtama / kantaka) or 8th (ashtama) from the Moon sign


def dhaiya(moon_sign: int, as_of_utc: datetime, tz: str = DEFAULT_TZ) -> dict:
    """Shani dhaiya ("small panoti", ~2.5 years): Saturn transiting the 4th or 8th sign from the Moon sign.

    `moon_sign` is 1-12. `period` is the continuous stay of Saturn in that sign around `as_of_utc`
    (a retrograde re-entry is a separate stay). Inactive -> kind and period are null.
    """
    zone = parse_tz(tz)
    jd_now = julian_day(as_of_utc)

    def iso(jd: float) -> str:
        return from_julian_day(jd).astimezone(zone).date().isoformat()

    for sign, jd_start, jd_end in _saturn_segments(as_of_utc.year):
        if jd_start <= jd_now < jd_end:
            house = house_from(moon_sign, sign)
            kind = _DHAIYA.get(house)
            return {
                "active": kind is not None,
                "kind": kind,  # "fourth" | "eighth" | null
                "saturn_sign": sign_info(sign - 1),
                "saturn_house_from_moon": house,
                "period": {"start": iso(jd_start), "end": iso(jd_end)} if kind else None,
            }
    raise ValueError("date outside the computed Saturn table")


_SATURN_PHASES = {12: "sade_sati_rising", 1: "sade_sati_peak", 2: "sade_sati_setting",
                  4: "dhaiya_fourth", 8: "dhaiya_eighth"}
PHASE_LABELS = {
    "sade_sati_rising": "Sade Sati, first phase (Shani in the 12th from the Moon sign)",
    "sade_sati_peak": "Sade Sati, peak phase (Shani over the Moon sign)",
    "sade_sati_setting": "Sade Sati, last phase (Shani in the 2nd from the Moon sign)",
    "dhaiya_fourth": "Shani dhaiya / kantaka shani (Shani in the 4th from the Moon sign)",
    "dhaiya_eighth": "Shani dhaiya / ashtama shani (Shani in the 8th from the Moon sign)",
}


def saturn_stays(moon_sign: int, start_utc: datetime, end_utc: datetime, tz: str = DEFAULT_TZ) -> list[dict]:
    """Every continuous stay of Shani in one sign overlapping [start, end), with its house from the
    Moon sign and, where it is one, the sade-sati or dhaiya phase it represents.

    A retrograde slip back over a sign boundary makes two separate stays, as in `sade_sati`. This is
    what the report timeline uses to place Shani's phase changes on the calendar; `phase` is null for
    the stays that are neither sade-sati nor dhaiya.
    """
    zone = parse_tz(tz)
    jd_from, jd_to = julian_day(start_utc), julian_day(end_utc)

    def iso(jd: float) -> str:
        return from_julian_day(jd).astimezone(zone).date().isoformat()

    stays = []
    for sign, jd_start, jd_end in _saturn_segments(start_utc.year):
        if jd_end <= jd_from or jd_start >= jd_to:
            continue
        house = house_from(moon_sign, sign)
        phase = _SATURN_PHASES.get(house)
        stays.append({
            "sign": sign_info(sign - 1),
            "house_from_moon": house,
            "phase": phase,
            "phase_label": PHASE_LABELS.get(phase),
            "start": iso(jd_start),
            "end": iso(jd_end),
        })
    return stays
