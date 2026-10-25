"""A birth known only to within a window of time: what that still settles, and what it does not.

THE CASE THIS IS FOR. "Some time in the morning" and "about 7:30" are different kinds of not-knowing,
and the no-time module treats them the same - it checks the whole day and reports only what holds at
both ends. For somebody who knows the hour to within forty minutes that throws away almost everything,
because the lagna very often does not move at all inside a window that short.

WHAT A WINDOW SETTLES. The lagna advances through one sign roughly every two hours, so a window either
sits inside one sign - in which case the lagna and the houses are KNOWN, not guessed - or it crosses a
boundary, in which case there are two or three possibilities and each one owns a slice of the window.
Both are useful answers and neither is a guess. Where it crosses, the slices are found by bisection on
the ascendant itself rather than by sampling, so the boundary time is exact to the second.

WHAT A WINDOW DOES NOT SETTLE. The dasha. Vimshottari is keyed on the Moon's longitude, which moves
about one degree every two hours - and the balance at birth sets every date in the sequence for a
lifetime, so an error of minutes at the start becomes an error of months by the third mahadasha. It is
refused unless the window is under DASHA_MINUTES, and that threshold is about what the arithmetic can
carry rather than about what a reader would like.
"""
from __future__ import annotations

import datetime as dt

from app.engine.constants import sign_info
from app.engine.core import ascendant, julian_day, parse_tz

#: A window at or under this many minutes is tight enough for the dasha to be worth computing. Ten
#: minutes of Moon motion is about five arc-minutes, which moves a mahadasha boundary by a few weeks at
#: the far end of a life - visible, but not the kind of error that renames the period somebody is in.
DASHA_MINUTES = 10

#: The longest window worth answering at all. Past six hours the lagna has usually crossed three or four
#: signs and "it is one of these four" is the same answer the no-time page already gives, with more
#: words. Refused rather than answered thinly.
MAX_HOURS = 6


def _sign_at(moment: dt.datetime, lat: float, lon: float) -> int:
    """The rising sign as the ORDINAL sign_info() takes: 0 = Mesha.

    Not sign_info(...)["index"], which is 1-based - the argument and the field disagree, so feeding one
    back into the other shifts every answer by a sign. It did: this reported Karka for a birth whose
    chart says Vrishabha, which is what comparing against compute_chart() caught.
    """
    return int(ascendant(julian_day(moment), lat, lon) // 30)


def _boundary(low: dt.datetime, high: dt.datetime, lat: float, lon: float) -> dt.datetime:
    """The moment the rising sign changes, between two moments that differ. Bisection, to the second.

    The ascendant is monotonic in time over any window this short, so bisection is exact rather than
    approximate - which matters because the answer is printed as a time somebody will compare against
    what they were told.
    """
    while (high - low) > dt.timedelta(seconds=1):
        middle = low + (high - low) / 2
        if _sign_at(middle, lat, lon) == _sign_at(low, lat, lon):
            low = middle
        else:
            high = middle
    return high


def _to_minute(moment: dt.datetime) -> str:
    """HH:MM, rounded to the nearest minute."""
    rounded = (moment + dt.timedelta(seconds=30)).replace(second=0, microsecond=0)
    return rounded.strftime("%H:%M")


def lagna_in_window(birth_date: dt.date, start: dt.time, end: dt.time, lat: float, lon: float,
                    tz: str = "Asia/Kolkata") -> dict:
    """What the lagna is, or might be, for a birth somewhere inside [start, end] on this date."""
    zone = parse_tz(tz)
    begins = dt.datetime.combine(birth_date, start, tzinfo=zone)
    ends = dt.datetime.combine(birth_date, end, tzinfo=zone)
    if ends <= begins:
        return {"error": "end_before_start"}
    minutes = (ends - begins).total_seconds() / 60
    if minutes > MAX_HOURS * 60:
        return {"error": "window_too_wide", "max_hours": MAX_HOURS, "minutes": round(minutes)}

    # Walk the window, splitting at each change of rising sign. At most a handful of slices: the lagna
    # moves through one sign roughly every two hours and the window is capped at six.
    slices, cursor = [], begins
    guard = 0
    while cursor < ends and guard < 12:
        guard += 1
        here = _sign_at(cursor, lat, lon)
        if _sign_at(ends, lat, lon) == here:
            slices.append((cursor, ends, here))
            break
        edge = _boundary(cursor, ends, lat, lon)
        slices.append((cursor, edge, here))
        cursor = edge

    # ROUNDED TO THE NEAREST MINUTE, not truncated. A boundary found at 06:07:45 printed as "06:07"
    # reads as a claim that a birth at 06:07:10 falls in the later slice, which it does not - the
    # printed time is what somebody will compare against whatever they were told, so it should be the
    # closest minute rather than the one below. The slices themselves are exact to the second.
    possibilities = [{"sign": sign_info(index),
                      "from": _to_minute(slice_start),
                      "to": _to_minute(slice_end),
                      "minutes": round((slice_end - slice_start).total_seconds() / 60)}
                     for slice_start, slice_end, index in slices]
    settled = len(possibilities) == 1
    return {
        "date": birth_date.isoformat(),
        "window": {"from": start.strftime("%H:%M"), "to": end.strftime("%H:%M"),
                   "minutes": round(minutes)},
        "settled": settled,
        # The lagna, only when the whole window agrees. Houses follow the lagna, so they are offered on
        # exactly the same condition and never on a majority.
        "lagna": possibilities[0]["sign"] if settled else None,
        "houses_known": settled,
        "possibilities": possibilities,
        # Refused with the reason and the threshold, so a page can say what it would take rather than
        # only that it will not.
        "dasha": {"available": minutes <= DASHA_MINUTES, "needs_minutes": DASHA_MINUTES,
                  "why": ("the Moon moves about a degree every two hours, and the balance at birth sets "
                          "every date in the sequence for a lifetime")},
    }
