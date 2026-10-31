"""The panchang pages: /panchang, /hi/aaj-ka-panchang, /mr/aajche-panchang.

ZERO COST PER VIEW AND PER DAY. Everything here comes out of the ephemeris - no model call, no stored
reading, nothing to refresh overnight. That is the whole reason this page is worth having: "aaj ka
panchang" is searched 100K-1M times a month and the answer is arithmetic.

ONE INDEXED URL PER LANGUAGE, which is TODAY. A panchang has a page for every date since the calendar
began; inviting a crawler to all of them spends the crawl budget on pages nobody searched for. Other
dates are reachable from the picker and carry noindex, which is also the honest signal - they are a tool,
not content.
"""
from __future__ import annotations

import datetime as dt

from fastapi import Request
from fastapi.responses import HTMLResponse

from app.engine.cities import CITIES, find_city
from app.engine.panchang import full_panchang
from app.web import i18n

#: Where the reader's chosen city is remembered. A city is not a person: it is one of 137 names from a
#: list we ship, it is what they typed into a picker, and it saves them doing it again tomorrow.
CITY_COOKIE = "panchang_city"
COOKIE_MAX_AGE = 180 * 24 * 3600

#: Delhi for English and Hindi, Pune for Marathi - where each tree's readers mostly are. Sunrise at Pune
#: and Delhi differs by about twenty minutes, which on a day when a tithi ends near dawn is the
#: difference between two different answers, both correct.
DEFAULT_CITY = {"en": "Delhi", "hi": "Delhi", "mr": "Pune"}

#: How far either way the picker will go. Far enough to be useful for a vrat or a muhurat somebody is
#: planning, close enough that we are not generating a century of pages nobody asked for.
RANGE_DAYS = 400


def resolve_city(name: str | None, lang: str) -> dict:
    """The city to compute for: what was asked, else what was remembered, else the tree's default."""
    return find_city(name or "") or find_city(DEFAULT_CITY[lang]) or CITIES[0]


def resolve_date(raw: str | None, today: dt.date) -> tuple[dt.date, bool]:
    """-> (date, is_today). Anything unparseable or out of range falls back to today rather than erroring:
    a panchang asked for a date it cannot answer should still show one."""
    if not raw:
        return today, True
    try:
        asked = dt.date.fromisoformat(raw)
    except ValueError:
        return today, True
    if abs((asked - today).days) > RANGE_DAYS:
        return today, True
    return asked, asked == today


#: Page copy. The two METHOD NOTES are the important entries and they are stated rather than buried,
#: because a reader who compares us with another panchang will otherwise conclude we are wrong.
#:
#: Their direction was checked before they were written: swisseph's BIT_HINDU_RISING is DISC_CENTER |
#: NO_REFRACTION, and computing 21 October 2026 at Delhi gives 06:29:23 with it against 06:25:18 with the
#: upper limb and refraction - ProKerala publishes 06:29 and Drik Panchang 06:25. So WE are the disc
#: centre and Drik is the upper limb, which is the opposite of what it is easy to assume.
COPY = {
    "en": {
        "title": "Today's Panchang - Tithi, Nakshatra, Rahu Kaal",
        "h1": "Today's Panchang",
        "intro": "The five limbs of the day - vara, tithi, nakshatra, yoga and karana - as they stand at "
                 "sunrise, with the day's auspicious and inauspicious windows. Calculated from the Swiss "
                 "Ephemeris for your city.",
        "good_times": "Auspicious times today", "bad_times": "Times to avoid today",
        "limbs": "The five limbs", "sun_moon": "Sun and Moon", "calendar": "The lunar calendar",
        "city": "City", "date": "Date", "show": "Show", "today": "Today",
        "vara": "Weekday", "tithi": "Tithi", "nakshatra": "Nakshatra", "yoga": "Yoga",
        "karana": "Karana", "paksha": "Paksha", "masa": "Lunar month", "samvat": "Samvat",
        "sunrise": "Sunrise", "sunset": "Sunset", "moonrise": "Moonrise", "moonset": "Moonset",
        "moon_sign": "Moon sign", "sun_sign": "Sun sign",
        "rahu_kaal": "Rahu Kaal", "yamaganda": "Yamaganda", "gulika": "Gulika",
        "abhijit": "Abhijit Muhurat", "brahma": "Brahma Muhurat",
        "until": "until", "no_moonrise": "The Moon does not rise today",
        "abhijit_void": "Not observed today: Abhijit is held void on a Wednesday.",
        "amanta": "Amanta", "purnimanta": "Purnimanta",
        "masa_note": "Maharashtra and the south name the month from one new moon to the next; the north "
                     "names it from one full moon to the next. In the dark fortnight the two differ by a "
                     "month, so both are given.",
        # THE SUNRISE METHOD NOTE
        "sunrise_note": "Sunrise here is the moment the centre of the Sun's disc reaches the horizon, "
                        "without refraction - the classical panchang method. Some panchangs use the "
                        "upper edge of the disc with refraction, which gives a sunrise about four "
                        "minutes earlier; every time derived from sunrise shifts with it.",
        # THE BRAHMA MUHURAT NOTE
        "brahma_note": "Counted as the second-to-last of the fifteen muhurtas of the night, measured "
                       "from the previous sunset. Published panchangs differ by several minutes here "
                       "because they divide the night slightly differently.",
        "more": "More for today",
    },
    "hi": {
        "title": "आज का पंचांग - तिथि, नक्षत्र, राहु काल",
        "h1": "आज का पंचांग",
        "intro": "सूर्योदय के समय दिन के पाँच अंग - वार, तिथि, नक्षत्र, योग और करण - और दिन के शुभ तथा "
                 "अशुभ समय। आपके शहर के लिए स्विस एफेमेरिस से गणना किया हुआ।",
        "good_times": "आज के शुभ समय", "bad_times": "आज बचने के समय",
        "limbs": "पंचांग के पाँच अंग", "sun_moon": "सूर्य और चंद्र", "calendar": "चंद्र पंचांग",
        "city": "शहर", "date": "तारीख़", "show": "दिखाइए", "today": "आज",
        "vara": "वार", "tithi": "तिथि", "nakshatra": "नक्षत्र", "yoga": "योग",
        "karana": "करण", "paksha": "पक्ष", "masa": "मास", "samvat": "संवत",
        "sunrise": "सूर्योदय", "sunset": "सूर्यास्त", "moonrise": "चंद्रोदय", "moonset": "चंद्रास्त",
        "moon_sign": "चंद्र राशि", "sun_sign": "सूर्य राशि",
        "rahu_kaal": "राहु काल", "yamaganda": "यमगंड", "gulika": "गुलिक",
        "abhijit": "अभिजित मुहूर्त", "brahma": "ब्रह्म मुहूर्त",
        "until": "तक", "no_moonrise": "आज चंद्रोदय नहीं है",
        "abhijit_void": "आज नहीं: बुधवार को अभिजित मुहूर्त नहीं माना जाता।",
        "amanta": "अमांत", "purnimanta": "पूर्णिमांत",
        "masa_note": "महाराष्ट्र और दक्षिण में मास अमावस्या से अमावस्या तक गिना जाता है, उत्तर में "
                     "पूर्णिमा से पूर्णिमा तक। कृष्ण पक्ष में दोनों नामों में एक महीने का अंतर आता है, "
                     "इसलिए दोनों दिए गए हैं।",
        "sunrise_note": "यहाँ सूर्योदय वह क्षण है जब सूर्य बिंब का केंद्र क्षितिज पर आता है, वक्रीभवन "
                        "के बिना - यही शास्त्रीय पंचांग की रीति है। कुछ पंचांग बिंब का ऊपरी किनारा और "
                        "वक्रीभवन लेते हैं, जिससे सूर्योदय लगभग चार मिनट पहले आता है; सूर्योदय से "
                        "निकलने वाला हर समय उतना ही खिसक जाता है।",
        "brahma_note": "रात्रि के पंद्रह मुहूर्तों में से अंतिम से पहले वाला, पिछले सूर्यास्त से गिना "
                       "हुआ। रात को बाँटने की रीति थोड़ी अलग होने से प्रकाशित पंचांगों में यहाँ कुछ "
                       "मिनटों का अंतर रहता है।",
        "more": "आज के लिए और",
    },
    "mr": {
        "title": "आजचे पंचांग - तिथी, नक्षत्र, राहू काळ",
        "h1": "आजचे पंचांग",
        "intro": "सूर्योदयाच्या वेळची दिवसाची पाच अंगे - वार, तिथी, नक्षत्र, योग आणि करण - आणि दिवसातील "
                 "शुभ व अशुभ वेळा. तुमच्या शहरासाठी स्विस एफेमेरिसने गणना केलेली.",
        "good_times": "आजच्या शुभ वेळा", "bad_times": "आज टाळायच्या वेळा",
        "limbs": "पंचांगाची पाच अंगे", "sun_moon": "सूर्य आणि चंद्र", "calendar": "चांद्र पंचांग",
        "city": "शहर", "date": "तारीख", "show": "दाखवा", "today": "आज",
        "vara": "वार", "tithi": "तिथी", "nakshatra": "नक्षत्र", "yoga": "योग",
        "karana": "करण", "paksha": "पक्ष", "masa": "मास", "samvat": "संवत",
        "sunrise": "सूर्योदय", "sunset": "सूर्यास्त", "moonrise": "चंद्रोदय", "moonset": "चंद्रास्त",
        "moon_sign": "चंद्र रास", "sun_sign": "सूर्य रास",
        "rahu_kaal": "राहू काळ", "yamaganda": "यमगंड", "gulika": "गुलिक",
        "abhijit": "अभिजित मुहूर्त", "brahma": "ब्रह्म मुहूर्त",
        "until": "पर्यंत", "no_moonrise": "आज चंद्रोदय नाही",
        "abhijit_void": "आज नाही: बुधवारी अभिजित मुहूर्त धरला जात नाही.",
        "amanta": "अमांत", "purnimanta": "पौर्णिमांत",
        "masa_note": "महाराष्ट्रात आणि दक्षिणेत मास अमावस्येपासून अमावस्येपर्यंत मोजतात, उत्तरेत "
                     "पौर्णिमेपासून पौर्णिमेपर्यंत. कृष्ण पक्षात दोन्ही नावांत एका महिन्याचा फरक येतो, "
                     "म्हणून दोन्ही दिली आहेत.",
        "sunrise_note": "इथे सूर्योदय म्हणजे सूर्यबिंबाचा मध्य क्षितिजावर येण्याचा क्षण, वक्रीभवनाशिवाय "
                        "- हीच शास्त्रीय पंचांगाची रीत आहे. काही पंचांगे बिंबाची वरची कड आणि वक्रीभवन "
                        "धरतात, त्यामुळे सूर्योदय सुमारे चार मिनिटे आधी येतो; सूर्योदयावरून काढलेली "
                        "प्रत्येक वेळ तितकीच सरकते.",
        "brahma_note": "रात्रीच्या पंधरा मुहूर्तांपैकी शेवटच्या आधीचा, मागच्या सूर्यास्तापासून मोजलेला. "
                       "रात्र वाटण्याची रीत थोडी वेगळी असल्याने प्रकाशित पंचांगांत इथे काही मिनिटांचा "
                       "फरक राहतो.",
        "more": "आजसाठी आणखी",
    },
}


def _clock(stamp: str | None, on: dt.date) -> str:
    """"14:12", or "14:12 (23 Oct)" when it falls on another date.

    THE DATE IS NOT OPTIONAL DECORATION. A tithi that ends at 06:11 tomorrow printed as "06:11" reads as
    this morning, which is the single most misleading thing a panchang can do - somebody plans a vrat
    around it.
    """
    if not stamp:
        return ""
    when = dt.datetime.fromisoformat(stamp)
    if when.date() == on:
        return when.strftime("%H:%M")
    return f"{when:%H:%M} ({when:%-d %b})"


def view(day: dt.date, city: dict, lang: str) -> dict:
    """The page's whole view model. No branching in the template beyond "is this present"."""
    words = COPY[lang]
    data = full_panchang(day, city)

    def window(entry, label):
        return {"label": label, "from": _clock(entry["from"], day), "to": _clock(entry["to"], day),
                "void": entry.get("void", False)}

    limb = lambda key, label: {  # noqa: E731
        "label": label, "name": data[key].get("devanagari") if lang in ("hi", "mr") else data[key]["name"],
        "latin": data[key]["name"],
        "ends_at": _clock(data[key].get("ends_at"), day)}

    masa = data["masa"]
    return {
        "date": day,
        "city": city,
        "is_today": day == dt.date.today(),
        "sunrise": _clock(data["sunrise"], day), "sunset": _clock(data["sunset"], day),
        "moonrise": _clock(data["moonrise"], day), "moonset": _clock(data["moonset"], day),
        "no_moonrise": data["moonrise"] is None,
        "limbs": [
            {"label": words["vara"], "name": data["vara"].get("devanagari") if lang in ("hi", "mr")
             else data["vara"]["key"], "latin": data["vara"]["name"], "ends_at": ""},
            limb("tithi", words["tithi"]),
            limb("nakshatra", words["nakshatra"]),
            limb("yoga", words["yoga"]),
            limb("karana", words["karana"]),
        ],
        "paksha": (data["paksha"] or {}).get("devanagari" if lang in ("hi", "mr") else "name", ""),
        "masa": masa, "masa_differ": masa["differ"],
        "samvat": data["samvat"],
        "moon_sign": data["moon_sign"], "sun_sign": data["sun_sign"],
        "good": [window(data["auspicious"]["abhijit"], words["abhijit"]),
                 window(data["auspicious"]["brahma_muhurat"], words["brahma"])],
        "bad": [window(data["inauspicious"]["rahu_kaal"], words["rahu_kaal"]),
                window(data["inauspicious"]["yamaganda"], words["yamaganda"]),
                window(data["inauspicious"]["gulika"], words["gulika"])],
        "cities": [c["name"] for c in CITIES],
        "min_date": (dt.date.today() - dt.timedelta(days=RANGE_DAYS)).isoformat(),
        "max_date": (dt.date.today() + dt.timedelta(days=RANGE_DAYS)).isoformat(),
    }


def add_routes(router, page_context, respond, _json_ld) -> None:
    """Registered from routes.py, which owns the router and the shared context builder."""
    for lang in i18n.PAGES["panchang"]:
        _add(router, page_context, respond, _json_ld, lang)


def _add(router, page_context, respond, _json_ld, lang: str) -> None:
    def panchang_page(request: Request):
        today = dt.date.today()
        day, is_today = resolve_date(request.query_params.get("date"), today)
        asked_city = request.query_params.get("city") or request.cookies.get(CITY_COOKIE)
        city = resolve_city(asked_city, lang)
        context = page_context("panchang", lang)
        words = COPY[lang]
        # STRUCTURED DATA, like every other indexable page. A WebApplication (this IS a calculator - a
        # city and a date go in, a panchang comes out) plus breadcrumbs. Without it the page is the only
        # entry in the sitemap with no JSON-LD, which the SEO test rightly refuses.
        from app.web import seo as _seo

        path = i18n.url_for("panchang", lang)
        json_ld = [_json_ld(_seo.web_application(words["h1"], path, words["intro"],
                                                 i18n.HTML_LANG[lang])),
                   _json_ld(_seo.breadcrumbs([(context["ui"]["home"], i18n.url_for("home", lang)),
                                              (words["h1"], path)]))]
        context.update(words=words, panchang=view(day, city, lang), json_ld=json_ld,
                       # EVERY OTHER DATE IS noindex. One indexed panchang per language - today's - is
                       # the page people search for; the rest are a tool.
                       noindex=not is_today,
                       title=words["title"], h1=words["h1"])
        response = respond(request, "panchang.html", context)
        if request.query_params.get("city") and city["name"] == request.query_params.get("city"):
            # Remembered so tomorrow's visit does not start at Delhi again. One city name from a list we
            # ship; nothing about the reader.
            response.set_cookie(CITY_COOKIE, city["name"], max_age=COOKIE_MAX_AGE,
                                httponly=True, samesite="lax")
        return response

    router.add_api_route(i18n.url_for("panchang", lang), panchang_page, methods=["GET"],
                         response_class=HTMLResponse, name=f"panchang-{lang}")
