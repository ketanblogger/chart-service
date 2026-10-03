"""PROTOTYPE: the labels and the context for the full-width home page (`?design=v2`).

WHY THESE STRINGS ARE HERE AND NOT IN `app/web/content/<lang>.py`. This is a prototype behind a flag, and the
content modules are what the live site reads: putting a dozen speculative labels in them would mean the live
copy carried strings nothing renders, and deleting the prototype would mean going back through three files to
find them. When phase 2 is approved these move into `PageCopy.extra` where the rest of the page's words live,
and this module goes away.

Everything a reader sees is in all three languages. The Marathi is checked against
`app/ai/language.language_problems` by tests/test_design_v2.py, which is the same checker the paid reports go
through - a prototype is exactly where a Hindi spelling slips in unnoticed.
"""

# ---- the twelve sign glyphs -------------------------------------------------------------------------
#
# Inline SVG paths, drawn here rather than downloaded: no request, no image to go stale, and no dependency on
# a font containing U+2648-2653 (the bundled Noto faces do not, so the Unicode zodiac characters would have
# rendered as tofu on the machines least likely to have a fallback). One 24x24 viewBox, stroke only, no fill,
# so they take the surrounding colour and stay legible at 26px.
SIGN_GLYPHS = {
    "mesha":     "M12 20c0-6-1-9-4.5-9S3 14 3 16.5M12 20c0-6 1-9 4.5-9S21 14 21 16.5",
    "vrishabha": "M5 6c2 3 4 4 7 4s5-1 7-4M12 10a5 5 0 1 0 0 10 5 5 0 0 0 0-10",
    "mithuna":   "M5 5h14M5 19h14M8 5v14M16 5v14",
    "karka":     "M4 10c3-3 8-3 10 0M20 16c-3 3-8 3-10 0M6 8a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5M18 13a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5",
    "simha":     "M7 19a3.5 3.5 0 1 0 0-7c-2.5 0-4-2-4-4.5S5 3 8 3s5 2.5 5 6v6c0 2 1.5 3.5 3.5 3.5S20 17 20 15",
    "kanya":     "M4 6v10M4 8c0-1.5 1-2 2-2s2 .5 2 2v8M8 8c0-1.5 1-2 2-2s2 .5 2 2v8M12 8c0-1.5 1-2 2.5-2S17 7 17 9v6c0 2-1 3-2 4M14 15c2 0 4 1.5 5.5 4",
    "tula":      "M3 19h18M3 14h4.5a5 5 0 0 1 9 0H21",
    "vrishchika": "M3 7v9M3 9c0-1.5 1-2 2-2s2 .5 2 2v7M7 9c0-1.5 1-2 2-2s2 .5 2 2v7M11 9c0-1.5 1-2 2.5-2S16 8 16 10v6l4-3M20 13v4h-4",
    "dhanu":     "M5 19L18 6M12 6h6v6M8 11l5 5",
    "makara":    "M4 7v9M4 9c0-1.5 1-2 2-2s2 .5 2 2v7M8 9c0-1.5 1-2 2.5-2S13 8 13 10v4a4 4 0 0 0 7 2.5c1.5-2 .5-5-2-5",
    "kumbha":    "M3 9l3.5-2.5L10 9l3.5-2.5L17 9l3.5-2.5M3 16l3.5-2.5L10 16l3.5-2.5L17 16l3.5-2.5",
    "meena":     "M7 3c-4 4-4 14 0 18M17 3c4 4 4 14 0 18M3 12h18",
}

# ---- the tool-card glyphs ---------------------------------------------------------------------------
TOOL_GLYPHS = {
    "kundali":      "M3 3h18v18H3zM3 12h18M12 3v18M3 3l18 18M21 3L3 21",
    "matching":     "M9 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8M15 8a4 4 0 1 1 0 8 4 4 0 0 1 0-8",
    "mangal-dosha": "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18M12 7v6M12 16h.01",
    "sade-sati":    "M12 4a8 8 0 1 0 0 16 8 8 0 0 0 0-16M3 15c5 2 13 2 18-3",
    "rashifal-hub": "M12 3l2.6 5.6 6.4.8-4.7 4.3 1.3 6.3L12 17l-5.6 3 1.3-6.3L3 9.4l6.4-.8z",
    "consultation": "M4 5h16v11H9l-5 4z",
}

# The four needs in "Which tool do you actually need?", in the order the copy lists them, each with the tool
# it sends a reader to. POSITIONAL, and that is safe only because it is asserted: tests/test_design_v2.py
# checks every language's section has exactly four bullets, in this order, each naming its own tool. All three
# languages were written from one outline, so the order is the same in each - but an order that is true today
# and unchecked is how a card quietly starts linking to the wrong page.
NEED_TOOLS = ("kundali", "matching", "sade-sati", "rashifal-hub")

# ---- words ------------------------------------------------------------------------------------------
LABELS = {
    "en": {
        "form_heading": "Free janam kundali",
        "hero_points": ["Swiss Ephemeris positions, not an app's guess",
                        "Every date and degree calculated before a word is written",
                        "Free: chart, dasha, dosha and panchang"],
        "tools_heading": "What you can work out here",
        "signs_heading": "Today, by moon sign",
        "signs_note": "Vedic astrology reads the MOON sign. Not sure which is yours? The free kundali says so in seconds.",
        "periods": "Weekly · Monthly · Next 6 months · This year",
        "ai_heading": "Ask about your own chart",
        "ai_q": "Is this a good year to change jobs?",
        "ai_a": "Your Guru mahadasha runs to 2029 and Guru sits in the 10th from your moon sign, which "
                "traditionally favours a considered move rather than a sudden one. The window your chart "
                "actually opens is 14 March to 2 July 2027.",
        "ai_who_q": "You",
        "ai_who_a": "AI astrologer",
        "ai_note": "Written by an AI from YOUR calculated chart. It never works out a position or a date "
                   "itself - the Swiss Ephemeris does that, and every answer is checked against it.",
        "ai_cta": "Ask your first two questions free",
        "trust_heading": "How this is calculated",
        "trust_steps": ["The Swiss Ephemeris computes the nine grahas, your lagna, nakshatra and every "
                        "Vimshottari date from your birth details.",
                        "Those numbers are checked, then handed to the AI as facts it may explain and may "
                        "not change.",
                        "Every report is verified against the chart again before you see it."],
        "report_heading": "The detailed Kundali book",
        "report_text": "35-45 pages from your own chart: yogas, dashas, the year ahead, remedies and a "
                       "navamsha reading. Delivered as a PDF in a few minutes.",
        "report_note": "Illustration, not a real reader's book.",
        "report_cta": "See what is in it",
        "sky_heading": "Sky right now",
        "sky_note": "Sidereal, Lahiri ayanamsa. Updated every few minutes.",
        "sky_rx": "R",
        "sky_rx_label": "retrograde",
        "picker_heading": "Your rashi today",
        "sell_heading": "Your full reading",
        "sell_cta": "Get your report",
        "sell_note": "One payment. No subscription.",
        "bar_kundali": "Free kundali",
        "bar_ai": "Ask AI astrologer",
        "read_more": "Read more",
        "read_less": "Show less",
        "needs_heading_note": "Four things people arrive wanting. Each one has its own page.",
        "faq_heading": "Questions people ask",
    },
    "hi": {
        "form_heading": "मुफ़्त जन्म कुंडली",
        "hero_points": ["स्विस एफेमेरिस से ग्रह स्थिति, किसी ऐप का अंदाज़ा नहीं",
                        "हर तारीख़ और अंश पहले गिना जाता है, लिखा बाद में",
                        "मुफ़्त: कुंडली, दशा, दोष और पंचांग"],
        "tools_heading": "यहाँ आप क्या निकाल सकते हैं",
        "signs_heading": "आज का राशिफल, चंद्र राशि से",
        "signs_note": "वैदिक ज्योतिष चंद्र राशि से पढ़ा जाता है। आपकी कौन सी है? मुफ़्त कुंडली कुछ सेकंड में बता देती है।",
        "periods": "साप्ताहिक · मासिक · अगले 6 महीने · इस साल",
        "ai_heading": "अपनी कुंडली के बारे में पूछिए",
        "ai_q": "क्या यह साल नौकरी बदलने के लिए अच्छा है?",
        "ai_a": "आपकी गुरु महादशा 2029 तक चलती है और गुरु आपकी चंद्र राशि से दशम भाव में है, जो परंपरा के "
                "अनुसार सोच-समझकर उठाए क़दम के लिए अनुकूल है, अचानक बदलाव के लिए नहीं। आपकी कुंडली जो "
                "समय खोलती है वह 14 मार्च से 2 जुलाई 2027 है।",
        "ai_who_q": "आप",
        "ai_who_a": "AI ज्योतिषी",
        "ai_note": "यह उत्तर AI ने आपकी गणना की गई कुंडली से लिखा है। वह ख़ुद कोई स्थिति या तारीख़ नहीं "
                   "निकालता - वह काम स्विस एफेमेरिस करता है, और हर उत्तर उसी से जाँचा जाता है।",
        "ai_cta": "पहले दो सवाल मुफ़्त पूछिए",
        "trust_heading": "गणना कैसे होती है",
        "trust_steps": ["स्विस एफेमेरिस आपके जन्म विवरण से नौ ग्रह, लग्न, नक्षत्र और विंशोत्तरी की हर तारीख़ "
                        "गिनता है।",
                        "वे संख्याएँ जाँची जाती हैं, फिर AI को तथ्य के रूप में दी जाती हैं - वह उन्हें समझा "
                        "सकता है, बदल नहीं सकता।",
                        "आप तक पहुँचने से पहले हर रिपोर्ट दोबारा उसी कुंडली से जाँची जाती है।"],
        "report_heading": "विस्तृत कुंडली रिपोर्ट",
        "report_text": "आपकी अपनी कुंडली से 35-45 पेज: योग, दशाएँ, आने वाला साल, उपाय और नवांश विश्लेषण। "
                       "कुछ ही मिनटों में PDF में।",
        "report_note": "यह नमूना चित्र है, किसी पाठक की असली रिपोर्ट नहीं।",
        "report_cta": "इसमें क्या है, देखिए",
        "sky_heading": "अभी का आकाश",
        "sky_note": "निरयन, लाहिरी अयनांश। हर कुछ मिनट में अपडेट।",
        "sky_rx": "व",
        "sky_rx_label": "वक्री",
        "picker_heading": "आपकी राशि, आज",
        "sell_heading": "आपकी पूरी रिपोर्ट",
        "sell_cta": "अपनी रिपोर्ट लीजिए",
        "sell_note": "एक बार का भुगतान। कोई सदस्यता नहीं।",
        "bar_kundali": "मुफ़्त कुंडली",
        "bar_ai": "AI ज्योतिषी से पूछें",
        "read_more": "और पढ़ें",
        "read_less": "कम दिखाएँ",
        "needs_heading_note": "लोग चार में से कोई एक चीज़ चाहते हुए आते हैं। हर एक का अपना पेज है।",
        "faq_heading": "अक्सर पूछे जाने वाले सवाल",
    },
    "mr": {
        "form_heading": "मोफत जन्मकुंडली",
        "hero_points": ["स्विस एफेमेरिसवरून ग्रहस्थिती, कोणत्या अ‍ॅपचा अंदाज नाही",
                        "प्रत्येक तारीख आणि अंश आधी गणिताने, लिहिणे नंतर",
                        "मोफत: कुंडली, दशा, दोष आणि पंचांग"],
        "tools_heading": "इथे तुम्ही काय काढू शकता",
        "signs_heading": "आजचे राशिभविष्य, चंद्रराशीवरून",
        "signs_note": "वैदिक ज्योतिष चंद्रराशीवरून पाहिले जाते. तुमची कोणती आहे? मोफत कुंडली काही सेकंदांत सांगते.",
        "periods": "साप्ताहिक · मासिक · पुढचे 6 महिने · हे वर्ष",
        "ai_heading": "तुमच्या कुंडलीबद्दल विचारा",
        "ai_q": "नोकरी बदलण्यासाठी हे वर्ष चांगले आहे का?",
        "ai_a": "तुमची गुरू महादशा 2029 पर्यंत चालते आणि गुरू तुमच्या चंद्रराशीपासून दशम स्थानात आहे, "
                "जे परंपरेनुसार विचारपूर्वक उचललेल्या पावलाला अनुकूल आहे, घाईच्या बदलाला नाही. तुमची "
                "कुंडली जो काळ उघडते तो 14 मार्च ते 2 जुलै 2027 आहे.",
        "ai_who_q": "तुम्ही",
        "ai_who_a": "AI ज्योतिषी",
        "ai_note": "हे उत्तर AI ने तुमच्या गणित केलेल्या कुंडलीवरून लिहिले आहे. तो स्वतः कोणतीही स्थिती "
                   "किंवा तारीख काढत नाही - ते काम स्विस एफेमेरिस करते, आणि प्रत्येक उत्तर त्याच्याशी "
                   "तपासले जाते.",
        "ai_cta": "पहिले दोन प्रश्न मोफत विचारा",
        "trust_heading": "गणित कसे होते",
        "trust_steps": ["स्विस एफेमेरिस तुमच्या जन्मतपशिलावरून नऊ ग्रह, लग्न, नक्षत्र आणि विंशोत्तरीची "
                        "प्रत्येक तारीख गणिताने काढते.",
                        "ते आकडे तपासले जातात आणि मग AI ला तथ्य म्हणून दिले जातात - तो ते समजावून सांगू "
                        "शकतो, बदलू शकत नाही.",
                        "तुमच्यापर्यंत पोहोचण्यापूर्वी प्रत्येक अहवाल पुन्हा त्याच कुंडलीशी तपासला जातो."],
        "report_heading": "सविस्तर कुंडली अहवाल",
        "report_text": "तुमच्याच कुंडलीवरून 35-45 पाने: योग, दशा, पुढचे वर्ष, उपाय आणि नवांश विश्लेषण. "
                       "काही मिनिटांत PDF मध्ये.",
        "report_note": "हे नमुना चित्र आहे, कोणत्या वाचकाचा खरा अहवाल नाही.",
        "report_cta": "यात काय आहे ते पाहा",
        "sky_heading": "आत्ताचे आकाश",
        "sky_note": "निरयन, लाहिरी अयनांश. दर काही मिनिटांनी अपडेट.",
        "sky_rx": "व",
        "sky_rx_label": "वक्री",
        "picker_heading": "तुमची रास, आज",
        "sell_heading": "तुमचा संपूर्ण अहवाल",
        "sell_cta": "तुमचा अहवाल घ्या",
        "sell_note": "एकदाच पैसे. वर्गणी नाही.",
        "bar_kundali": "मोफत कुंडली",
        "bar_ai": "AI ज्योतिषी विचारा",
        "read_more": "अधिक वाचा",
        "read_less": "कमी दाखवा",
        "needs_heading_note": "लोक चारपैकी एक गोष्ट हवी म्हणून येतात. प्रत्येकाचे स्वतःचे पान आहे.",
        "faq_heading": "नेहमी विचारले जाणारे प्रश्न",
    },
}

# Which nav key gets which glyph; anything unlisted falls back to the kundali mark rather than to nothing.
DEFAULT_GLYPH = TOOL_GLYPHS["kundali"]


def labels(language: str) -> dict:
    return LABELS.get(language, LABELS["en"])


def glyph(key: str) -> str:
    return TOOL_GLYPHS.get(key, DEFAULT_GLYPH)
