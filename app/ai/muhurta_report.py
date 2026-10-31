"""The Muhurta Report, built from the engine and nothing else.

Every other product in `app/ai` is a brief handed to a writer. This one is not written at all: the dates,
the panchang behind each one and the rule each satisfied are arithmetic, and a model asked to phrase them
is a model able to get them wrong. So this fills the same report shape the writer would have filled, from
`app/engine/muhurta.py`, and the only prose in it is fixed copy that says what was done.

It is deliberately the same SHAPE, so the catalogue, the order, the GST split, the entitlement check and
the PDF pipeline all treat it like any other report and none of them needs to know it had no model.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json

from app.engine import muhurta

CACHE_VERSION = 1

_LANGS = ("en", "hi", "mr")

# THE NAME, in one place, used by the page, the nav, the chat and the PDF cover. A searcher types
# "auspicious date" far more often than "muhurta", and a reader who knows the word recognises it in the
# bracket - so both are in the English name rather than one of them.
TITLE = {
    "en": "Find an Auspicious Date (Muhurat)",
    "hi": "शुभ मुहूर्त खोजें",
    "mr": "शुभ मुहूर्त शोधा",
}
SUBLINE = {
    "en": "Shubh muhurat for your launch, business, griha pravesh or vehicle",
    "hi": "अपने काम के लिए अच्छा दिन और समय",
    "mr": "तुमच्या कामासाठी चांगला दिवस आणि वेळ",
}
BUTTON = {
    "en": "Get Muhurat free",
    "hi": "शुभ मुहूर्त मुफ्त पाएं",
    "mr": "शुभ मुहूर्त मोफत मिळवा",
}

# THE LINE THAT GOES ON EVERY RESULT, in the reader's language. It is not a disclaimer in small print at
# the end: what this product sells is arithmetic, and saying so is the honest description of it.
BASIS = {
    "en": "This is arithmetic, not a guarantee. The sunrise, the tithi and the nakshatra are computed from "
          "the ephemeris; which of them suits a purpose is tradition, and tradition does not agree with "
          "itself everywhere.",
    "hi": "यह गणित है, कोई गारंटी नहीं। सूर्योदय, तिथि और नक्षत्र ग्रहगणित से निकाले गए हैं; इनमें से कौन सा काम "
          "किस दिन शुभ है, यह परंपरा कहती है, और परंपरा हर जगह एक जैसी नहीं है।",
    "mr": "हे गणित आहे, हमी नाही. सूर्योदय, तिथी आणि नक्षत्र ग्रहगणितातून काढले आहेत; त्यांपैकी कोणता दिवस कोणत्या "
          "कामाला योग्य, हे परंपरा सांगते, आणि परंपरा सर्वत्र सारखी नाही.",
}

_NONE_FOUND = {
    "en": "No day in this range satisfied the rule for this purpose. That is the answer, not a shortage of "
          "effort: a near miss offered as a date would hide which rule it failed.",
    "hi": "इस अवधि में कोई दिन इस काम के नियम पर खरा नहीं उतरा। यही उत्तर है - लगभग सही दिन दे देना उस नियम को "
          "छिपा देता जिस पर वह चूका।",
    "mr": "या कालावधीत एकही दिवस या कामाच्या नियमात बसला नाही. हेच उत्तर आहे - जवळपास बसणारा दिवस दिला असता तर "
          "तो कोणत्या नियमात बसला नाही हे लपले असते.",
}

_FOUND = {
    "en": "{found} date(s) found in {searched} day(s) searched, between {start} and {end} for {place}.",
    "hi": "{start} से {end} के बीच {place} के लिए {searched} दिन देखे गए, उनमें से {found} दिन उपयुक्त मिले।",
    "mr": "{start} ते {end} दरम्यान {place} साठी {searched} दिवस तपासले, त्यांपैकी {found} दिवस योग्य आढळले.",
}

_HEADINGS = {
    "dates": {"en": "The dates", "hi": "तिथियाँ", "mr": "तारखा"},
    "how": {"en": "How these were chosen", "hi": "ये कैसे चुने गए", "mr": "या कशा निवडल्या"},
    "panchang": {"en": "The panchang behind each date", "hi": "हर दिन का पंचांग", "mr": "प्रत्येक दिवसाचे पंचांग"},
    "backups": {"en": "Two more, if those do not suit", "hi": "दो और दिन, अगर ये न जमें",
                "mr": "आणखी दोन दिवस, हे जमले नाहीत तर"},
}
_FIELD = {
    "window": {"en": "Best windows", "hi": "उपयुक्त समय", "mr": "योग्य वेळ"},
    "rahu": {"en": "Rahu Kaal", "hi": "राहु काल", "mr": "राहू काळ"},
    "yama": {"en": "Yamaganda", "hi": "यमगंड", "mr": "यमगंड"},
    "abhijit": {"en": "Abhijit", "hi": "अभिजित", "mr": "अभिजित"},
    "yoga": {"en": "Yoga", "hi": "योग", "mr": "योग"},
    "tara": {"en": "Tara bala", "hi": "तारा बल", "mr": "तारा बल"},
    "chandra": {"en": "Chandra bala", "hi": "चंद्र बल", "mr": "चंद्र बल"},
    "passed": {"en": "Rules it passed", "hi": "जो नियम पूरे हुए", "mr": "पूर्ण झालेले नियम"},
    "failed": {"en": "Rules it failed", "hi": "जो नियम पूरे नहीं हुए", "mr": "पूर्ण न झालेले नियम"},
    "void": {"en": "(set aside on a Wednesday)", "hi": "(बुधवार को नहीं)", "mr": "(बुधवारी नाही)"},
    "none": {"en": "none", "hi": "कोई नहीं", "mr": "काही नाही"},
    "house": {"en": "house from your Moon", "hi": "भाव, आपके चंद्र से", "mr": "स्थान, तुमच्या चंद्रापासून"},
}
# The engine's verdicts are English keys; a Marathi sentence must not end in "(good)".
_VERDICT = {
    "good": {"en": "good", "hi": "अच्छा", "mr": "चांगले"},
    "avoid": {"en": "avoid", "hi": "टालें", "mr": "टाळा"},
    "mixed": {"en": "mixed", "hi": "मिश्रित", "mr": "संमिश्र"},
}

# The window replaced the sunrise and the Rahu Kaal: a reader wants to know WHEN, and sunrise minus the
# bands is that answer. Both of the bands are still printed, per date, in the panchang section.
_ROW = {
    "en": ("Date", "Weekday", "Best windows", "Tithi", "Nakshatra", "Yoga"),
    "hi": ("दिनांक", "वार", "उपयुक्त समय", "तिथि", "नक्षत्र", "योग"),
    "mr": ("दिनांक", "वार", "योग्य वेळ", "तिथी", "नक्षत्र", "योग"),
}

_WITH_BIRTH = {
    "en": "Your birth chart is used for two of the lines below and nothing else: tara bala counts from your "
          "janma nakshatra to the day's, and chandra bala counts the Moon's sign from your Moon's. They are "
          "reported beside the verdict rather than folded into it - a day can suit the work and not suit you.",
    "hi": "नीचे दी गई दो बातों के लिए ही आपकी कुंडली देखी गई है: तारा बल आपके जन्म नक्षत्र से उस दिन के नक्षत्र तक "
          "गिना जाता है, और चंद्र बल आपके चंद्र की राशि से उस दिन की। ये फ़ैसले में मिलाए नहीं गए हैं - कोई दिन काम के "
          "लिए ठीक हो सकता है और आपके लिए नहीं।",
    "mr": "खालच्या दोनच गोष्टींसाठी तुमची कुंडली वापरली आहे: तारा बल तुमच्या जन्मनक्षत्रापासून त्या दिवसाच्या "
          "नक्षत्रापर्यंत मोजले जाते, आणि चंद्र बल तुमच्या चंद्राच्या राशीपासून त्या दिवसाच्या राशीपर्यंत. ही निर्णयात "
          "मिसळलेली नाहीत - एखादा दिवस कामाला योग्य असू शकतो आणि तुम्हाला नाही.",
}
_STOPPED_EARLY = {
    "en": "The search stopped once it had enough dates, so the days counted are the days it needed to look "
          "at, not the whole range.",
    "hi": "पर्याप्त दिन मिलते ही खोज रुक गई, इसलिए गिने गए दिन उतने ही हैं जितने देखने पड़े, पूरी अवधि नहीं।",
    "mr": "पुरेसे दिवस मिळताच शोध थांबला, म्हणून मोजलेले दिवस तेवढेच आहेत जेवढे पाहावे लागले, पूर्ण कालावधी नाही.",
}

_HOW = {
    "en": "A day is offered only when its nakshatra at sunrise is one this purpose traditionally uses, its "
          "tithi is not one of the rikta tithis (the fourth, ninth and fourteenth), it is not amavasya, and "
          "the weekday is not one the purpose sets aside. Rahu Kaal is given for each day so it can be "
          "avoided within the day; it does not disqualify the day itself. Nothing about your birth chart is "
          "used unless you give one, and then only for tara bala and chandra bala - this is "
          "the panchang for the place, not a reading for a person.",
    "hi": "कोई दिन तभी दिया गया है जब सूर्योदय के समय उसका नक्षत्र इस काम के लिए परंपरा में माना जाता हो, तिथि रिक्ता "
          "(चतुर्थी, नवमी, चतुर्दशी) न हो, अमावस्या न हो, और वार वह न हो जिसे इस काम के लिए छोड़ा जाता है। राहु काल "
          "हर दिन के साथ दिया है ताकि दिन के भीतर उससे बचा जा सके; उससे पूरा दिन अशुभ नहीं होता। इसमें आपकी "
          "जन्मकुंडली का उपयोग नहीं हुआ है - यह स्थान का पंचांग है, किसी व्यक्ति का फलादेश नहीं।",
    "mr": "एखादा दिवस तेव्हाच दिला आहे जेव्हा सूर्योदयाच्या वेळी त्याचे नक्षत्र या कामासाठी परंपरेत मानले जाते, तिथी "
          "रिक्ता (चतुर्थी, नवमी, चतुर्दशी) नाही, अमावस्या नाही, आणि वार या कामासाठी वर्ज्य नाही. राहू काळ प्रत्येक "
          "दिवसासोबत दिला आहे, म्हणजे दिवसातल्या त्या वेळेत काम टाळता येईल; त्याने पूर्ण दिवस वर्ज्य होत नाही. यात "
          "तुमची जन्मकुंडली वापरलेली नाही - हे त्या ठिकाणाचे पंचांग आहे, व्यक्तीचे भविष्य नाही.",
}


def report_id(purpose: str, language: str, start: dt.date, end: dt.date, place: dict,
              birth: dict | None = None) -> str:
    """Its own id recipe, because its inputs are not births.

    A muhurta order is identified by what was SEARCHED - the purpose, the range and the place. Two searches
    that differ in any of those are different reports and must not share a cached one.
    """
    payload = {"v": CACHE_VERSION, "product": "muhurta-report", "purpose": purpose, "language": language,
               "from": start.isoformat(), "to": end.isoformat(),
               "place": {"lat": round(float(place["lat"]), 4), "lon": round(float(place["lon"]), 4),
                         "tz": place.get("tz") or "Asia/Kolkata"},
               # Tara bala and chandra bala are personal, so two people asking for the same dates get
               # DIFFERENT documents. Leaving the birth out of the id would hand the second one the first
               # one's PDF out of the cache.
               "birth": None if not birth else {"n": birth.get("nakshatra_index"),
                                                "m": birth.get("moon_sign_index")}}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:32]


# "4 house from your Moon" is not a thing anybody writes. English needs its own suffix because
# `rashifal.i18n.ordinal` returns a bare number for English - the rashifal prose writes the suffix itself,
# and a line like this one has no prose around it to do that.
_EN_SUFFIX = {1: "st", 2: "nd", 3: "rd"}


def _ordinal(house: int, language: str) -> str:
    if language == "en":
        return f"{house}{_EN_SUFFIX.get(house, 'th')}"
    from app.rashifal.i18n import ordinal

    return ordinal(house, language)


def _place_label(place: dict) -> str:
    # `city` as well as `name`: the order model calls it one thing and the chart form the other, and a
    # report headed "18.52, 73.86" instead of "Pune" is the kind of wrong that nobody reports.
    return place.get("name") or place.get("city") or f"{float(place['lat']):.2f}, {float(place['lon']):.2f}"


def _time_only(stamp: str) -> str:
    return stamp[11:16]


def build(purpose: str, language: str, start: dt.date, end: dt.date, place: dict, limit: int = 5,
          birth: dict | None = None) -> dict:
    """The full report dict, in the same shape as a written one. No model is called.

    FIVE dates and two backups rather than everything that passed: a list of forty dates is not a choice,
    it is a spreadsheet. The backups are real passing dates found the same way, not near misses.
    """
    if language not in _LANGS:
        raise ValueError(f"unknown language {language!r}")
    result = muhurta.find(purpose, start, end, place, limit=limit, birth=birth)
    rule = muhurta.purposes()[purpose]
    label = rule.get(language) or rule["en"]
    place_label = _place_label(place)
    field = {key: value[language] for key, value in _FIELD.items()}

    def deva(block: dict, key: str = "devanagari") -> str:
        return (block.get(key) if language != "en" else None) or block["name"]

    def window_text(day: dict) -> str:
        return ", ".join(f"{_time_only(w['from'])}-{_time_only(w['to'])}" for w in day["clear_windows"]) or "-"

    header = list(_ROW[language])
    rows = [[day["date"], day["vara"]["devanagari"] if language != "en" else day["vara"]["key"],
             window_text(day),
             deva(day["tithi"]), deva(day["nakshatra"]), deva(day["yoga"])]
            for day in result["days"]]

    summary = _FOUND[language].format(found=result["found"], searched=result["searched_days"],
                                      start=start.isoformat(), end=end.isoformat(), place=place_label)

    def detail_for(day: dict) -> dict:
        """One date in full: the windows, the bands it avoids, and every rule it passed and failed."""
        lines = [
            f"{field['window']}: {window_text(day)}",
            f"{field['rahu']}: {_time_only(day['rahu_kaal']['from'])}-{_time_only(day['rahu_kaal']['to'])}"
            f" | {field['yama']}: {_time_only(day['yamaganda']['from'])}-{_time_only(day['yamaganda']['to'])}"
            f" | {field['abhijit']}: {_time_only(day['abhijit']['from'])}-{_time_only(day['abhijit']['to'])}"
            + (f" {field['void']}" if day["abhijit"]["void"] else ""),
            f"{header[3]}: {deva(day['tithi']['paksha'])} {deva(day['tithi'])}"
            f" | {header[4]}: {deva(day['nakshatra'])} | {field['yoga']}: {deva(day['yoga'])}"
            f" | {header[1]}: {day['vara']['devanagari'] if language != 'en' else day['vara']['key']}",
        ]
        personal = day.get("personal")
        if personal:
            lines.append(
                f"{field['tara']}: {deva(personal['tara'])} "
                f"({_VERDICT[personal['tara']['verdict']][language]})"
                f" | {field['chandra']}: {_ordinal(personal['chandra']['house'], language)} {field['house']} "
                f"({_VERDICT[personal['chandra']['verdict']][language]})")
        lines.append(f"{field['passed']}: {', '.join(day.get('passed') or []) or field['none']}")
        lines.append(f"{field['failed']}: {', '.join(day.get('failed') or []) or field['none']}")
        return {"heading": f"{day['date']} "
                           f"({day['vara']['devanagari'] if language != 'en' else day['vara']['key']})",
                "paragraphs": lines}

    dates_section = {
        "id": "dates",
        "heading": f"{_HEADINGS['dates'][language]} - {label}",
        "paragraphs": [summary] + ([] if result["found"] else [_NONE_FOUND[language]]),
        "bullets": [], "subsections": [],
        "table": {"columns": header, "rows": rows} if rows else None,
    }
    how_paragraphs = [_HOW[language]]
    if birth:
        how_paragraphs.append(_WITH_BIRTH[language])
    if result["searched_days"] < (end - start).days + 1:
        how_paragraphs.append(_STOPPED_EARLY[language])
    how_paragraphs.append(BASIS[language])
    how_section = {
        "id": "how", "heading": _HEADINGS["how"][language], "paragraphs": how_paragraphs,
        "bullets": [], "subsections": [], "table": None,
    }
    panchang_section = {
        "id": "panchang", "heading": _HEADINGS["panchang"][language], "paragraphs": [], "bullets": [],
        "subsections": [detail_for(day) for day in result["days"]], "table": None,
    }
    sections = [dates_section, how_section, panchang_section]
    if result.get("backups"):
        sections.append({
            "id": "backups", "heading": _HEADINGS["backups"][language], "paragraphs": [], "bullets": [],
            "subsections": [detail_for(day) for day in result["backups"]], "table": None,
        })

    return {
        "id": report_id(purpose, language, start, end, place, birth),
        "product": "muhurta-report",
        "product_name": TITLE[language],
        "language": language,
        "title": f"{TITLE[language]} - {label}",
        "summary": summary,
        "sections": sections,
        "remedies": [],
        "disclaimer": BASIS[language],
        "data": {"muhurta": result, "purpose": purpose, "place": place},
        "meta": {
            "model": None,              # none was used, and saying so is the point
            "as_of": dt.date.today().isoformat(),
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "engine_only": True,
            "usage": {}, "cost_estimate_usd": 0.0, "cost_estimate_inr": 0.0,
            "checks": {"clean": True, "redactions": [], "warnings": [], "rejected_drafts": [],
                       "spelling_fixes": []},
        },
    }
