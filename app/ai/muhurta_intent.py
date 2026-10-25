"""Spotting a muhurta question in a consultation, and answering it from the engine.

DELIBERATELY HARD TO TRIGGER. The cost of a false positive is far higher than a miss: a reader who asked
about their marriage prospects and got a table of dates has been answered by the wrong feature, and will
reasonably conclude the astrologer did not read the question. So a message has to carry BOTH a word that
asks for a date - muhurta, shubh din, good day to - AND a purpose this finder actually knows. Either alone
is not enough, and "my marriage is not going well" matches neither.

The answer costs no model call, so it is delivered the way a screened reply is: recorded as an exchange,
counted by the rate limiter, and NOT charged against the free or paid message quota. Charging for
arithmetic we did not pay for would be the wrong way round.
"""

from __future__ import annotations

import datetime as dt
import re

from app.engine import muhurta

DEFAULT_RANGE_DAYS = 60
MAX_DATES_IN_CHAT = 5

# A word that asks WHEN. Without one of these, nothing here fires.
_WHEN_WORDS = {
    "en": ("muhurat", "muhurta", "muhurth", "auspicious date", "auspicious day", "auspicious time",
           "good date", "good day", "best date", "best day", "shubh din", "shubh muhurat", "when should i",
           "which date", "what date"),
    "hi": ("मुहूर्त", "शुभ दिन", "शुभ तारीख", "शुभ दिनांक", "कौन सा दिन", "कौन सी तारीख", "कब करें", "कब करना"),
    "mr": ("मुहूर्त", "शुभ दिवस", "चांगला दिवस", "कोणता दिवस", "कोणती तारीख", "कधी करावे", "केव्हा करावे"),
}

# ...and a purpose. The keys are the ids in muhurta_rules.json; a purpose that is not listed here simply
# cannot be reached from chat, which is the safe direction.
_PURPOSE_WORDS = {
    "griha-pravesh": ("griha pravesh", "grih pravesh", "gruha pravesh", "house warming", "housewarming",
                      "move into", "moving into", "new house", "new home", "new flat",
                      "गृह प्रवेश", "गृहप्रवेश", "नया घर", "नवीन घर", "नव्या घरात"),
    "vehicle": ("vehicle", "car", "bike", "scooter", "new vehicle", "buying a car", "buy a car",
                "वाहन", "गाड़ी", "कार", "गाडी", "दुचाकी"),
    "business": ("business", "shop", "office", "new work", "start work", "startup", "venture",
                 "व्यापार", "दुकान", "काम शुरू", "नया काम", "व्यवसाय", "नवा व्यवसाय", "दुकान सुरू"),
    "naming": ("naming", "namkaran", "name ceremony", "baby name", "नामकरण", "बारसे", "बारसं"),
    "travel": ("travel", "journey", "trip", "यात्रा", "सफर", "प्रवास"),
}


def detect(text: str) -> str | None:
    """The purpose this message is asking a date for, or None. Both halves must match."""
    lowered = (text or "").lower()
    if not any(word in lowered for words in _WHEN_WORDS.values() for word in words):
        return None
    for purpose, words in _PURPOSE_WORDS.items():
        if any(word in lowered for word in words):
            return purpose
    return None


_REFUSAL = {
    "en": "I do not pick dates for anything to do with health, surgery or the outcome of a case. A date "
          "chosen that way can delay a decision that should be made on medical advice.",
    "hi": "स्वास्थ्य, ऑपरेशन या किसी मुक़दमे के नतीजे के लिए मैं दिन नहीं निकालता। ऐसे चुना गया दिन उस फ़ैसले को "
          "टाल सकता है जो डॉक्टर की सलाह पर होना चाहिए।",
    "mr": "आरोग्य, शस्त्रक्रिया किंवा खटल्याच्या निकालासाठी मी दिवस काढत नाही. अशा प्रकारे निवडलेला दिवस "
          "डॉक्टरांच्या सल्ल्यावर घ्यायचा निर्णय लांबवू शकतो.",
}


def refusal_for(text: str, language: str) -> str | None:
    """A refusal when a date is asked for something this will not date. None otherwise.

    Spelled out rather than left to fall through to the model: the model does refuse health questions, but
    "muhurat for my operation" would reach it as an ordinary question and be answered as one. The reader
    asked a finder for a date; the finder should be the thing that says no.
    """
    lowered = (text or "").lower()
    if not any(word in lowered for words in _WHEN_WORDS.values() for word in words):
        return None
    try:
        muhurta.check_allowed(lowered)
    except muhurta.Refused:
        return _REFUSAL[language if language in _REFUSAL else "en"]
    return None


_LEAD = {
    "en": "{found} date(s) in the next {days} days for {label}, from the panchang at {place}:",
    "hi": "{place} के पंचांग से, अगले {days} दिनों में {label} के लिए {found} दिन:",
    "mr": "{place} च्या पंचांगानुसार, पुढच्या {days} दिवसांत {label} साठी {found} दिवस:",
}
_ROW = {
    "en": "{date} ({weekday}) - {tithi}, {nakshatra}. Avoid Rahu Kaal {rahu}.",
    "hi": "{date} ({weekday}) - {tithi}, {nakshatra}। राहु काल {rahu} टालें।",
    "mr": "{date} ({weekday}) - {tithi}, {nakshatra}. राहू काळ {rahu} टाळा.",
}
_NONE = {
    "en": "No day in the next {days} days satisfies the rule for {label}. I would rather say that than offer "
          "a date that does not.",
    "hi": "अगले {days} दिनों में {label} के लिए कोई दिन नियम पर खरा नहीं उतरता। ऐसा दिन देने से यह कहना बेहतर है।",
    "mr": "पुढच्या {days} दिवसांत {label} साठी एकही दिवस नियमात बसत नाही. न बसणारा दिवस देण्यापेक्षा हे सांगणे बरे.",
}
_BASIS = {
    "en": "This is arithmetic, not a guarantee - the panchang is computed, and which day suits a purpose is "
          "tradition.",
    "hi": "यह गणित है, गारंटी नहीं - पंचांग गणना से निकला है, और कौन सा दिन किस काम के लिए शुभ है यह परंपरा कहती है।",
    "mr": "हे गणित आहे, हमी नाही - पंचांग गणनेतून आले आहे, आणि कोणता दिवस कोणत्या कामाला योग्य हे परंपरा सांगते.",
}
_MORE = {
    "en": "There is a fuller search, with every date and its panchang, at {path}.",
    "hi": "हर तारीख़ और उसका पंचांग {path} पर देखा जा सकता है।",
    "mr": "प्रत्येक तारीख आणि तिचे पंचांग {path} इथे पाहता येईल.",
}


def answer(purpose: str, language: str, place: dict, today: dt.date | None = None) -> str:
    """The reply text. Engine only - every date and every time in it was computed, not written."""
    language = language if language in ("en", "hi", "mr") else "en"
    start = today or dt.date.today()
    end = start + dt.timedelta(days=DEFAULT_RANGE_DAYS)
    rule = muhurta.purposes()[purpose]
    label = rule.get(language) or rule["en"]
    result = muhurta.find(purpose, start, end, place, limit=MAX_DATES_IN_CHAT)
    place_label = place.get("name") or "the chart's place"
    path = "/muhurta" if language == "en" else f"/{language}/muhurta"

    if not result["found"]:
        return "\n\n".join([_NONE[language].format(days=DEFAULT_RANGE_DAYS, label=label), _BASIS[language]])

    lines = [_LEAD[language].format(found=result["found"], days=DEFAULT_RANGE_DAYS, label=label,
                                    place=place_label)]
    for day in result["days"]:
        lines.append(_ROW[language].format(
            date=day["date"],
            weekday=day["vara"]["key"] if language == "en" else day["vara"]["devanagari"],
            tithi=(f"{day['tithi']['paksha']['name']} {day['tithi']['name']}" if language == "en"
                   else f"{day['tithi']['paksha']['devanagari']} {day['tithi']['devanagari']}"),
            nakshatra=(day["nakshatra"]["name"] if language == "en"
                       else (day["nakshatra"].get("devanagari") or day["nakshatra"]["name"])),
            rahu=f"{day['rahu_kaal']['from'][11:16]}-{day['rahu_kaal']['to'][11:16]}"))
    return "\n".join(lines) + "\n\n" + _BASIS[language] + " " + _MORE[language].format(path=path)
