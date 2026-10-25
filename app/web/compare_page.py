"""An honest, dated comparison with the three sites people actually use.

THE RULES THIS PAGE IS WRITTEN UNDER, because a comparison page naming real companies is the easiest
thing on a site to get wrong - legally and morally:

  Every claim is about a PUBLICLY VISIBLE feature, checkable by opening their page. No claims about
  accuracy we have not measured, no claims about their internals, no speculation about their business.

  It is DATED, in the page body, because these are live products and anything said about them has a
  shelf life. An undated comparison is a claim that silently becomes false.

  IT CONCEDES. Each competitor has a row saying where they are genuinely better than us, and those rows
  are real rather than token - AstroSage's language coverage and app, Drik Panchang's depth of
  calendrical detail, Prokerala's breadth. A comparison that finds the author best at everything is an
  advertisement, and readers can tell.

  No logos, no trademarks used as ours, no implied affiliation or endorsement.
"""
from __future__ import annotations

import datetime as dt

from fastapi import Request
from fastapi.responses import HTMLResponse

from app.web import i18n

#: The day the claims below were checked by opening each site. Shown on the page.
CHECKED_ON = dt.date(2026, 10, 22)

#: Public pages the claims can be checked against. Cited on the page, as required.
SOURCES = (
    ("AstroSage", "https://www.astrosage.com/"),
    ("Drik Panchang", "https://www.drikpanchang.com/"),
    ("Prokerala", "https://www.prokerala.com/astrology/"),
)

COPY = {
    "en": {
        "title": "Best Free Kundli Websites Compared (2026)",
        "h1": "Free kundli websites, compared honestly",
        "intro": "AstroSage, Drik Panchang, Prokerala and this site. What each is genuinely good at, "
                 "including where the others beat us.",
        "checked": "Checked by opening each site on {date}. These are live products and this page has "
                   "a shelf life; if something below is out of date, it is out of date.",
        "rows_heading": "Where each one is strongest",
        "rows": (
            ("AstroSage",
             "The widest reach of any of them: many more Indian languages than we support, a mature "
             "mobile app, and a very large body of article content. If you want an app and your "
             "language is not one of our three, this is the straightforward answer."),
            ("Drik Panchang",
             "The deepest calendrical detail anywhere - festivals, vrats, regional variations and "
             "muhurat tables we do not attempt. If you need a panchang for a specific tradition or an "
             "obscure observance, go there. Note that it computes sunrise with the upper limb and "
             "refraction, where we and Prokerala use the disc centre: times can differ by a few "
             "minutes, and neither is wrong."),
            ("Prokerala",
             "A very broad set of calculators covering more ground than ours, and a clean presentation. "
             "Its panchang uses the same sunrise convention we do, so its times and ours agree closely."),
            ("RashiKundli",
             "Three languages done properly rather than many done thinly, every number from the Swiss "
             "Ephemeris with the method stated on the page, no AI anywhere in a calculation, and no "
             "fear-selling: the dosha pages tell you what a configuration is and sell nothing against "
             "it. The free PDF is the whole calculation, not a teaser."),
        ),
        "fair_heading": "What we do not claim",
        "fair": (
            "We have not measured their accuracy against ours across a large sample, so this page makes "
            "no accuracy claim about them. Where we have compared - the panchang - we published the "
            "result including the four-minute sunrise difference with Drik, which is a convention "
            "difference and not an error on either side.",
            "We are smaller than all three and newer than all three. If you want the broadest feature "
            "set or the most languages, we are not it.",
        ),
        "sources_heading": "Checked against their own public pages",
    },
}
COPY["hi"] = {
    "title": "सबसे अच्छी मुफ़्त कुंडली वेबसाइट - तुलना (2026)",
    "h1": "मुफ़्त कुंडली वेबसाइटों की ईमानदार तुलना",
    "intro": "AstroSage, Drik Panchang, Prokerala और यह साइट। हर एक किसमें वाक़ई अच्छी है - उसमें भी "
             "जहाँ दूसरे हमसे बेहतर हैं।",
    "checked": "{date} को हर साइट खोलकर जाँचा गया। ये चालू उत्पाद हैं और इस पन्ने की एक उम्र है; "
               "नीचे कुछ पुराना पड़ गया हो तो वह पुराना है।",
    "rows_heading": "कौन किसमें सबसे मज़बूत है",
    "rows": (
        ("AstroSage",
         "सबसे बड़ी पहुँच: हमसे कहीं अधिक भारतीय भाषाएँ, एक परिपक्व मोबाइल ऐप, और बहुत बड़ा लेख "
         "संग्रह। अगर आपको ऐप चाहिए या आपकी भाषा हमारी तीन में नहीं है, तो सीधा उत्तर यही है।"),
        ("Drik Panchang",
         "पंचांग का सबसे गहरा विवरण - त्योहार, व्रत, क्षेत्रीय भेद और मुहूर्त सारणियाँ जो हम नहीं "
         "देते। किसी विशेष परंपरा का पंचांग चाहिए तो वहीं जाइए। ध्यान रहे कि वे सूर्योदय बिंब के "
         "ऊपरी किनारे और वक्रीभवन से लेते हैं, जबकि हम और Prokerala बिंब का केंद्र लेते हैं: "
         "समय में कुछ मिनट का अंतर आता है, और दोनों में कोई ग़लत नहीं।"),
        ("Prokerala",
         "कैलकुलेटरों का बहुत व्यापक संग्रह, हमसे अधिक, और साफ़-सुथरी प्रस्तुति। इनका पंचांग वही "
         "सूर्योदय रीति लेता है जो हमारी है, इसलिए समय आपस में मिलते हैं।"),
        ("RashiKundli",
         "तीन भाषाएँ ठीक से, न कि बहुत सी ऊपर-ऊपर; हर संख्या स्विस एफेमेरिस से और रीति पन्ने पर "
         "लिखी हुई; किसी भी गणना में AI नहीं; और डर नहीं बेचा जाता - दोष के पन्ने बताते हैं कि योग "
         "क्या है और उसके विरुद्ध कुछ बेचते नहीं। मुफ़्त PDF पूरी गणना है, झाँकी नहीं।"),
    ),
    "fair_heading": "हम क्या दावा नहीं करते",
    "fair": (
        "हमने बड़े नमूने पर उनकी सटीकता अपनी सटीकता से नहीं नापी, इसलिए यह पन्ना उनके बारे में कोई "
        "सटीकता-दावा नहीं करता। जहाँ नापा - पंचांग में - वहाँ परिणाम प्रकाशित किया, Drik से चार "
        "मिनट के सूर्योदय अंतर सहित, जो रीति का अंतर है, किसी की ग़लती नहीं।",
        "हम तीनों से छोटे हैं और तीनों से नए। अगर सबसे अधिक सुविधाएँ या सबसे अधिक भाषाएँ चाहिए, तो "
        "हम वह नहीं हैं।",
    ),
    "sources_heading": "उनके अपने सार्वजनिक पन्नों से जाँचा गया",
}
COPY["mr"] = {
    "title": "सर्वोत्तम मोफत कुंडली वेबसाइट - तुलना (2026)",
    "h1": "मोफत कुंडली वेबसाइटची प्रामाणिक तुलना",
    "intro": "AstroSage, Drik Panchang, Prokerala आणि ही साइट. प्रत्येक कशात खरोखर चांगली आहे - "
             "जिथे इतर आमच्यापेक्षा सरस आहेत तिथेसुद्धा.",
    "checked": "{date} रोजी प्रत्येक साइट उघडून तपासले. ही चालू उत्पादने आहेत आणि या पानाला आयुष्य "
               "आहे; खालचे काही जुने झाले असेल तर ते जुने आहे.",
    "rows_heading": "कोण कशात सर्वात बलवान",
    "rows": (
        ("AstroSage",
         "सर्वात मोठी पोहोच: आमच्यापेक्षा कितीतरी अधिक भारतीय भाषा, प्रगल्भ मोबाइल अॅप, आणि फार "
         "मोठा लेखसंग्रह. अॅप हवे असेल किंवा तुमची भाषा आमच्या तिघांत नसेल, तर सरळ उत्तर हेच."),
        ("Drik Panchang",
         "पंचांगाचा सर्वात सखोल तपशील - सण, व्रते, प्रादेशिक भेद आणि मुहूर्त तक्ते जे आम्ही देत "
         "नाही. विशिष्ट परंपरेचे पंचांग हवे असेल तर तिथेच जा. ते सूर्योदय बिंबाच्या वरच्या कडेने "
         "आणि वक्रीभवनासह घेतात, तर आम्ही व Prokerala बिंबाचा मध्य घेतो: वेळेत काही मिनिटांचा फरक "
         "येतो, आणि दोघांपैकी कोणीही चुकीचे नाही."),
        ("Prokerala",
         "आमच्यापेक्षा बराच अधिक व्यापक कॅल्क्युलेटर संग्रह, आणि मांडणी स्वच्छ व जाहिरातींनी कमी "
         "भरलेली. त्यांचे पंचांग आमचीच सूर्योदय पद्धत वापरते - बिंबाचा मध्य, वक्रीभवनाशिवाय - "
         "त्यामुळे तिथीच्या आणि नक्षत्राच्या वेळा आमच्या वेळांशी मिनिटाच्या फरकाने जुळतात, हे "
         "आम्ही प्रत्यक्ष तपासले आहे. अनेक साधने एकाच ठिकाणी हवी असतील तर हा चांगला पर्याय आहे."),
        ("RashiKundli",
         "तीन भाषा नीट, पुष्कळ भाषा वरवर नव्हे; प्रत्येक आकडा स्विस एफेमेरिसमधून आणि पद्धत पानावर "
         "लिहिलेली; कोणत्याही गणितात AI नाही; आणि भीती विकली जात नाही - दोषाची पाने योग काय आहे ते "
         "सांगतात आणि त्याविरुद्ध काहीही विकत नाहीत. मोफत PDF ही संपूर्ण गणना आहे, झलक नव्हे."),
    ),
    "fair_heading": "आम्ही काय दावा करत नाही",
    "fair": (
        "मोठ्या नमुन्यावर त्यांची अचूकता आमच्याशी मोजलेली नाही, त्यामुळे हे पान त्यांच्याबद्दल "
        "अचूकतेचा दावा करत नाही. जिथे मोजले - पंचांगात - तिथला निकाल प्रसिद्ध केला, Drik शी "
        "चार मिनिटांच्या सूर्योदय फरकासह, जो पद्धतीचा फरक आहे, कोणाची चूक नाही.",
        "आम्ही तिघांपेक्षा लहान आणि नवे आहोत. सर्वाधिक सुविधा किंवा सर्वाधिक भाषा हव्या असतील, तर "
        "आम्ही ते नाही.",
    ),
    "sources_heading": "त्यांच्याच सार्वजनिक पानांवरून तपासले",
}


def add_routes(router, page_context, respond, _json_ld) -> None:
    for lang in i18n.PAGES["compare"]:
        _add(router, page_context, respond, _json_ld, lang)


def _add(router, page_context, respond, _json_ld, lang: str) -> None:
    def compare_page(request: Request):
        from app.web import seo as _seo

        words = dict(COPY[lang])
        words["checked"] = words["checked"].format(date=CHECKED_ON.strftime("%-d %B %Y"))
        context = page_context("compare", lang)
        path = i18n.url_for("compare", lang)
        context.update(words=words, sources=SOURCES, title=words["title"],
                       json_ld=[_json_ld(_seo.breadcrumbs(
                           [(context["ui"]["home"], i18n.url_for("home", lang)),
                            (words["h1"], path)]))])
        return respond(request, "compare.html", context)

    router.add_api_route(i18n.url_for("compare", lang), compare_page, methods=["GET"],
                         response_class=HTMLResponse, name=f"compare-{lang}")
