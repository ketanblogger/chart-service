"""Texts of the permanent purchase page /order/{token} in the ORDER's language (en / hi / mr).

The language is the one stored on the order: the report language the buyer chose, or - for a consultation purchase -
the language of that consultation. `context(order, view)` returns everything templates/order.html prints, so the
route (app/web/routes.py `order_page`) only has to pass it on and render the page with `<html lang>` = `lang`.

The status title / text are the server-rendered first paint of what static/js/pay.js `AstroPay.describe(view, lang)`
shows after its refresh; tests/test_payments.py asserts that the two are word-for-word identical in all three
languages, so the page never flickers between two wordings. Vocabulary follows each tree's page copy (Hindi सवाल,
Marathi प्रश्न).
"""

import datetime as dt

from .catalogue import report_product

LANGS = ("en", "hi", "mr")
_IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
_MONTHS = {
    "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    "hi": ["जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर"],
    "mr": ["जानेवारी", "फेब्रुवारी", "मार्च", "एप्रिल", "मे", "जून", "जुलै", "ऑगस्ट", "सप्टेंबर", "ऑक्टोबर", "नोव्हेंबर", "डिसेंबर"],
}
LANGUAGE_NAMES = {"en": {"en": "English", "hi": "Hindi", "mr": "Marathi"},
                  "hi": {"en": "अंग्रेज़ी", "hi": "हिन्दी", "mr": "मराठी"},
                  "mr": {"en": "इंग्रजी", "hi": "हिंदी", "mr": "मराठी"}}
PRODUCT_NAMES = {
    "kundali-report": {"en": "Detailed Janam Kundali Report", "hi": "विस्तृत जन्म कुंडली रिपोर्ट", "mr": "सविस्तर जन्मकुंडली अहवाल"},
    "kundali-report-simple": {"en": "Janam Kundali Report", "hi": "जन्म कुंडली रिपोर्ट", "mr": "जन्मकुंडली अहवाल"},
    "matching-report": {"en": "Kundali Matching Report", "hi": "कुंडली मिलान रिपोर्ट", "mr": "कुंडली गुणमेलन अहवाल"},
    "mangal-dosha-remedy": {"en": "Mangal Dosha Remedy Guide", "hi": "मंगल दोष उपाय मार्गदर्शिका", "mr": "मंगळ दोष उपाय मार्गदर्शिका"},
    "sade-sati-guide": {"en": "Sade Sati Guide", "hi": "साढ़े साती मार्गदर्शिका", "mr": "साडेसाती मार्गदर्शिका"},
    # the two consultation tiers, and the id they were sold under before the tiers existed
    "consultation-basic": {"en": "AI consultation: {n} questions + Kundali PDF report", "hi": "AI ज्योतिष परामर्श: {n} सवाल + कुंडली PDF रिपोर्ट",
                           "mr": "AI ज्योतिष सल्ला: {n} प्रश्न + कुंडली PDF अहवाल"},
    "consultation-premium": {"en": "AI consultation: {n} questions + the detailed Kundali book",
                             "hi": "AI ज्योतिष परामर्श: {n} सवाल + विस्तृत कुंडली पुस्तिका",
                             "mr": "AI ज्योतिष सल्ला: {n} प्रश्न + सविस्तर कुंडली पुस्तिका"},
    "consultation-pack": {"en": "AI consultation: {n} questions + Kundali PDF report", "hi": "AI ज्योतिष परामर्श: {n} सवाल + कुंडली PDF रिपोर्ट",
                          "mr": "AI ज्योतिष सल्ला: {n} प्रश्न + कुंडली PDF अहवाल"},
}

LABELS = {
    "en": {"title": "Your order", "description": "Your purchase: payment status and downloads.", "heading": "Your order",
           "purchase": "Purchase", "amount": "Amount", "paid_on": "Paid on", "report_language": "Report language",
           "download": "Download your PDF", "reference": "Order reference: ", "continue": "Continue your consultation",
           "email_copy": "We have e-mailed your permanent download link to {email}. It works even if you close this page.",
           "keep": "Bookmark this page: it is your permanent link to this purchase, and it works on any device. Anyone who has "
                   "this link can open it, so share it only with people you trust. Need help? Quote the order reference above."},
    "hi": {"title": "आपका ऑर्डर", "description": "आपकी ख़रीद: भुगतान की स्थिति और डाउनलोड।", "heading": "आपका ऑर्डर",
           "purchase": "ख़रीद", "amount": "राशि", "paid_on": "भुगतान की तारीख़", "report_language": "रिपोर्ट की भाषा",
           "download": "अपना PDF डाउनलोड करें", "reference": "ऑर्डर संदर्भ: ", "continue": "अपनी बातचीत जारी रखें",
           "email_copy": "आपका स्थायी डाउनलोड लिंक हमने {email} पर ई-मेल कर दिया है। यह पेज बंद करने पर भी वह काम करता है।",
           "keep": "इस पेज को बुकमार्क कर लें: यह आपकी इस ख़रीद का स्थायी लिंक है और किसी भी डिवाइस पर खुलता है। जिसके पास यह लिंक है "
                   "वह इसे खोल सकता है, इसलिए इसे केवल भरोसेमंद लोगों के साथ साझा करें। मदद चाहिए? ऊपर दिया ऑर्डर संदर्भ बताएँ।"},
    "mr": {"title": "तुमची ऑर्डर", "description": "तुमची खरेदी: पेमेंटची स्थिती आणि डाउनलोड.", "heading": "तुमची ऑर्डर",
           "purchase": "खरेदी", "amount": "रक्कम", "paid_on": "पेमेंटची तारीख", "report_language": "अहवालाची भाषा",
           "download": "तुमचा PDF डाउनलोड करा", "reference": "ऑर्डर क्रमांक: ", "continue": "तुमची सल्लामसलत पुढे सुरू ठेवा",
           "email_copy": "तुमचा कायमचा डाउनलोड दुवा आम्ही {email} या पत्त्यावर ई-मेलने पाठवला आहे. हे पान बंद केले तरी तो चालतो.",
           "keep": "हे पान बुकमार्क करून ठेवा: हा तुमच्या या खरेदीचा कायमचा दुवा आहे आणि तो कोणत्याही डिव्हाइसवर उघडतो. ज्याच्याकडे हा "
                   "दुवा आहे तो हे पान उघडू शकतो, म्हणून तो फक्त विश्वासू व्यक्तींनाच द्या. मदत हवी आहे? वरील ऑर्डर क्रमांक सांगा."},
}

# How long we tell the customer the report takes. MEASURED, one real billed run per tier (Sept 2026):
#   detailed book   12 calls, four waves   528s = 8.8 min  -> promise "5-10"
#   simple report    3 calls, one wave     240s = 4.0 min  -> promise "3-5"
# The simple run took 5 attempts for 3 calls, so 240s already includes a retry: a fair typical figure rather
# than a best case. Both are ONE measurement on ONE chart, so each promise keeps headroom above what we saw.
# Only the RANGE is substituted, never the unit word - every language keeps its own noun and its own case
# ("5-10 minutes" / "5-10 मिनट" / "5-10 मिनिटे"). Mirrored in pay.js; tests/test_payments.py asserts they agree.
WAIT_RANGE = {"simple": "3-5", "detailed": "5-10"}
DEFAULT_WAIT = WAIT_RANGE["detailed"]  # an unknown product promises the LONGER wait, never the shorter


def wait_range(order: dict) -> str:
    """The wait to quote for this order: the tier of the report it entitles, else the longer default."""
    from app.ai.products import PRODUCTS

    product = report_product(order)
    entry = PRODUCTS.get(product) if product else None
    return WAIT_RANGE.get(getattr(entry, "tier", ""), DEFAULT_WAIT)


# state -> (title, text); "{n}" = number of questions. MUST equal pay.js TEXT[lang] (creditedTitle/Text, bundle*, ready*, delayed*, preparing*).
STATUS = {
    "en": {
        "credited": ("Payment received - thank you", "{n} questions have been added to your consultation."),
        "bundle_preparing": ("Payment received - {n} questions added",
                             "You can continue your consultation now. Your Kundali PDF report, which is included, is being written "
                             "from your exact chart - this takes {wait} minutes. It will appear here and on your order page."),
        "bundle_ready": ("{n} questions added - your Kundali PDF is ready",
                         "Payment received - thank you. Download your Kundali report below; you can download it again at any time from your order page."),
        "bundle_delayed": ("{n} questions added - your Kundali PDF is delayed",
                           "Your payment is safe and your questions are ready to use. Preparing the included Kundali report is taking "
                           "longer than it should; we will complete it and it will appear on your order page. Please keep the link below."),
        "ready": ("Your report is ready", "Payment received - thank you. Download your PDF below. You can download it again at any time from your order page."),
        "delayed": ("Payment received - your report is delayed",
                    "Your payment is safe and recorded. Preparing the report is taking longer than it should; we will complete it "
                    "and it will appear on your order page. Please keep the link below."),
        "preparing": ("Payment received - preparing your report",
                      "Your report is being written from your exact chart. This takes {wait} minutes. You can keep this page open, "
                      "or come back later using your order page link below."),
    },
    "hi": {
        "credited": ("भुगतान मिल गया - धन्यवाद", "आपकी बातचीत में {n} सवाल जोड़ दिए गए हैं।"),
        "bundle_preparing": ("भुगतान मिल गया - {n} सवाल जोड़ दिए गए",
                             "अब आप अपनी बातचीत जारी रख सकते हैं। इसके साथ मिलने वाली आपकी कुंडली PDF रिपोर्ट आपकी सटीक कुंडली से लिखी जा रही है - "
                             "इसमें {wait} मिनट लगते हैं। यह यहाँ और आपके ऑर्डर के पेज पर दिखेगी।"),
        "bundle_ready": ("{n} सवाल जोड़ दिए गए - आपकी कुंडली PDF तैयार है",
                         "भुगतान मिल गया - धन्यवाद। नीचे से अपनी कुंडली रिपोर्ट डाउनलोड करें; ऑर्डर के पेज से इसे कभी भी दोबारा डाउनलोड किया जा सकता है।"),
        "bundle_delayed": ("{n} सवाल जोड़ दिए गए - कुंडली PDF में देर हो रही है",
                           "आपका भुगतान सुरक्षित है और आपके सवाल उपयोग के लिए तैयार हैं। साथ की कुंडली रिपोर्ट बनने में अपेक्षा से अधिक समय लग रहा है; "
                           "हम इसे पूरा करेंगे और यह आपके ऑर्डर के पेज पर दिखेगी। कृपया नीचे दिया लिंक सँभालकर रखें।"),
        "ready": ("आपकी रिपोर्ट तैयार है", "भुगतान मिल गया - धन्यवाद। नीचे से अपना PDF डाउनलोड करें। ऑर्डर के पेज से इसे कभी भी दोबारा डाउनलोड किया जा सकता है।"),
        "delayed": ("भुगतान मिल गया - रिपोर्ट में देर हो रही है",
                    "आपका भुगतान सुरक्षित है और दर्ज हो चुका है। रिपोर्ट बनने में अपेक्षा से अधिक समय लग रहा है; हम इसे पूरा करेंगे "
                    "और यह आपके ऑर्डर के पेज पर दिखेगी। कृपया नीचे दिया लिंक सँभालकर रखें।"),
        "preparing": ("भुगतान मिल गया - आपकी रिपोर्ट तैयार हो रही है",
                      "आपकी सटीक कुंडली से रिपोर्ट लिखी जा रही है। इसमें {wait} मिनट लगते हैं। यह पेज खुला रखें, या नीचे दिए "
                      "ऑर्डर के पेज के लिंक से बाद में लौटें।"),
    },
    "mr": {
        "credited": ("पेमेंट मिळाले - धन्यवाद", "तुमच्या सल्लामसलतीत {n} प्रश्न जमा झाले आहेत."),
        "bundle_preparing": ("पेमेंट मिळाले - {n} प्रश्न जमा झाले",
                             "तुम्ही आता सल्लामसलत पुढे सुरू ठेवू शकता. यासोबत मिळणारा तुमचा कुंडली PDF अहवाल तुमच्या नेमक्या कुंडलीवरून "
                             "लिहिला जात आहे - याला {wait} मिनिटे लागतात. तो येथे आणि तुमच्या ऑर्डरच्या पानावर दिसेल."),
        "bundle_ready": ("{n} प्रश्न जमा झाले - तुमचा कुंडली PDF तयार आहे",
                         "पेमेंट मिळाले - धन्यवाद. खालील बटणाने कुंडली अहवाल डाउनलोड करा; ऑर्डरच्या पानावरून तो केव्हाही पुन्हा डाउनलोड करता येईल."),
        "bundle_delayed": ("{n} प्रश्न जमा झाले - कुंडली PDF ला उशीर होत आहे",
                           "तुमचे पेमेंट सुरक्षित आहे आणि तुमचे प्रश्न वापरासाठी तयार आहेत. सोबतचा कुंडली अहवाल तयार होण्यास अपेक्षेपेक्षा जास्त "
                           "वेळ लागत आहे; आम्ही तो पूर्ण करू आणि तो तुमच्या ऑर्डरच्या पानावर दिसेल. कृपया खालील दुवा जपून ठेवा."),
        "ready": ("तुमचा अहवाल तयार आहे", "पेमेंट मिळाले - धन्यवाद. खालील बटणाने PDF डाउनलोड करा. तुमच्या ऑर्डरच्या पानावरून तो केव्हाही पुन्हा डाउनलोड करता येईल."),
        "delayed": ("पेमेंट मिळाले - अहवालाला उशीर होत आहे",
                    "तुमचे पेमेंट सुरक्षित आहे आणि त्याची नोंद झाली आहे. अहवाल तयार होण्यास अपेक्षेपेक्षा जास्त वेळ लागत आहे; आम्ही तो पूर्ण करू "
                    "आणि तो तुमच्या ऑर्डरच्या पानावर दिसेल. कृपया खालील दुवा जपून ठेवा."),
        "preparing": ("पेमेंट मिळाले - तुमचा अहवाल तयार होत आहे",
                      "तुमच्या नेमक्या कुंडलीवरून अहवाल लिहिला जात आहे. याला {wait} मिनिटे लागतात. हे पान उघडे ठेवा, किंवा खालील "
                      "ऑर्डरच्या पानाच्या दुव्यावरून नंतर परत या."),
    },
}


def order_language(order: dict) -> str:
    return order.get("language") if order.get("language") in LANGS else "en"


def status_key(view: dict) -> tuple[str, str, bool]:
    """(key into STATUS, css state, done) for a PAID order's public view - the same decision as pay.js describe()."""
    bundle = view["kind"] == "pack" and view.get("includes_report")
    if view["kind"] == "pack" and not bundle:
        return "credited", "credited", True
    if view["fulfilment"] == "ready":
        state = "ready"
    elif view["fulfilment"] == "failed" and not view.get("retrying"):
        state = "delayed"
    else:
        state = "preparing"
    return (f"bundle_{state}" if bundle else state), state, state != "preparing"


def context(order: dict, view: dict) -> dict:
    """{"lang", "labels", "info": {state, title, text, done}, "product_name", "paid_on", "language_name"}."""
    lang = order_language(order)
    key, state, done = status_key(view)
    title, text = STATUS[lang][key]
    n = str(view.get("messages") or 0)
    paid = dt.datetime.fromtimestamp(order["paid_at"], _IST)
    names = PRODUCT_NAMES.get(order["product"], {})
    return {
        "lang": lang,
        "labels": LABELS[lang],
        "info": {"state": state, "title": title.replace("{n}", n),
                 "text": text.replace("{n}", n).replace("{wait}", wait_range(order)), "done": done},
        "product_name": names.get(lang, view.get("product_name", order["product"])).replace("{n}", n),
        "paid_on": f"{paid.day} {_MONTHS[lang][paid.month - 1]} {paid.year}, {paid:%H:%M} IST",
        # the language the report is written in, named in the language of the page (they are the same language today)
        "language_name": LANGUAGE_NAMES[lang][order_language(order)] if report_product(order) else None,
        # Only while the report is still being written, and only when service.report_email_enabled() put an
        # address on the view - so this never promises an e-mail that nothing sends. Same words as pay.js.
        "email_copy": (LABELS[lang]["email_copy"].replace("{email}", view["email_copy"])
                       if state == "preparing" and view.get("email_copy") else None),
    }
