"""What a chart can honestly say when the birth TIME is unknown.

"समय नहीं पता" is the commonest obstacle on this site: a great many people know the date and the place
and not the hour. The usual answers are both bad - refuse them a chart, or quietly assume noon and hand
them a lagna, houses and dasha dates that are fiction.

WHAT ACTUALLY SURVIVES A MISSING TIME, and why:

  the Sun's sign          the Sun moves about a degree a day, so it can only be in doubt if the birth
                          fell on the day it changed sign - which this checks for rather than assumes
  every other graha       checked the same way, and for the same reason. Jupiter changes sign about once
                          a year and Saturn once in two and a half - rare, but somebody IS born on those
                          days, and for them the answer depends on the hour exactly as it does for the
                          Moon. Nothing here is assumed safe because it is usually safe.
  the Moon's sign         ONLY SOMETIMES. The Moon covers about thirteen degrees a day, so on roughly
                          one day in two and a half it crosses a sign boundary and the answer genuinely
                          depends on the hour. This reports it when it is safe and says so when it is not
  the Moon's nakshatra    rarely safe: a nakshatra is 13 deg 20', which the Moon crosses in about a day

  WHAT DOES NOT SURVIVE: the lagna, every house, everything counted from a house, and the dasha dates.
  The lagna changes every two hours; the dasha balance at birth is read from the Moon's exact degree and
  a day's worth of doubt moves the dates by years. These are not approximated here. A dasha that is
  "probably about right" is the kind of thing somebody plans around.
"""
from __future__ import annotations

import datetime as dt

from .constants import sign_info
from .core import julian_day, longitude_and_speed, parse_tz

#: EVERY graha is checked, not a chosen few. The Moon is the one that moves fast enough to be in doubt
#: on most days, but a birth on ANY graha's ingress day has that graha in doubt too - Jupiter changes
#: sign about once a year and Saturn once in two and a half, and somebody born on 31 October 2026 has
#: Jupiter in Karka or Simha depending on whether they were born before or after 12:02. The list is
#: named _OTHERS rather than _SLOW because "slow" was the assumption that made it look like these did
#: not need checking.
_OTHERS = ("Sun", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu")
_SLOW = _OTHERS   # the old name, kept so nothing importing it breaks


def _sign_index(jd: float, graha: str) -> int:
    longitude, _ = longitude_and_speed(jd, graha)
    return int(longitude % 360 // 30)


def what_is_known(birth_date: dt.date, tz: str = "Asia/Kolkata") -> dict:
    """What can be said about a birth on this date without knowing the hour.

    Every value is checked across the WHOLE DAY - midnight to midnight in the birth's own timezone - and
    reported only where the answer is the same at both ends. Where it is not, the two possibilities are
    named, because "it is either Mesha or Vrishabha, depending on the hour" is a useful thing to be told
    and "Mesha" would be a guess presented as a fact.
    """
    zone = parse_tz(tz)
    start = julian_day(dt.datetime.combine(birth_date, dt.time(0, 0), tzinfo=zone))
    end = julian_day(dt.datetime.combine(birth_date, dt.time(23, 59), tzinfo=zone))

    settled, unsettled = [], []
    for graha in ("Moon", *_OTHERS):
        first, last = _sign_index(start, graha), _sign_index(end, graha)
        if first == last:
            settled.append({"graha": graha, "sign": sign_info(first)})
        else:
            unsettled.append({"graha": graha,
                              "signs": [sign_info(first), sign_info(last)],
                              # The hour decides it, so the reader is told exactly that.
                              "depends_on_time": True})
    return {
        "date": birth_date.isoformat(),
        "settled": settled,
        "unsettled": unsettled,
        # Named explicitly rather than left as an absence, so a page can say what it is NOT showing and
        # why - which is the whole point of this module.
        "needs_birth_time": ["lagna", "houses", "dasha", "bhava_positions", "mangal_dosha"],
    }


def moon_sign_is_safe(birth_date: dt.date, tz: str = "Asia/Kolkata") -> bool:
    """Does the Moon stay in one sign all day? True for roughly three days in five."""
    known = what_is_known(birth_date, tz)
    return any(entry["graha"] == "Moon" for entry in known["settled"])
