"""Everything the rashifal pages print that is NOT written by the AI: titles, labels, names, dates and the
sentences that describe engine facts (events, sade-sati, panchang) - in English, Marathi and Hindi.

Facts are rendered by this code from the engine brief, never from AI prose, so a date or a house on the
page is always the engine's.
"""

import datetime as dt

from app.engine.constants import sign_info

from .periods import RASHI_SLUGS, URL_RASHI_SLUGS

LANGUAGES = {"en": "English", "mr": "मराठी", "hi": "हिन्दी"}
HTML_LANG = {"en": "en", "mr": "mr", "hi": "hi"}
OG_LOCALE = {"en": "en_IN", "mr": "mr_IN", "hi": "hi_IN"}

_MONTHS = {
    "en": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
           "November", "December"],
    "mr": ["जानेवारी", "फेब्रुवारी", "मार्च", "एप्रिल", "मे", "जून", "जुलै", "ऑगस्ट", "सप्टेंबर", "ऑक्टोबर",
           "नोव्हेंबर", "डिसेंबर"],
    "hi": ["जनवरी", "फरवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर"],
}
_WEEKDAYS = {  # Monday first (date.weekday())
    "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
    "mr": ["सोमवार", "मंगळवार", "बुधवार", "गुरुवार", "शुक्रवार", "शनिवार", "रविवार"],
    "hi": ["सोमवार", "मंगलवार", "बुधवार", "गुरुवार", "शुक्रवार", "शनिवार", "रविवार"],
}

# Marathi spellings where they differ from the engine's (Sanskrit / Hindi) Devanagari.
_MR_GRAHA = {"Mars": "मंगळ", "Saturn": "शनी", "Jupiter": "गुरू", "Rahu": "राहू", "Ketu": "केतू"}
_MR_SIGN = {7: "तूळ"}
_HI_TITHI = {"Purnima": "पूर्णिमा"}
_PLACES = {"Mumbai": "मुंबई"}  # the panchang reference place, in Devanagari for mr / hi
_EN_GRAHA = {"Sun": "Sun", "Moon": "Moon", "Mars": "Mars", "Mercury": "Mercury", "Jupiter": "Jupiter",
             "Venus": "Venus", "Saturn": "Saturn", "Rahu": "Rahu", "Ketu": "Ketu"}

_ORDINALS = {
    "mr": ["पहिले", "दुसरे", "तिसरे", "चौथे", "पाचवे", "सहावे", "सातवे", "आठवे", "नववे", "दहावे", "अकरावे", "बारावे"],
    "hi": ["पहला", "दूसरा", "तीसरा", "चौथा", "पाँचवाँ", "छठा", "सातवाँ", "आठवाँ", "नौवाँ", "दसवाँ", "ग्यारहवाँ", "बारहवाँ"],
}

PERIOD_LABELS = {
    "en": {"today": "Today", "weekly": "This Week", "monthly": "This Month", "6-months": "Next 6 Months",
           "yearly": "Yearly"},
    "mr": {"today": "आज", "weekly": "साप्ताहिक", "monthly": "मासिक", "6-months": "पुढील 6 महिने",
           "yearly": "वार्षिक"},
    "hi": {"today": "आज", "weekly": "साप्ताहिक", "monthly": "मासिक", "6-months": "अगले 6 महीने",
           "yearly": "वार्षिक"},
}

# Query vocabulary - the words each language actually searches with: Hindi = rashifal / राशिफल,
# Marathi = rashi bhavishya / राशिभविष्य,
# English = horoscope. Titles and H1s are made HERE, by code, from the exact query patterns - never by the AI.
# People type Latin transliteration, so Hindi / Marathi titles carry both scripts ("Tula Rashi Today – तुला राशिफल आज").
# {n} = rashi name in the page language's script, {l} = typed transliteration (Tula, Kumbh, Singh),
# {e} = English sign (Libra), {s} = Sanskrit name in Latin (Tula, Kumbha, Simha). Permanent: never date-stamped.
KEYWORD = {"en": "horoscope", "hi": "राशिफल", "mr": "राशिभविष्य"}
_TITLES = {  # (title, h1)
    "en": {
        "today": ("{e} Horoscope Today – {s} Rashi Daily Horoscope", "{e} Horoscope Today ({s} Rashi)"),
        "weekly": ("{e} Weekly Horoscope – {s} Rashi This Week", "{e} Weekly Horoscope ({s} Rashi)"),
        "monthly": ("{e} Horoscope {month} {year} – {s} Rashi Monthly Horoscope",
                    "{e} Horoscope {month} {year} ({s} Rashi)"),
        "6-months": ("{e} Horoscope for the Next 6 Months – {s} Rashi", "{e} Horoscope: Next 6 Months ({s} Rashi)"),
        "yearly": ("{e} Horoscope {year} – {s} Rashi Yearly Horoscope {year}", "{e} Horoscope {year} ({s} Rashi)"),
    },
    "hi": {
        "today": ("{l} Rashi Today – {n} राशिफल आज | Aaj Ka {l} Rashifal", "{l} Rashi Today – {n} राशिफल आज"),
        "weekly": ("{l} Saptahik Rashifal – {n} साप्ताहिक राशिफल", "{l} Saptahik Rashifal – {n} साप्ताहिक राशिफल"),
        "monthly": ("{l} Rashifal {month_latin} {year} – {n} राशिफल {month} {year} | {l} Masik Rashifal",
                    "{l} Rashifal {month_latin} {year} – {n} मासिक राशिफल"),
        "6-months": ("{l} Rashifal Agle 6 Mahine – {n} राशिफल अगले 6 महीने", "{l} Rashifal – {n} राशिफल अगले 6 महीने"),
        "yearly": ("{l} Rashifal {year} – {n} राशिफल {year} | {l} Varshik Rashifal",
                   "{l} Rashifal {year} – {n} वार्षिक राशिफल {year}"),
    },
    "mr": {
        "today": ("{l} Rashi Bhavishya Today – आजचे {n} राशिभविष्य", "{l} Rashi Bhavishya – आजचे {n} राशिभविष्य"),
        "weekly": ("{l} Saptahik Rashi Bhavishya – {n} साप्ताहिक राशिभविष्य", "{l} Saptahik Rashi Bhavishya – {n} साप्ताहिक राशिभविष्य"),
        "monthly": ("{l} Rashi Bhavishya {month_latin} {year} – {n} राशिभविष्य {month} {year} | {l} Masik Rashi Bhavishya",
                    "{l} Rashi Bhavishya {month_latin} {year} – {n} मासिक राशिभविष्य"),
        "6-months": ("{l} Rashi Bhavishya Pudhil 6 Mahine – {n} राशिभविष्य पुढील 6 महिने", "{l} Rashi Bhavishya – {n} राशिभविष्य पुढील 6 महिने"),
        "yearly": ("{l} Rashi Bhavishya {year} – {n} राशिभविष्य {year} | {l} Varshik Rashi Bhavishya",
                   "{l} Rashi Bhavishya {year} – {n} वार्षिक राशिभविष्य {year}"),
    },
}

_META = {
    "en": {
        "today": "Free {e} horoscope today ({s} rashi): career, money, love, family and wellbeing, written from today's "
                 "exact planetary transits by Vedic astrology (Swiss Ephemeris, Lahiri). Updated every day.",
        "weekly": "Free {e} weekly horoscope ({s} rashi), Monday to Sunday: career, money, love and wellbeing, with the "
                  "week's key dates from exact planetary transits. Updated every Monday.",
        "monthly": "Free {e} horoscope for {month} {year} ({s} rashi): career, money, love and wellbeing through the "
                   "month, with every sign change and retrograde date, by Vedic astrology.",
        "6-months": "{e} horoscope for the next 6 months ({s} rashi): career, money, family and wellbeing trends with every "
                    "major transit date, by Vedic astrology. Free, refreshed every month.",
        "yearly": "{e} horoscope {year} ({s} rashi): the whole of {year} - career, money, love, wellbeing, sade sati status "
                  "and all major transit dates, by Vedic astrology. Free, refreshed every month.",
    },
    "mr": {
        "today": "{n} राशीचे आजचे राशिभविष्य मोफत वाचा ({l} rashi bhavishya today): करिअर, पैसा, प्रेम, कुटुंब आणि आरोग्य. आजच्या "
                 "अचूक ग्रहस्थितीवर (स्विस एफेमेरिस, लाहिरी अयनांश) आधारित. दररोज अपडेट.",
        "weekly": "{n} राशीचे साप्ताहिक राशिभविष्य ({l} saptahik rashi bhavishya), सोमवार ते रविवार: करिअर, पैसा, प्रेम आणि आरोग्य, "
                  "तसेच आठवड्यातील महत्त्वाच्या तारखा. अचूक ग्रहगोचरावर आधारित. दर सोमवारी अपडेट.",
        "monthly": "{n} राशीचे {month} {year} चे राशिभविष्य ({l} rashi bhavishya {month_latin} {year}): या महिन्यातील करिअर, "
                   "पैसा, प्रेम आणि आरोग्य, राशीबदल आणि वक्री तारखांसह. मोफत.",
        "6-months": "{n} राशीसाठी पुढील 6 महिन्यांचे राशिभविष्य ({l} rashi bhavishya): करिअर, पैसा, कुटुंब आणि आरोग्य, सर्व महत्त्वाच्या "
                    "ग्रहगोचर तारखांसह. मोफत, दर महिन्याला अपडेट.",
        "yearly": "{n} राशीचे {year} सालचे वार्षिक राशिभविष्य ({l} rashi bhavishya {year}): करिअर, पैसा, प्रेम, आरोग्य, "
                  "साडेसातीची स्थिती आणि सर्व महत्त्वाच्या गोचर तारखा. मोफत, दर महिन्याला अपडेट.",
    },
    "hi": {
        "today": "{n} राशि का आज का राशिफल मुफ़्त पढ़ें ({l} rashi today): करियर, धन, प्रेम, परिवार और स्वास्थ्य। आज की सटीक ग्रह "
                 "स्थिति (स्विस एफेमेरिस, लाहिरी अयनांश) पर आधारित। हर दिन अपडेट।",
        "weekly": "{n} राशि का साप्ताहिक राशिफल ({l} saptahik rashifal), सोमवार से रविवार: करियर, धन, प्रेम और स्वास्थ्य, साथ में "
                  "सप्ताह की महत्वपूर्ण तिथियाँ। सटीक ग्रह गोचर पर आधारित। हर सोमवार अपडेट।",
        "monthly": "{n} राशि का {month} {year} का राशिफल ({l} rashifal {month_latin} {year}): इस महीने करियर, धन, प्रेम और "
                   "स्वास्थ्य, राशि परिवर्तन और वक्री तिथियों के साथ। मुफ़्त।",
        "6-months": "{n} राशि के लिए अगले 6 महीनों का राशिफल ({l} rashifal): करियर, धन, परिवार और स्वास्थ्य, सभी प्रमुख ग्रह गोचर "
                    "तिथियों के साथ। मुफ़्त, हर महीने अपडेट।",
        "yearly": "{n} राशि का {year} का वार्षिक राशिफल ({l} rashifal {year}): करियर, धन, प्रेम, स्वास्थ्य, साढ़ेसाती की "
                  "स्थिति और सभी प्रमुख गोचर तिथियाँ। मुफ़्त, हर महीने अपडेट।",
    },
}

# Hub pages: all 12 rashis on one page. Daily hubs (period "today") and weekly hubs. (title, h1, meta description)
_HUBS = {
    "en": {
        "today": ("Horoscope Today – Free Daily Horoscope for All 12 Zodiac Signs", "Horoscope Today",
                  "Today's horoscope for all 12 zodiac signs, Aries to Pisces: a short daily reading for each sign from exact "
                  "planetary transits by Vedic astrology, with links to the full daily, weekly and yearly horoscopes. Free."),
        "weekly": ("Weekly Horoscope – This Week for All 12 Zodiac Signs", "Weekly Horoscope",
                   "This week's horoscope for all 12 zodiac signs, Monday to Sunday: a short weekly reading for each sign from "
                   "exact planetary transits by Vedic astrology, with links to every full weekly horoscope. Free."),
    },
    "hi": {
        "today": ("Aaj Ka Rashifal – आज का राशिफल | सभी 12 राशियाँ", "Aaj Ka Rashifal – आज का राशिफल",
                  "आज का राशिफल, मेष से मीन तक सभी 12 राशियों के लिए: हर राशि का संक्षिप्त दैनिक राशिफल, आज के सटीक ग्रह गोचर पर "
                  "आधारित, साथ में पूरा दैनिक, साप्ताहिक और वार्षिक राशिफल। मुफ़्त, हर दिन अपडेट।"),
        "weekly": ("Saptahik Rashifal – साप्ताहिक राशिफल | सभी 12 राशियाँ", "Saptahik Rashifal – साप्ताहिक राशिफल",
                   "इस सप्ताह का राशिफल, सोमवार से रविवार, सभी 12 राशियों के लिए: हर राशि का संक्षिप्त साप्ताहिक राशिफल, सटीक ग्रह "
                   "गोचर पर आधारित, साथ में पूरा साप्ताहिक राशिफल। मुफ़्त, हर सोमवार अपडेट।"),
    },
    "mr": {
        "today": ("Rashi Bhavishya – आजचे राशिभविष्य | सर्व 12 राशी", "Rashi Bhavishya – आजचे राशिभविष्य",
                  "आजचे राशिभविष्य, मेष ते मीन सर्व 12 राशींसाठी: प्रत्येक राशीचे थोडक्यात दैनिक राशिभविष्य, आजच्या अचूक ग्रहगोचरावर "
                  "आधारित, तसेच संपूर्ण दैनिक, साप्ताहिक आणि वार्षिक राशिभविष्य. मोफत, दररोज अपडेट."),
        "weekly": ("Saptahik Rashi Bhavishya – साप्ताहिक राशिभविष्य | सर्व 12 राशी", "Saptahik Rashi Bhavishya – साप्ताहिक राशिभविष्य",
                   "या आठवड्याचे राशिभविष्य, सोमवार ते रविवार, सर्व 12 राशींसाठी: प्रत्येक राशीचे थोडक्यात साप्ताहिक राशिभविष्य, अचूक "
                   "ग्रहगोचरावर आधारित, तसेच संपूर्ण साप्ताहिक राशिभविष्य. मोफत, दर सोमवारी अपडेट."),
    },
}

UI = {
    "en": {
        "breadcrumb_home": "Home", "breadcrumb_rashifal": "Rashifal",
        "period_covers": "Period", "updated": "Last updated", "language": "Language",
        "reading_heading": "The reading", "reading_for": "Reading for",
        "career_money": "Career and money", "love_family": "Love and family", "health_wellbeing": "Health and wellbeing",
        "key_dates": "Key dates", "tip": "Tip for this period",
        "lucky_heading": "Colour and number of the day", "lucky_colour": "Colour", "lucky_number": "Number",
        "lucky_day_lord": "Chandra (Moon) supports your rashi today, so the day follows the lord of the weekday, {graha}.",
        "lucky_rashi_lord": "Chandra (Moon) is in a quieter place from your rashi today, so lean on your own rashi lord, {graha}.",
        "panchang_heading": "Panchang today", "vara": "Vara (day)", "tithi": "Tithi", "nakshatra": "Nakshatra",
        "sunrise": "Sunrise", "until": "until", "panchang_note": "Values at sunrise in {place}; times in IST.",
        "moon_heading": "Chandra (Moon) for your rashi",
        "moon_line": "Chandra is in {sign}, nakshatra {nakshatra} - house {house} from your rashi.",
        "chandra_bala_good": "Chandra bala: favourable", "chandra_bala_quiet": "Chandra bala: quieter day",
        "facts_heading": "Graha positions for {rashi}", "facts_as_of": "Positions on {date} (start of the period). "
        "Houses are whole-sign houses counted from {rashi}.",
        "col_graha": "Graha", "col_sign": "Sign (rashi)", "col_nakshatra": "Nakshatra", "col_house": "House from {rashi}",
        "col_motion": "Motion", "retrograde": "Retrograde", "direct": "Direct",
        "events_heading": "Sign changes and retrogrades in this period", "no_events": "No graha changes sign or direction in this period.",
        "col_date": "Date", "col_event": "What happens",
        "stays_heading": "Where the slow grahas stay", "col_from": "From", "col_to": "To",
        "saturn_heading": "Sade sati and dhaiya status",
        "sade_sati_active": "Sade sati is active for {rashi}: {phase} phase, with Shani in house {house} from your rashi"
                            " (this phase: {start} to {end}).",
        "sade_sati_paused": "Sade sati is in progress for {rashi}, but Shani has stepped out of the three signs for now "
                            "(cycle: {start} to {end}).",
        "sade_sati_inactive": "Sade sati is not active for {rashi}. Shani is in house {house} from your rashi.",
        "dhaiya_active": "Shani dhaiya is active: Shani is in house {house} from your rashi ({start} to {end}).",
        "phase_rising": "rising (first)", "phase_peak": "peak (second)", "phase_setting": "setting (third)",
        "pending_title": "A new reading is being prepared",
        "pending_text": "The written reading for this period is on its way. Meanwhile, here are the exact planetary "
                        "facts for {rashi} - calculated with the Swiss Ephemeris, not estimated.",
        "stale_note": "This reading was written for {range}. The next one is being prepared.",
        "other_periods": "More {rashi} rashifal", "other_rashis": "{period} rashifal for other rashis",
        "cta_kundali_title": "Your own chart says more than your rashi",
        "cta_kundali_text": "A rashifal reads only your Moon sign. Your janam kundali shows your lagna, all nine grahas and your dasha - free.",
        "cta_kundali_button": "Create free Janam Kundali",
        "cta_chat_title": "Ask about your own chart",
        "cta_chat_text": "Career, marriage, this year - ask our AI astrologer, who reads your exact birth chart. First 2 answers free.",
        "cta_chat_button": "Start AI consultation",
        "about_heading": "How this rashifal is made",
        "about_text": "Planet positions, sign changes, retrograde dates, tithi and nakshatra on this page are calculated "
                      "with the Swiss Ephemeris (sidereal zodiac, Lahiri ayanamsa). The written reading interprets those "
                      "transits for {rashi} as the Moon sign (janma rashi); it is a general reading, not a personal birth-chart reading.",
        "disclaimer": "Astrology is a traditional faith-based practice. This rashifal is a general reading for a Moon sign, "
                      "offered for reflection and guidance only - not a prediction of certain events and not a substitute "
                      "for professional advice. For health, legal or financial matters, please consult a qualified professional.",
        "ist": "IST",
    },
    "mr": {
        "breadcrumb_home": "मुख्यपृष्ठ", "breadcrumb_rashifal": "राशिभविष्य",
        "period_covers": "कालावधी", "updated": "शेवटचे अपडेट", "language": "भाषा",
        "reading_heading": "राशिभविष्य", "reading_for": "कालावधी",
        "career_money": "करिअर आणि पैसा", "love_family": "प्रेम आणि कुटुंब", "health_wellbeing": "आरोग्य आणि स्वास्थ्य",
        "key_dates": "महत्त्वाच्या तारखा", "tip": "या काळासाठी उपाय",
        "lucky_heading": "आजचा शुभ रंग आणि अंक", "lucky_colour": "शुभ रंग", "lucky_number": "शुभ अंक",
        "lucky_day_lord": "आज चंद्र तुमच्या राशीला अनुकूल आहे, म्हणून आजचा रंग वाराच्या स्वामीचा - {graha}.",
        "lucky_rashi_lord": "आज चंद्र तुमच्या राशीपासून शांत स्थानात आहे, म्हणून तुमच्या राशीस्वामीचा आधार घ्या - {graha}.",
        "panchang_heading": "आजचे पंचांग", "vara": "वार", "tithi": "तिथी", "nakshatra": "नक्षत्र",
        "sunrise": "सूर्योदय", "until": "पर्यंत", "panchang_note": "{place} येथील सूर्योदयाच्या वेळची स्थिती; वेळा भारतीय प्रमाणवेळेनुसार.",
        "moon_heading": "तुमच्या राशीसाठी चंद्र",
        "moon_line": "चंद्र {sign} राशीत, {nakshatra} नक्षत्रात - तुमच्या राशीपासून स्थान {house}.",
        "chandra_bala_good": "चंद्रबळ: अनुकूल", "chandra_bala_quiet": "चंद्रबळ: शांत दिवस",
        "facts_heading": "{rashi} राशीसाठी ग्रहस्थिती", "facts_as_of": "{date} रोजीची (कालावधीच्या सुरुवातीची) ग्रहस्थिती. "
        "स्थाने {rashi} राशीपासून मोजली आहेत.",
        "col_graha": "ग्रह", "col_sign": "राशी", "col_nakshatra": "नक्षत्र", "col_house": "{rashi} राशीपासून स्थान",
        "col_motion": "गती", "retrograde": "वक्री", "direct": "मार्गी",
        "events_heading": "या काळातील राशीबदल आणि वक्री-मार्गी तारखा", "no_events": "या काळात कोणताही ग्रह रास किंवा गती बदलत नाही.",
        "col_date": "तारीख", "col_event": "काय घडते",
        "stays_heading": "मंद गतीचे ग्रह कुठे आहेत", "col_from": "पासून", "col_to": "पर्यंत",
        "saturn_heading": "साडेसाती आणि अडीचकीची स्थिती",
        "sade_sati_active": "{rashi} राशीला साडेसाती सुरू आहे: {phase}, शनी तुमच्या राशीपासून स्थान {house} मध्ये"
                            " (हा टप्पा: {start} ते {end}).",
        "sade_sati_paused": "{rashi} राशीची साडेसाती सुरू आहे, पण सध्या शनी त्या तीन राशींच्या बाहेर आहे (चक्र: {start} ते {end}).",
        "sade_sati_inactive": "{rashi} राशीला सध्या साडेसाती नाही. शनी तुमच्या राशीपासून स्थान {house} मध्ये आहे.",
        "dhaiya_active": "शनीची अडीचकी सुरू आहे: शनी तुमच्या राशीपासून स्थान {house} मध्ये ({start} ते {end}).",
        "phase_rising": "पहिला टप्पा", "phase_peak": "दुसरा (मधला) टप्पा", "phase_setting": "तिसरा टप्पा",
        "pending_title": "नवीन राशिभविष्य तयार होत आहे",
        "pending_text": "या कालावधीचे लिखित राशिभविष्य लवकरच येथे दिसेल. तोपर्यंत {rashi} राशीसाठी अचूक ग्रहस्थिती पाहा - "
                        "स्विस एफेमेरिसने गणित केलेली, अंदाजे नाही.",
        "stale_note": "हे राशिभविष्य {range} या कालावधीसाठी लिहिले होते. पुढील राशिभविष्य तयार होत आहे.",
        "other_periods": "{rashi} राशीचे आणखी राशिभविष्य", "other_rashis": "इतर राशींचे {period} राशिभविष्य",
        "cta_kundali_title": "तुमची कुंडली राशीपेक्षा बरेच काही सांगते",
        "cta_kundali_text": "राशिभविष्य फक्त चंद्रराशीवर आधारित असते. जन्मकुंडलीत तुमचे लग्न, नऊ ग्रह आणि दशा दिसतात - मोफत.",
        "cta_kundali_button": "मोफत जन्मकुंडली बनवा",
        "cta_chat_title": "तुमच्या कुंडलीबद्दल प्रश्न विचारा",
        "cta_chat_text": "करिअर, विवाह, हे वर्ष - तुमची अचूक जन्मकुंडली वाचणाऱ्या AI ज्योतिषाला विचारा. पहिली 2 उत्तरे मोफत.",
        "cta_chat_button": "AI सल्ला सुरू करा",
        "about_heading": "हे राशिभविष्य कसे तयार होते",
        "about_text": "या पानावरील ग्रहस्थिती, राशीबदल, वक्री तारखा, तिथी आणि नक्षत्र स्विस एफेमेरिसने (निरयन राशिचक्र, लाहिरी "
                      "अयनांश) गणित केले आहेत. लिखित राशिभविष्य हे {rashi} या चंद्रराशीसाठी त्या गोचराचे विवेचन आहे; ते सर्वसाधारण "
                      "भविष्य आहे, वैयक्तिक जन्मकुंडलीचे नाही.",
        "disclaimer": "ज्योतिष ही एक पारंपरिक, श्रद्धेवर आधारित विद्या आहे. हे राशिभविष्य चंद्रराशीसाठीचे सर्वसाधारण विवेचन असून "
                      "केवळ चिंतन आणि मार्गदर्शनासाठी आहे - ही निश्चित घटनांची भविष्यवाणी नाही आणि व्यावसायिक सल्ल्याला पर्याय नाही. "
                      "आरोग्य, कायदेशीर किंवा आर्थिक बाबींसाठी कृपया पात्र तज्ज्ञांचा सल्ला घ्या.",
        "ist": "भारतीय वेळ",
    },
    "hi": {
        "breadcrumb_home": "मुखपृष्ठ", "breadcrumb_rashifal": "राशिफल",
        "period_covers": "अवधि", "updated": "अंतिम अपडेट", "language": "भाषा",
        "reading_heading": "राशिफल", "reading_for": "अवधि",
        "career_money": "करियर और धन", "love_family": "प्रेम और परिवार", "health_wellbeing": "स्वास्थ्य और दिनचर्या",
        "key_dates": "महत्वपूर्ण तिथियाँ", "tip": "इस अवधि का उपाय",
        "lucky_heading": "आज का शुभ रंग और अंक", "lucky_colour": "शुभ रंग", "lucky_number": "शुभ अंक",
        "lucky_day_lord": "आज चंद्र आपकी राशि के अनुकूल है, इसलिए आज का रंग वार के स्वामी का - {graha}.",
        "lucky_rashi_lord": "आज चंद्र आपकी राशि से शांत भाव में है, इसलिए अपने राशि स्वामी का सहारा लें - {graha}.",
        "panchang_heading": "आज का पंचांग", "vara": "वार", "tithi": "तिथि", "nakshatra": "नक्षत्र",
        "sunrise": "सूर्योदय", "until": "तक", "panchang_note": "{place} में सूर्योदय के समय की स्थिति; समय भारतीय मानक समय में।",
        "moon_heading": "आपकी राशि के लिए चंद्र",
        "moon_line": "चंद्र {sign} राशि में, {nakshatra} नक्षत्र में - आपकी राशि से भाव {house}.",
        "chandra_bala_good": "चंद्र बल: अनुकूल", "chandra_bala_quiet": "चंद्र बल: शांत दिन",
        "facts_heading": "{rashi} राशि के लिए ग्रह स्थिति", "facts_as_of": "{date} (अवधि के आरंभ) की ग्रह स्थिति। "
        "भाव {rashi} राशि से गिने गए हैं।",
        "col_graha": "ग्रह", "col_sign": "राशि", "col_nakshatra": "नक्षत्र", "col_house": "{rashi} राशि से भाव",
        "col_motion": "गति", "retrograde": "वक्री", "direct": "मार्गी",
        "events_heading": "इस अवधि के राशि परिवर्तन और वक्री-मार्गी तिथियाँ", "no_events": "इस अवधि में कोई ग्रह राशि या गति नहीं बदलता।",
        "col_date": "तिथि", "col_event": "क्या होता है",
        "stays_heading": "धीमी गति के ग्रह कहाँ हैं", "col_from": "से", "col_to": "तक",
        "saturn_heading": "साढ़ेसाती और ढैया की स्थिति",
        "sade_sati_active": "{rashi} राशि पर साढ़ेसाती चल रही है: {phase}, शनि आपकी राशि से भाव {house} में"
                            " (यह चरण: {start} से {end}).",
        "sade_sati_paused": "{rashi} राशि की साढ़ेसाती जारी है, पर अभी शनि उन तीन राशियों से बाहर है (चक्र: {start} से {end}).",
        "sade_sati_inactive": "{rashi} राशि पर अभी साढ़ेसाती नहीं है। शनि आपकी राशि से भाव {house} में है।",
        "dhaiya_active": "शनि की ढैया चल रही है: शनि आपकी राशि से भाव {house} में ({start} से {end}).",
        "phase_rising": "पहला चरण", "phase_peak": "दूसरा (मध्य) चरण", "phase_setting": "तीसरा चरण",
        "pending_title": "नया राशिफल तैयार हो रहा है",
        "pending_text": "इस अवधि का लिखित राशिफल जल्द ही यहाँ दिखेगा। तब तक {rashi} राशि के लिए सटीक ग्रह स्थिति देखें - "
                        "स्विस एफेमेरिस से गणना की हुई, अनुमानित नहीं।",
        "stale_note": "यह राशिफल {range} की अवधि के लिए लिखा गया था। अगला राशिफल तैयार हो रहा है।",
        "other_periods": "{rashi} राशि के और राशिफल", "other_rashis": "अन्य राशियों का {period} राशिफल",
        "cta_kundali_title": "आपकी कुंडली राशि से कहीं अधिक बताती है",
        "cta_kundali_text": "राशिफल केवल चंद्र राशि पर आधारित होता है। जन्म कुंडली में आपका लग्न, नौ ग्रह और दशा दिखती है - मुफ़्त।",
        "cta_kundali_button": "मुफ़्त जन्म कुंडली बनाएँ",
        "cta_chat_title": "अपनी कुंडली के बारे में पूछें",
        "cta_chat_text": "करियर, विवाह, यह वर्ष - आपकी सटीक जन्म कुंडली पढ़ने वाले AI ज्योतिषी से पूछें। पहले 2 उत्तर मुफ़्त।",
        "cta_chat_button": "AI परामर्श शुरू करें",
        "about_heading": "यह राशिफल कैसे बनता है",
        "about_text": "इस पृष्ठ की ग्रह स्थिति, राशि परिवर्तन, वक्री तिथियाँ, तिथि और नक्षत्र स्विस एफेमेरिस (निरयन राशिचक्र, लाहिरी "
                      "अयनांश) से गणना किए गए हैं। लिखित राशिफल {rashi} चंद्र राशि के लिए उसी गोचर की व्याख्या है; यह सामान्य "
                      "राशिफल है, व्यक्तिगत जन्म कुंडली का नहीं।",
        "disclaimer": "ज्योतिष एक पारंपरिक, आस्था पर आधारित विद्या है। यह राशिफल चंद्र राशि के लिए सामान्य व्याख्या है और केवल "
                      "आत्मचिंतन व मार्गदर्शन के लिए है - यह निश्चित घटनाओं की भविष्यवाणी नहीं है और पेशेवर सलाह का विकल्प नहीं है। "
                      "स्वास्थ्य, कानूनी या आर्थिक विषयों में कृपया योग्य विशेषज्ञ से सलाह लें।",
        "ist": "भारतीय समय",
    },
}

_EVENT_TEXT = {
    "en": {"ingress": "{graha} enters {sign} - house {house} from your rashi",
           "ingress_retro": "{graha}, moving retrograde, re-enters {sign} - house {house} from your rashi",
           "retrograde": "{graha} turns retrograde in {sign} - house {house} from your rashi",
           "direct": "{graha} turns direct in {sign} - house {house} from your rashi"},
    "mr": {"ingress": "{graha} {sign} राशीत प्रवेश करतो - तुमच्या राशीपासून {ordinal} स्थान",
           "ingress_retro": "वक्री {graha} पुन्हा {sign} राशीत येतो - तुमच्या राशीपासून {ordinal} स्थान",
           "retrograde": "{graha} {sign} राशीत वक्री होतो - तुमच्या राशीपासून {ordinal} स्थान",
           "direct": "{graha} {sign} राशीत मार्गी होतो - तुमच्या राशीपासून {ordinal} स्थान"},
    "hi": {"ingress": "{graha} {sign} राशि में प्रवेश करता है - आपकी राशि से {ordinal} भाव",
           "ingress_retro": "वक्री {graha} फिर {sign} राशि में आता है - आपकी राशि से {ordinal} भाव",
           "retrograde": "{graha} {sign} राशि में वक्री होता है - आपकी राशि से {ordinal} भाव",
           "direct": "{graha} {sign} राशि में मार्गी होता है - आपकी राशि से {ordinal} भाव"},
}


def normalise_language(code: str | None) -> str | None:
    """'en' for None/empty, the code if supported, None for anything else (-> 404)."""
    if not code:
        return "en"
    return code if code in LANGUAGES else None


def rashi_name(index: int, language: str) -> str:
    sign = sign_info(index - 1)
    if language == "en":
        return sign["key"]  # English readers search by zodiac sign: Aries ... Pisces (the Sanskrit name is secondary)
    if language == "mr":
        return _MR_SIGN.get(index, sign["devanagari"])
    return sign["devanagari"]


def rashi_names(slug: str) -> dict:
    """Every way a rashi is named: `en` Libra, `hi` तुला, `mr` तूळ, `sanskrit` Tula, `latin` Tula / Kumbh / Singh (the
    transliteration Hindi and Marathi searchers type), plus `english`, `devanagari`, `index`, `slug` (internal key)."""
    index = RASHI_SLUGS.index(slug) + 1
    sign = sign_info(index - 1)
    return {"slug": slug, "index": index, "english": sign["key"], "sanskrit": sign["name"],
            "latin": URL_RASHI_SLUGS["hi"][slug].capitalize(), "devanagari": sign["devanagari"],
            **{code: rashi_name(index, code) for code in LANGUAGES}}


def sign_name(sign: dict, language: str) -> str:
    """A sign in running facts (tables, events): English pages give both names, "Virgo (Kanya)"."""
    if language == "en":
        info = sign_info(sign["index"] - 1)
        return f"{info['key']} ({info['name']})"
    return rashi_name(sign["index"], language)


def graha_name(graha: dict, language: str) -> str:
    if language == "en":
        english = _EN_GRAHA[graha["key"]]
        return english if graha["name"] == english else f"{english} ({graha['name']})"
    if language == "mr":
        return _MR_GRAHA.get(graha["key"], graha["devanagari"])
    return graha["devanagari"]


def nakshatra_name(nakshatra: dict, language: str) -> str:
    return nakshatra["name"] if language == "en" else nakshatra["devanagari"]


def tithi_name(tithi: dict, language: str) -> str:
    if language == "en":
        return f"{tithi['paksha']['name']} {tithi['name']}"
    name = _HI_TITHI.get(tithi["name"], tithi["devanagari"]) if language == "hi" else tithi["devanagari"]
    return f"{tithi['paksha']['devanagari']} {name}"


def place_name(name: str, language: str) -> str:
    return name if language == "en" else _PLACES.get(name, name)


def weekday_name(day: dt.date, language: str) -> str:
    return _WEEKDAYS[language][day.weekday()]


def format_date(value: str | dt.date, language: str, weekday: bool = False) -> str:
    day = dt.date.fromisoformat(value[:10]) if isinstance(value, str) else value
    text = f"{day.day} {_MONTHS[language][day.month - 1]} {day.year}"
    return f"{weekday_name(day, language)}, {text}" if weekday else text


def format_range(start: str, end: str, language: str) -> str:
    if start == end:
        return format_date(start, language, weekday=True)
    return f"{format_date(start, language)} – {format_date(end, language)}"


def format_time(iso_datetime: str, language: str, reference_date: str | None = None) -> str:
    """'20:01' or, when the moment falls on another day than `reference_date`, '22 September 2026, 07:07'."""
    date_part, time_part = iso_datetime[:10], iso_datetime[11:16]
    if reference_date and date_part != reference_date:
        return f"{format_date(date_part, language)}, {time_part}"
    return time_part


def format_timestamp(iso_utc: str, language: str) -> str:
    from .periods import IST

    moment = dt.datetime.fromisoformat(iso_utc).astimezone(IST)
    return f"{format_date(moment.date(), language)}, {moment:%H:%M} {UI[language]['ist']}"


def ordinal(house: int, language: str) -> str:
    return str(house) if language == "en" else _ORDINALS[language][house - 1]


def describe_event(event: dict, language: str) -> str:
    if event["type"] == "ingress":
        kind, sign = ("ingress_retro" if event.get("retrograde_entry") else "ingress"), event["to_sign"]
    else:
        kind, sign = event["direction"], event["sign"]
    return _EVENT_TEXT[language][kind].format(graha=graha_name(event["graha"], language), sign=sign_name(sign, language),
                                              house=event["house"], ordinal=ordinal(event["house"], language))


def month_name(month: int, language: str) -> str:
    """The month as this tree writes it: "September", "सितंबर", "सप्टेंबर"."""
    return _MONTHS[language][month - 1]


def _fill(template: str, slug: str, language: str, year: int | None = None, month: str = "") -> str:
    """`year` and `month` come from the page's own window. Only the yearly and monthly templates spell
    `{year}` / `{month}`; `str.format` ignores a keyword no template uses, so the other periods are
    untouched by them."""
    names = rashi_names(slug)
    # `month` is this tree's spelling, `month_latin` the English one. The Latin half of a Devanagari title
    # exists for people typing "dhanu rashifal september 2026"; putting सितंबर inside it answers neither
    # query well, so each half of the title stays in one script.
    return template.format(n=names[language], e=names["english"], s=names["sanskrit"], l=names["latin"],
                           year="" if year is None else year, month=month,
                           month_latin=_MONTHS["en"][_MONTHS[language].index(month)] if month else "")


def page_title(slug: str, period: str, language: str, year: int | None = None, month: str = "") -> str:
    return _fill(_TITLES[language][period][0], slug, language, year, month)


def page_h1(slug: str, period: str, language: str, year: int | None = None, month: str = "") -> str:
    return _fill(_TITLES[language][period][1], slug, language, year, month)


def page_meta(slug: str, period: str, language: str, year: int | None = None, month: str = "") -> str:
    return _fill(_META[language][period], slug, language, year, month)


def hub_title(period: str, language: str) -> str:
    """Hub = all 12 rashis on one page. `period` is "today" (daily hub) or "weekly"."""
    return _HUBS[language][period][0]


def hub_h1(period: str, language: str) -> str:
    return _HUBS[language][period][1]


def hub_meta(period: str, language: str) -> str:
    return _HUBS[language][period][2]
