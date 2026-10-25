"""A year of the Hindu calendar: the festivals, the ekadashis, and every amavasya and purnima.

TWO CONVENTIONS, AND THEY DISAGREE BY A DAY ON PURPOSE.

A panchang NAMES a day after the tithi running at SUNRISE, and that is how almost every festival in
this file is dated - Holi is the day named Phalguna Purnima, Janmashtami the day named Ashtami. So
this module walks the year once, records the tithi at sunrise, and matches each festival's rule
against that.

An observance done in the EVENING is a different question, because a tithi lasts about 23 hours 37
minutes and the one at sunset is routinely the next one. Dhanteras and Lakshmi puja are decided that
way, by app/engine/festivals.py, which asks what the tithi is at pradosh rather than what the day is
called. Those two are deliberately NOT recomputed here: this module imports their answer, so the
calendar and the Diwali page can never print different dates for the same evening.

The disagreement is stated on the page rather than resolved silently. A family acts on these dates.

THE LUNAR MONTH IS PINNED BY THE SUN'S SIGN, not by a Gregorian month, the same way the festival
engine does it - Phalguna Purnima is "the purnima while the Sun is in Kumbha", which is right in
every year rather than right in most.
"""
from __future__ import annotations

import datetime as dt
from functools import lru_cache

from .festivals import IST, _place, _tithi_at
from .panchang import panchang

# (key, paksha, tithi, sun_sign or None, names). sun_sign is the SIDEREAL sign the Sun is in on the
# day, which is what pins the lunar month. None means the tithi is unambiguous enough in the year
# that no pinning is needed - no entry here uses that, and the field is kept so one can.
FESTIVALS = (
    ("maha-shivaratri", "krishna", 14, "Kumbha",
     ("Maha Shivaratri", "महा शिवरात्रि", "महाशिवरात्री")),
    ("holika-dahan", "shukla", 15, "Meena", ("Holika Dahan", "होलिका दहन", "होळी पौर्णिमा")),
    ("holi", "krishna", 1, "Meena", ("Holi", "होली", "धुलिवंदन")),
    ("gudi-padwa", "shukla", 1, "Meena", ("Gudi Padwa / Ugadi", "गुड़ी पड़वा / उगादि", "गुढीपाडवा")),
    ("ram-navami", "shukla", 9, "Mesha", ("Ram Navami", "राम नवमी", "राम नवमी")),
    ("hanuman-jayanti", "shukla", 15, "Mesha", ("Hanuman Jayanti", "हनुमान जयंती", "हनुमान जयंती")),
    ("akshaya-tritiya", "shukla", 3, "Mesha", ("Akshaya Tritiya", "अक्षय तृतीया", "अक्षय्य तृतीया")),
    ("vat-purnima", "shukla", 15, "Vrishabha", ("Vat Purnima", "वट पूर्णिमा", "वटपौर्णिमा")),
    ("guru-purnima", "shukla", 15, "Mithuna", ("Guru Purnima", "गुरु पूर्णिमा", "गुरुपौर्णिमा")),
    ("nag-panchami", "shukla", 5, "Karka", ("Nag Panchami", "नाग पंचमी", "नागपंचमी")),
    ("raksha-bandhan", "shukla", 15, "Karka", ("Raksha Bandhan", "रक्षा बंधन", "रक्षाबंधन")),
    ("janmashtami", "krishna", 8, "Simha", ("Krishna Janmashtami", "कृष्ण जन्माष्टमी",
                                            "कृष्ण जन्माष्टमी")),
    ("ganesh-chaturthi", "shukla", 4, "Simha", ("Ganesh Chaturthi", "गणेश चतुर्थी", "गणेश चतुर्थी")),
    ("anant-chaturdashi", "shukla", 14, "Simha", ("Anant Chaturdashi", "अनंत चतुर्दशी",
                                                  "अनंत चतुर्दशी")),
    ("navratri-start", "shukla", 1, "Kanya", ("Sharad Navratri begins", "शारदीय नवरात्रि आरंभ",
                                              "शारदीय नवरात्र प्रारंभ")),
    ("dussehra", "shukla", 10, "Kanya", ("Dussehra / Vijayadashami", "दशहरा / विजयादशमी",
                                         "दसरा / विजयादशमी")),
    ("kojagiri", "shukla", 15, "Kanya", ("Sharad Purnima / Kojagiri", "शरद पूर्णिमा",
                                        "कोजागिरी पौर्णिमा")),
    ("karva-chauth", "krishna", 4, "Tula", ("Karva Chauth", "करवा चौथ", "करवा चौथ")),
    ("tulsi-vivah", "shukla", 12, "Tula", ("Tulsi Vivah", "तुलसी विवाह", "तुळशी विवाह")),
    ("kartik-purnima", "shukla", 15, "Tula", ("Kartik Purnima / Dev Diwali",
                                                    "कार्तिक पूर्णिमा", "त्रिपुरारी पौर्णिमा")),
)

EKADASHI_NAMES = {"en": "Ekadashi", "hi": "एकादशी", "mr": "एकादशी"}
AMAVASYA_NAMES = {"en": "Amavasya", "hi": "अमावस्या", "mr": "अमावस्या"}
PURNIMA_NAMES = {"en": "Purnima", "hi": "पूर्णिमा", "mr": "पौर्णिमा"}

# Makar Sankranti is SOLAR, not lunar: it is the day the Sun enters Makara, so it is found by
# watching the Sun's sign change rather than by matching a tithi.
SANKRANTI_NAMES = ("Makar Sankranti", "मकर संक्रांति", "मकर संक्रांत")

DEFAULT_CITY = "Ujjain"


def _names(triple: tuple[str, str, str]) -> dict:
    return {"en": triple[0], "hi": triple[1], "mr": triple[2]}


@lru_cache(maxsize=8)
def _year_days(year: int, city: str) -> tuple:
    """One walk of the year: for each date, the tithi at sunrise and the Sun's sign.

    Cached, because every list on the calendar page comes out of this same walk and a year is three
    hundred and sixty-five ephemeris calls.
    """
    place = _place(city)
    out = []
    day = dt.date(year, 1, 1)
    while day.year == year:
        facts = panchang(day, place["lat"], place["lon"], tz=place.get("tz", "Asia/Kolkata"))
        sunrise = dt.datetime.fromisoformat(facts["sunrise"])
        tithi = _tithi_at(sunrise + dt.timedelta(minutes=1))
        out.append({
            "date": day,
            "tithi": tithi,
            "sun_sign": facts["sun"]["sign"]["name"] if "sun" in facts else None,
            "vara": facts["vara"],
        })
        day += dt.timedelta(days=1)
    return tuple(out)


def _sun_sign_on(day: dt.date, city: str) -> str:
    """The Sun's sign BY NAME. `festivals._sun_sign` answers with a 1-based index, and comparing
    that against "Kumbha" is a comparison that is simply always false - which found no festivals at
    all rather than finding the wrong ones, and so was obvious the moment the list came back empty.
    The rules are written with names because a reader of this file should be able to check them."""
    from .constants import sign_info
    from .festivals import _sun_sign

    return sign_info(_sun_sign(day, _place(city)) - 1)["name"]


def festivals(year: int, *, city: str = DEFAULT_CITY) -> list[dict]:
    """Every festival in FESTIVALS, dated by the tithi at sunrise, in date order.

    Dhanteras and Lakshmi puja come from app/engine/festivals.py instead - they are evening
    observances and that module already decides them by the tithi at pradosh. Importing its answer
    is what keeps the calendar and the Diwali page from printing different dates.
    """
    walk = _year_days(year, city)
    found = []
    for key, paksha, tithi_day, sun_sign, names in FESTIVALS:
        match = _by_sunrise(walk, paksha, tithi_day, sun_sign, city)
        basis = "sunrise"
        if match is None:
            # A KSHAYA TITHI: one that begins after sunrise and ends before the next, so no day is
            # NAMED for it. A tithi runs about 23 hours 37 minutes, so this happens several times a
            # year - in 2027 there is no sunrise at all on Phalguna Purnima at Ujjain. The festival
            # does not stop existing, so it is dated to the day the tithi BEGINS, which is the usual
            # convention for one. Without this branch a festival simply vanished from the calendar,
            # which is the kind of gap nobody notices until a reader does.
            match = _by_start(year, paksha, tithi_day, sun_sign, city)
            basis = "tithi-start"
        if match is not None:
            found.append({"key": key, "date": match["date"], "names": _names(names),
                          "tithi": match["tithi"], "basis": basis})

    from .festivals import windows

    for key, names in (("dhanteras", ("Dhanteras", "धनतेरस", "धनत्रयोदशी")),
                       ("lakshmi-puja", ("Diwali / Lakshmi Puja", "दिवाली / लक्ष्मी पूजा",
                                         "दिवाळी / लक्ष्मी पूजन"))):
        answer = windows(key, year, city)
        if answer and answer.get("date"):
            # `windows()` returns a real date object, not an ISO string.
            found.append({"key": key, "date": answer["date"], "names": _names(names),
                          "tithi": answer.get("tithi"), "basis": "pradosh"})

    sankranti = makar_sankranti(year, city=city)
    if sankranti:
        found.append({"key": "makar-sankranti", "date": sankranti, "names": _names(SANKRANTI_NAMES),
                      "tithi": None, "basis": "solar"})
    return sorted(found, key=lambda item: item["date"])


def _by_sunrise(walk, paksha: str, tithi_day: int, sun_sign: str | None, city: str):
    for entry in walk:
        if entry["tithi"]["paksha"]["key"] != paksha or entry["tithi"]["day"] != tithi_day:
            continue
        if sun_sign and _sun_sign_on(entry["date"], city) != sun_sign:
            continue
        return entry
    return None


def _by_start(year: int, paksha: str, tithi_day: int, sun_sign: str | None, city: str):
    """The day a tithi that never catches a sunrise begins on. Probed every two hours, which is far
    finer than a tithi's roughly twenty-four-hour length and cheap enough to do only on the rare
    occasions the sunrise pass found nothing."""
    place = _place(city)
    zone = IST
    previous = None
    moment = dt.datetime(year, 1, 1, 0, 0, tzinfo=zone)
    end = dt.datetime(year + 1, 1, 1, 0, 0, tzinfo=zone)
    while moment < end:
        tithi = _tithi_at(moment)
        here = (tithi["paksha"]["key"], tithi["day"])
        if here == (paksha, tithi_day) and previous != here:
            day = moment.date()
            if not sun_sign or _sun_sign_on(day, city) == sun_sign:
                return {"date": day, "tithi": tithi}
        previous = here
        moment += dt.timedelta(hours=2)
    return None


def makar_sankranti(year: int, *, city: str = DEFAULT_CITY) -> dt.date | None:
    """The day the Sun enters Makara. Solar, so no tithi is involved at all."""
    previous = None
    for day in (dt.date(year, 1, 1) + dt.timedelta(days=n) for n in range(0, 31)):
        sign = _sun_sign_on(day, city)
        if previous is not None and sign == "Makara" and previous != "Makara":
            return day
        previous = sign
    return None


def ekadashis(year: int, *, city: str = DEFAULT_CITY) -> list[dict]:
    """Every ekadashi in the year: tithi 11 of either paksha at sunrise."""
    return [{"date": entry["date"], "paksha": entry["tithi"]["paksha"]}
            for entry in _year_days(year, city) if entry["tithi"]["day"] == 11]


def amavasyas(year: int, *, city: str = DEFAULT_CITY) -> list[dict]:
    return [{"date": entry["date"]} for entry in _year_days(year, city)
            if entry["tithi"]["name"] == "Amavasya"]


def purnimas(year: int, *, city: str = DEFAULT_CITY) -> list[dict]:
    return [{"date": entry["date"]} for entry in _year_days(year, city)
            if entry["tithi"]["name"] == "Purnima"]
