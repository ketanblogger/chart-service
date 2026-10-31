"""The "shaadi kab hogi" page: what the chart favours, as periods, never as a date.

THE PROMISE THIS PAGE MAKES IS A NEGATIVE ONE, and it is the whole design. "meri shadi kab hogi" is
asked 50,000 times a month by people who want a date, and a chart cannot give one. What classical
practice times is a supportive PERIOD - a dasha of a lord connected to the seventh house, a Jupiter
transit over it - and periods are what this returns, in the reader's own language, with the reason
beside each one.

Every string that could read as a promise is absent by construction rather than by review: the copy has
no future-tense claim about the reader's life in it, and a test asserts that the words for "will happen",
"guaranteed" and a bare year never appear as a prediction.
"""
from __future__ import annotations

import datetime as dt

from fastapi import Request
from fastapi.responses import HTMLResponse

from app.web import i18n

COPY = {
    "en": {
        "title": "When Will I Get Married? Your Chart's Answer",
        "h1": "When will I get married?",
        # Doubles as the meta description, which is capped at 230 characters.
        "intro": "A birth chart does not hold a wedding date. It holds the seventh house, its lord, "
                 "Venus and Jupiter, and the periods tradition reads as supportive. This page shows "
                 "those periods and why each is on the list.",
        "honest": "No chart can name the day, and anyone who gives you one is guessing. What follows "
                  "are tendencies and windows.",
        "what_chart_says": "What your chart says about marriage",
        "seventh": "Seventh house", "lord": "Its lord", "karaka": "Significators",
        "in_house": "in house", "occupants": "Planets in the seventh",
        "windows": "Supportive periods in the next three years",
        "strong": "Strongly supportive", "supportive": "Supportive",
        "because": "because", "none": "No strongly supportive dasha period falls in the next three "
                                      "years. That is a statement about timing, not about whether it "
                                      "happens.",
        "transits": "Jupiter's movement",
        "transit_line": "Jupiter enters {sign} on {date}, moving over {over}. It stays about a year, and "
                        "can step back over it once while retrograde.",
        "no_transit": "Jupiter does not reach your seventh house or your lagna in the next three years.",
        "ask": "Ask the AI astrologer about your own chart",
        "form_heading": "Your birth details",
        "mahadasha": "Mahadasha", "antardasha": "Antardasha",
        "mahadasha": "महादशा", "antardasha": "अंतर्दशा",
        "mahadasha": "महादशा", "antardasha": "अंतर्दशा",
        "caveat": "Astrology is a traditional, faith-based practice. Use this alongside your own "
                  "judgement, never instead of it.",
    },
    "hi": {
        "title": "मेरी शादी कब होगी? कुंडली से समय",
        "h1": "मेरी शादी कब होगी?",
        "intro": "कुंडली में शादी की तारीख़ नहीं लिखी होती। उसमें सातवाँ भाव, उसका स्वामी, शुक्र और गुरु "
                 "होते हैं, और वे समय होते हैं जिनमें परंपरा इन्हें बल में मानती है। यह पन्ना वही समय "
                 "दिखाता है, और हर एक के साथ कारण भी।",
        "honest": "कोई कुंडली दिन नहीं बता सकती, और जो बता दे वह अनुमान लगा रहा है। आगे जो है वह "
                  "प्रवृत्तियाँ और समय-खिड़कियाँ हैं।",
        "what_chart_says": "आपकी कुंडली विवाह के बारे में क्या कहती है",
        "seventh": "सातवाँ भाव", "lord": "भावेश", "karaka": "कारक",
        "in_house": "भाव में", "occupants": "सातवें भाव में ग्रह",
        "windows": "अगले तीन साल के अनुकूल समय",
        "strong": "विशेष अनुकूल", "supportive": "अनुकूल",
        "because": "क्योंकि", "none": "अगले तीन साल में कोई विशेष अनुकूल दशा नहीं पड़ती। यह समय के बारे "
                                      "में कथन है, इस बारे में नहीं कि विवाह होगा या नहीं।",
        "transits": "गुरु का गोचर",
        "transit_line": "गुरु {date} को {sign} में आते हैं, {over} पर से होकर। वे लगभग एक वर्ष रहते हैं, "
                        "और वक्री होकर एक बार लौट भी सकते हैं।",
        "no_transit": "अगले तीन साल में गुरु आपके सातवें भाव या लग्न तक नहीं पहुँचते।",
        "ask": "अपनी कुंडली के बारे में AI ज्योतिषी से पूछिए",
        "form_heading": "आपका जन्म विवरण",
        "caveat": "ज्योतिष एक पारंपरिक, आस्था-आधारित विद्या है। इसे अपने विवेक के साथ देखिए, उसकी जगह नहीं।",
        "mahadasha": "महादशा", "antardasha": "अंतर्दशा",
    },
    "mr": {
        "title": "माझे लग्न कधी होईल? पत्रिकेतून वेळ",
        "h1": "माझे लग्न कधी होईल?",
        "intro": "पत्रिकेत लग्नाची तारीख लिहिलेली नसते. तिच्यात सातवे स्थान, त्याचा स्वामी, शुक्र आणि "
                 "गुरू असतात, आणि ते काळ असतात ज्यांत परंपरा त्यांना बलवान मानते. हे पान तेच काळ "
                 "दाखवते, प्रत्येकामागचे कारण देऊन.",
        "honest": "कोणतीही पत्रिका दिवस सांगू शकत नाही, आणि जो सांगतो तो अंदाज लावतो आहे. पुढे "
                  "प्रवृत्ती आणि अनुकूल काळ आहेत.",
        "what_chart_says": "तुमची पत्रिका विवाहाबद्दल काय सांगते",
        "seventh": "सातवे स्थान", "lord": "स्थानाधिपती", "karaka": "कारक",
        "in_house": "स्थानात", "occupants": "सातव्या स्थानातील ग्रह",
        "windows": "पुढील तीन वर्षांतील अनुकूल काळ",
        "strong": "विशेष अनुकूल", "supportive": "अनुकूल",
        "because": "कारण", "none": "पुढील तीन वर्षांत विशेष अनुकूल दशा येत नाही. हे काळाबद्दलचे विधान "
                                   "आहे, विवाह होईल की नाही याबद्दल नाही.",
        "transits": "गुरूचे गोचर",
        "transit_line": "गुरू {date} रोजी {sign} राशीत येतो, {over} वरून जात. तो सुमारे वर्षभर राहतो, "
                        "आणि वक्री होऊन एकदा परत येऊ शकतो.",
        "no_transit": "पुढील तीन वर्षांत गुरू तुमच्या सातव्या स्थानात किंवा लग्नात पोहोचत नाही.",
        "ask": "तुमच्या पत्रिकेबद्दल AI ज्योतिषाला विचारा",
        "form_heading": "तुमचा जन्मतपशील",
        "caveat": "ज्योतिष ही पारंपरिक, श्रद्धेवर आधारित विद्या आहे. ती तुमच्या विवेकासोबत पाहा, "
                  "त्याच्या जागी नाही.",
        "mahadasha": "महादशा", "antardasha": "अंतर्दशा",
    },
}


def _graha(key: str, lang: str) -> str:
    """A graha in the page's own language. The engine speaks in keys ("Mars"); a Hindi page must not."""
    from app.engine.constants import graha_name

    if not key:
        return ""
    names = graha_name(key)
    if lang in ("hi", "mr"):
        return names.get("devanagari") or names.get("name") or key
    return f'{names.get("name", key)} ({key})' if names.get("name") != key else key


def _sign(sign: dict | None, lang: str) -> str:
    if not sign:
        return ""
    return (sign.get("devanagari") if lang in ("hi", "mr") else sign.get("name")) or sign.get("name", "")


def view(chart: dict, lang: str, today: dt.date | None = None) -> dict:
    """The page's view model from a computed chart. Pure: no request, no network, easy to test."""
    from app.engine.timing import indications, transit_openings, windows

    words = COPY[lang]
    today = today or dt.date.today()
    facts = indications(chart, "marriage")
    found = windows(chart, "marriage", today=today)
    # ONE OPENING PER SIGN. Jupiter can enter a sign, retrograde out and come back, which produced three
    # "openings" for one arrival and reads as three separate chances. The first entry is the opening; the
    # line says it stays about a year and can step back, which is the truth without the triplication.
    openings, seen = [], set()
    for entry in transit_openings(chart, "marriage", today=today):
        if entry["sign"] in seen:
            continue
        seen.add(entry["sign"])
        openings.append({"text": words["transit_line"].format(
            sign=entry["sign"], date=entry["from"].strftime("%-d %b %Y"), over=entry["over"])})
    # THE REASONS ARE REBUILT IN THE PAGE'S LANGUAGE. The engine returns them as "mahadasha of Mars",
    # which is the right thing for an engine to return and the wrong thing to print on a Hindi page.
    def why(window) -> str:
        parts = []
        for reason in window.reasons:
            level, _, key = reason.partition(" of ")
            label = words["mahadasha"] if level == "mahadasha" else words["antardasha"]
            parts.append(f"{label}: {_graha(key, lang)}")
        return " · ".join(parts)

    return {
        "seventh": _sign(facts["sign"], lang),
        "lord": _graha(facts["lord"], lang), "lord_house": facts["lord_house"],
        "occupants": [_graha(g, lang) for g in facts["occupants"]],
        "karakas": [{"graha": _graha(k["graha"], lang), "house": k["house"]} for k in facts["karakas"]],
        "windows": [{"from": w.start.strftime("%b %Y"), "to": w.end.strftime("%b %Y"),
                     "strength": words[w.strength], "why": why(w)} for w in found],
        "openings": openings,
    }


def add_routes(router, page_context, respond, _json_ld) -> None:
    for lang in i18n.PAGES["marriage-timing"]:
        _add(router, page_context, respond, _json_ld, lang)


def _chart_from(form, lang: str):
    """A chart from the submitted birth details, or (None, error-key) if they are not usable."""
    import datetime as _dt

    from app.engine.cities import find_city

    try:
        birth_date = _dt.date.fromisoformat((form.get("date") or "").strip())
        clock = (form.get("time") or "").strip()
        birth_time = _dt.time.fromisoformat(clock) if clock else _dt.time(12, 0)
    except ValueError:
        return None, "date"
    city = find_city((form.get("city") or "").strip())
    if not city:
        return None, "city"
    from app.engine.chart import compute_chart

    return compute_chart(birth_date, birth_time, city["lat"], city["lon"], city["tz"]), None


def _add(router, page_context, respond, _json_ld, lang: str) -> None:
    async def marriage_submit(request: Request):
        """POST, NOT GET, AND THAT IS THE POINT. A birth date, a time and a city in a query string end up
        in the server log, in the browser history and in the Referer header of every link the reader
        clicks next. The panchang picker is a GET form because a city and a date are not a person; this
        one is a POST because together they are."""
        # PARSED FROM THE RAW BODY, not via request.form(). Starlette's form() pulls in python-multipart,
        # and a plain HTML form without enctype posts application/x-www-form-urlencoded - which the
        # standard library has parsed since forever. A new runtime dependency for one form, which then
        # has to be installed on the VPS before this page works, is a worse trade than four lines.
        from urllib.parse import parse_qs

        raw = (await request.body()).decode("utf-8", "replace")
        form = {key: values[0] for key, values in parse_qs(raw, keep_blank_values=True).items()}
        chart, problem = _chart_from(form, lang)
        context = _base_context(page_context, _json_ld, lang)
        if chart is None:
            context["problem"] = problem
        else:
            context["result"] = view(chart, lang)
        return respond(request, "marriage_timing.html", context)

    def marriage_page(request: Request):
        return respond(request, "marriage_timing.html", _base_context(page_context, _json_ld, lang))

    router.add_api_route(i18n.url_for("marriage-timing", lang), marriage_page, methods=["GET"],
                         response_class=HTMLResponse, name=f"marriage-timing-{lang}")
    router.add_api_route(i18n.url_for("marriage-timing", lang), marriage_submit, methods=["POST"],
                         response_class=HTMLResponse, name=f"marriage-timing-post-{lang}")


def _base_context(page_context, _json_ld, lang: str) -> dict:
    from app.web import pages as _pages
    from app.web import seo as _seo

    words = COPY[lang]
    context = page_context("marriage-timing", lang)
    path = i18n.url_for("marriage-timing", lang)
    context.update(
        words=words, copy=_pages.get("kundali", lang), result=None, problem=None,
        json_ld=[_json_ld(_seo.web_application(words["h1"], path, words["intro"],
                                               i18n.HTML_LANG[lang])),
                 _json_ld(_seo.breadcrumbs([(context["ui"]["home"], i18n.url_for("home", lang)),
                                            (words["h1"], path)]))])
    return context
