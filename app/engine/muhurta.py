"""Muhurta: the days in a range whose panchang satisfies a purpose's classical rules.

ARITHMETIC, NOT A GUARANTEE. Everything here is computed - sunrise and sunset from the ephemeris, the
tithi and nakshatra from the Moon and Sun, the day's divisions from the two. What the rules then say about
those numbers is tradition, written down in `muhurta_rules.json` so it can be read and argued with. The
engine's claim is only that the arithmetic is right and the rule was applied as written.

The conventions are the site's existing ones, deliberately: Lahiri ayanamsa, and our own sunrise (disc
centre, no refraction - `core.sunrise`). A muhurta computed against a different sunrise is a different
answer, so the panchang and the day's divisions are taken from one source rather than two.

NOTHING IS PADDED. A search returns the days that pass and says how many it found. If that is none, it is
none: a near miss offered as a result is worth less than an empty answer, because the reader cannot see
which rule it failed.
"""

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
from pathlib import Path

from .constants import nakshatra_info, sign_info
from .core import (DEFAULT_TZ, from_julian_day, julian_day, longitude_and_speed, parse_tz,
                   sunrise, sunset)
from .panchang import (REFERENCE_PLACE, _nakshatra_index, _next_change, tithi_index, tithi_info,
                       vara_info, yoga_index, yoga_info)

RULES_PATH = Path(__file__).with_name("muhurta_rules.json")

# Rahu kaal is one of the eight equal parts of a day, and WHICH part is fixed per weekday. Monday = 0, as
# date.weekday() has it. The sequence below is the standard one: Sunday the eighth part, Monday the second,
# Tuesday the seventh, Wednesday the fifth, Thursday the sixth, Friday the fourth, Saturday the third.
_RAHU_PART = {0: 2, 1: 7, 2: 5, 3: 6, 4: 4, 5: 3, 6: 8}
# Yamaganda takes its own part of the same eight, by the same weekday rule and a different sequence:
# Sunday the fifth, Monday the fourth, Tuesday the third, Wednesday the second, Thursday the first,
# Friday the seventh, Saturday the sixth.
_YAMA_PART = {0: 4, 1: 3, 2: 2, 3: 1, 4: 7, 5: 6, 6: 5}
_PARTS_IN_A_DAY = 8
# Abhijit is the eighth of the FIFTEEN muhurtas the daylight is divided into - the one straddling midday.
# It is the classical "always auspicious" window, with one exception that is stated rather than hidden:
# most traditions hold it void on a Wednesday, so it is marked rather than silently dropped.
_MUHURTAS_IN_A_DAY = 15
_ABHIJIT_MUHURTA = 8
_ABHIJIT_VOID_WEEKDAY = 2      # Wednesday, as date.weekday() numbers it

# The nine taras, counted from the birth nakshatra to the day's. 3, 5 and 7 are the ones classical texts
# tell you to avoid; 1 (Janma) is mixed and is reported as such rather than scored.
_TARA_NAMES = [
    ("Janma", "जन्म", "mixed"), ("Sampat", "संपत", "good"), ("Vipat", "विपत", "avoid"),
    ("Kshema", "क्षेम", "good"), ("Pratyari", "प्रत्यरि", "avoid"), ("Sadhaka", "साधक", "good"),
    ("Vadha", "वध", "avoid"), ("Mitra", "मित्र", "good"), ("Ati-Mitra", "अतिमित्र", "good"),
]
# The Moon's sign counted from the birth Moon sign. The 4th, 8th and 12th are the ones to avoid; this is
# chandra bala, and it is the reason two people can be given different dates for the same purpose.
_CHANDRA_GOOD = {1, 3, 6, 7, 10, 11}
_CHANDRA_AVOID = {4, 8, 12}
_MAX_RANGE_DAYS = 400       # a year and a bit; past that a search is not a question, it is a crawl


def rules() -> dict:
    """The rule file, read from disk. Small, and read per call so an edit needs no restart in development."""
    return json.loads(RULES_PATH.read_text(encoding="utf-8"))


def purposes() -> dict:
    return rules()["purposes"]


class Refused(Exception):
    """A purpose this service will not answer for. Carries the reason, which the caller shows the reader."""


def check_allowed(text: str) -> None:
    """Raise `Refused` when a request is about health, death or a legal outcome.

    These are refused everywhere else on the site and a date-finder is not a loophole: "when should the
    operation be" is a medical question wearing a calendar. The refusal names itself rather than returning
    an empty list, because an empty list reads as "no good days", which is a worse answer than none.
    """
    refused = rules()["refused"]
    lowered = (text or "").lower()
    for key in ("keywords_en", "keywords_hi", "keywords_mr"):
        for word in refused[key]:
            if word.lower() in lowered:
                raise Refused(word)


def _place(place: dict | None) -> dict:
    if not place:
        return dict(REFERENCE_PLACE)
    return {"name": place.get("name"), "lat": float(place["lat"]), "lon": float(place["lon"]),
            "tz": place.get("tz") or DEFAULT_TZ}


def day_facts(day: date, place: dict | None = None) -> dict:
    """Everything a rule can ask about one civil day at one place. All times local, to the minute."""
    spot = _place(place)
    zone = parse_tz(spot["tz"])
    midnight = datetime.combine(day, time(0, 0), tzinfo=zone)
    jd_rise = sunrise(julian_day(midnight), spot["lat"], spot["lon"])
    jd_set = sunset(jd_rise, spot["lat"], spot["lon"])
    rise_local = from_julian_day(jd_rise).astimezone(zone)
    if rise_local.date() != day:
        raise ValueError(f"no sunrise on {day.isoformat()} at lat={spot['lat']}, lon={spot['lon']}")

    def local(jd: float) -> datetime:
        moment = from_julian_day(jd).astimezone(zone)
        return (moment + timedelta(seconds=30)).replace(second=0, microsecond=0)

    def stamp(jd: float) -> str:
        return local(jd).isoformat(timespec="minutes")

    # The day's eight equal parts, measured sunrise to sunset - not over a civil day, and not over a fixed
    # twelve hours. In March at Pune that is the difference between 14:13 and about half past one.
    part = (jd_set - jd_rise) / _PARTS_IN_A_DAY
    nth = _RAHU_PART[day.weekday()]
    rahu_from, rahu_to = jd_rise + part * (nth - 1), jd_rise + part * nth

    yama_nth = _YAMA_PART[day.weekday()]
    yama_from, yama_to = jd_rise + part * (yama_nth - 1), jd_rise + part * yama_nth
    muhurta_len = (jd_set - jd_rise) / _MUHURTAS_IN_A_DAY
    abhijit_from = jd_rise + muhurta_len * (_ABHIJIT_MUHURTA - 1)
    abhijit_to = jd_rise + muhurta_len * _ABHIJIT_MUHURTA

    tithi = tithi_info(tithi_index(jd_rise))
    tithi["ends_at"] = stamp(_next_change(jd_rise, tithi_index))
    nakshatra = nakshatra_info(_nakshatra_index(jd_rise))
    nakshatra["ends_at"] = stamp(_next_change(jd_rise, _nakshatra_index))
    return {
        "date": day.isoformat(),
        "place": spot,
        "convention": "values current at sunrise; Lahiri ayanamsa",
        "sunrise": stamp(jd_rise),
        "sunset": stamp(jd_set),
        "vara": vara_info(day),
        "tithi": tithi,
        "nakshatra": nakshatra,
        # The Moon's SIGN at sunrise, which the nakshatra does not give: chandra bala counts signs from the
        # birth Moon, and a nakshatra can straddle two of them.
        "moon_sign": sign_info(int(longitude_and_speed(jd_rise, "Moon")[0] % 360 // 30)),
        "yoga": yoga_info(yoga_index(jd_rise)),
        "rahu_kaal": {"from": stamp(rahu_from), "to": stamp(rahu_to), "part": nth},
        "yamaganda": {"from": stamp(yama_from), "to": stamp(yama_to), "part": yama_nth},
        "abhijit": {"from": stamp(abhijit_from), "to": stamp(abhijit_to),
                    # Said, not silently dropped: a reader who knows the rule would otherwise think we
                    # did not, and one who does not know it would use a window tradition sets aside.
                    "void": day.weekday() == _ABHIJIT_VOID_WEEKDAY},
        "clear_windows": _clear_windows(local(jd_rise), local(jd_set),
                                        [(local(rahu_from), local(rahu_to)),
                                         (local(yama_from), local(yama_to))]),
    }


def _clear_windows(start: datetime, end: datetime, blocked: list[tuple]) -> list[dict]:
    """Daylight with the inauspicious bands cut out of it, as start-end windows.

    THE ACTUAL ANSWER TO "WHEN". A date on its own is half of a muhurta: the day is chosen by its panchang
    and the hour by what is cut out of it. Rahu Kaal and Yamaganda were being printed as times to avoid and
    left for the reader to subtract; this does the subtraction. Windows shorter than twenty minutes are
    dropped, because nothing is begun in them and they only make the list harder to read.
    """
    spans = sorted((max(start, a), min(end, b)) for a, b in blocked if b > start and a < end)
    windows, cursor = [], start
    for block_start, block_end in spans:
        if block_start > cursor:
            windows.append((cursor, block_start))
        cursor = max(cursor, block_end)
    if cursor < end:
        windows.append((cursor, end))
    return [{"from": a.isoformat(timespec="minutes"), "to": b.isoformat(timespec="minutes"),
             "minutes": int((b - a).total_seconds() // 60)}
            for a, b in windows if (b - a) >= timedelta(minutes=20)]


def _tithi_number(tithi: dict) -> int:
    """1-15 within the paksha, which is what the rule file states. `tithi_info` calls that field `day`;
    `index` is 1-30 across both halves, and reading the wrong one would silently shift every rikta rule
    into the dark half."""
    return int(tithi["day"])


def tara_bala(day_nakshatra_index: int, birth_nakshatra_index: int) -> dict:
    """Which of the nine taras this day's nakshatra is, counted from the birth nakshatra.

    Both indices are 1-27. This is half of why two people are given different dates for the same purpose:
    the panchang is the same for the city, and tara bala is not.
    """
    steps = (int(day_nakshatra_index) - int(birth_nakshatra_index)) % 27
    name, devanagari, verdict = _TARA_NAMES[steps % 9]
    return {"tara": (steps % 9) + 1, "name": name, "devanagari": devanagari, "verdict": verdict}


def chandra_bala(day_moon_sign_index: int, birth_moon_sign_index: int) -> dict:
    """The Moon's sign counted from the birth Moon sign, 1-12, and whether that count is a good one."""
    house = ((int(day_moon_sign_index) - int(birth_moon_sign_index)) % 12) + 1
    verdict = "good" if house in _CHANDRA_GOOD else ("avoid" if house in _CHANDRA_AVOID else "mixed")
    return {"house": house, "verdict": verdict}


def judge(facts: dict, purpose: str, birth: dict | None = None) -> dict:
    """Apply one purpose's rules to one day.

    -> {"passes", "passed": [...], "failed": [...], "personal": {...}|None, "note"}

    BOTH HALVES ARE RETURNED. A date with no reasons attached is an opinion; one that says what it passed
    AND what it failed can be argued with, which is the whole claim this feature makes. `passed` is not
    derived from `failed` - each rule appends to one or the other as it is applied, so a rule that stops
    being applied disappears from both rather than silently counting as passed.

    `birth` is optional: {"nakshatra_index", "moon_sign_index"}. With it, tara bala and chandra bala are
    reported ALONGSIDE the verdict rather than folded into it - they are a different tradition's question
    and a reader is owed the difference between "this day does not suit the work" and "this day does not
    suit you".
    """
    rule = purposes().get(purpose)
    if rule is None:
        raise KeyError(purpose)
    passed, failed = [], []
    nakshatra = facts["nakshatra"]["name"]
    (passed if nakshatra in rule["nakshatras"] else failed).append(f"nakshatra {nakshatra}")
    number = _tithi_number(facts["tithi"])
    (failed if number in rule["avoid_tithis"] else passed).append(f"tithi {facts['tithi']['name']}")
    if rule.get("avoid_amavasya"):
        (failed if facts["tithi"]["name"] == "Amavasya" else passed).append("not amavasya")
    weekday = date.fromisoformat(facts["date"]).weekday()
    if rule["avoid_varas"]:
        # `key` is the English weekday; `name` is the Sanskrit vara. The reason is read by people and by
        # tests, so it says Tuesday rather than Mangalavara.
        (failed if weekday in rule["avoid_varas"] else passed).append(f"{facts['vara']['key']}")

    personal = None
    if birth and birth.get("nakshatra_index") and birth.get("moon_sign_index"):
        personal = {
            "tara": tara_bala(facts["nakshatra"]["index"], birth["nakshatra_index"]),
            "chandra": chandra_bala(facts["moon_sign"]["index"], birth["moon_sign_index"]),
        }
    return {"passes": not failed, "passed": passed, "failed": failed, "personal": personal,
            "note": rule.get("note_en", "")}


BACKUPS = 2


def find(purpose: str, start: date, end: date, place: dict | None = None, limit: int = 12,
         birth: dict | None = None) -> dict:
    """The days between `start` and `end` (inclusive) that pass, in order, at most `limit` of them.

    Returns the count SEARCHED as well as the count found, because "3 days" means nothing without the
    range it came out of, and because a reader is owed the difference between "few good days" and "short
    search".
    """
    if purpose not in purposes():
        raise KeyError(purpose)
    if end < start:
        raise ValueError("the range ends before it starts")
    if (end - start).days > _MAX_RANGE_DAYS:
        raise ValueError(f"a range longer than {_MAX_RANGE_DAYS} days is not searched")

    found, day, searched = [], start, 0
    while day <= end:
        searched += 1
        facts = day_facts(day, place)
        verdict = judge(facts, purpose, birth)
        if verdict["passes"]:
            found.append({**facts, "why": verdict["note"], "passed": verdict["passed"],
                          "failed": verdict["failed"], "personal": verdict["personal"]})
            # limit + BACKUPS, because the backups are the next passing dates and are found the same way.
            if len(found) >= limit + BACKUPS:
                break
        day += timedelta(days=1)
    # THE BACKUPS ARE REAL DATES, not near misses. A "backup" that failed a rule would be a date offered
    # with its reason for being unsuitable attached, which is worse than offering nothing.
    return {"purpose": purpose, "from": start.isoformat(), "to": end.isoformat(),
            "searched_days": searched, "found": len(found[:limit]), "days": found[:limit],
            "backups": found[limit:limit + BACKUPS],
            "basis": "arithmetic, not a guarantee"}
