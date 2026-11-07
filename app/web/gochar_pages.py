"""One page per slow graha per year: Shani, Guru and Rahu-Ketu.

"jupiter transit 2026" is 50,000 searches a month and the gochar terms 5,000 each. This site has had
the dates all along - they come from the same ephemeris scan the charts use - and nowhere to put
them.

WHAT IS COMPUTED AND WHAT IS WRITTEN. Everything dated here is computed: the ingresses, the
retrograde stations, which sign the graha sits in and for how long, and the house that is from each
of the twelve rashis. The sentence under each rashi is WRITTEN, once, by hand, and it is about the
HOUSE rather than about the reader - "the tenth house is work and standing in the world" is a fact
about the tradition, not a prediction about anybody. There is no AI on this path and no per-reader
text: twelve house meanings per graha, written once and reused for whichever rashi the house lands
in, which is also why they cannot drift between the three pages.

RAHU AND KETU SHARE A PAGE. They are always opposite, so separate pages would carry the same dates
twice with the houses swapped - a duplicate in every sense a search engine cares about and in the
only sense a reader does.

THE SAME RULES AS EVERYTHING ELSE. No guarantee, nothing that happens TO the reader, no fear, no
remedy anybody has to buy. A test runs every line of this file's copy through app/blog/safety.py.
"""
from __future__ import annotations

import datetime as dt

from fastapi import Request
from fastapi.responses import HTMLResponse

from app.engine.constants import graha_name, sign_info
from app.engine.core import house_from
from app.rashifal import year_facts
from app.web import i18n

#: Which engine graha each page is about. "rahu-ketu" is one page covering both.
GRAHA_KEYS = {"shani": ("Saturn",), "guru": ("Jupiter",), "rahu-ketu": ("Rahu", "Ketu")}


def stays_for(slug: str, year: int) -> list[dict]:
    """Where this page's graha (or pair) sits through the year, with no house: the same sky for all."""
    wanted = GRAHA_KEYS[slug]
    names = {graha_name(key)["name"] for key in wanted if key != "Ketu"}
    out = []
    for stay in year_facts.slow_graha_stays(year):
        label = stay["graha"]["name"] if isinstance(stay["graha"], dict) else stay["graha"]
        if label in names:
            out.append(stay)
            if "Ketu" in wanted:
                # KETU IS ALWAYS THE OPPOSITE SIGN. The engine scans Rahu; deriving Ketu from it is
                # exact rather than approximate, and scanning it separately would be the same work
                # twice for a number that is one addition away.
                opposite = (stay["sign"]["index"] + 5) % 12
                out.append({**stay, "graha": graha_name("Ketu"), "sign": sign_info(opposite)})
    return out


def houses_for(slug: str, year: int, lang: str) -> list[dict]:
    """For each of the twelve rashis: which house this graha occupies, and what that house is about."""
    stays = stays_for(slug, year)
    primary = GRAHA_KEYS[slug][0]
    primary_name = graha_name(primary)["name"]
    rows = []
    for index, rashi_key in enumerate(i18n.RASHI_KEYS, start=1):
        names = i18n.rashi_names(rashi_key, lang)
        spans = []
        for stay in stays:
            label = stay["graha"]["name"] if isinstance(stay["graha"], dict) else stay["graha"]
            if label != primary_name:
                continue
            house = house_from(index, stay["sign"]["index"])
            spans.append({
                "house": house,
                "sign": stay["sign"],
                "start": stay["start"],
                "end": stay["end"],
                "meaning": HOUSE_MEANINGS[lang][house - 1],
            })
        rows.append({
            "rashi": rashi_key,
            "name": names["rashi"],
            "latin": names["latin"],
            "spans": spans,
            "path": i18n.url_for("rashifal-year", lang, rashi=rashi_key, year=year),
        })
    return rows


#: WHAT EACH HOUSE IS ABOUT, written once and used for whichever rashi the graha lands in. A fact
#: about the tradition rather than a prediction about a person - which is the whole reason these can
#: be written once and reused, and the reason they pass the site's own checker.
HOUSE_MEANINGS = {
    "en": (
        "the self: how you carry yourself and how the year finds you",
        "money kept, family, and what you say",
        "courage, effort, siblings and short journeys",
        "home, mother, property and peace of mind",
        "children, learning, and what you make",
        "work, debts, health and daily routine",
        "marriage, partners and anybody you deal with face to face",
        "what is shared, inheritance, and change that is not asked for",
        "belief, fortune, teachers and long journeys",
        "work and standing in the world",
        "gains, friendships and what you hope for",
        "expenses, rest, travel abroad and what is left behind",
    ),
    "hi": (
        "स्वयं: आप कैसे दिखते हैं और यह वर्ष आपको कहाँ पाता है",
        "संचित धन, परिवार और वाणी",
        "साहस, प्रयास, भाई-बहन और छोटी यात्राएँ",
        "घर, माता, संपत्ति और मन की शांति",
        "संतान, विद्या और आपका रचा हुआ काम",
        "काम, ऋण, सेहत और दिनचर्या",
        "विवाह, साझेदार और जिनसे आमने-सामने व्यवहार होता है",
        "साझा धन, उत्तराधिकार और बिना माँगे आया बदलाव",
        "आस्था, भाग्य, गुरु और लंबी यात्राएँ",
        "कर्म और समाज में स्थान",
        "लाभ, मित्रता और आपकी आशाएँ",
        "व्यय, विश्राम, विदेश यात्रा और पीछे छूटा हुआ",
    ),
    "mr": (
        "स्वतः: तुम्ही कसे वावरता आणि हे वर्ष तुम्हाला कुठे गाठते",
        "साठवलेला पैसा, कुटुंब आणि वाणी",
        "धैर्य, प्रयत्न, भावंडे आणि छोटे प्रवास",
        "घर, आई, मालमत्ता आणि मनःशांती",
        "संतती, विद्या आणि तुम्ही घडवलेले काम",
        "काम, कर्ज, आरोग्य आणि दिनचर्या",
        "विवाह, भागीदार आणि समोरासमोर व्यवहार करणारे",
        "सामायिक धन, वारसा आणि न मागता आलेला बदल",
        "श्रद्धा, भाग्य, गुरू आणि लांबचे प्रवास",
        "काम आणि समाजातील स्थान",
        "लाभ, मैत्री आणि तुमच्या आशा",
        "खर्च, विश्रांती, परदेश प्रवास आणि मागे राहिलेले",
    ),
}


#: TITLES FROM THE SEARCH DATA. "jupiter transit 2026" is 50,000 a month and "guru gochar" 5,000, so
#: the English page leads with the Roman transit phrase and carries the gochar word; the Devanagari
#: trees lead with गोचर and carry the Roman phrase for the readers who type it.
GRAHA_LABELS = {
    "shani": {"en": ("Shani", "Saturn"), "hi": ("शनि", "Shani"), "mr": ("शनी", "Shani")},
    "guru": {"en": ("Guru", "Jupiter"), "hi": ("गुरु", "Guru"), "mr": ("गुरू", "Guru")},
    "rahu-ketu": {"en": ("Rahu-Ketu", "Rahu Ketu"), "hi": ("राहु-केतु", "Rahu Ketu"),
                  "mr": ("राहू-केतू", "Rahu Ketu")},
}

COPY = {
    "en": {
        "title": "{native} Gochar {year}: {english} Transit {year} Dates",
        "h1": "{native} Gochar {year} ({english} Transit {year})",
        "meta": ("{english} transit {year}: the exact dates {native} changes sign and goes "
                 "retrograde, and which house that is from each of the twelve rashis. Computed, "
                 "not copied. Free."),
        "lead": ("Every date on this page is computed from the same ephemeris this site draws charts "
                 "with. What a transit means for you depends on the house it falls in counted from "
                 "your Moon sign, which is the table below."),
        "dates_heading": "{native} in {year}: the dates",
        "houses_heading": "{native} in {year} for your rashi",
        "cols": ("Rashi", "House", "From", "To"),
        "house_word": "house",
        "read_more": "{rashi} Rashi {year}",
        "kundli_cta": "Not sure of your rashi? Get your free kundli",
        "note": ("The house is counted from the rashi as the Moon sign. A transit is a position and "
                 "a date; what anybody does with it is theirs to decide."),
    },
    "hi": {
        # The Roman phrase is required on a Devanagari title (tests/test_pages_i18n.py) and is
        # wanted anyway: "shani gochar 2027" is typed in Roman as often as in Devanagari.
        "title": "{native} गोचर {year} | {english} Gochar {year} तारीख़ें",
        "h1": "{native} गोचर {year} ({english} Transit {year})",
        "meta": ("{native} गोचर {year}: {native} कब राशि बदलते हैं और कब वक्री होते हैं, सटीक तारीख़ों के "
                 "साथ, और यह बारह राशियों में से हर एक से कौन से भाव में पड़ता है। गणना से, नकल से नहीं। मुफ़्त।"),
        "lead": ("इस पन्ने की हर तारीख़ उसी एफेमेरिस से गिनी गई है जिससे यह साइट कुंडली बनाती है। किसी गोचर "
                 "का आपके लिए क्या अर्थ है, यह इस पर निर्भर करता है कि वह आपकी चंद्र राशि से कौन से भाव में "
                 "पड़ता है - वही नीचे की तालिका है।"),
        "dates_heading": "{year} में {native}: तारीख़ें",
        "houses_heading": "{year} में {native} आपकी राशि के लिए",
        "cols": ("राशि", "भाव", "से", "तक"),
        "house_word": "भाव",
        "read_more": "{rashi} राशिफल {year}",
        "kundli_cta": "अपनी राशि नहीं पता? मुफ़्त कुंडली बनाइए",
        "note": ("भाव चंद्र राशि से गिना गया है। गोचर एक स्थिति और एक तारीख़ है; उसका क्या करना है, यह "
                 "आपका निर्णय है।"),
    },
    "mr": {
        "title": "{native} गोचर {year} | {english} Gochar {year} तारखा",
        "h1": "{native} गोचर {year} ({english} Transit {year})",
        "meta": ("{native} गोचर {year}: {native} कधी रास बदलतात आणि कधी वक्री होतात, नेमक्या तारखांसह, "
                 "आणि ते बाराही राशींपैकी प्रत्येकीपासून कोणत्या भावात येते. गणनेवरून, नक्कल नाही. मोफत."),
        "lead": ("या पानावरील प्रत्येक तारीख त्याच एफेमेरिसवरून मोजली आहे जिच्यावरून ही साइट पत्रिका बनवते. "
                 "कोणत्याही गोचराचा तुमच्यासाठी अर्थ तो तुमच्या चंद्रराशीपासून कोणत्या भावात येतो यावर "
                 "अवलंबून असतो - तीच खालील तक्त्यात आहे."),
        "dates_heading": "{year} मध्ये {native}: तारखा",
        "houses_heading": "{year} मध्ये {native} तुमच्या राशीसाठी",
        "cols": ("रास", "भाव", "पासून", "पर्यंत"),
        "house_word": "भाव",
        "read_more": "{rashi} राशीभविष्य {year}",
        "kundli_cta": "तुमची रास माहीत नाही? मोफत पत्रिका बनवा",
        "note": ("भाव चंद्रराशीपासून मोजला आहे. गोचर ही एक स्थिती आणि एक तारीख आहे; त्याचे काय करायचे हे "
                 "तुमचे ठरवायचे."),
    },
}


def add_routes(router, page_context, respond, _json_ld) -> None:
    for lang in i18n.PAGES["gochar"]:
        for slug in i18n.GOCHAR_GRAHAS:
            for year in i18n.YEAR_PAGES:
                _add(router, page_context, respond, _json_ld, lang, slug, year)


def _add(router, page_context, respond, _json_ld, lang: str, slug: str, year: int) -> None:
    def gochar_page(request: Request):
        from app.web import seo as _seo

        words = COPY[lang]
        native, english = GRAHA_LABELS[slug][lang]
        # `rashi` stays a placeholder: `read_more` is filled per card further down, and formatting
        # the whole copy dict with a value it does not have raises KeyError on every one of these
        # nine pages.
        fill = {"native": native, "english": english, "year": year, "rashi": "{rashi}"}
        context = page_context("gochar", lang, graha=slug, year=str(year))
        path = i18n.url_for("gochar", lang, graha=slug, year=year)
        title = words["title"].format(**fill)
        context.update(
            words={key: (value.format(**fill) if isinstance(value, str) else value)
                   for key, value in words.items()},
            native=native, english=english, year=year, slug=slug,
            stays=stays_for(slug, year), rows=houses_for(slug, year, lang),
            title=title, meta_description=words["meta"].format(**fill),
            h1=words["h1"].format(**fill),
            kundali_path=i18n.url_for("kundali", lang),
            year_hub_path=i18n.url_for("rashifal-year-hub", lang, year=year),
            deva=lang in ("hi", "mr"),
            json_ld=[_json_ld(_seo.breadcrumbs([(context["ui"]["home"], i18n.url_for("home", lang)),
                                                (title, path)]))])
        return respond(request, "gochar.html", context)

    router.add_api_route(i18n.url_for("gochar", lang, graha=slug, year=year), gochar_page,
                         methods=["GET"], response_class=HTMLResponse,
                         name=f"gochar-{slug}-{year}-{lang}")
