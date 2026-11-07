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


# The twenty-seven nitya yogas, in order. The yoga is the FIFTH limb of the panchang and was the one this
# engine did not have: it is the Sun's and the Moon's longitudes ADDED, not subtracted, divided into the
# same 13 deg 20' the nakshatras use. Four of them - Vishkambha, Atiganda, Shula, Vyaghata, Vajra, Vyatipata,
# Parigha and Vaidhriti - are the ones muhurta texts set aside; which of those a rule cares about is the
# rule file's business, not this table's.
_YOGA_NAMES = [
    ("Vishkambha", "विष्कंभ"), ("Priti", "प्रीति"), ("Ayushman", "आयुष्मान"), ("Saubhagya", "सौभाग्य"),
    ("Shobhana", "शोभन"), ("Atiganda", "अतिगंड"), ("Sukarma", "सुकर्मा"), ("Dhriti", "धृति"),
    ("Shula", "शूल"), ("Ganda", "गंड"), ("Vriddhi", "वृद्धि"), ("Dhruva", "ध्रुव"),
    ("Vyaghata", "व्याघात"), ("Harshana", "हर्षण"), ("Vajra", "वज्र"), ("Siddhi", "सिद्धि"),
    ("Vyatipata", "व्यतीपात"), ("Variyana", "वरीयान"), ("Parigha", "परिघ"), ("Shiva", "शिव"),
    ("Siddha", "सिद्ध"), ("Sadhya", "साध्य"), ("Shubha", "शुभ"), ("Shukla", "शुक्ल"),
    ("Brahma", "ब्रह्म"), ("Indra", "इंद्र"), ("Vaidhriti", "वैधृति"),
]
YOGA_SPAN = NAKSHATRA_SPAN   # the same 13 deg 20', applied to the SUM of the two longitudes


def yoga_index(jd: float) -> int:
    """0-26. Sun + Moon, not Moon - Sun: that difference is the tithi."""
    moon, _ = longitude_and_speed(jd, "Moon")
    sun, _ = longitude_and_speed(jd, "Sun")
    return int(((moon + sun) % 360) // YOGA_SPAN)


def yoga_info(index: int) -> dict:
    name, devanagari = _YOGA_NAMES[index]
    return {"index": index + 1, "name": name, "devanagari": devanagari}


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


# ---- karana ------------------------------------------------------------------------------------------
# A karana is HALF a tithi, so there are 60 in a lunar month. Eleven names cover them: seven "movable"
# ones repeat eight times each (56), and four "fixed" ones occupy the remaining four - the second half of
# Krishna Chaturdashi and then Amavasya's two halves and the first half of Shukla Pratipada.
_MOVABLE_KARANAS = [
    ("Bava", "बव"), ("Balava", "बालव"), ("Kaulava", "कौलव"), ("Taitila", "तैतिल"),
    ("Gara", "गर"), ("Vanija", "वणिज"), ("Vishti", "विष्टि"),
]
#: Vishti is Bhadra, the one karana tradition says to avoid for anything begun. Named so a page can say
#: so rather than leave a reader to recognise it.
_BHADRA = "Vishti"
_FIXED_KARANAS = {
    0: ("Kimstughna", "किंस्तुघ्न"),    # first half of Shukla Pratipada
    57: ("Shakuni", "शकुनि"),           # second half of Krishna Chaturdashi
    58: ("Chatushpada", "चतुष्पाद"),    # first half of Amavasya
    59: ("Naga", "नाग"),                # second half of Amavasya
}
KARANA_SPAN = TITHI_SPAN / 2


def karana_index(jd: float) -> int:
    """0-59, counted from the start of the bright half - the same origin tithi_index uses."""
    moon, _ = longitude_and_speed(jd, "Moon")
    sun, _ = longitude_and_speed(jd, "Sun")
    return int(((moon - sun) % 360) // KARANA_SPAN)


def karana_info(index: int) -> dict:
    """The karana at `index`, with whether it is Bhadra.

    The four fixed karanas sit at known positions; everything else cycles through the seven movable ones.
    The cycle starts at index 1 (Bava), because index 0 is Kimstughna.
    """
    index = int(index) % 60
    if index in _FIXED_KARANAS:
        name, devanagari = _FIXED_KARANAS[index]
        kind = "fixed"
    else:
        name, devanagari = _MOVABLE_KARANAS[(index - 1) % 7]
        kind = "movable"
    return {"index": index, "name": name, "devanagari": devanagari, "kind": kind,
            "is_bhadra": name == _BHADRA}


# ---- the lunar month, and the eras -------------------------------------------------------------------
_MASA_NAMES = [
    ("Chaitra", "चैत्र"), ("Vaishakha", "वैशाख"), ("Jyeshtha", "ज्येष्ठ"), ("Ashadha", "आषाढ"),
    ("Shravana", "श्रावण"), ("Bhadrapada", "भाद्रपद"), ("Ashwina", "आश्विन"), ("Kartika", "कार्तिक"),
    ("Margashirsha", "मार्गशीर्ष"), ("Pausha", "पौष"), ("Magha", "माघ"), ("Phalguna", "फाल्गुन"),
]


def _previous_new_moon(jd: float) -> float:
    """The instant of the new moon at or before `jd`, to about a second.

    The amanta month runs new moon to new moon, so this is what names it.
    """
    low, high = jd - 31.0, jd
    # Step back to a point that is certainly in the previous lunation, then bisect on "elongation has
    # wrapped" - which is what a new moon IS.
    def elongation(at: float) -> float:
        moon, _ = longitude_and_speed(at, "Moon")
        sun, _ = longitude_and_speed(at, "Sun")
        return (moon - sun) % 360

    here = elongation(jd)
    probe = jd - here / 12.19          # the Moon gains ~12.19 deg a day on the Sun
    low, high = probe - 2.0, probe + 2.0
    while high - low > _PRECISION_DAYS:
        middle = (low + high) / 2
        if elongation(middle) > 180:   # still in the old lunation
            low = middle
        else:
            high = middle
    return high


def masa(jd: float) -> dict:
    """The lunar month this instant falls in, amanta (new moon to new moon) and purnimanta.

    AMANTA IS THE DEFAULT because it is what the southern and western states use - including Maharashtra,
    which is this site's Marathi audience. The purnimanta name, used across the north, is given beside it:
    in the dark half the two differ by one month, and a reader in Delhi and a reader in Pune genuinely
    call the same fortnight by different names. Saying both is the only honest answer.

    The month is named from the SOLAR SIGN the Sun occupies at that new moon: Chaitra begins at the new
    moon while the Sun is in Meena, and so on.
    """
    new_moon = _previous_new_moon(jd)
    sun, _ = longitude_and_speed(new_moon, "Sun")
    # The Sun in Meena (sign index 11) at the new moon starts Chaitra, so the month index is the sign
    # index shifted by one.
    index = int((int(sun % 360 // 30) + 1) % 12)
    amanta, amanta_dev = _MASA_NAMES[index]
    # Purnimanta runs full moon to full moon, so during the DARK half it is already the next month.
    dark = tithi_index(jd) >= 15
    p_index = (index + 1) % 12 if dark else index
    purnimanta, purnimanta_dev = _MASA_NAMES[p_index]
    return {"amanta": amanta, "amanta_devanagari": amanta_dev,
            "purnimanta": purnimanta, "purnimanta_devanagari": purnimanta_dev,
            "differ": amanta != purnimanta}


def samvat(day: date, jd: float) -> dict:
    """Vikram and Shaka years for this instant.

    BOTH TURN AT CHAITRA, not in January, so the year changes in March or April. A panchang that adds a
    constant to the Gregorian year is wrong for a quarter of every year - and wrong precisely in the
    months when somebody is most likely to be looking the year up.

    WHICH LUNAR YEAR ARE WE IN? The months run Chaitra, Vaishakha ... Phalguna within one lunar year, and
    Chaitra begins in March or April. So a date in Pausha, Magha or Phalguna that falls in a Gregorian
    January, February or March belongs to the lunar year that began in the PREVIOUS Gregorian year. That
    is the only case that needs saying, and it is said here rather than inferred from an offset.
    """
    month = masa(jd)
    index = _MASA_NAMES.index((month["amanta"], month["amanta_devanagari"]))
    late_months = index >= 9                 # Pausha, Magha, Phalguna
    began = day.year - 1 if (late_months and day.month <= 4) else day.year
    return {"vikram": began + 57, "shaka": began - 78,
            "lunar_year_began": began,
            "masa_index": index}


def full_panchang(day: date, place: dict | None = None) -> dict:
    """Everything a printed panchang prints, for one civil day at one place. No AI, no network.

    The five limbs (vara, tithi, nakshatra, yoga, karana) are read AT SUNRISE, which is the convention
    every published panchang uses and the reason a page must state its place: sunrise at Pune and at
    Delhi differ by about twenty minutes, and on a day when a tithi ends at 06:45 that is the difference
    between two different answers, both correct.

    Each limb carries `ends_at` as well as its name, because "Dashami" alone is the half-truth that makes
    people miss a vrat: what a reader needs is that it gives way to Ekadashi at two in the afternoon.
    """
    from .muhurta import day_facts

    facts = day_facts(day, place)
    spot = facts["place"]
    tz = parse_tz(spot.get("tz") or DEFAULT_TZ)
    jd_rise = julian_day(datetime.fromisoformat(facts["sunrise"]))

    def stamp(jd):
        return from_julian_day(jd).astimezone(tz).isoformat(timespec="minutes") if jd else None

    from .core import moonrise as _moonrise
    from .core import moonset as _moonset

    karana = karana_info(karana_index(jd_rise))
    karana["ends_at"] = stamp(_next_change(jd_rise, karana_index))
    yoga = dict(facts["yoga"])
    yoga["ends_at"] = stamp(_next_change(jd_rise, yoga_index))

    midnight = julian_day(datetime.combine(day, time(0, 0), tzinfo=tz))
    # THE MOONSET THAT BELONGS TO THIS MOONRISE, not the first one after midnight. Searching from
    # midnight returned 01:26 for Delhi on 21 October 2026 - a setting that happened BEFORE that day's
    # moonrise at 14:50, which is nonsense as a pair and disagreed with both published panchangs (02:19
    # and 02:22, the following morning). The Moon rises about fifty minutes later each day, so for most
    # of the month its set belongs to the next civil date, and that is what a panchang prints.
    rise_jd = _moonrise(midnight, spot["lat"], spot["lon"])
    set_jd = _moonset(rise_jd if rise_jd else midnight, spot["lat"], spot["lon"])
    sun_longitude, _ = longitude_and_speed(jd_rise, "Sun")
    from .constants import sign_info

    return {
        "date": day.isoformat(),
        "place": spot,
        "convention": "the five limbs are those current at sunrise; sidereal, Lahiri ayanamsa",
        "sunrise": facts["sunrise"],
        "sunset": facts["sunset"],
        # None is a real answer: the Moon does not rise at all on about one civil day a month, and a
        # panchang that prints a time anyway is wrong on exactly those days.
        "moonrise": stamp(rise_jd),
        "moonset": stamp(set_jd),
        "vara": facts["vara"],
        "tithi": facts["tithi"],
        "nakshatra": facts["nakshatra"],
        "yoga": yoga,
        "karana": karana,
        "paksha": facts["tithi"].get("paksha"),
        "masa": masa(jd_rise),
        "samvat": samvat(day, jd_rise),
        "moon_sign": facts["moon_sign"],
        "sun_sign": sign_info(int(sun_longitude % 360 // 30)),
        "auspicious": {"abhijit": facts["abhijit"], "brahma_muhurat": facts["brahma_muhurat"]},
        "inauspicious": {"rahu_kaal": facts["rahu_kaal"], "yamaganda": facts["yamaganda"],
                         "gulika": facts["gulika"]},
        "clear_windows": facts["clear_windows"],
    }
