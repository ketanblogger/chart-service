"""Every word the PDF template prints on its own, in English, Hindi and Marathi.

The AI text arrives already in the report language; this file covers the template's own headings,
table headers and the display names of engine values (grahas, signs, koota values, phases ...).
Marathi is written as Marathi, not transliterated Hindi (मंगळ / शनी / गुरू / तूळ, स्थान not भाव, आहे not है).
Nothing is calculated here.
"""

import datetime as dt

from app.engine import format_range  # the one date-range formatter in the product
from app.engine.constants import MONTHS as ENGINE_MONTHS
from app.engine.constants import GRAHA_KEYS, graha_name, nakshatra_info, sign_info  # display names only
from app.web.site import SITE_NAME

_SIGNS = [sign_info(i) for i in range(12)]
_NAKSHATRAS = [nakshatra_info(i) for i in range(27)]

LANGS = ("en", "hi", "mr")

# ---- template text -------------------------------------------------------------------------------

T = {
    "en": {
        "site_name": SITE_NAME,
        "footer_line": "Astrology is a traditional faith-based practice. For guidance and reflection only.",
        "page": "Page", "of": "of",
        "name": "Name", "dob": "Date of birth", "tob": "Time of birth", "pob": "Place of birth",
        "coordinates": "Coordinates", "timezone": "Time zone", "report_date": "Report date",
        "boy": "Boy", "girl": "Girl",
        "summary": "Summary",
        "lagna": "Lagna (ascendant)", "rashi": "Rashi (Moon sign)", "nakshatra": "Janma nakshatra",
        "pada": "pada", "lord": "Lord",
        "chart_heading": "Lagna kundali (North Indian style)",
        "chart_note": "The number in each house is the sign (1 = Mesha ... 12 = Meena). The top-centre "
                      "diamond is the first house; houses run anticlockwise.",
        "retrograde": "retrograde", "legend_lagna": "Lagna",
        "grahas_heading": "Graha positions",
        "col_graha": "Graha", "col_sign": "Rashi", "col_degree": "Degree", "col_nakshatra": "Nakshatra",
        "col_pada": "Pada", "col_house": "House", "col_retro": "Retro.",
        "yes": "Yes", "no": "No", "always": "Always", "lagna_row": "Lagna",
        "dasha_heading": "Vimshottari dasha",
        "current_maha": "Current mahadasha", "current_antar": "Current antardasha",
        "balance": "Dasha balance at birth", "balance_fmt": "{y} y {m} m {d} d",
        "maha_timeline": "Mahadasha timeline", "col_maha": "Mahadasha", "col_antar": "Antardasha",
        "col_years": "Years", "col_from": "From", "col_to": "To", "now": "now",
        "antar_in_current": "Antardashas of the current {lord} mahadasha",
        "full_dasha": "Complete Vimshottari table (mahadasha and antardashas)",
        "dasha_note": "The first mahadasha began before birth; only its balance was left at birth. "
                      "Current periods are as of {date}.",
        "calc_note": "Calculated with the Swiss Ephemeris: sidereal zodiac, Lahiri ayanamsa {ayanamsa}, "
                     "whole-sign houses, mean Rahu/Ketu.",
        "reading": "Your reading",
        "outlook_table": "Dasha periods and slow-graha sign changes, year by year",
        "col_year": "Year", "col_dasha_periods": "Dasha (mahadasha - antardasha)",
        "col_ingresses": "Sign changes of slow grahas", "from_moon": "{n} from the Moon",
        "ingress_fmt": "{graha} enters {sign}",
        "none": "-",
        "remedies": "Remedies", "how_to": "How", "when": "When",
        "disclaimer": "Disclaimer",
        "report_id": "Report ID",
        # matching
        "guna_heading": "Ashtakoota guna milan", "gunas": "gunas", "col_koota": "Koota", "col_points": "Points",
        "total": "Total", "charts_heading": "Lagna kundalis",
        "doshas_heading": "Nadi and Bhakoot dosha", "nadi_dosha": "Nadi dosha", "bhakoot_dosha": "Bhakoot dosha",
        "dosha_absent": "Not present", "dosha_present": "Present",
        "dosha_cancelled": "Present, with a classical exception that cancels it",
        "moon_distance": "Moon signs are {a}-{b} from each other",
        "mangal_compare": "Mangal dosha comparison",
        "mangal_compatible_both": "Both charts have Mangal dosha; tradition treats this as mutually balancing.",
        "mangal_compatible_none": "Neither chart has Mangal dosha.",
        "mangal_one_sided": "One chart has Mangal dosha. Tradition looks at the mitigating factors and the "
                            "overall strength of both charts.",
        # mangal dosha
        "mangal_heading": "Mangal dosha status", "status": "Status", "intensity": "Intensity",
        "mars": "Mars (Mangal)", "mars_refs": "Where Mars falls in the chart",
        "col_counted": "Counted from", "col_mars_in": "Mars is in", "col_triggers": "Counts as dosha?",
        "from_lagna": "Lagna", "from_moon_ref": "Moon (Chandra)", "from_venus": "Venus (Shukra)",
        "mangal_rule": "Rule used: Mars in the 1st, 2nd, 4th, 7th, 8th or 12th house (whole-sign), counted "
                       "from the Lagna, the Moon and Venus.",
        "cancellations": "Cancellation rules (dosha bhanga)", "col_rule": "Rule", "col_applies": "In this chart",
        "applies": "Applies", "not_applies": "Does not apply",
        # sade sati
        "sade_heading": "Sade sati status", "moon_sign": "Moon sign (rashi)", "saturn_now": "Saturn (Shani) is now in",
        "as_of": "Status as of", "cycle_current": "Current sade sati", "cycle_next": "Next sade sati",
        "col_phase": "Phase", "col_saturn_in": "Saturn in",
        "sade_note": "A phase can appear more than once: Saturn turns retrograde every year and sometimes "
                     "re-enters the previous sign for a few months. Dates are Saturn's actual sidereal sign changes.",
    },
    "hi": {
        "site_name": SITE_NAME,
        "footer_line": "ज्योतिष एक पारंपरिक, आस्था पर आधारित विद्या है। केवल मार्गदर्शन और आत्मचिंतन के लिए।",
        "page": "पृष्ठ", "of": "/",
        "name": "नाम", "dob": "जन्म तिथि", "tob": "जन्म समय", "pob": "जन्म स्थान",
        "coordinates": "अक्षांश-रेखांश", "timezone": "समय क्षेत्र", "report_date": "रिपोर्ट की तिथि",
        "boy": "वर", "girl": "वधू",
        "summary": "सारांश",
        "lagna": "लग्न", "rashi": "राशि (चंद्र राशि)", "nakshatra": "जन्म नक्षत्र",
        "pada": "चरण", "lord": "स्वामी",
        "chart_heading": "लग्न कुंडली (उत्तर भारतीय शैली)",
        "chart_note": "हर भाव में लिखा अंक राशि का क्रमांक है (1 = मेष ... 12 = मीन)। ऊपर बीच का "
                      "चतुर्भुज पहला भाव है; भाव घड़ी की उलटी दिशा में गिने जाते हैं।",
        "retrograde": "वक्री", "legend_lagna": "लग्न",
        "grahas_heading": "ग्रह स्थिति",
        "col_graha": "ग्रह", "col_sign": "राशि", "col_degree": "अंश", "col_nakshatra": "नक्षत्र",
        "col_pada": "चरण", "col_house": "भाव", "col_retro": "वक्री",
        "yes": "हाँ", "no": "नहीं", "always": "सदैव", "lagna_row": "लग्न",
        "dasha_heading": "विंशोत्तरी दशा",
        "current_maha": "वर्तमान महादशा", "current_antar": "वर्तमान अंतर्दशा",
        "balance": "जन्म के समय शेष दशा", "balance_fmt": "{y} वर्ष {m} माह {d} दिन",
        "maha_timeline": "महादशा क्रम", "col_maha": "महादशा", "col_antar": "अंतर्दशा",
        "col_years": "वर्ष", "col_from": "से", "col_to": "तक", "now": "वर्तमान",
        "antar_in_current": "वर्तमान {lord} महादशा की अंतर्दशाएँ",
        "full_dasha": "संपूर्ण विंशोत्तरी तालिका (महादशा और अंतर्दशाएँ)",
        "dasha_note": "पहली महादशा जन्म से पहले शुरू हुई थी; जन्म के समय उसका केवल शेष भाग बचा था। "
                      "वर्तमान दशा {date} के अनुसार है।",
        "calc_note": "गणना स्विस एफेमेरिस से: निरयन राशिचक्र, लाहिरी अयनांश {ayanamsa}, "
                     "संपूर्ण-राशि भाव पद्धति, मध्यम राहु/केतु।",
        "reading": "आपका फलादेश",
        "outlook_table": "वर्षवार दशा और धीमे ग्रहों के राशि परिवर्तन",
        "col_year": "वर्ष", "col_dasha_periods": "दशा (महादशा - अंतर्दशा)",
        "col_ingresses": "धीमे ग्रहों के राशि परिवर्तन", "from_moon": "चंद्र से {n}",
        "ingress_fmt": "{graha} का {sign} राशि में प्रवेश",
        "none": "-",
        "remedies": "उपाय", "how_to": "विधि", "when": "कब",
        "disclaimer": "महत्वपूर्ण सूचना",
        "report_id": "रिपोर्ट क्रमांक",
        "guna_heading": "अष्टकूट गुण मिलान", "gunas": "गुण", "col_koota": "कूट", "col_points": "गुण",
        "total": "कुल", "charts_heading": "लग्न कुंडलियाँ",
        "doshas_heading": "नाड़ी और भकूट दोष", "nadi_dosha": "नाड़ी दोष", "bhakoot_dosha": "भकूट दोष",
        "dosha_absent": "नहीं है", "dosha_present": "है",
        "dosha_cancelled": "है, पर शास्त्रीय अपवाद से इसका परिहार होता है",
        "moon_distance": "चंद्र राशियाँ एक-दूसरे से {a}-{b} हैं",
        "mangal_compare": "मंगल दोष की तुलना",
        "mangal_compatible_both": "दोनों कुंडलियों में मंगल दोष है; परंपरा इसे एक-दूसरे को संतुलित करने वाला मानती है।",
        "mangal_compatible_none": "दोनों में से किसी भी कुंडली में मंगल दोष नहीं है।",
        "mangal_one_sided": "एक कुंडली में मंगल दोष है। परंपरा में दोष कम करने वाले कारकों और दोनों कुंडलियों के "
                            "समग्र बल को देखा जाता है।",
        "mangal_heading": "मंगल दोष की स्थिति", "status": "स्थिति", "intensity": "तीव्रता",
        "mars": "मंगल", "mars_refs": "कुंडली में मंगल कहाँ है",
        "col_counted": "कहाँ से गिना", "col_mars_in": "मंगल का भाव", "col_triggers": "दोष माना जाता है?",
        "from_lagna": "लग्न से", "from_moon_ref": "चंद्र से", "from_venus": "शुक्र से",
        "mangal_rule": "नियम: लग्न, चंद्र और शुक्र से गिनने पर मंगल का पहले, दूसरे, चौथे, सातवें, आठवें या "
                       "बारहवें भाव में होना (संपूर्ण-राशि भाव)।",
        "cancellations": "दोष परिहार के नियम (दोष भंग)", "col_rule": "नियम", "col_applies": "इस कुंडली में",
        "applies": "लागू", "not_applies": "लागू नहीं",
        "sade_heading": "साढ़े साती की स्थिति", "moon_sign": "चंद्र राशि", "saturn_now": "शनि अभी इस राशि में है",
        "as_of": "इस तिथि के अनुसार", "cycle_current": "वर्तमान साढ़े साती", "cycle_next": "अगली साढ़े साती",
        "col_phase": "चरण", "col_saturn_in": "शनि की राशि",
        "sade_note": "एक ही चरण एक से अधिक बार आ सकता है: शनि हर वर्ष वक्री होता है और कभी-कभी कुछ महीनों के "
                     "लिए पिछली राशि में लौट आता है। तिथियाँ शनि के वास्तविक निरयन राशि परिवर्तन की हैं।",
    },
    "mr": {
        "site_name": SITE_NAME,
        "footer_line": "ज्योतिष ही पारंपरिक, श्रद्धेवर आधारित विद्या आहे. केवळ मार्गदर्शन आणि आत्मचिंतनासाठी.",
        "page": "पृष्ठ", "of": "/",
        "name": "नाव", "dob": "जन्मतारीख", "tob": "जन्मवेळ", "pob": "जन्मस्थळ",
        "coordinates": "अक्षांश-रेखांश", "timezone": "वेळ क्षेत्र", "report_date": "अहवालाची तारीख",
        "boy": "वर", "girl": "वधू",
        "summary": "सारांश",
        "lagna": "लग्न", "rashi": "रास (चंद्ररास)", "nakshatra": "जन्मनक्षत्र",
        "pada": "चरण", "lord": "स्वामी",
        "chart_heading": "लग्नकुंडली (उत्तर भारतीय पद्धत)",
        "chart_note": "प्रत्येक स्थानातील अंक हा राशीचा क्रमांक आहे (1 = मेष ... 12 = मीन). वरचा मधला "
                      "चौकोन हे प्रथम स्थान; स्थाने घड्याळाच्या उलट दिशेने मोजली जातात.",
        "retrograde": "वक्री", "legend_lagna": "लग्न",
        "grahas_heading": "ग्रहस्थिती",
        "col_graha": "ग्रह", "col_sign": "रास", "col_degree": "अंश", "col_nakshatra": "नक्षत्र",
        "col_pada": "चरण", "col_house": "स्थान", "col_retro": "वक्री",
        "yes": "होय", "no": "नाही", "always": "नेहमी", "lagna_row": "लग्न",
        "dasha_heading": "विंशोत्तरी दशा",
        "current_maha": "सध्याची महादशा", "current_antar": "सध्याची अंतर्दशा",
        "balance": "जन्मवेळी शिल्लक दशा", "balance_fmt": "{y} वर्षे {m} महिने {d} दिवस",
        "maha_timeline": "महादशांचा क्रम", "col_maha": "महादशा", "col_antar": "अंतर्दशा",
        "col_years": "वर्षे", "col_from": "पासून", "col_to": "पर्यंत", "now": "सध्या",
        "antar_in_current": "सध्याच्या {lord} महादशेतील अंतर्दशा",
        "full_dasha": "संपूर्ण विंशोत्तरी तक्ता (महादशा आणि अंतर्दशा)",
        "dasha_note": "पहिली महादशा जन्मापूर्वीच सुरू झाली होती; जन्मवेळी तिचा फक्त शिल्लक भाग उरला होता. "
                      "सध्याची दशा {date} या तारखेनुसार दिली आहे.",
        "calc_note": "गणित स्विस एफेमेरिसवर आधारित: निरयन राशिचक्र, लाहिरी अयनांश {ayanamsa}, "
                     "संपूर्ण-रास स्थानपद्धत, मध्यम राहू/केतू.",
        "reading": "तुमचे फलादेश",
        "outlook_table": "वर्षनिहाय दशा आणि मंद ग्रहांचे राशीबदल",
        "col_year": "वर्ष", "col_dasha_periods": "दशा (महादशा - अंतर्दशा)",
        "col_ingresses": "मंद ग्रहांचे राशीबदल", "from_moon": "चंद्रापासून {n}",
        "ingress_fmt": "{graha} {sign} राशीत",
        "none": "-",
        "remedies": "उपाय", "how_to": "कसे करावे", "when": "केव्हा",
        "disclaimer": "महत्त्वाची सूचना",
        "report_id": "अहवाल क्रमांक",
        "guna_heading": "अष्टकूट गुणमेलन", "gunas": "गुण", "col_koota": "कूट", "col_points": "गुण",
        "total": "एकूण", "charts_heading": "लग्नकुंडल्या",
        "doshas_heading": "नाडी आणि भकूट दोष", "nadi_dosha": "नाडी दोष", "bhakoot_dosha": "भकूट दोष",
        "dosha_absent": "नाही", "dosha_present": "आहे",
        "dosha_cancelled": "आहे, परंतु शास्त्रीय अपवादामुळे त्याचा परिहार होतो",
        "moon_distance": "चंद्रराशी एकमेकींपासून {a}-{b} आहेत",
        "mangal_compare": "मंगळ दोषाची तुलना",
        "mangal_compatible_both": "दोन्ही कुंडल्यांत मंगळ दोष आहे; परंपरेनुसार असे दोष एकमेकांना संतुलित करतात.",
        "mangal_compatible_none": "दोन्हीपैकी कोणत्याही कुंडलीत मंगळ दोष नाही.",
        "mangal_one_sided": "एका कुंडलीत मंगळ दोष आहे. परंपरेनुसार दोष सौम्य करणारे घटक आणि दोन्ही कुंडल्यांचे "
                            "एकूण बळ पाहिले जाते.",
        "mangal_heading": "मंगळ दोषाची स्थिती", "status": "स्थिती", "intensity": "तीव्रता",
        "mars": "मंगळ", "mars_refs": "कुंडलीत मंगळ कोठे आहे",
        "col_counted": "कोठून मोजले", "col_mars_in": "मंगळाचे स्थान", "col_triggers": "दोष धरला जातो का?",
        "from_lagna": "लग्नापासून", "from_moon_ref": "चंद्रापासून", "from_venus": "शुक्रापासून",
        "mangal_rule": "नियम: लग्न, चंद्र आणि शुक्र यांच्यापासून मोजल्यावर मंगळ पहिल्या, दुसऱ्या, चौथ्या, सातव्या, "
                       "आठव्या किंवा बाराव्या स्थानी असणे (संपूर्ण-रास स्थानपद्धत).",
        "cancellations": "दोष परिहाराचे नियम (दोषभंग)", "col_rule": "नियम", "col_applies": "या कुंडलीत",
        "applies": "लागू", "not_applies": "लागू नाही",
        "sade_heading": "साडेसातीची स्थिती", "moon_sign": "चंद्ररास", "saturn_now": "शनी सध्या या राशीत आहे",
        "as_of": "या तारखेनुसार", "cycle_current": "सध्याची साडेसाती", "cycle_next": "पुढील साडेसाती",
        "col_phase": "टप्पा", "col_saturn_in": "शनीची रास",
        "sade_note": "एकच टप्पा एकापेक्षा जास्त वेळा येऊ शकतो: शनी दरवर्षी वक्री होतो आणि कधीकधी काही महिन्यांसाठी "
                     "मागील राशीत परत येतो. तारखा शनीच्या प्रत्यक्ष निरयन राशीबदलांच्या आहेत.",
    },
}

# ---- the book (Phase 4 rebuild: the Kundali report is a print-and-bind book) ------------------------
# Merged into T below, so every key exists in all three languages (tests/test_pdf.py checks that).

BOOK_T = {
    "en": {
        "contents": "Contents", "part": "Part", "running_title": "Kundali Report",
        "prepared_for": "Prepared for", "cover_tagline": "Your personal Vedic birth-chart book",
        "cover_note": "Calculated with the Swiss Ephemeris - interpreted for this chart alone",
        "navamsa_heading": "Navamsa chart (D9)", "vargottama": "Vargottama (same sign in D1 and D9)",
        "navamsa_note": "The navamsa (D9) is the ninth division of the zodiac. Tradition reads it alongside the "
                        "lagna chart for the strength of a graha and for marriage and later life.",
        "col_combust": "Combust", "combust_note": "\"Combust\" means the graha is close to the Sun and its "
                                                  "significations are read as muted for a while.",
        "gemstone_heading": "Gemstone", "gem_stone": "Stone", "gem_finger": "Finger", "gem_day": "Day to begin",
        "gem_metal": "Metal", "gem_avoid": "Better avoided",
        "hl_mangal": "Mangal dosha", "hl_sade": "Sade sati", "hl_dasha": "Current period",
        "hl_strengths": "Three strengths of this chart", "hl_cautions": "Three things to watch",
        "hl_yogas": "Yogas present in this chart", "hl_remedy": "Remedy", "hl_guidance": "Guidance",
        "timeline_heading": "Life timeline", "round": "round {n}",
        "cycle_note": "This table is the FIRST 120-year Vimshottari cycle, counted from birth. A life longer "
                      "than that begins the same sequence again, so the period running now belongs to round "
                      "{n} and falls after the last row above.", "saturn_phase": "Shani", "col_kind": "Kind", "col_nature": "Nature", "col_strength": "Strength", "col_period": "Period", "col_theme": "Theme",
        "station_retro_fmt": "{graha} turns retrograde in {sign}",
        "station_direct_fmt": "{graha} turns direct in {sign}",
        "areas_heading": "Life areas in this window",
        "of_pages": "Page {n}",
        "toc_note": "Page numbers refer to the printed pages of this book.",
    },
    "hi": {
        "contents": "अनुक्रमणिका", "part": "भाग", "running_title": "कुंडली रिपोर्ट",
        "prepared_for": "यह रिपोर्ट इनके लिए", "cover_tagline": "आपकी अपनी जन्म कुंडली पुस्तिका",
        "cover_note": "गणना स्विस एफेमेरिस से - फलादेश केवल इसी कुंडली के आधार पर",
        "navamsa_heading": "नवांश कुंडली (D9)", "vargottama": "वर्गोत्तम (D1 और D9 में एक ही राशि)",
        "navamsa_note": "नवांश (D9) राशिचक्र का नौवाँ विभाग है। परंपरा में ग्रह के बल के लिए तथा विवाह और उत्तर "
                        "जीवन के लिए इसे लग्न कुंडली के साथ देखा जाता है।",
        "col_combust": "अस्त", "combust_note": "\"अस्त\" का अर्थ है ग्रह सूर्य के बहुत निकट है; कुछ समय के लिए "
                                               "उसके फल मंद माने जाते हैं।",
        "gemstone_heading": "रत्न", "gem_stone": "रत्न", "gem_finger": "उँगली", "gem_day": "धारण का दिन",
        "gem_metal": "धातु", "gem_avoid": "इनसे बचें",
        "hl_mangal": "मंगल दोष", "hl_sade": "साढ़े साती", "hl_dasha": "वर्तमान दशा",
        "hl_strengths": "इस कुंडली की तीन शक्तियाँ", "hl_cautions": "तीन बातें जिन पर ध्यान दें",
        "hl_yogas": "इस कुंडली में बनने वाले योग", "hl_remedy": "उपाय", "hl_guidance": "मार्गदर्शन",
        "timeline_heading": "जीवन की समय-रेखा", "round": "चक्र {n}",
        "cycle_note": "यह तालिका जन्म से गिना गया पहला 120-वर्षीय विंशोत्तरी चक्र है। इससे लंबे जीवन में वही क्रम "
                      "दोबारा शुरू होता है, इसलिए वर्तमान दशा {n} वें चक्र की है और ऊपर की अंतिम पंक्ति के बाद आती है.", "saturn_phase": "शनि", "col_kind": "प्रकार", "col_nature": "स्वभाव", "col_strength": "बल", "col_period": "अवधि", "col_theme": "मुख्य बात",
        "station_retro_fmt": "{graha} {sign} राशि में वक्री",
        "station_direct_fmt": "{graha} {sign} राशि में मार्गी",
        "areas_heading": "इस अवधि में सक्रिय जीवन-क्षेत्र",
        "of_pages": "पृष्ठ {n}",
        "toc_note": "पृष्ठ क्रमांक इसी पुस्तिका के मुद्रित पृष्ठों के हैं।",
    },
    "mr": {
        "contents": "अनुक्रमणिका", "part": "भाग", "running_title": "कुंडली अहवाल",
        "prepared_for": "हा अहवाल यांच्यासाठी", "cover_tagline": "तुमची स्वतःची जन्मकुंडली पुस्तिका",
        "cover_note": "गणना स्विस एफेमेरिसने - फलादेश केवळ याच कुंडलीवर आधारित",
        "navamsa_heading": "नवांश कुंडली (D9)", "vargottama": "वर्गोत्तम (D1 आणि D9 मध्ये एकच रास)",
        "navamsa_note": "नवांश (D9) हा राशिचक्राचा नववा विभाग आहे. ग्रहाचे बळ तसेच विवाह आणि उत्तरायुष्य "
                        "पाहण्यासाठी परंपरेत ही कुंडली लग्नकुंडलीसोबत पाहिली जाते.",
        "col_combust": "अस्त", "combust_note": "\"अस्त\" म्हणजे ग्रह सूर्याच्या अगदी जवळ आहे; काही काळ त्याचे "
                                               "फळ मंद मानले जाते.",
        "gemstone_heading": "रत्न", "gem_stone": "रत्न", "gem_finger": "बोट", "gem_day": "धारण करण्याचा दिवस",
        "gem_metal": "धातू", "gem_avoid": "हे टाळावे",
        "hl_mangal": "मंगळ दोष", "hl_sade": "साडेसाती", "hl_dasha": "सध्याची दशा",
        "hl_strengths": "या कुंडलीची तीन बलस्थाने", "hl_cautions": "लक्ष ठेवण्याच्या तीन गोष्टी",
        "hl_yogas": "या कुंडलीत असलेले योग", "hl_remedy": "उपाय", "hl_guidance": "मार्गदर्शन",
        "timeline_heading": "आयुष्याचा कालपट", "round": "चक्र {n}",
        "cycle_note": "हा तक्ता जन्मापासून मोजलेले पहिले 120 वर्षांचे विंशोत्तरी चक्र आहे. त्याहून दीर्घ आयुष्यात तोच क्रम "
                      "पुन्हा सुरू होतो, म्हणून सध्याची दशा {n} व्या चक्रातील असून वरील शेवटच्या ओळीनंतर येते.", "saturn_phase": "शनी", "col_kind": "प्रकार", "col_nature": "स्वभाव", "col_strength": "बळ", "col_period": "कालावधी", "col_theme": "मुख्य सूत्र",
        "station_retro_fmt": "{graha} {sign} राशीत वक्री",
        "station_direct_fmt": "{graha} {sign} राशीत मार्गी",
        "areas_heading": "या कालावधीत सक्रिय जीवनक्षेत्रे",
        "of_pages": "पृष्ठ {n}",
        "toc_note": "पृष्ठ क्रमांक याच पुस्तिकेच्या छापील पानांचे आहेत.",
    },
}

for _lang, _extra in BOOK_T.items():
    T[_lang].update(_extra)

# ---- the trust box, the accuracy caveats, and the free Basic Chart PDF -------------------------------
# Merged into T below, so every key exists in all three languages (tests/test_pdf.py checks that).
#
# TRUST BOX (a trust requirement): it goes on the FIRST PAGE of every PDF we make,
# paid or free. Its real job is not to sell: it is to tell a reader that the DATES were computed rather
# than invented, which is the one thing an "AI astrology" product has to answer. So `trust_calc` names
# Swiss Ephemeris and what it produced, and only then does `trust_ai` say what the AI did. The two are
# always printed together, in that order - the guideline everywhere is that AI is never mentioned
# without Swiss Ephemeris in the same section, and `trust_no_ai` is the free PDF's version of that: it
# has no AI text at all, and says so rather than leaving the reader to wonder.
#
# ACCURACY CAVEATS: the same two notes the chart page shows (app/static/js/render.js, `accuracyHtml`),
# word for word, so a customer who reads the page and then the PDF is told the same thing twice rather
# than two different things once. They are printed only when `chart["accuracy"]` sets the flag, which is
# about 6% of charts. Marathi has its own place template because it attaches the postposition to the
# noun; the clock note names the ERA from `ERA_NAMES` below rather than interpolating the engine's
# English `era_label`, which would drop an English clause into a Devanagari sentence.
FREE_T = {
    "en": {
        "trust_heading": "How this report was made",
        "trust_heading_chart": "How this chart was made",
        "trust_calc": "Your birth details were converted into exact planetary positions using the Swiss "
                      "Ephemeris - the astronomical calculation library trusted by observatories and "
                      "professional astrologers worldwide. Every date, dasha period and dosha status here "
                      "comes directly from that calculation, not from guesswork.",
        "trust_ai": "AI is used only to explain what the chart shows, in clear language.",
        "trust_no_ai": "Nothing in this chart was written by AI. There is no interpretation in it at all: "
                       "every line is a calculated value or the label of one.",
        "acc_heading": "Worth knowing about this chart",
        "acc_place": "The rising sign is close to a boundary here: a birthplace about {km}\u00a0{unit} from "
                     "{place} would make it {adjacent} instead of {lagna}. Your Moon sign, nakshatra and "
                     "dasha dates do not depend on the birthplace.",
        "acc_place_here": "The rising sign is close to a boundary here: a birthplace about {km}\u00a0{unit} "
                          "from the place you entered would make it {adjacent} instead of {lagna}. Your Moon "
                          "sign, nakshatra and dasha dates do not depend on the birthplace.",
        "acc_km": "km",
        "acc_clock": "This birth was converted on the clock in civil use at the time - {era}, {minutes} "
                     "minutes {direction} today's Indian Standard Time. If the time you have was written "
                     "down by today's clock, the rising sign may differ.",
        "acc_clock_plain": "This birth was converted on {offset}, which is not today's Indian Standard Time. "
                           "If the time you have was written down by today's clock, the rising sign may differ.",
        "acc_ahead": "ahead of", "acc_behind": "behind",
        # Bhagavad Gita 2.47, then what it means, then - separately - what WE take from it. Kept in three
        # fields on purpose: run together they read as a translation, and the verse is about action and
        # its fruits, not about astrology. Claiming scripture for our own sentence is the same false and
        # checkable sourcing claim that app/web/policies.py rules out for the Bhrigu Samhita.
        "verse": "कर्मण्येवाधिकारस्ते",
        "verse_translit": "Karmanye vadhikaraste",   # Latin only where the reader has no Devanagari
        "verse_gloss": "\u201cyours is the right to action alone\u201d \u2014 Bhagavad Gita 2.47",
        "verse_ours": "In that spirit: astrology only shows the path; the decision and effort are yours.",
        "acc_approx_time": "The birth time here was chosen from a range, not recorded to the minute, so read this "
                           "as a sketch rather than a record. The nearest option on the form can be up to ninety "
                           "minutes from your real time. Over ninety minutes the lagna changes for about three "
                           "charts in four; the houses follow it, and the mangal dosha verdict comes out "
                           "differently for about one chart in ten. The dasha dates move by more than a year for "
                           "about two charts in five - though never by more than about a year and a half, because "
                           "that is as far as the Moon can travel in ninety minutes. The slower things are "
                           "steadier but not fixed: the nakshatra and the running mahadasha each change for about "
                           "one chart in fifteen, the Moon sign for one in forty, and even sade sati for fewer "
                           "than one in two hundred. Nothing here is independent of your birth time - if you find "
                           "an exact one later, this chart is worth making again.",
        "acc_approx_dasha": "These dates come from an approximate birth time: over ninety minutes they move by "
                            "more than a year for about two charts in five, and can never move by more than about "
                            "a year and a half.",
        "basic_title": "Basic Birth Chart",
        "basic_product": "Free chart PDF",
        "basic_running_title": "Birth Chart",
        "basic_tagline": "Calculated with the Swiss Ephemeris",
        "basic_note": "Every value in this PDF is calculated. Nothing in it was written by AI.",
        "as_of_note": "Current periods are as of {date}.",
        "excluded_heading": "What this free chart does not include",
        "excluded_note": "Those are what the paid Kundali reports add. This free chart is the calculation "
                         "on its own - the same calculation the paid reports are built on.",
    },
    "hi": {
        "trust_heading": "यह रिपोर्ट कैसे बनी",
        "trust_heading_chart": "यह कुंडली कैसे बनी",
        "trust_calc": "आपके जन्म विवरण से ग्रहों की सटीक स्थिति स्विस एफेमेरिस से निकाली गई है - वही खगोलीय गणना "
                      "लाइब्रेरी जिस पर दुनिया भर की वेधशालाएँ और पेशेवर ज्योतिषी भरोसा करते हैं। यहाँ की हर तिथि, हर "
                      "दशा अवधि और हर दोष की स्थिति सीधे उसी गणना से आती है, अनुमान से नहीं।",
        "trust_ai": "AI का काम केवल इतना है कि यह गणना क्या कहती है, उसे सरल भाषा में समझाए।",
        "trust_no_ai": "इस कुंडली में कुछ भी AI ने नहीं लिखा है। इसमें फलादेश है ही नहीं: हर पंक्ति या तो गणना का "
                       "मान है या उसका शीर्षक।",
        "acc_heading": "इस कुंडली के बारे में जान लेना अच्छा है",
        "acc_place": "यहाँ लग्न राशि की संधि पास है: जन्मस्थान {place} से लगभग {km}\u00a0{unit} दूर होता तो लग्न "
                     "{lagna} की जगह {adjacent} होता। आपकी चंद्र राशि, नक्षत्र और दशाओं की तिथियाँ जन्मस्थान पर "
                     "निर्भर नहीं करतीं।",
        "acc_place_here": "यहाँ लग्न राशि की संधि पास है: जन्मस्थान आपके बताए स्थान से लगभग {km}\u00a0{unit} दूर "
                          "होता तो लग्न {lagna} की जगह {adjacent} होता। आपकी चंद्र राशि, नक्षत्र और दशाओं की तिथियाँ "
                          "जन्मस्थान पर निर्भर नहीं करतीं।",
        "acc_km": "किमी",
        "acc_clock": "इस जन्म की गणना उस समय प्रचलित घड़ी के अनुसार की गई है - {era}, जो आज के भारतीय मानक समय से "
                     "{minutes} मिनट {direction} है। यदि आपके पास लिखा समय आज की घड़ी के हिसाब से है, तो लग्न बदल "
                     "सकता है।",
        "acc_clock_plain": "इस जन्म की गणना {offset} के अनुसार की गई है, जो आज का भारतीय मानक समय नहीं है। यदि "
                           "आपके पास लिखा समय आज की घड़ी के हिसाब से है, तो लग्न बदल सकता है।",
        "acc_ahead": "आगे", "acc_behind": "पीछे",
        "verse": "कर्मण्येवाधिकारस्ते",
        "verse_translit": "",
        "verse_gloss": "\u201cकर्म पर ही तुम्हारा अधिकार है\u201d \u2014 भगवद्गीता 2.47",
        "verse_ours": "इसी भाव में: ज्योतिष केवल मार्गदर्शन देता है; निर्णय और परिश्रम आपके हाथ में है।",
        "acc_approx_time": "यहाँ जन्म समय एक अवधि में से चुना गया है, मिनट तक दर्ज नहीं - इसलिए इसे रिकॉर्ड नहीं, "
                           "एक अनुमान की तरह पढ़ें। फ़ॉर्म पर चुना गया निकटतम विकल्प आपके वास्तविक समय से डेढ़ घंटे तक "
                           "दूर हो सकता है। डेढ़ घंटे में लगभग चार में से तीन कुंडलियों का लग्न बदल जाता है; भाव उसके "
                           "साथ चलते हैं, और लगभग हर दसवीं कुंडली में मंगल दोष का निर्णय अलग निकलता है। दशाओं की "
                           "तिथियाँ लगभग हर पाँच में से दो कुंडलियों में एक वर्ष से अधिक खिसकती हैं - पर डेढ़ वर्ष से "
                           "अधिक कभी नहीं, क्योंकि डेढ़ घंटे में चंद्रमा इससे आगे चल ही नहीं सकता। धीमे चलने वाली बातें "
                           "अधिक स्थिर हैं, पर अटल नहीं: नक्षत्र और वर्तमान महादशा का स्वामी, दोनों लगभग हर पंद्रहवीं "
                           "कुंडली में बदलते हैं, चंद्र राशि हर चालीसवीं में, और साढ़ेसाती दो सौ में से एक से भी कम में। "
                           "यहाँ कुछ भी जन्म समय से पूरी तरह स्वतंत्र नहीं है - आगे सटीक समय मिल जाए तो यह कुंडली "
                           "दोबारा बनवाना ठीक रहेगा।",
        "acc_approx_dasha": "ये तिथियाँ अनुमानित जन्म समय से निकली हैं: डेढ़ घंटे में ये लगभग हर पाँच में से दो "
                            "कुंडलियों में एक वर्ष से अधिक खिसकती हैं, और डेढ़ वर्ष से अधिक कभी नहीं।",
        "basic_title": "मूल जन्म कुंडली",
        "basic_product": "निःशुल्क कुंडली PDF",
        "basic_running_title": "जन्म कुंडली",
        "basic_tagline": "स्विस एफेमेरिस से गणना की गई",
        "basic_note": "इस PDF का हर मान गणना से आया है। इसमें कुछ भी AI ने नहीं लिखा।",
        "as_of_note": "वर्तमान दशा {date} के अनुसार है।",
        "excluded_heading": "इस निःशुल्क कुंडली में क्या नहीं है",
        "excluded_note": "ये सब सशुल्क कुंडली रिपोर्ट में मिलते हैं। यह निःशुल्क कुंडली केवल गणना है - वही गणना "
                         "जिस पर सशुल्क रिपोर्ट भी बनती है।",
    },
    "mr": {
        "trust_heading": "हा अहवाल कसा तयार झाला",
        "trust_heading_chart": "ही कुंडली कशी तयार झाली",
        "trust_calc": "तुमच्या जन्मतपशिलावरून ग्रहांची नेमकी स्थिती स्विस एफेमेरिस या खगोलशास्त्रीय गणित-ग्रंथालयातून "
                      "काढली आहे - जगभरातील वेधशाळा आणि व्यावसायिक ज्योतिषी हेच ग्रंथालय वापरतात. इथली प्रत्येक तारीख, "
                      "प्रत्येक दशाकाळ आणि प्रत्येक दोषाची स्थिती थेट त्याच गणितातून येते, अंदाजाने नाही.",
        "trust_ai": "AI चे काम एवढेच: हे गणित काय सांगते ते सोप्या भाषेत समजावून सांगणे.",
        "trust_no_ai": "या कुंडलीतील काहीही AI ने लिहिलेले नाही. यात विवेचन मुळीच नाही: प्रत्येक ओळ म्हणजे गणिताचा "
                       "आकडा किंवा त्याचे शीर्षक.",
        "acc_heading": "या कुंडलीबद्दल आवर्जून लक्षात घ्या",
        "acc_place": "इथे लग्नराशीची संधी जवळ आहे: जन्मस्थळ {place} पासून सुमारे {km}\u00a0{unit} दूर असते तर लग्न "
                     "{lagna} ऐवजी {adjacent} आले असते. तुमची चंद्ररास, नक्षत्र आणि दशांच्या तारखा जन्मस्थळावर "
                     "अवलंबून नाहीत.",
        "acc_place_here": "इथे लग्नराशीची संधी जवळ आहे: जन्मस्थळ तुम्ही दिलेल्या ठिकाणापासून सुमारे {km}\u00a0{unit} "
                          "दूर असते तर लग्न {lagna} ऐवजी {adjacent} आले असते. तुमची चंद्ररास, नक्षत्र आणि दशांच्या "
                          "तारखा जन्मस्थळावर अवलंबून नाहीत.",
        "acc_km": "किमी",
        "acc_clock": "या जन्माची गणना त्या काळी प्रचलित असलेल्या वेळेनुसार केली आहे - {era}, आजच्या भारतीय "
                     "प्रमाणवेळेपेक्षा {minutes} मिनिटे {direction}. तुमच्याकडील वेळ आजच्या घड्याळाने लिहिलेली असेल, "
                     "तर लग्न वेगळे येऊ शकते.",
        "acc_clock_plain": "या जन्माची गणना {offset} नुसार केली आहे, जी आजची भारतीय प्रमाणवेळ नाही. तुमच्याकडील वेळ "
                           "आजच्या घड्याळाने लिहिलेली असेल, तर लग्न वेगळे येऊ शकते.",
        "acc_ahead": "पुढे", "acc_behind": "मागे",
        "verse": "कर्मण्येवाधिकारस्ते",
        "verse_translit": "",
        "verse_gloss": "\u201cकर्मावरच तुमचा अधिकार आहे\u201d \u2014 भगवद्गीता 2.47",
        "verse_ours": "याच भावनेने: ज्योतिष केवळ मार्गदर्शन देते; निर्णय आणि परिश्रम तुमच्या हातात आहेत.",
        "acc_approx_time": "इथली जन्मवेळ एका कालावधीतून निवडली आहे, मिनिटापर्यंत नोंदवलेली नाही - म्हणून ही नोंद "
                           "नव्हे, अंदाज म्हणून वाचा. फॉर्मवरचा सर्वात जवळचा पर्याय तुमच्या खऱ्या वेळेपासून दीड "
                           "तासापर्यंत दूर असू शकतो. दीड तासात जवळपास चारपैकी तीन कुंडल्यांचे लग्न बदलते; स्थाने "
                           "त्याबरोबर सरकतात, आणि जवळपास दर दहाव्या कुंडलीत मंगळ दोषाचा निर्णय वेगळा येतो. दशांच्या "
                           "तारखा जवळपास पाचपैकी दोन कुंडल्यांत एक वर्षाहून अधिक सरकतात - पण दीड वर्षाहून अधिक कधीच "
                           "नाही, कारण दीड तासात चंद्र त्याहून पुढे जाऊच शकत नाही. सावकाश चालणाऱ्या गोष्टी अधिक "
                           "स्थिर आहेत, पण अढळ नाहीत: नक्षत्र आणि चालू महादशेचा स्वामी, दोन्ही जवळपास दर पंधराव्या "
                           "कुंडलीत बदलतात, चंद्ररास दर चाळिसाव्या कुंडलीत, आणि साडेसाती दोनशेपैकी एकाहूनही कमी "
                           "कुंडल्यांत. इथले काहीही जन्मवेळेपासून पूर्णपणे स्वतंत्र नाही - पुढे नेमकी वेळ मिळाली तर "
                           "ही कुंडली पुन्हा काढणे योग्य ठरेल.",
        "acc_approx_dasha": "या तारखा अंदाजे जन्मवेळेवरून आल्या आहेत: दीड तासात त्या जवळपास पाचपैकी दोन कुंडल्यांत "
                            "एक वर्षाहून अधिक सरकतात, आणि दीड वर्षाहून अधिक कधीच नाही.",
        "basic_title": "मूलभूत जन्मकुंडली",
        "basic_product": "मोफत कुंडली PDF",
        "basic_running_title": "जन्मकुंडली",
        "basic_tagline": "स्विस एफेमेरिसने गणित केलेली",
        "basic_note": "या PDF मधील प्रत्येक आकडा गणिताने आलेला आहे. यात काहीही AI ने लिहिलेले नाही.",
        "as_of_note": "सध्याच्या दशा {date} नुसार आहेत.",
        "excluded_heading": "या मोफत कुंडलीत काय नाही",
        "excluded_note": "हे सर्व सशुल्क कुंडली अहवालात मिळते. ही मोफत कुंडली म्हणजे फक्त गणित - सशुल्क अहवालही "
                         "याच गणितावर उभे असतात.",
    },
}

for _lang, _extra in FREE_T.items():
    T[_lang].update(_extra)

# What the free chart leaves out, said plainly. Four lines, the same four in every language, printed in
# order by `Labels.excluded()`. Deliberately no price and no product id: a PDF outlives a price list, and
# app/payments/catalogue.py is the only place an amount may come from. The line that names the paid tiers
# is `excluded_note` above, and it names them without a number.
EXCLUDED_ITEMS = (
    ("Interpretation - what any of this means for you.",
     "फलादेश - इन स्थितियों का आपके लिए क्या अर्थ है।",
     "विवेचन - या स्थितींचा तुमच्यासाठी काय अर्थ आहे."),
    ("The dated timeline: which years matter, and what each period is about.",
     "तारीखों वाली समय-रेखा: कौन से वर्ष महत्वपूर्ण हैं और हर अवधि किस बारे में है।",
     "तारखांचा कालक्रम: कोणती वर्षे महत्त्वाची आणि प्रत्येक काळ कशाबद्दल."),
    ("Remedies, gemstone guidance, and the yogas, strengths and cautions of the chart.",
     "उपाय, रत्न मार्गदर्शन, और कुंडली के योग, बल तथा सावधानियाँ।",
     "उपाय, रत्नांचे मार्गदर्शन, आणि कुंडलीतील योग, बलस्थाने व सावधानतेच्या बाबी."),
    ("The complete Vimshottari table - every mahadasha and antardasha, with dates.",
     "संपूर्ण विंशोत्तरी तालिका - हर महादशा और अंतर्दशा, तिथियों सहित।",
     "संपूर्ण विंशोत्तरी तक्ता - प्रत्येक महादशा आणि अंतर्दशा, तारखांसह."),
)

# `accuracy["clock"]["era"]` -> the era's name in the reader's language. The engine also ships
# `era_label`, but that is English prose, so it is used only as an English-page fallback for an era key
# this table does not know yet.
ERA_NAMES = {
    "madras_time": ("Madras time", "मद्रास समय", "मद्रास वेळ"),
    "wartime": ("India's wartime clock of 1942-45", "1942-45 की युद्धकालीन घड़ी", "1942-45 मधील युद्धकाळातील वेळ"),
    "calcutta_local_mean_time": ("Calcutta local mean time", "कलकत्ता का स्थानीय मध्यमान समय",
                                 "कलकत्त्याची स्थानिक मध्यम वेळ"),
    "ist": ("Indian Standard Time", "भारतीय मानक समय", "भारतीय प्रमाणवेळ"),
}

# The eight PARTS of the Kundali book, A-H, in order. The letter is the position, not an id.
PART_IDS = ("highlights", "chart_basics", "personality", "timeline", "life_areas", "doshas_remedies",
            "year_table", "closing")
PART_LABELS = {
    "highlights": ("Your chart in one page", "आपकी कुंडली एक पृष्ठ में", "तुमची कुंडली एका पानात"),
    "chart_basics": ("The charts and the grahas", "कुंडलियाँ और ग्रह", "कुंडल्या आणि ग्रह"),
    "personality": ("Personality and life themes", "व्यक्तित्व और जीवन के सूत्र", "व्यक्तिमत्त्व आणि जीवनसूत्रे"),
    "timeline": ("Your life timeline", "आपके जीवन की समय-रेखा", "तुमच्या आयुष्याचा कालपट"),
    "life_areas": ("Life area by life area", "जीवन के हर क्षेत्र का फलादेश", "प्रत्येक जीवनक्षेत्राचा आढावा"),
    "doshas_remedies": ("Doshas, remedies and gemstone", "दोष, उपाय और रत्न", "दोष, उपाय आणि रत्न"),
    # the same part has been called both things while the book settled; keep a heading for either id
    "remedies": ("Doshas, remedies and gemstone", "दोष, उपाय और रत्न", "दोष, उपाय आणि रत्न"),
    "reading": ("Your reading", "आपका फलादेश", "तुमचे फलादेश"),
    "year_table": ("Year by year, at a glance", "वर्षवार सार-तालिका", "वर्षनिहाय सारतक्ता"),
    "closing": ("Closing", "समापन", "समारोप"),
}
CHAPTER_LABELS = {
    # A (the chapter, and the keys of the highlight items inside it)
    "at_a_glance": ("At a glance", "एक नज़र में", "एका दृष्टिक्षेपात"),
    "basics": ("The three basics", "तीन मूल बातें", "तीन मूलभूत गोष्टी"),
    "mangal": ("Mangal dosha", "मंगल दोष", "मंगळ दोष"),  # the highlights key; "mangal_dosha" is the chapter
    "dasha": ("The period you are in", "चल रही दशा", "सध्या सुरू असलेली दशा"),
    "strengths": ("Three strengths", "तीन शक्तियाँ", "तीन बलस्थाने"),
    "cautions": ("Three things to watch", "तीन सावधानियाँ", "तीन सावधानता"),
    "yogas": ("Yogas in this chart", "इस कुंडली के योग", "या कुंडलीतील योग"),
    # B
    "what_your_chart_looks_like": ("What your chart looks like", "आपकी कुंडली कैसी है", "तुमची कुंडली कशी आहे"),
    "navamsa": ("The navamsa (D9)", "नवांश (D9)", "नवांश (D9)"),
    "lagna_chart": ("Lagna chart (D1)", "लग्न कुंडली (D1)", "लग्नकुंडली (D1)"),
    "navamsa_chart": ("Navamsa chart (D9)", "नवांश कुंडली (D9)", "नवांश कुंडली (D9)"),
    "graha_positions": ("Where every graha sits", "हर ग्रह की स्थिति", "प्रत्येक ग्रहाची स्थिती"),
    "chart_intro": ("What your chart looks like", "आपकी कुंडली कैसी है", "तुमची कुंडली कशी आहे"),
    # C
    "nature_and_mind": ("Nature and mind", "स्वभाव और मन", "स्वभाव आणि मन"),
    "drive_and_relating": ("Drive and relating", "ऊर्जा और नाते", "ऊर्जा आणि नाती"),
    "work_money_health": ("Work, money and health", "काम, धन और स्वास्थ्य", "काम, पैसा आणि आरोग्य"),
    "nature": ("Your nature", "आपका स्वभाव", "तुमचा स्वभाव"),
    "mind": ("Mind and emotions", "मन और भावनाएँ", "मन आणि भावना"),
    "drive": ("Drive and energy", "ऊर्जा और प्रेरणा", "ऊर्जा आणि प्रेरणा"),
    "relationships": ("How you relate to people", "लोगों से आपका रिश्ता", "माणसांशी तुमचे नाते"),
    "work_style": ("How you work", "आपके काम करने का ढंग", "तुमची कामाची पद्धत"),
    "money_habits": ("Your way with money", "धन के प्रति आपका रुझान", "पैशाबाबत तुमचा कल"),
    "health_tendencies": ("Health tendencies", "स्वास्थ्य की प्रवृत्ति", "आरोग्याचा कल"),
    # D
    "past": ("The road so far", "अब तक का सफ़र", "आतापर्यंतचा प्रवास"),
    "current_year": ("This year, month by month", "यह वर्ष, महीने दर महीने", "हे वर्ष, महिन्या-महिन्याने"),
    "next_years": ("The next four years", "अगले चार वर्ष", "पुढील चार वर्षे"),
    "beyond": ("Further ahead", "उसके आगे", "त्यापुढील काळ"),
    # E
    "career": ("Career and profession", "करियर और व्यवसाय", "करिअर आणि व्यवसाय"),
    "money": ("Money and wealth", "धन और संपत्ति", "पैसा आणि संपत्ती"),
    "marriage": ("Marriage and relationships", "विवाह और संबंध", "विवाह आणि नातेसंबंध"),
    "health": ("Health", "स्वास्थ्य", "आरोग्य"),
    "education": ("Education and learning", "शिक्षा और अध्ययन", "शिक्षण आणि अध्ययन"),
    "family_property": ("Family, home and property", "परिवार, घर और संपत्ति", "कुटुंब, घर आणि मालमत्ता"),
    # F
    "mangal_dosha": ("Mangal dosha", "मंगल दोष", "मंगळ दोष"),
    "sade_sati": ("Sade sati", "साढ़े साती", "साडेसाती"),
    "other_doshas": ("Other doshas", "अन्य दोष", "इतर दोष"),
    "gemstone": ("Gemstone", "रत्न", "रत्न"),
    "remedies": ("Remedies", "उपाय", "उपाय"),
    # G / H
    "year_by_year": ("Year by year", "वर्षवार तालिका", "वर्षनिहाय तक्ता"),
    "year_table": ("Year by year", "वर्षवार तालिका", "वर्षनिहाय तक्ता"),
    "closing": ("In closing", "अंत में", "शेवटी"),
    "disclaimer": ("Important notice", "महत्वपूर्ण सूचना", "महत्त्वाची सूचना"),
}
# The gemstone table comes out of the engine in English (metal, finger, day, and the role of each stone).
# These are small closed vocabularies, so the book translates them itself rather than printing English
# words inside a Marathi page. Anything not listed is printed exactly as the engine wrote it.
YOGA_TERMS = {  # the engine's own vocabulary for a yoga's strength, nature and family
    "strong": ("Strong", "प्रबल", "प्रबळ"), "moderate": ("Moderate", "मध्यम", "मध्यम"),
    "mild": ("Mild", "अल्प", "सौम्य"), "weak": ("Weak", "क्षीण", "क्षीण"),
    "benefic": ("Benefic", "शुभ", "शुभ"), "malefic": ("Malefic", "अशुभ", "अशुभ"),
    "challenging": ("Challenging", "कष्टकारक", "कष्टदायक"), "mixed": ("Mixed", "मिश्र", "संमिश्र"),
    "raj": ("Raja yoga", "राज योग", "राज योग"), "dhana": ("Dhana yoga", "धन योग", "धन योग"),
    "mahapurusha": ("Panchamahapurusha yoga", "पंचमहापुरुष योग", "पंचमहापुरुष योग"),
    "dosha": ("Dosha", "दोष", "दोष"),
}

GEM_TERMS = {
    "gold": ("Gold", "सोना", "सोने"), "silver": ("Silver", "चाँदी", "चांदी"),
    "copper": ("Copper", "ताँबा", "तांबे"), "iron": ("Iron", "लोहा", "लोखंड"),
    "bronze": ("Bronze", "काँसा", "कांसे"), "panchdhatu": ("Panchdhatu", "पंचधातु", "पंचधातू"),
    "ring finger": ("Ring finger", "अनामिका", "अनामिका"), "index finger": ("Index finger", "तर्जनी", "तर्जनी"),
    "middle finger": ("Middle finger", "मध्यमा", "मध्यमा"), "little finger": ("Little finger", "कनिष्ठिका", "कनिष्ठिका"),
    "sunday": ("Sunday", "रविवार", "रविवार"), "monday": ("Monday", "सोमवार", "सोमवार"),
    "tuesday": ("Tuesday", "मंगलवार", "मंगळवार"), "wednesday": ("Wednesday", "बुधवार", "बुधवार"),
    "thursday": ("Thursday", "गुरुवार", "गुरुवार"), "friday": ("Friday", "शुक्रवार", "शुक्रवार"),
    "saturday": ("Saturday", "शनिवार", "शनिवार"),
}
GEM_ROLES = {
    "life_stone": ("Life stone (jeevan ratna), for the lagna lord",
                   "जीवन रत्न - लग्नेश का रत्न", "जीवन रत्न - लग्नेशाचे रत्न"),
    "fortune_stone": ("Fortune stone (bhagya ratna), for the 9th lord",
                      "भाग्य रत्न - नवमेश का रत्न", "भाग्य रत्न - नवमेशाचे रत्न"),
    "benefic_stone": ("Benefic stone (ishta ratna), for the 5th lord",
                      "इष्ट रत्न - पंचमेश का रत्न", "इष्ट रत्न - पंचमेशाचे रत्न"),
}

# The life areas a timeline window may be tagged with. The engine owns the list and has already changed it
# twice; `Labels.area()` prints an unknown key as itself rather than failing, so a new one costs nothing.
AREA_LABELS = {
    "career": ("Career", "करियर", "करिअर"),
    "money": ("Money", "धन", "पैसा"),
    "marriage": ("Marriage", "विवाह", "विवाह"),
    "relationships": ("Relationships", "संबंध", "नातेसंबंध"),
    "health": ("Health", "स्वास्थ्य", "आरोग्य"),
    "education": ("Education", "शिक्षा", "शिक्षण"),
    "family": ("Family", "परिवार", "कुटुंब"),
    "property": ("Property", "संपत्ति", "मालमत्ता"),
    "travel": ("Travel", "यात्रा", "प्रवास"),
    "study": ("Study", "अध्ययन", "अभ्यास"),
    "spiritual": ("Inner life", "अध्यात्म", "अध्यात्म"),
}

# Month names and the printed form of a date range belong to the engine now (app/engine/constants.py):
# it owns date formatting for the whole product, so the book and the rashifal pages can never spell a
# month two ways. Nothing here keeps a second table.
MONTHS = ENGINE_MONTHS

PRODUCT_NAMES = {
    "kundali-report": {"en": "Detailed Janam Kundali Report", "hi": "विस्तृत जन्म कुंडली रिपोर्ट",
                       "mr": "सविस्तर जन्मकुंडली अहवाल"},
    "kundali-report-simple": {"en": "Janam Kundali Report", "hi": "जन्म कुंडली रिपोर्ट",
                              "mr": "जन्मकुंडली अहवाल"},
    "matching-report": {"en": "Kundali Matching Report", "hi": "कुंडली मिलान रिपोर्ट", "mr": "कुंडली गुणमेलन अहवाल"},
    "mangal-dosha-remedy": {"en": "Mangal Dosha Remedy Guide", "hi": "मंगल दोष उपाय मार्गदर्शिका",
                            "mr": "मंगळ दोष उपाय मार्गदर्शिका"},
    "sade-sati-guide": {"en": "Sade Sati Guide", "hi": "साढ़े साती मार्गदर्शिका", "mr": "साडेसाती मार्गदर्शिका"},
}

# Used when a section heading is "" (blanked by the Phase 3 redactor). Keyed by (product, section id)
# because ids such as "status" and "guidance" mean different things in different products.
SECTION_LABELS = {
    "kundali-report": {
        "chart_overview": ("Your chart at a glance", "आपकी कुंडली एक नज़र में", "तुमची कुंडली एका दृष्टिक्षेपात"),
        "personality": ("Personality and strengths", "व्यक्तित्व और स्वभाव", "व्यक्तिमत्त्व आणि स्वभाव"),
        "career": ("Career and money", "करियर और धन", "करिअर आणि अर्थकारण"),
        "relationships": ("Relationships, marriage and family", "संबंध, विवाह और परिवार", "नातेसंबंध, विवाह आणि कुटुंब"),
        "current_dasha": ("Your current dasha", "वर्तमान दशा", "सध्याची दशा"),
        "yearly_outlook": ("Year-by-year outlook", "वर्षवार फलादेश", "वर्षनिहाय आढावा"),
        "sade_sati": ("Sade sati", "साढ़े साती", "साडेसाती"),
        "guidance": ("Guidance for the years ahead", "आने वाले वर्षों के लिए मार्गदर्शन", "पुढील वाटचालीसाठी मार्गदर्शन"),
    },
    "matching-report": {
        "overview": ("Guna milan at a glance", "गुण मिलान: एक नज़र में", "गुणमेलन: एका दृष्टिक्षेपात"),
        "koota_analysis": ("The eight kootas", "अष्टकूट विश्लेषण", "अष्टकूट विश्लेषण"),
        "strengths": ("Where you fit naturally", "आपके रिश्ते की ताकत", "तुमच्या नात्याची बलस्थाने"),
        "growth_areas": ("Areas to work on together", "जिन बातों पर साथ मिलकर ध्यान दें", "एकत्र मिळून लक्ष देण्याच्या बाबी"),
        "mangal_dosha": ("Mangal dosha", "मंगल दोष", "मंगळ दोष"),
        "guidance": ("Guidance for the couple and families", "दंपति और परिवारों के लिए मार्गदर्शन",
                     "जोडप्यासाठी आणि कुटुंबांसाठी मार्गदर्शन"),
    },
    "mangal-dosha-remedy": {
        "status": ("Your Mangal dosha status", "आपके मंगल दोष की स्थिति", "तुमच्या मंगळ दोषाची स्थिती"),
        "meaning": ("What Mars means in your chart", "आपकी कुंडली में मंगल का अर्थ", "तुमच्या कुंडलीतील मंगळाचा अर्थ"),
        "mitigating_factors": ("Mitigating factors", "दोष कम करने वाले कारक", "दोष सौम्य करणारे घटक"),
        "marriage": ("Marriage and partnership", "विवाह और साझेदारी", "विवाह आणि सहजीवन"),
        "myths_and_facts": ("Myths and facts", "भ्रम और तथ्य", "गैरसमज आणि वस्तुस्थिती"),
        "daily_practice": ("A simple weekly routine", "सरल साप्ताहिक दिनचर्या", "सोपा साप्ताहिक दिनक्रम"),
    },
    "sade-sati-guide": {
        "status": ("Your sade sati status", "आपकी साढ़े साती की स्थिति", "तुमच्या साडेसातीची स्थिती"),
        "timeline": ("The timeline", "समय-रेखा", "कालक्रम"),
        "work_and_money": ("Work and money", "काम और धन", "काम आणि पैसा"),
        "mind_and_relationships": ("Mind and relationships", "मन और रिश्ते", "मन आणि नातेसंबंध"),
        "myths_and_facts": ("Myths and facts", "भ्रम और तथ्य", "गैरसमज आणि वस्तुस्थिती"),
        "daily_practice": ("A simple routine", "सरल दिनचर्या", "सोपा दिनक्रम"),
    },
}

REMEDY_TYPES = {
    "mantra": ("Mantra", "मंत्र", "मंत्र"), "charity": ("Charity", "दान", "दान"),
    "service": ("Service", "सेवा", "सेवा"), "habit": ("Habit", "आदत", "सवय"),
    "worship": ("Worship", "उपासना", "उपासना"), "meditation": ("Meditation", "ध्यान", "ध्यान"),
}

# ---- display names of engine values ----------------------------------------------------------------

_MR_GRAHAS = {"Mars": "मंगळ", "Jupiter": "गुरू", "Saturn": "शनी", "Rahu": "राहू", "Ketu": "केतू"}
_MR_SIGNS = {"Libra": "तूळ"}

GRAHA_ABBR = {
    "en": {"Lagna": "Lg", "Sun": "Su", "Moon": "Mo", "Mars": "Ma", "Mercury": "Me", "Jupiter": "Ju",
           "Venus": "Ve", "Saturn": "Sa", "Rahu": "Ra", "Ketu": "Ke"},
    "deva": {"Lagna": "ल", "Sun": "सू", "Moon": "चं", "Mars": "मं", "Mercury": "बु", "Jupiter": "गु",
             "Venus": "शु", "Saturn": "श", "Rahu": "रा", "Ketu": "के"},
}

KOOTAS = {
    "varna": (("Varna", "Outlook and values"), ("वर्ण", "दृष्टिकोण और मूल्य"), ("वर्ण", "दृष्टिकोन आणि मूल्ये")),
    "vashya": (("Vashya", "Mutual attraction"), ("वश्य", "परस्पर आकर्षण"), ("वश्य", "परस्पर आकर्षण")),
    "tara": (("Tara", "Fortune and well-being"), ("तारा", "भाग्य और कल्याण"), ("तारा", "भाग्य आणि कल्याण")),
    "yoni": (("Yoni", "Physical compatibility"), ("योनि", "शारीरिक अनुकूलता"), ("योनी", "शारीरिक अनुरूपता")),
    "graha_maitri": (("Graha Maitri", "Mental compatibility"), ("ग्रह मैत्री", "मानसिक अनुकूलता"),
                     ("ग्रहमैत्री", "मानसिक अनुरूपता")),
    "gana": (("Gana", "Temperament"), ("गण", "स्वभाव"), ("गण", "स्वभाव")),
    "bhakoot": (("Bhakoot", "Family harmony and prosperity"), ("भकूट", "पारिवारिक सुख और समृद्धि"),
                ("भकूट", "कौटुंबिक सौख्य आणि समृद्धी")),
    "nadi": (("Nadi", "Constitution and progeny"), ("नाड़ी", "प्रकृति और संतान"), ("नाडी", "प्रकृती आणि संतती")),
}

# Engine value (English) -> (hi, mr). The Sanskrit terms are shared by both traditions.
_KOOTA_VALUES = {
    "Brahmin": ("ब्राह्मण", "ब्राह्मण"), "Kshatriya": ("क्षत्रिय", "क्षत्रिय"), "Vaishya": ("वैश्य", "वैश्य"),
    "Shudra": ("शूद्र", "शूद्र"),
    "Chatushpada": ("चतुष्पाद", "चतुष्पाद"), "Manava": ("मानव", "मानव"), "Jalachara": ("जलचर", "जलचर"),
    "Vanachara": ("वनचर", "वनचर"), "Keeta": ("कीट", "कीटक"),
    "Horse": ("अश्व", "अश्व"), "Elephant": ("गज", "गज"), "Sheep": ("मेष", "मेष"), "Serpent": ("सर्प", "सर्प"),
    "Dog": ("श्वान", "श्वान"), "Cat": ("मार्जार", "मार्जार"), "Rat": ("मूषक", "मूषक"), "Cow": ("गौ", "गो"),
    "Buffalo": ("महिष", "महिष"), "Tiger": ("व्याघ्र", "व्याघ्र"), "Deer": ("मृग", "मृग"), "Monkey": ("वानर", "वानर"),
    "Mongoose": ("नकुल", "नकुल"), "Lion": ("सिंह", "सिंह"),
    "Deva": ("देव", "देव"), "Manushya": ("मनुष्य", "मनुष्य"), "Rakshasa": ("राक्षस", "राक्षस"),
    "Aadi": ("आदि", "आद्य"), "Madhya": ("मध्य", "मध्य"), "Antya": ("अंत्य", "अंत्य"),
}

VERDICTS = {
    "below_average": ("Below the traditional 18-guna mark", "पारंपरिक 18 गुणों से कम", "पारंपरिक 18 गुणांपेक्षा कमी"),
    "average": ("Average match by traditional standards", "पारंपरिक मानकों से मध्यम मिलान", "पारंपरिक निकषांनुसार मध्यम गुणमेलन"),
    "good": ("Good match by traditional standards", "पारंपरिक मानकों से अच्छा मिलान", "पारंपरिक निकषांनुसार चांगले गुणमेलन"),
    "excellent": ("Excellent match by traditional standards", "पारंपरिक मानकों से उत्तम मिलान",
                  "पारंपरिक निकषांनुसार उत्तम गुणमेलन"),
}

MANGAL_STATUS = {
    "none": ("No Mangal dosha", "मंगल दोष नहीं है", "मंगळ दोष नाही"),
    "present": ("Mangal dosha present", "मंगल दोष है", "मंगळ दोष आहे"),
    "mitigated": ("Mangal dosha present, with mitigating factors", "मंगल दोष है, पर उसे कम करने वाले कारक मौजूद हैं",
                  "मंगळ दोष आहे, परंतु तो सौम्य करणारे घटक आहेत"),
}
INTENSITY = {"none": ("None", "नहीं", "नाही"), "low": ("Low", "कम", "कमी"),
             "medium": ("Medium", "मध्यम", "मध्यम"), "high": ("High", "अधिक", "अधिक")}

CANCELLATIONS = {  # key -> (hi, mr); English uses the engine's own description
    "mars_in_own_or_exaltation_sign": (
        "मंगल का अपनी राशि (मेष, वृश्चिक) या उच्च राशि (मकर) में होना",
        "मंगळ स्वराशीत (मेष, वृश्चिक) किंवा उच्च राशीत (मकर) असणे"),
    "jupiter_conjunct_or_aspecting_mars": (
        "गुरु का मंगल के साथ उसी राशि में होना, या मंगल पर गुरु की दृष्टि होना (गुरु से 5वाँ, 7वाँ या 9वाँ भाव)",
        "गुरू मंगळाच्याच राशीत असणे, किंवा मंगळावर गुरूची दृष्टी असणे (गुरूपासून 5 वे, 7 वे किंवा 9 वे स्थान)"),
    "house_sign_exception": (
        "लग्न से मंगल का दूसरे भाव में मिथुन/कन्या, चौथे में मेष/वृश्चिक, सातवें में कर्क/मकर, आठवें में धनु/मीन "
        "या बारहवें में वृषभ/तुला राशि में होना",
        "लग्नापासून मंगळ दुसऱ्या स्थानी मिथुन/कन्या, चौथ्या स्थानी मेष/वृश्चिक, सातव्या स्थानी कर्क/मकर, आठव्या स्थानी "
        "धनु/मीन किंवा बाराव्या स्थानी वृषभ/तूळ राशीत असणे"),
    "cancer_or_leo_lagna": (
        "कर्क और सिंह लग्न के लिए मंगल योगकारक है, इसलिए उसका दोष निष्प्रभावी माना जाता है",
        "कर्क आणि सिंह लग्नासाठी मंगळ योगकारक असल्याने त्याचा दोष निष्प्रभ मानला जातो"),
}

SADE_STATUS = {
    "active": ("Sade sati is active", "साढ़े साती चल रही है", "साडेसाती सुरू आहे"),
    "paused": ("Sade sati is in progress (brief pause)", "साढ़े साती जारी है (अल्प विराम)", "साडेसाती सुरू आहे (तात्पुरता विराम)"),
    "inactive": ("Sade sati is not active now", "अभी साढ़े साती नहीं है", "सध्या साडेसाती नाही"),
}
# phase -> ((label, note) per language, sign offset from the Moon sign)
PHASES = {
    "rising": ((("Rising phase", "Saturn in the 12th sign from the Moon"),
                ("पहला चरण", "शनि चंद्र राशि से 12वीं राशि में"),
                ("पहिला टप्पा", "शनी चंद्रराशीपासून 12 व्या राशीत")), -1),
    "peak": ((("Peak phase", "Saturn over the Moon sign"),
              ("मध्य चरण", "शनि चंद्र राशि में"),
              ("मधला टप्पा", "शनी चंद्रराशीत")), 0),
    "setting": ((("Setting phase", "Saturn in the 2nd sign from the Moon"),
                 ("अंतिम चरण", "शनि चंद्र राशि से दूसरी राशि में"),
                 ("शेवटचा टप्पा", "शनी चंद्रराशीपासून दुसऱ्या राशीत")), 1),
}

# The Shani phases a timeline window may sit in. The three sade-sati phases are in PHASES above; these are
# the two dhaiyas (Shani in the 4th or the 8th from the Moon). A phase key we do not know is not printed at
# all - better a missing line than an English one in a Marathi book.
DHAIYA_PHASES = {
    "dhaiya_fourth": ("Kantaka shani (Shani in the 4th from the Moon)", "कंटक शनि (चंद्र से चौथे भाव में शनि)",
                      "कंटक शनी (चंद्रापासून चौथ्या स्थानी शनी)"),
    "dhaiya_eighth": ("Ashtama shani (Shani in the 8th from the Moon)", "अष्टम शनि (चंद्र से आठवें भाव में शनि)",
                      "अष्टम शनी (चंद्रापासून आठव्या स्थानी शनी)"),
}

_HI_ORDINALS = ["पहला", "दूसरा", "तीसरा", "चौथा", "पाँचवाँ", "छठा", "सातवाँ", "आठवाँ", "नौवाँ", "दसवाँ", "ग्यारहवाँ", "बारहवाँ"]
_MR_ORDINALS = ["पहिले", "दुसरे", "तिसरे", "चौथे", "पाचवे", "सहावे", "सातवे", "आठवे", "नववे", "दहावे", "अकरावे", "बारावे"]


def _pick(triple, lang: str):
    return triple[LANGS.index(lang)]


class Labels:
    """All label lookups for one language. `lang` is validated by the caller (render.py)."""

    def __init__(self, lang: str):
        self.lang = lang
        self.t = T[lang]

    def __getitem__(self, key: str) -> str:
        return self.t[key]

    # -- engine objects --
    def graha(self, graha: dict | str | None) -> str:
        """Graha object ({key,name,devanagari}) or bare key -> display name."""
        if not graha:
            return ""
        if isinstance(graha, str):
            if graha not in GRAHA_KEYS:
                return graha
            graha = graha_name(graha)
        if self.lang == "en":
            return f"{graha['name']} ({graha['key']})" if graha["name"] != graha["key"] else graha["name"]
        if self.lang == "mr":
            return _MR_GRAHAS.get(graha["key"], graha["devanagari"])
        return graha["devanagari"]

    def graha_short(self, graha: dict) -> str:
        return graha["name"] if self.lang == "en" else self.graha(graha)

    def graha_short_key(self, key: str | None) -> str:
        """'Jupiter' (as in sign["lord"]) -> 'Guru' / 'गुरु' / 'गुरू'."""
        return self.graha_short(graha_name(key)) if key in GRAHA_KEYS else (key or "")

    def sign(self, sign: dict | None, *, short: bool = False) -> str:
        if not sign:
            return ""
        if self.lang == "en":
            return sign["name"] if short or sign["key"] == sign["name"] else f"{sign['name']} ({sign['key']})"
        if self.lang == "mr":
            return _MR_SIGNS.get(sign["key"], sign["devanagari"])
        return sign["devanagari"]

    def sign_by_index(self, index: int, **kw) -> str:
        return self.sign(_SIGNS[(index - 1) % 12], **kw)

    def nakshatra(self, nakshatra: dict | None) -> str:
        if not nakshatra:
            return ""
        return nakshatra["name"] if self.lang == "en" else nakshatra["devanagari"]

    def house(self, n: int) -> str:
        """Ordinal house: '12th house' / 'बारहवाँ भाव' / 'बारावे स्थान'."""
        if not isinstance(n, int) or not 1 <= n <= 12:
            return str(n)
        if self.lang == "en":
            return f"{ordinal_en(n)} house"
        return f"{_HI_ORDINALS[n - 1]} भाव" if self.lang == "hi" else f"{_MR_ORDINALS[n - 1]} स्थान"

    def nth(self, n: int) -> str:
        """Bare ordinal for 'Nth from the Moon'."""
        if self.lang == "en":
            return ordinal_en(n)
        if self.lang == "hi":
            return f"{n}वाँ"
        return f"{n} {'ले' if n == 1 else 'रे' if n in (2, 3) else 'थे' if n == 4 else 'वे'}"

    # -- other engine values --
    def koota(self, key: str) -> tuple[str, str]:
        return _pick(KOOTAS[key], self.lang) if key in KOOTAS else (key, "")

    def koota_value(self, koota: str, value) -> str:
        """The boy/girl cell of a koota row. Engine gives English words, nakshatra / sign names or graha keys."""
        if value is None:
            return ""
        value = str(value)
        if self.lang == "en":
            return value
        if koota == "graha_maitri":
            return self.graha(value)
        if koota == "tara":
            for nakshatra in _NAKSHATRAS:
                if nakshatra["name"] == value:
                    return nakshatra["devanagari"]
        if koota == "bhakoot":
            for sign in _SIGNS:
                if sign["name"] == value:
                    return self.sign(sign)
        pair = _KOOTA_VALUES.get(value)
        return pair[0 if self.lang == "hi" else 1] if pair else value

    def verdict(self, key: str) -> str:
        return _pick(VERDICTS[key], self.lang) if key in VERDICTS else str(key)

    def intensity(self, key: str) -> str:
        return _pick(INTENSITY[key], self.lang) if key in INTENSITY else str(key)

    def mangal_status(self, dosha: dict) -> str:
        key = "none" if not dosha.get("present") else "mitigated" if dosha.get("cancellation_applies") else "present"
        return _pick(MANGAL_STATUS[key], self.lang)

    def cancellation(self, rule: dict) -> str:
        if self.lang != "en" and rule.get("key") in CANCELLATIONS:
            return CANCELLATIONS[rule["key"]][0 if self.lang == "hi" else 1]
        return rule.get("description") or rule.get("key", "")

    def sade_status(self, key: str) -> str:
        return _pick(SADE_STATUS[key], self.lang)

    def phase(self, key: str) -> tuple[str, str, int]:
        if key not in PHASES:
            return str(key), "", 0
        texts, offset = PHASES[key]
        label, note = _pick(texts, self.lang)
        return label, note, offset

    def phase_name(self, key: str) -> str:
        """A Shani phase by its engine key - a sade-sati phase or a dhaiya. "" when we have no name for it."""
        if key in PHASES:
            return self.phase(key)[0]
        return _pick(DHAIYA_PHASES[key], self.lang) if key in DHAIYA_PHASES else ""

    def era(self, clock: dict) -> str:
        """The civil-clock era of a birth, named in the reader's language. "" when we have no name for it
        and the reader is not on the English page - better no clause than an English one in Devanagari."""
        key = (clock or {}).get("era")
        if key in ERA_NAMES:
            return _pick(ERA_NAMES[key], self.lang)
        return str((clock or {}).get("era_label") or "") if self.lang == "en" else ""

    def excluded(self) -> list[str]:
        """What the free chart PDF does not include, in this language (EXCLUDED_ITEMS, in order)."""
        return [_pick(item, self.lang) for item in EXCLUDED_ITEMS]

    def remedy_type(self, key: str) -> str:
        return _pick(REMEDY_TYPES[key], self.lang) if key in REMEDY_TYPES else str(key)

    def product(self, slug: str, fallback: str = "") -> str:
        return PRODUCT_NAMES.get(slug, {}).get(self.lang, fallback or slug)

    def section(self, product: str, section_id: str) -> str:
        triple = SECTION_LABELS.get(product, {}).get(section_id)
        return _pick(triple, self.lang) if triple else section_id.replace("_", " ").capitalize()

    # -- formatting --
    def date(self, iso: str | None) -> str:
        """'2024-04-08' -> '8 Apr 2024' / '8 एप्रिल 2024'. Parsed by hand; no timezone maths. NBSPs: never wraps."""
        parts = (iso or "")[:10].split("-")
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            return iso or ""
        year, month, day = (int(p) for p in parts)
        if not 1 <= month <= 12:
            return iso
        return f"{day} {MONTHS[self.lang][month - 1]} {year}"

    def month(self, iso: str | None) -> str:
        """'2028-01-14' -> 'Jan 2028' / 'जनवरी 2028'."""
        parts = (iso or "")[:10].split("-")
        if len(parts) < 2 or not parts[0].isdigit() or not parts[1].isdigit() or not 1 <= int(parts[1]) <= 12:
            return iso or ""
        return f"{MONTHS[self.lang][int(parts[1]) - 1]} {int(parts[0])}"

    def range(self, start: str | None, end: str | None, *, precision: str = "month") -> str:
        """A date range the engine did not already label, printed by the engine's own formatter.

        `end` is the engine's EXCLUSIVE end (it equals the next period's start), so the label names
        `end` minus a day - the last day actually covered. Nothing in the book formats a range by hand:
        `app.engine.format_range` is the only implementation, here and on the rashifal pages alike."""
        first, last = _as_date(start), _as_date(end)
        if first is None and last is None:
            return ""
        if first is None or last is None:
            return self.date(start or end)
        last = max(first, last - dt.timedelta(days=1))
        return _keep_together(format_range(first, last, self.lang, precision))

    def label(self, ranged: dict | None, *, fallback_start=None, fallback_end=None) -> str:
        """The printed range of an engine object that carries its own label ({labels: {en,hi,mr}} or
        {label: "..."}), which is always preferred: the engine chose the precision and the wording."""
        ranged = ranged if isinstance(ranged, dict) else {}
        inner = ranged.get("range") if isinstance(ranged.get("range"), dict) else ranged
        labels = inner.get("labels") if isinstance(inner.get("labels"), dict) else {}
        text = labels.get(self.lang) or labels.get("en") or inner.get("label")
        if isinstance(text, dict):  # an older shape put the languages directly under `label`
            text = text.get(self.lang) or text.get("en")
        if isinstance(text, str) and text.strip():
            return _keep_together(text.strip())
        return self.range(inner.get("start") or fallback_start, inner.get("end") or fallback_end)

    # -- the book --
    def part(self, index: int, part_id: str, heading: str = "") -> str:
        """Heading of part `index` (0-based). The AI heading wins; ours is the fallback."""
        text = (heading or "").strip()
        if text:
            return text
        triple = PART_LABELS.get(part_id)
        return _pick(triple, self.lang) if triple else part_id.replace("_", " ").capitalize()

    def part_letter(self, index: int) -> str:
        """'A' ... 'H' - printed as 'Part A'. Beyond Z it simply becomes a number."""
        return chr(ord("A") + index) if 0 <= index < 26 else str(index + 1)

    def chapter(self, chapter_id: str, heading: str = "") -> str:
        text = (heading or "").strip()
        if text:
            return text
        triple = CHAPTER_LABELS.get(chapter_id)
        return _pick(triple, self.lang) if triple else chapter_id.replace("_", " ").capitalize()

    def yoga_term(self, value) -> str:
        """strength / nature / category of a yoga, as the engine names it, in the report language."""
        key = str(value or "").strip().lower()
        return _pick(YOGA_TERMS[key], self.lang) if key in YOGA_TERMS else str(value or "").strip()

    def gem_term(self, text: str) -> str:
        """A metal / finger / weekday from the engine's gemstone table, in the report language.
        "gold or copper" -> "सोने किंवा तांबे"; anything unknown is printed as the engine wrote it."""
        raw = str(text or "").strip()
        if not raw or self.lang == "en":
            return raw
        joiner = " या " if self.lang == "hi" else " किंवा "
        parts = [part.strip() for part in raw.replace(" and ", " or ").split(" or ") if part.strip()]
        out = [_pick(GEM_TERMS[part.lower()], self.lang) if part.lower() in GEM_TERMS else part for part in parts]
        return joiner.join(out)

    def gem_role(self, entry: dict) -> str:
        """The role of one recommended stone; the engine's own English description is the fallback."""
        triple = GEM_ROLES.get(str(entry.get("role") or "").strip())
        if triple:
            return _pick(triple, self.lang)
        return str(entry.get("role_description") or entry.get("role") or "").strip()

    def area(self, key) -> str:
        """One life-area tag, from any of the shapes a stored report carries.

        The published contract is [{area, text}] (app/ai/schema.py `pair_areas`); reports written before
        that, and the model's own raw output, carry plain strings. Both arrive here. A dict used to go
        straight into AREA_LABELS.get as a key, which raises `unhashable type: dict` - that crashed the
        render of every paid report, so this stays total: unknown shapes print as themselves."""
        if isinstance(key, dict):
            key = key.get("area") or key.get("key") or ""
        elif isinstance(key, (list, tuple)):
            key = key[0] if key else ""
        name = str(key or "").strip()
        triple = AREA_LABELS.get(name)
        return _pick(triple, self.lang) if triple else name.replace("_", " ").capitalize()


def _as_date(iso: str | None):
    try:
        return dt.date.fromisoformat(str(iso)[:10])
    except (TypeError, ValueError):
        return None


def _keep_together(text: str) -> str:
    """Non-breaking spaces inside each end of a range, so "16 Nov" never wraps, while the range itself
    may still break at the dash if a narrow column needs it to."""
    return " \u2013 ".join(part.strip().replace(" ", "\u00a0") for part in text.split("\u2013"))


def ordinal_en(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def fmt_num(value) -> str:
    """17.5 -> '17.5', 5.0 -> '5' (same as the web pages)."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        rounded = round(float(value), 1)
        return str(int(rounded)) if rounded == int(rounded) else str(rounded)
    return "" if value is None else str(value)
