"""One page per purpose per year: the auspicious dates, month by month, computed.

NO AI AND NO STORED CONTENT. Every date on these pages comes out of app/engine/muhurta.py at render
time, from the same rules the finder tool applies, so there is nothing to generate, nothing to
regenerate when a year rolls, and nothing that can drift away from what the tool would say.

WHAT A DATE LIST CAN AND CANNOT DO, said on the page rather than implied. These are the panchang-
level dates: the nakshatra, the tithi, the weekday, and for a wedding the months the Sun's position
rules out. What they are not is a muhurta chosen for two particular people - that needs the couple's
charts and where Guru and Shukra are standing, and a family's own astrologer does it. A page that
let a reader think otherwise would be the most consequential thing on this site to be wrong about.
"""
from __future__ import annotations

import datetime as dt

from fastapi import Request
from fastapi.responses import HTMLResponse

from app.engine import muhurta
from app.web import i18n

MONTH_NAMES = {
    "en": ("January", "February", "March", "April", "May", "June", "July", "August", "September",
           "October", "November", "December"),
    "hi": ("जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर",
           "अक्टूबर", "नवंबर", "दिसंबर"),
    "mr": ("जानेवारी", "फेब्रुवारी", "मार्च", "एप्रिल", "मे", "जून", "जुलै", "ऑगस्ट", "सप्टेंबर",
           "ऑक्टोबर", "नोव्हेंबर", "डिसेंबर"),
}

# Per purpose, per language: the H1 and the title. The keyword is the H1 wherever the keyword is
# what somebody types - "vivah muhurat 2027" is 5,000 searches a month and rising.
TITLES = {
    "vivah": {
        "en": ("Vivah Muhurat {year}: auspicious marriage dates",
               "Vivah Muhurat {year} - Marriage Dates, Month by Month"),
        "hi": ("विवाह मुहूर्त {year}: शुभ विवाह तिथियाँ",
               "विवाह मुहूर्त {year} - Vivah Muhurat Dates"),
        "mr": ("विवाह मुहूर्त {year}: शुभ विवाह तारखा",
               "विवाह मुहूर्त {year} - Vivah Muhurat Tarkha"),
    },
    "griha-pravesh": {
        "en": ("Griha Pravesh Muhurat {year}: dates to move in",
               "Griha Pravesh Muhurat {year} - Housewarming Dates"),
        "hi": ("गृह प्रवेश मुहूर्त {year}: शुभ तिथियाँ",
               "गृह प्रवेश मुहूर्त {year} - Griha Pravesh Muhurat"),
        "mr": ("गृहप्रवेश मुहूर्त {year}: शुभ तारखा",
               "गृहप्रवेश मुहूर्त {year} - Griha Pravesh Muhurat"),
    },
    "vehicle": {
        "en": ("Vehicle Purchase Muhurat {year}: dates to buy",
               "Vehicle Muhurat {year} - Auspicious Dates to Buy a Car or Bike"),
        "hi": ("वाहन खरीदने का मुहूर्त {year}: शुभ तिथियाँ",
               "वाहन मुहूर्त {year} - Vahan Kharidne ka Muhurat"),
        "mr": ("वाहन खरेदी मुहूर्त {year}: शुभ तारखा",
               "वाहन मुहूर्त {year} - Vahan Kharedi Muhurat"),
    },
    "property": {
        "en": ("Property Purchase Muhurat {year}: dates to buy land or a flat",
               "Property Muhurat {year} - Dates to Buy Land or a Flat"),
        "hi": ("संपत्ति खरीदने का मुहूर्त {year}: शुभ तिथियाँ",
               "संपत्ति मुहूर्त {year} - Property Kharidne ka Muhurat"),
        "mr": ("मालमत्ता खरेदी मुहूर्त {year}: शुभ तारखा",
               "मालमत्ता मुहूर्त {year} - Malmatta Kharedi Muhurat"),
    },
    "naming": {
        "en": ("Namkaran Muhurat {year}: naming ceremony dates",
               "Namkaran Muhurat {year} - Naming Ceremony Dates"),
        "hi": ("नामकरण मुहूर्त {year}: शुभ तिथियाँ",
               "नामकरण मुहूर्त {year} - Namkaran Muhurat Dates"),
        "mr": ("बारसे मुहूर्त {year}: शुभ तारखा",
               "बारसे मुहूर्त {year} - Barse Namkaran Muhurat"),
    },
}

COPY = {
    "en": {
        "lede": "Every date in {year} that meets the classical rules for {what}, month by month - "
                "the nakshatra, the tithi and the weekday for each one. Computed with Swiss "
                "Ephemeris, not written by hand.",
        "nothing": "No date in this month meets the rules.",
        "columns": ("Date", "Day", "Nakshatra", "Tithi"),
        "what_heading": "What these dates are",
        "limits_heading": "What a date list cannot do",
        "limits": "These are the panchang-level dates: they are right about the nakshatra, the "
                  "tithi and the weekday for everybody. A muhurta chosen for two particular people "
                  "also needs their charts, and that is the work a family's own astrologer does. "
                  "Use this to narrow the choice, then ask them.",
        "basis_heading": "The rule applied",
        "others_heading": "Other muhurat dates for {year}",
        "cta_match": "Check gun milan for two kundalis",
        "cta_biodata": "Make a marriage biodata",
        "cta_finder": "Find a muhurta for your own date range",
        "count": "{n} dates in {year}",
    },
    "hi": {
        "lede": "{year} की वे सभी तिथियाँ जो {what} के शास्त्रीय नियमों पर खरी उतरती हैं, महीने के "
                "अनुसार - हर तिथि का नक्षत्र, तिथि और वार। Swiss Ephemeris से गणना की गई, हाथ से "
                "लिखी नहीं।",
        "nothing": "इस महीने कोई तिथि नियमों पर खरी नहीं उतरती।",
        "columns": ("तारीख़", "वार", "नक्षत्र", "तिथि"),
        "what_heading": "ये तिथियाँ क्या हैं",
        "limits_heading": "तिथि सूची क्या नहीं कर सकती",
        "limits": "ये पंचांग-स्तर की तिथियाँ हैं: नक्षत्र, तिथि और वार के बारे में ये सबके लिए सही "
                  "हैं। दो विशेष व्यक्तियों के लिए चुना गया मुहूर्त उनकी कुंडलियाँ भी देखता है, और "
                  "वह काम परिवार के अपने ज्योतिषी का है। इससे विकल्प छाँटें, फिर उनसे पूछें।",
        "basis_heading": "लागू नियम",
        "others_heading": "{year} के अन्य मुहूर्त",
        "cta_match": "दो कुंडलियों का गुण मिलान देखें",
        "cta_biodata": "विवाह बायोडाटा बनाएँ",
        "cta_finder": "अपनी तिथि सीमा के लिए मुहूर्त खोजें",
        "count": "{year} में {n} तिथियाँ",
    },
    "mr": {
        "lede": "{year} मधील त्या सर्व तारखा ज्या {what} च्या शास्त्रीय नियमांत बसतात, "
                "महिन्यानुसार - प्रत्येकीचे नक्षत्र, तिथी आणि वार. Swiss Ephemeris ने गणना केलेली, "
                "हाताने लिहिलेली नाही.",
        "nothing": "या महिन्यात कोणतीही तारीख नियमांत बसत नाही.",
        "columns": ("तारीख", "वार", "नक्षत्र", "तिथी"),
        "what_heading": "या तारखा काय आहेत",
        "limits_heading": "तारखांची यादी काय करू शकत नाही",
        "limits": "या पंचांग-स्तरावरील तारखा आहेत: नक्षत्र, तिथी आणि वाराबाबत त्या सर्वांसाठी "
                  "बरोबर आहेत. दोन विशिष्ट व्यक्तींसाठी निवडलेला मुहूर्त त्यांच्या कुंडल्याही "
                  "पाहतो, आणि ते काम कुटुंबाच्या स्वतःच्या ज्योतिषाचे आहे. यातून पर्याय कमी करा, "
                  "मग त्यांना विचारा.",
        "basis_heading": "लागू नियम",
        "others_heading": "{year} मधील इतर मुहूर्त",
        "cta_match": "दोन कुंडल्यांचे गुण मिलन पहा",
        "cta_biodata": "विवाह बायोडाटा तयार करा",
        "cta_finder": "तुमच्या तारखांसाठी मुहूर्त शोधा",
        "count": "{year} मध्ये {n} तारखा",
    },
}


def _nakshatra_names(keys, lang: str) -> list[str]:
    """The rule's nakshatras written in this tree's script."""
    from app.engine.constants import nakshatra_info

    if lang == "en":
        return list(keys)
    by_name = {}
    for index in range(27):
        info = nakshatra_info(index)
        by_name[info["name"]] = info["devanagari"]
    return [by_name.get(key, key) for key in keys]


def months_for(purpose: str, year: int, lang: str) -> list[dict]:
    """The year's dates, grouped into twelve months. Every month appears, including empty ones: a
    month missing from the list reads as an oversight, and "no date this month" is information."""
    found = muhurta.find(purpose, dt.date(year, 1, 1), dt.date(year, 12, 31), limit=400)
    by_month: dict[int, list[dict]] = {number: [] for number in range(1, 13)}
    for day in found["days"]:
        when = dt.date.fromisoformat(day["date"])
        by_month[when.month].append({
            "date": when,
            "day": when.day,
            "vara": day["vara"]["devanagari"] if lang != "en" else day["vara"]["key"],
            "nakshatra": day["nakshatra"]["devanagari"] if lang != "en" else day["nakshatra"]["name"],
            "tithi": day["tithi"]["devanagari"] if lang != "en" else day["tithi"]["name"],
            "paksha": day["tithi"]["paksha"]["devanagari"] if lang != "en"
                      else day["tithi"]["paksha"]["name"],
        })
    return [{"number": number, "name": MONTH_NAMES[lang][number - 1], "days": days}
            for number, days in sorted(by_month.items())]


def add_routes(router, page_context, respond, _json_ld) -> None:
    for lang in i18n.LANGS:
        for purpose in i18n.MUHURAT_PURPOSES:
            for year in i18n.YEAR_PAGES:
                _add(router, page_context, respond, _json_ld, lang, purpose, year)


def _add(router, page_context, respond, _json_ld, lang: str, purpose: str, year: int) -> None:
    path = i18n.url_for("muhurat-year", lang, purpose=purpose, year=year)
    words = COPY[lang]
    h1, title = (text.format(year=year) for text in TITLES[purpose][lang])
    rule = muhurta.purposes()[purpose]
    what = rule[lang]

    def muhurat_page(request: Request):
        from app.web import seo as _seo

        months = months_for(purpose, year, lang)
        total = sum(len(month["days"]) for month in months)
        context = page_context("muhurat-year", lang, purpose=purpose, year=year)
        context.update({
            "words": words,
            "year": year,
            "title": title,
            "h1": h1,
            "meta_description": words["lede"].format(year=year, what=what)[:180],
            "months": months,
            "total": total,
            "count_line": words["count"].format(n=total, year=year),
            "lede": words["lede"].format(year=year, what=what),
            "what": what,
            # THE NOTE AND THE NAKSHATRA NAMES IN THE READER'S SCRIPT. The rules file stores the
            # nakshatras by their English key because that is what the engine matches on; printing
            # those keys on a Hindi or Marathi page would put Latin words in the middle of
            # Devanagari prose, which the site-wide language guard refuses and a reader would
            # simply find wrong.
            "rule_note": rule.get(f"note_{lang}") or rule.get("note_en", ""),
            "nakshatras": _nakshatra_names(rule["nakshatras"], lang),
            "is_vivah": purpose == "vivah",
            # THE OTHER FOUR. Somebody looking up a wedding date this year is often the same
            # person who will look up a griha pravesh date next year, and without these the five
            # pages are five dead ends that only the sitemap reaches.
            "siblings": [
                {"path": i18n.url_for("muhurat-year", lang, purpose=other, year=year),
                 "label": TITLES[other][lang][0].format(year=year)}
                for other in i18n.MUHURAT_PURPOSES if other != purpose],
            "match_path": i18n.url_for("matching", lang),
            "biodata_path": i18n.url_for("biodata", lang),
            "finder_path": i18n.url_for("muhurta", lang) if "muhurta" in i18n.PAGES else "",
            "json_ld": [_json_ld(_seo.breadcrumbs([
                (context["ui"]["home"], i18n.url_for("home", lang)), (h1, path)]))],
        })
        return respond(request, "muhurat_year.html", context)

    router.add_api_route(path, muhurat_page, methods=["GET"], response_class=HTMLResponse,
                         name=f"muhurat-{purpose}-{year}-{lang}", include_in_schema=False)
