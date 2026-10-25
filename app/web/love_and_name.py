"""Two pages the demand data asked for: love rashifal per sign, and rashi from a name.

LOVE RASHIFAL COSTS NOTHING EXTRA, which is the point of how it is built. Every reading already contains
a relationships section - it is one of the three the model writes every time - and these pages show that
section on its own, for one sign, with the transit reasons behind it. No second AI call, no new daily
spend. The measured cost of ADDING a separate love paragraph instead would be about Rs 79 a month for a
daily refresh or Rs 11 for weekly only, and that is a decision to take deliberately rather than by
accident.

RASHI FROM A NAME is the traditional namakshar method and the page says so in the first line. The first
syllable of a name maps to a nakshatra pada, and the pada to a Moon sign. It is what a family uses when
naming a child, and it is NOT a birth chart: anybody whose name was chosen for any other reason - which
is most people - gets an answer that is about their name and nothing else.
"""
from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse

from app.engine import namakshar
from app.web import i18n

NAME_COPY = {
    "en": {
        # "rashi on names" is ~50,000 a month and is an ungrammatical query form - people
        # searching "rashi based on name". The title targets the natural phrasing rather than
        # printing the broken one, which would read as machine-written to every reader who saw it.
        "title": "Rashi by Name: Find Your Rashi Based on Your Name",
        "h1": "Find your rashi from your name",
        "intro": "The traditional namakshar method: the first syllable of a name belongs to one of the "
                 "108 nakshatra padas, and each pada falls in a Moon sign. This is how families pick a "
                 "name AFTER a chart is cast - so read it the right way round.",
        "honest": "This tells you what your NAME says, not what your chart says. If your name was "
                  "chosen for any other reason - and most are - the answer below is about the name "
                  "only. For your actual rashi, use your birth date, time and place.",
        "label": "Your name", "submit": "Find the rashi", "result": "What this name gives",
        "syllable": "First syllable", "nakshatra": "Nakshatra", "pada": "Pada", "rashi": "Moon sign",
        "real": "Get your real rashi from your birth details",
        "unknown": "That name could not be read. Try the spelling you would use in Devanagari, or use "
                   "your birth details instead.",
    },
    "hi": {
        "title": "नाम से राशि कैसे जानें | Rashi by Name in Hindi",
        "h1": "नाम से राशि जानिए",
        "intro": "पारंपरिक नामाक्षर पद्धति: नाम का पहला अक्षर 108 नक्षत्र पादों में से किसी एक का "
                 "होता है, और हर पाद किसी न किसी चंद्र राशि में पड़ता है। परिवार कुंडली बनने के "
                 "बाद इसी से नाम चुनते हैं - इसलिए इसे सही दिशा में पढ़िए।",
        "honest": "यह बताता है कि आपका नाम क्या कहता है, आपकी कुंडली क्या कहती है यह नहीं। अगर नाम "
                  "किसी और कारण से रखा गया - और अधिकतर नाम ऐसे ही होते हैं - तो नीचे का उत्तर केवल "
                  "नाम के बारे में है। असली राशि के लिए जन्म तिथि, समय और स्थान चाहिए।",
        "label": "आपका नाम", "submit": "राशि जानिए", "result": "इस नाम से क्या निकलता है",
        "syllable": "पहला अक्षर", "nakshatra": "नक्षत्र", "pada": "पाद", "rashi": "चंद्र राशि",
        "real": "जन्म विवरण से अपनी असली राशि जानिए",
        "unknown": "यह नाम पढ़ा नहीं जा सका। देवनागरी वर्तनी आज़माइए, या जन्म विवरण का उपयोग कीजिए।",
    },
    "mr": {
        "title": "नावावरून रास कशी ओळखावी | Rashi by Name Marathi",
        "h1": "नावावरून रास जाणून घ्या",
        "intro": "पारंपरिक नामाक्षर पद्धत: नावाचे पहिले अक्षर 108 नक्षत्र चरणांपैकी एकाचे असते, आणि "
                 "प्रत्येक चरण कोणत्या ना कोणत्या चंद्रराशीत येते. पत्रिका झाल्यावर कुटुंब याच "
                 "पद्धतीने नाव ठेवते - म्हणून हे योग्य दिशेने वाचा.",
        "honest": "हे तुमचे नाव काय सांगते ते सांगते, तुमची पत्रिका काय सांगते ते नाही. नाव दुसऱ्या "
                  "कारणाने ठेवले असेल - आणि बहुतेक नावे तशीच असतात - तर खालचे उत्तर फक्त नावाबद्दल "
                  "आहे. खऱ्या राशीसाठी जन्मतारीख, वेळ आणि ठिकाण लागते.",
        "label": "तुमचे नाव", "submit": "रास पाहा", "result": "या नावावरून काय निघते",
        "syllable": "पहिले अक्षर", "nakshatra": "नक्षत्र", "pada": "चरण", "rashi": "चंद्र रास",
        "real": "जन्मतपशिलावरून तुमची खरी रास पाहा",
        "unknown": "हे नाव वाचता आले नाही. देवनागरी शुद्धलेखन वापरून पाहा, किंवा जन्मतपशील वापरा.",
    },
}


def name_view(name: str, lang: str) -> dict | None:
    try:
        found = namakshar.from_name(name)
    except Exception:  # noqa: BLE001 - an unreadable name is an answer, not an error
        return None
    if not found or not found.get("moon_sign"):
        return None
    deva = lang in ("hi", "mr")
    return {
        "name": found["name"],
        "syllable": found["syllable"],
        "nakshatra": found["nakshatra"]["devanagari"] if deva else found["nakshatra"]["name"],
        "pada": found["pada"],
        "rashi": found["moon_sign"]["devanagari"] if deva else found["moon_sign"]["name"],
        "rashi_slug": found["moon_sign"]["slug"],
        "confidence": found.get("confidence", ""),
    }


LOVE_COPY = {
    "en": {"title": "{rashi} Love Horoscope Today - Relationships",
           "h1": "{rashi} love rashifal",
           "intro": "What today's sky says about relationships for {rashi}, from the same transit "
                    "reading as the full horoscope - the relationships section on its own.",
           "heading": "Relationships today", "none": "Today's reading is being prepared.",
           "full": "Read the full {rashi} horoscope", "ask": "Ask about YOUR {rashi} relationships",
           # THE MOST RELEVANT LINK ON THIS PAGE and it was not here. Somebody reading a love
           # horoscope is the closest thing to a matching visitor this site has; until now the only
           # route from here to the matching tool was the nav, the same on every page.
           "match": "Matching two charts? Check all 36 gunas free"},
    "hi": {"title": "{rashi} लव राशिफल आज - रिश्ते और प्रेम",
           "h1": "{rashi} लव राशिफल",
           "intro": "आज का आकाश {rashi} के रिश्तों के बारे में क्या कहता है - वही गोचर पाठ, उसका "
                    "रिश्तों वाला हिस्सा अलग से।",
           "heading": "आज रिश्ते", "none": "आज का राशिफल तैयार हो रहा है।",
           "full": "{rashi} का पूरा राशिफल पढ़िए", "ask": "अपने {rashi} रिश्तों के बारे में पूछिए",
           "match": "दो कुंडलियाँ मिलानी हैं? 36 गुण मुफ़्त जाँचिए"},
    "mr": {"title": "{rashi} प्रेम राशीभविष्य आज - नाती",
           "h1": "{rashi} प्रेम राशिभविष्य",
           "intro": "आजचे आकाश {rashi} च्या नात्यांबद्दल काय सांगते - तेच गोचर वाचन, त्यातला "
                    "नात्यांचा भाग वेगळा.",
           "heading": "आज नाती", "none": "आजचे राशिभविष्य तयार होत आहे.",
           "full": "{rashi} चे संपूर्ण राशिभविष्य वाचा", "ask": "तुमच्या {rashi} नात्यांबद्दल विचारा",
           "match": "दोन पत्रिका जुळवायच्या आहेत? 36 गुण मोफत तपासा"},
}


def add_routes(router, page_context, respond, _json_ld) -> None:
    for lang in i18n.PAGES["rashi-by-name"]:
        _add_name(router, page_context, respond, _json_ld, lang)
    for lang in i18n.PAGES["love-rashifal"]:
        for rashi in i18n.RASHI_KEYS:
            _add_love(router, page_context, respond, _json_ld, lang, rashi)


def _add_name(router, page_context, respond, _json_ld, lang: str) -> None:
    async def name_submit(request: Request):
        from urllib.parse import parse_qs

        raw = (await request.body()).decode("utf-8", "replace")
        form = {k: v[0] for k, v in parse_qs(raw, keep_blank_values=True).items()}
        context = _name_context(page_context, _json_ld, lang)
        context["found"] = name_view(form.get("name", ""), lang)
        context["asked"] = bool(form.get("name", "").strip())
        return respond(request, "rashi_by_name.html", context)

    def name_page(request: Request):
        return respond(request, "rashi_by_name.html", _name_context(page_context, _json_ld, lang))

    path = i18n.url_for("rashi-by-name", lang)
    router.add_api_route(path, name_page, methods=["GET"], response_class=HTMLResponse,
                         name=f"rashi-by-name-{lang}")
    router.add_api_route(path, name_submit, methods=["POST"], response_class=HTMLResponse,
                         name=f"rashi-by-name-post-{lang}")


def _name_context(page_context, _json_ld, lang: str) -> dict:
    from app.web import seo as _seo

    words = NAME_COPY[lang]
    context = page_context("rashi-by-name", lang)
    path = i18n.url_for("rashi-by-name", lang)
    context.update(words=words, found=None, asked=False, title=words["title"],
                   # Breadcrumbs as well as the WebApplication block: every indexable page on this site
                   # carries them, and the i18n test checks the first crumb points at that tree's home.
                   json_ld=[_json_ld(_seo.web_application(words["h1"], path, words["intro"],
                                                          i18n.HTML_LANG[lang])),
                            _json_ld(_seo.breadcrumbs([(context["ui"]["home"],
                                                        i18n.url_for("home", lang)),
                                                       (words["h1"], path)]))])
    return context


def _add_love(router, page_context, respond, _json_ld, lang: str, rashi: str) -> None:
    def love_page(request: Request):
        from app.rashifal import store
        from app.web import seo as _seo
        from app.web.rashifal import _reading

        names = i18n.rashi_names(rashi, lang)
        words = {key: value.format(rashi=names["rashi"]) for key, value in LOVE_COPY[lang].items()}
        stored = store.get_page(rashi, "today")
        reading = _reading(stored, lang) if stored else None
        # THE RELATIONSHIPS SECTION THE READING ALREADY HAS. No second AI call: this is the same text
        # the full horoscope shows, on its own page, for the query that asks for exactly it.
        love = None
        if reading:
            for section in reading["sections"]:
                if section["anchors"][0] == "relationships":
                    love = section
                    break
        context = page_context("love-rashifal", lang, rashi=rashi)
        path = i18n.url_for("love-rashifal", lang, rashi=rashi)
        context.update(words=words, love=love, title=words["title"],
                       match_href=i18n.url_for("matching", lang),
                       full_href=i18n.url_for("rashifal-reading", lang, rashi=rashi, period="today"),
                       ask_href=f'{i18n.url_for("consultation", lang)}?topic=relationships',
                       json_ld=[_json_ld(_seo.breadcrumbs(
                           [(context["ui"]["home"], i18n.url_for("home", lang)),
                            (words["h1"], path)]))])
        return respond(request, "love_rashifal.html", context)

    router.add_api_route(i18n.url_for("love-rashifal", lang, rashi=rashi), love_page, methods=["GET"],
                         response_class=HTMLResponse, name=f"love-{rashi}-{lang}")
