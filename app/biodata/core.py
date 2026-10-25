"""What the engine can fill in on a marriage biodata, and what it must leave blank.

THE KUNDLI BLOCK ON A BIODATA IS SIX LINES - rashi, nakshatra, charan, gan, nadi, manglik - and
families read them as facts, not as a reading. So each one is reported only where it is settled:

* WITH A BIRTH TIME all six are computable and are computed.
* WITH ONLY A DATE the Moon has moved about thirteen degrees across the day, which is a whole
  nakshatra's width. So the nakshatra may or may not be decided by the date alone, and the engine
  checks both ends of the day in the birth's own timezone and reports the value only where the two
  agree - exactly what `engine.without_time.what_is_known` already does for the signs. Where they
  disagree, BOTH are named: "Rohini or Mrigashira, depending on the hour" is useful, and "Rohini"
  would be a guess printed on a document that gets shown to a prospective family.
* CHARAN IS A QUARTER OF A NAKSHATRA, three degrees twenty minutes, which the Moon crosses in about
  six hours. Four of them pass in a day, so a date alone never settles it and it is left out rather
  than guessed.
* MANGLIK NEEDS THE HOUSES, which need the lagna, which needs the hour. Without a time there is no
  manglik line at all - and a biodata with a blank manglik line is honest, while one that says "No"
  on the strength of a date is a claim the family may act on.

Gan and nadi follow from the nakshatra, so they inherit its uncertainty rather than being computed
a second way.
"""
from __future__ import annotations

import datetime as dt

from app.engine import compute_chart
from app.engine.constants import nakshatra_info, sign_info
from app.engine.matching import _GANA_BY_NAKSHATRA, _NADI_CYCLE
from app.engine.without_time import julian_day, longitude_and_speed, parse_tz

NAKSHATRA_SPAN = 360.0 / 27
CHARAN_SPAN = NAKSHATRA_SPAN / 4

# The five engine-filled rows, in the order a biodata prints them, with the label each language uses.
# Marathi is not a translation of the Hindi here: a Marathi biodata says रास where Hindi says राशि,
# and the whole point of this tool for a Marathi family is that it reads like their own paperwork.
ROWS = ("rashi", "nakshatra", "charan", "gan", "nadi", "manglik")
LABELS = {
    "en": {"rashi": "Rashi (moon sign)", "nakshatra": "Nakshatra", "charan": "Charan (pada)",
           "gan": "Gan", "nadi": "Nadi", "manglik": "Manglik", "devak": "Devak", "gotra": "Gotra"},
    "hi": {"rashi": "राशि", "nakshatra": "नक्षत्र", "charan": "चरण", "gan": "गण", "nadi": "नाड़ी",
           "manglik": "मांगलिक", "devak": "देवक", "gotra": "गोत्र"},
    "mr": {"rashi": "रास", "nakshatra": "नक्षत्र", "charan": "चरण", "gan": "गण", "nadi": "नाडी",
           "manglik": "मंगळ", "devak": "देवक", "gotra": "गोत्र"},
}

GAN_NAMES = {
    "Deva": {"en": "Deva", "hi": "देव", "mr": "देव"},
    "Manushya": {"en": "Manushya", "hi": "मनुष्य", "mr": "मनुष्य"},
    "Rakshasa": {"en": "Rakshasa", "hi": "राक्षस", "mr": "राक्षस"},
}
NADI_NAMES = {
    "Aadi": {"en": "Aadi", "hi": "आद्य", "mr": "आद्य"},
    "Madhya": {"en": "Madhya", "hi": "मध्य", "mr": "मध्य"},
    "Antya": {"en": "Antya", "hi": "अंत्य", "mr": "अंत्य"},
}
# THREE STATES, NOT TWO. The engine answers `present` and, separately, whether a classical
# cancellation applies - and this is the line on a biodata that families read hardest. Collapsing a
# cancelled dosha to "Yes" invites a refusal the texts themselves do not ask for; collapsing it to
# "No" hides something the other family's astrologer will find in an afternoon and be right about.
# "Yes, with parihar" is the answer both a family and a pandit already recognise.
MANGLIK_NAMES = {
    "yes": {"en": "Yes", "hi": "हाँ", "mr": "होय"},
    "no": {"en": "No", "hi": "नहीं", "mr": "नाही"},
    "cancelled": {"en": "Yes, with parihar (cancellation)", "hi": "हाँ, परिहार सहित",
                  "mr": "होय, परिहारासह"},
}
# Said where the hour would be needed to answer. NOT "unknown": the reader is told what to do about it.
NEEDS_TIME = {"en": "birth time needed", "hi": "जन्म समय चाहिए", "mr": "जन्मवेळ आवश्यक"}


def _moon_longitude(moment: dt.datetime) -> float:
    longitude, _ = longitude_and_speed(julian_day(moment), "Moon")
    return longitude % 360


def _nakshatra_at(moment: dt.datetime) -> int:
    return int(_moon_longitude(moment) // NAKSHATRA_SPAN)


def _row(value, *, language: str, names: dict | None = None) -> dict:
    """One printed row: a settled value, or the two it lies between, or a request for the time."""
    if value is None:
        return {"known": False, "text": NEEDS_TIME[language]}
    if isinstance(value, list):
        shown = [names[v][language] if names else v for v in value]
        return {"known": False, "either": shown, "text": " / ".join(shown)}
    shown = names[value][language] if names else value
    return {"known": True, "text": shown}


def from_birth(birth_date: dt.date, *, birth_time: dt.time | None = None,
               lat: float | None = None, lon: float | None = None,
               tz: str = "Asia/Kolkata", language: str = "en") -> dict:
    """The kundli block for a biodata. Everything it cannot settle, it says so about."""
    if language not in LABELS:
        raise ValueError(f"unknown language {language!r}; use one of {sorted(LABELS)}")
    zone = parse_tz(tz)

    if birth_time is not None and lat is not None and lon is not None:
        chart = compute_chart(birth_date, birth_time, float(lat), float(lon), tz=tz)
        longitude = chart["grahas"]["Moon"]["longitude"] % 360
        nakshatra = int(longitude // NAKSHATRA_SPAN)
        charan = int((longitude % NAKSHATRA_SPAN) // CHARAN_SPAN) + 1
        from app.engine import dosha

        found = dosha.mangal_dosha(dosha.chart_signs(chart))
        manglik = ("cancelled" if found["cancellation_applies"] else "yes") if found["present"] else "no"
        rows = {
            "rashi": _row(sign_info(int(longitude // 30))["devanagari" if language != "en" else "name"],
                          language=language),
            "nakshatra": _row(nakshatra_info(nakshatra)["devanagari" if language != "en" else "name"],
                              language=language),
            "charan": _row(str(charan), language=language),
            "gan": _row(_GANA_BY_NAKSHATRA[nakshatra], language=language, names=GAN_NAMES),
            "nadi": _row(_NADI_CYCLE[nakshatra % 6], language=language, names=NADI_NAMES),
            "manglik": _row(manglik, language=language, names=MANGLIK_NAMES),
        }
        return {"rows": rows, "labels": LABELS[language], "from_time": True,
                "language": language, "charan_index": charan}

    # DATE ONLY. Both ends of the day, and only what agrees.
    start = dt.datetime.combine(birth_date, dt.time(0, 0), tzinfo=zone)
    end = dt.datetime.combine(birth_date, dt.time(23, 59), tzinfo=zone)
    first_sign, last_sign = int(_moon_longitude(start) // 30), int(_moon_longitude(end) // 30)
    first_nak, last_nak = _nakshatra_at(start), _nakshatra_at(end)
    key = "devanagari" if language != "en" else "name"

    def pair(a, b, info, names=None):
        if a == b:
            return _row(info(a)[key] if names is None else names_of(a, names), language=language,
                        names=None)
        return _row([info(a)[key], info(b)[key]] if names is None else [names_of(a, names), names_of(b, names)],
                    language=language)

    def names_of(index, table):
        return table[index][language]

    gan = {i: GAN_NAMES[_GANA_BY_NAKSHATRA[i]] for i in (first_nak, last_nak)}
    nadi = {i: NADI_NAMES[_NADI_CYCLE[i % 6]] for i in (first_nak, last_nak)}
    rows = {
        "rashi": pair(first_sign, last_sign, sign_info),
        "nakshatra": pair(first_nak, last_nak, nakshatra_info),
        "charan": _row(None, language=language),      # four of them pass in a day
        "gan": pair(first_nak, last_nak, nakshatra_info, gan),
        "nadi": pair(first_nak, last_nak, nakshatra_info, nadi),
        "manglik": _row(None, language=language),     # needs the lagna, which needs the hour
    }
    return {"rows": rows, "labels": LABELS[language], "from_time": False,
            "language": language, "charan_index": None}
