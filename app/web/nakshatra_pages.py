"""One page per nakshatra, in three trees: 81 pages, written once, with no AI on the path.

Each page is the specific thing plus the shared framing - what a nakshatra IS, how the padas work, what
gandmool means - because a reader arriving at "mool nakshatra in hindi" has usually never been told the
general part either, and a page that gives only the specific paragraph is a page that answers half.
"""
from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse

from app.engine.constants import nakshatra_info
from app.web import i18n
from app.web.nakshatra_data import BY_KEY, NAKSHATRAS

#: Shared framing, per language. The per-nakshatra paragraph is in nakshatra_copy_<lang>.py.
FRAME = {
    "en": {
        "title": "{name} Nakshatra: Meaning, Lord, Deity and Traits",
        "h1": "{name} nakshatra",
        "lead": "{name} ({devanagari}) is the {ordinal} of the twenty-seven nakshatras, ruled by "
                "{lord}.",
        "what_is": "What a nakshatra is",
        "what_is_body": (
            "Before the twelve-sign zodiac, India divided the sky into twenty-seven lunar mansions of "
            "13 degrees 20 minutes each - roughly one day of the Moon's travel. The nakshatras are "
            "older than the rashis and carry more specific meaning.",
            "The nakshatra the Moon occupied at your birth is your janma nakshatra. It is the most "
            "important single fact in a Vedic chart after the lagna: it gives the traditional first "
            "letter for naming a child, and it decides where your entire Vimshottari dasha sequence "
            "begins.",
        ),
        "facts": "The facts", "meaning": "What {name} means", "padas": "The four padas",
        "padas_body": "Every nakshatra divides into four padas of 3 degrees 20 minutes. Which pada the "
                      "Moon falls in refines the reading and decides the naming syllable - two people "
                      "with the same nakshatra and different padas are read differently.",
        "gandmool": "{name} and gandmool",
        "gandmool_body": (
            "{name} is one of the six gandmool nakshatras - the ones sitting at the junctions between "
            "the elemental groups. Tradition holds that a birth here calls for a shanti ritual in the "
            "first month.",
            "It is worth being plain about this, because it is one of the most reliable ways to "
            "frighten a new parent. Gandmool marks a JUNCTION, not a defect. The child is not cursed, "
            "the chart is not damaged, and anybody selling you an expensive remedy against it is "
            "selling fear. The ritual is traditional and inexpensive; the anxiety sold alongside it is "
            "neither.",
        ),
        "lord_label": "Ruling graha", "deity_label": "Deity", "symbol_label": "Symbol",
        "gana_label": "Gana", "number_label": "Number",
        "find": "Find your own nakshatra", "all": "All twenty-seven nakshatras",
        "ordinals": ("first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth",
                     "ninth", "tenth", "eleventh", "twelfth", "thirteenth", "fourteenth", "fifteenth",
                     "sixteenth", "seventeenth", "eighteenth", "nineteenth", "twentieth",
                     "twenty-first", "twenty-second", "twenty-third", "twenty-fourth",
                     "twenty-fifth", "twenty-sixth", "twenty-seventh"),
        "ganas": {"deva": "Deva (divine)", "manushya": "Manushya (human)",
                  "rakshasa": "Rakshasa (fierce)"},
    },
    "hi": {
        "title": "{devanagari} नक्षत्र ({name}): अर्थ, स्वामी और स्वभाव",
        "h1": "{devanagari} नक्षत्र - अर्थ और फल",
        "lead": "{name} ({devanagari}) सत्ताईस नक्षत्रों में {ordinal} है, स्वामी {lord}।",
        "what_is": "नक्षत्र होता क्या है",
        "what_is_body": (
            "बारह राशियों से पहले भारत ने आकाश को सत्ताईस नक्षत्रों में बाँटा - हर एक 13 अंश 20 कला, "
            "लगभग चंद्र की एक दिन की यात्रा। नक्षत्र राशियों से पुराने हैं और अधिक विशिष्ट अर्थ रखते हैं।",
            "जन्म के समय चंद्र जिस नक्षत्र में था वह आपका जन्म नक्षत्र है। लग्न के बाद यह कुंडली का "
            "सबसे महत्वपूर्ण तथ्य है: इसी से नामकरण का पारंपरिक अक्षर आता है, और इसी से तय होता है कि "
            "आपकी पूरी विंशोत्तरी दशा कहाँ से शुरू होती है।",
        ),
        "facts": "तथ्य", "meaning": "{devanagari} नक्षत्र का अर्थ", "padas": "चार पाद",
        "padas_body": "हर नक्षत्र 3 अंश 20 कला के चार पादों में बँटा है। चंद्र किस पाद में है इससे "
                      "पाठ और सूक्ष्म होता है और नामाक्षर तय होता है - एक ही नक्षत्र पर अलग पाद वाले "
                      "दो लोग अलग पढ़े जाते हैं।",
        "gandmool": "{devanagari} और गंडमूल",
        "gandmool_body": (
            "{devanagari} छह गंडमूल नक्षत्रों में से है - वे जो तत्वों की संधि पर पड़ते हैं। परंपरा कहती है "
            "कि यहाँ जन्म होने पर पहले महीने में शांति विधान कराया जाए।",
            "इस बारे में स्पष्ट रहना ज़रूरी है, क्योंकि नए माता-पिता को डराने का यह सबसे कारगर तरीक़ा "
            "है। गंडमूल एक संधि बताता है, दोष नहीं। बच्चा शापित नहीं है, कुंडली बिगड़ी नहीं है, और जो "
            "इसके विरुद्ध महँगा उपाय बेचे वह डर बेच रहा है। विधान पारंपरिक और सस्ता है; साथ में बेची "
            "जाने वाली चिंता नहीं।",
        ),
        "lord_label": "स्वामी ग्रह", "deity_label": "देवता", "symbol_label": "प्रतीक",
        "gana_label": "गण", "number_label": "क्रम",
        "find": "अपना नक्षत्र जानिए", "all": "सत्ताईसों नक्षत्र",
        "ordinals": tuple(f"{n}वाँ" for n in ("पहला", "दूसरा", "तीसरा", "चौथा", "पाँचवाँ", "छठा",
                                              "सातवाँ", "आठवाँ", "नौवाँ", "दसवाँ", "ग्यारहवाँ",
                                              "बारहवाँ", "तेरहवाँ", "चौदहवाँ", "पंद्रहवाँ",
                                              "सोलहवाँ", "सत्रहवाँ", "अठारहवाँ", "उन्नीसवाँ",
                                              "बीसवाँ", "इक्कीसवाँ", "बाईसवाँ", "तेईसवाँ",
                                              "चौबीसवाँ", "पच्चीसवाँ", "छब्बीसवाँ", "सत्ताईसवाँ")),
        "ganas": {"deva": "देव", "manushya": "मनुष्य", "rakshasa": "राक्षस"},
    },
    "mr": {
        "title": "{devanagari} नक्षत्र ({name}): अर्थ, स्वामी आणि स्वभाव",
        "h1": "{devanagari} नक्षत्र - अर्थ आणि फल",
        "lead": "{name} ({devanagari}) हे सत्तावीस नक्षत्रांपैकी {ordinal} आहे, स्वामी {lord}.",
        "what_is": "नक्षत्र म्हणजे काय",
        "what_is_body": (
            "बारा राशींच्या आधी भारताने आकाश सत्तावीस नक्षत्रांत वाटले - प्रत्येक 13 अंश 20 कला, "
            "म्हणजे चंद्राचा सुमारे एका दिवसाचा प्रवास. नक्षत्रे राशींपेक्षा जुनी आहेत.",
            "जन्मावेळी चंद्र ज्या नक्षत्रात होता ते तुमचे जन्मनक्षत्र. लग्नानंतरचे हे पत्रिकेतील "
            "सर्वात महत्त्वाचे तथ्य आहे: त्यावरून नामकरणाचे पारंपरिक अक्षर येते, आणि तुमची संपूर्ण "
            "विंशोत्तरी दशा कुठून सुरू होते हे ठरते.",
        ),
        "facts": "तथ्ये", "meaning": "{devanagari} नक्षत्राचा अर्थ", "padas": "चार चरणे",
        "padas_body": "प्रत्येक नक्षत्र 3 अंश 20 कलांच्या चार चरणांत विभागले आहे. चंद्र कोणत्या "
                      "चरणात आहे यावरून वाचन अधिक नेमके होते आणि नामाक्षर ठरते.",
        "gandmool": "{devanagari} आणि गंडमूळ",
        "gandmool_body": (
            "{devanagari} हे सहा गंडमूळ नक्षत्रांपैकी एक आहे - जी तत्त्वांच्या संधीवर येतात. परंपरा सांगते "
            "की इथे जन्म झाल्यास पहिल्या महिन्यात शांती करावी.",
            "याबद्दल स्पष्ट बोलणे गरजेचे आहे, कारण नव्या पालकांना घाबरवण्याचा हा सर्वात परिणामकारक "
            "मार्ग आहे. गंडमूळ संधी दर्शवते, दोष नाही. मूल शापित नाही, पत्रिका बिघडलेली नाही, आणि "
            "याविरुद्ध महागडा उपाय विकणारा भीती विकतो आहे. शांती पारंपरिक आणि स्वस्त आहे; सोबत "
            "विकली जाणारी चिंता नाही.",
        ),
        "lord_label": "स्वामी ग्रह", "deity_label": "देवता", "symbol_label": "चिन्ह",
        "gana_label": "गण", "number_label": "क्रम",
        "find": "तुमचे नक्षत्र पाहा", "all": "सत्तावीस नक्षत्रे",
        "ordinals": ("पहिले", "दुसरे", "तिसरे", "चौथे", "पाचवे", "सहावे", "सातवे", "आठवे", "नववे",
                     "दहावे", "अकरावे", "बारावे", "तेरावे", "चौदावे", "पंधरावे", "सोळावे",
                     "सतरावे", "अठरावे", "एकोणिसावे", "विसावे", "एकविसावे", "बाविसावे",
                     "तेविसावे", "चोविसावे", "पंचविसावे", "सव्विसावे", "सत्ताविसावे"),
        "ganas": {"deva": "देव", "manushya": "मनुष्य", "rakshasa": "राक्षस"},
    },
}


def view(key: str, lang: str) -> dict:
    nakshatra = BY_KEY[key]
    engine = nakshatra_info(nakshatra.index - 1)
    words = FRAME[lang]
    return {
        "key": key,
        "name": engine["name"],
        "devanagari": engine["devanagari"],
        "lord": engine["lord"],
        "index": nakshatra.index,
        "ordinal": words["ordinals"][nakshatra.index - 1],
        "deity": nakshatra.deity,
        "symbol": nakshatra.symbol,
        "gana": words["ganas"][nakshatra.gana],
        "gandmool": nakshatra.gandmool,
    }



#: THE HUB. "nakshatras" is 50,000 searches a month and the twenty-seven pages had no front door -
#: which is also why the blog's link map could not use the word at all: it had nowhere single to
#: point. The short line per nakshatra is the FIRST SENTENCE of the meaning already written and
#: reviewed for its own page, not 27 new lines in three languages. One source, so the hub cannot
#: drift from what the page it links to actually says.
HUB = {
    "en": {
        "title": "Nakshatras: All 27 Lunar Mansions, Lords and Meanings",
        "h1": "The 27 nakshatras",
        "meta": ("All 27 nakshatras with their ruling planet, deity, symbol and meaning. The "
                 "nakshatra the Moon was in at your birth is your janma nakshatra - find yours from "
                 "your birth details, free."),
        "lead": ("India divided the sky into twenty-seven lunar mansions long before the twelve "
                 "signs. Each is 13 degrees 20 minutes wide - about one day of the Moon's travel - "
                 "and the one the Moon occupied at your birth is your janma nakshatra."),
        "table_heading": "All 27, in order",
        "cols": ("#", "Nakshatra", "Ruled by", "Deity", "Symbol"),
        "find_yours": "Find your nakshatra from your birth details",
    },
    "hi": {
        "title": "नक्षत्र: सभी 27 नक्षत्र, स्वामी और अर्थ",
        "h1": "सत्ताईस नक्षत्र",
        "meta": ("सभी 27 नक्षत्र - स्वामी ग्रह, देवता, प्रतीक और अर्थ के साथ। जन्म के समय चंद्रमा जिस नक्षत्र "
                 "में था वही आपका जन्म नक्षत्र है - अपने जन्म विवरण से मुफ़्त जानिए।"),
        "lead": ("बारह राशियों से बहुत पहले भारत ने आकाश को सत्ताईस नक्षत्रों में बाँटा था। हर नक्षत्र 13 अंश "
                 "20 कला का है - लगभग चंद्रमा की एक दिन की यात्रा - और जन्म के समय चंद्रमा जिसमें था, वही "
                 "आपका जन्म नक्षत्र है।"),
        "table_heading": "क्रम से सभी 27",
        "cols": ("क्रम", "नक्षत्र", "स्वामी", "देवता", "प्रतीक"),
        "find_yours": "अपने जन्म विवरण से अपना नक्षत्र जानिए",
    },
    "mr": {
        "title": "नक्षत्रे: सर्व 27 नक्षत्रे, स्वामी आणि अर्थ",
        "h1": "सत्तावीस नक्षत्रे",
        "meta": ("सर्व 27 नक्षत्रे - स्वामी ग्रह, देवता, चिन्ह आणि अर्थासह. जन्माच्या वेळी चंद्र ज्या नक्षत्रात "
                 "होता तेच तुमचे जन्मनक्षत्र - तुमच्या जन्मतपशिलांवरून मोफत पाहा."),
        "lead": ("बारा राशींच्या कितीतरी आधी भारताने आकाशाची सत्तावीस नक्षत्रांत विभागणी केली. प्रत्येक "
                 "नक्षत्र 13 अंश 20 कला रुंद आहे - चंद्राचा साधारण एका दिवसाचा प्रवास - आणि जन्माच्या वेळी "
                 "चंद्र ज्यात होता, तेच तुमचे जन्मनक्षत्र."),
        "table_heading": "क्रमाने सर्व 27",
        "cols": ("क्रम", "नक्षत्र", "स्वामी", "देवता", "चिन्ह"),
        "find_yours": "तुमच्या जन्मतपशिलांवरून तुमचे नक्षत्र पाहा",
    },
}


def hub_rows(lang: str) -> list[dict]:
    """All 27 in order, each with the first sentence of its own page's meaning."""
    rows = []
    for nakshatra in NAKSHATRAS:
        facts = view(nakshatra.key, lang)
        meaning = _meaning(nakshatra.key, lang)
        rows.append({**facts, "line": _first_sentence(meaning),
                     "href": i18n.url_for("nakshatra", lang, nakshatra=nakshatra.key)})
    return rows


def _first_sentence(text: str) -> str:
    """The opening sentence, for the hub's one-line summary.

    THE DANDA COUNTS. । ends a sentence in Hindi and Marathi, and splitting on "." alone returned the
    whole paragraph for every one of the 54 Devanagari entries - a hub where each of 27 rows carried
    a full paragraph, which is a wall of text rather than an index.
    """
    import re

    parts = re.split(r"(?<=[.।॥])\s+", text.strip(), maxsplit=1)
    return parts[0].strip() if parts else text.strip()


def add_routes(router, page_context, respond, _json_ld) -> None:
    for lang in i18n.PAGES["nakshatra"]:
        _add_hub(router, page_context, respond, _json_ld, lang)
        for nakshatra in NAKSHATRAS:
            _add(router, page_context, respond, _json_ld, lang, nakshatra.key)


def _add_hub(router, page_context, respond, _json_ld, lang: str) -> None:
    def nakshatra_hub(request: Request):
        from app.web import seo as _seo

        words = HUB[lang]
        context = page_context("nakshatra-hub", lang)
        path = i18n.url_for("nakshatra-hub", lang)
        context.update(
            words=words, rows=hub_rows(lang), title=words["title"],
            meta_description=words["meta"],
            kundli_path=i18n.url_for("kundali", lang),
            json_ld=[_json_ld(_seo.breadcrumbs([(context["ui"]["home"], i18n.url_for("home", lang)),
                                                (words["h1"], path)]))])
        return respond(request, "nakshatra_hub.html", context)

    router.add_api_route(i18n.url_for("nakshatra-hub", lang), nakshatra_hub, methods=["GET"],
                         response_class=HTMLResponse, name=f"nakshatra-hub-{lang}")


def _add(router, page_context, respond, _json_ld, lang: str, key: str) -> None:
    def nakshatra_page(request: Request):
        from app.web import seo as _seo

        words = FRAME[lang]
        facts = view(key, lang)
        meaning = _meaning(key, lang)
        context = page_context("nakshatra", lang, nakshatra=key)
        path = i18n.url_for("nakshatra", lang, nakshatra=key)
        title = words["title"].format(**facts)
        context.update(
            words=words, n=facts, meaning=meaning,
            title=title,
            # BACK TO THE HUB. Without it the hub was reachable only from the sitemap - the same
            # orphan the by-name matching pages were, caught by the same guard - and a reader on one
            # nakshatra page had no way to see the other twenty-six except through the nav.
            hub_href=i18n.url_for("nakshatra-hub", lang),
            hub_label=HUB[lang]["h1"],
            others=[{"name": nakshatra_info(other.index - 1)["name"],
                     "href": i18n.url_for("nakshatra", lang, nakshatra=other.key)}
                    for other in NAKSHATRAS if other.key != key],
            json_ld=[_json_ld(_seo.breadcrumbs([(context["ui"]["home"], i18n.url_for("home", lang)),
                                                (facts["name"], path)]))])
        return respond(request, "nakshatra.html", context)

    router.add_api_route(i18n.url_for("nakshatra", lang, nakshatra=key), nakshatra_page,
                         methods=["GET"], response_class=HTMLResponse,
                         name=f"nakshatra-{key.lower().replace(' ', '-')}-{lang}")


def _meaning(key: str, lang: str) -> str:
    from app.web import nakshatra_copy_en, nakshatra_copy_hi, nakshatra_copy_mr

    return {"en": nakshatra_copy_en.MEANINGS, "hi": nakshatra_copy_hi.MEANINGS,
            "mr": nakshatra_copy_mr.MEANINGS}[lang][key]
