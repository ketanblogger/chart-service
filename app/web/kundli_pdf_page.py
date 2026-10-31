"""The PDF landing page: what the free one contains, what the paid one adds, and the price.

"kundali pdf" and "detailed kundli" are transactional queries - somebody wants the document rather than
an explanation. The job of this page is to let them decide without having to generate a chart first, so
it states exactly what is in each and does not blur the line.

THE FREE PDF IS GENUINELY FREE, with no sign-up and no AI on its path, and the page says so plainly
rather than treating it as a teaser. A landing page that implies the free thing is crippled in order to
sell the paid one is the pattern that makes people distrust every other claim on the site.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse

from app.web import i18n

COPY = {
    "en": {
        "title": "Kundli PDF - Free Chart PDF and Detailed Report",
        "h1": "Kundli PDF: free chart, or the detailed report",
        "intro": "Two documents, and the difference is not a trick. The free PDF is your complete "
                 "calculated chart. The paid report is that chart read and written out.",
        "sample_heading": "A page of the free PDF",
        "sample_note": "Two pages of the actual document, rendered by the same code that makes yours. The birth is invented - Asha Kulkarni does not exist.",
        "sample_download": "Download the whole sample PDF",
        "sample_alt": "Page {n} of the free kundli PDF",
        "free_heading": "The free kundli PDF", "paid_heading": "The detailed report",
        "free_price": "Free, no sign-up", "paid_price": "Rs {price}",
        "free_points": (
            "Lagna, Moon sign and nakshatra with pada",
            "All nine grahas: rashi, degree, nakshatra, retrograde",
            "The house each graha falls in, and the chart diagram",
            "Vimshottari dasha with the dates you are running now",
            "Mangal dosha and sade sati, checked",
        ),
        "paid_points": (
            "Everything in the free PDF, plus the reading of it",
            "What your lagna, Moon and graha placements mean for temperament and work",
            "The dasha you are in, what it supports, and the dates it changes",
            "Navamsa, dignity, aspects and the yogas your chart actually carries",
            "Remedies that follow from this chart rather than a list everybody gets",
        ),
        "honest": "The free PDF is the whole calculation - nothing is held back to make the paid one "
                  "look better. What you pay for is the writing, not the arithmetic.",
        "cta_free": "Make your free kundli PDF", "cta_paid": "See the detailed report",
    },
    "hi": {
        "title": "कुंडली PDF - मुफ़्त चार्ट PDF और विस्तृत रिपोर्ट",
        "h1": "कुंडली PDF: मुफ़्त चार्ट, या विस्तृत रिपोर्ट",
        "intro": "दो दस्तावेज़, और अंतर में कोई चाल नहीं है। मुफ़्त PDF आपकी पूरी गणना की हुई कुंडली "
                 "है। सशुल्क रिपोर्ट उसी कुंडली को पढ़कर लिखी गई व्याख्या है।",
        "sample_heading": "मुफ़्त PDF का एक पन्ना",
        "sample_note": "असली दस्तावेज़ के दो पन्ने, उसी कोड से बने जो आपका बनाता है। जन्म-विवरण काल्पनिक है - आशा कुलकर्णी नाम का कोई व्यक्ति नहीं है।",
        "sample_download": "पूरा नमूना PDF डाउनलोड करें",
        "sample_alt": "मुफ़्त कुंडली PDF का पन्ना {n}",
        "free_heading": "मुफ़्त कुंडली PDF", "paid_heading": "विस्तृत रिपोर्ट",
        "free_price": "मुफ़्त, साइन-अप नहीं", "paid_price": "₹{price}",
        "free_points": (
            "लग्न, चंद्र राशि और नक्षत्र (पाद सहित)",
            "नौ ग्रह: राशि, अंश, नक्षत्र, वक्री स्थिति",
            "हर ग्रह किस भाव में है, और कुंडली चक्र",
            "विंशोत्तरी दशा, वर्तमान महादशा-अंतर्दशा की तारीख़ों के साथ",
            "मंगल दोष और साढ़े साती की जाँच",
        ),
        "paid_points": (
            "मुफ़्त PDF का सब कुछ, और उसकी व्याख्या",
            "लग्न, चंद्र और ग्रह स्थितियों का स्वभाव तथा काम पर क्या अर्थ",
            "कौन सी दशा चल रही है, वह किसका समर्थन करती है, और कब बदलती है",
            "नवांश, बल, दृष्टि और आपकी कुंडली में वास्तव में बनने वाले योग",
            "इसी कुंडली से निकले उपाय, सबको दी जाने वाली सूची नहीं",
        ),
        "honest": "मुफ़्त PDF पूरी गणना है - सशुल्क को बेहतर दिखाने के लिए कुछ भी रोका नहीं गया। "
                  "आप लेखन के लिए भुगतान करते हैं, गणित के लिए नहीं।",
        "cta_free": "अपनी मुफ़्त कुंडली PDF बनाइए", "cta_paid": "विस्तृत रिपोर्ट देखिए",
    },
    "mr": {
        "title": "कुंडली PDF - मोफत चार्ट PDF आणि सविस्तर अहवाल",
        "h1": "कुंडली PDF: मोफत चार्ट, की सविस्तर अहवाल",
        "intro": "दोन कागदपत्रे, आणि फरकात कोणतीही लपवाछपवी नाही. मोफत PDF ही तुमची संपूर्ण गणना "
                 "केलेली पत्रिका आहे. सशुल्क अहवाल म्हणजे तीच पत्रिका वाचून लिहिलेले विवेचन.",
        "sample_heading": "मोफत PDF चे एक पान",
        "sample_note": "खऱ्या दस्तऐवजाची दोन पाने, तुमचे बनवणाऱ्या त्याच कोडने तयार केलेली. जन्मतपशील काल्पनिक आहे - आशा कुलकर्णी ही व्यक्ती अस्तित्वात नाही.",
        "sample_download": "संपूर्ण नमुना PDF डाउनलोड करा",
        "sample_alt": "मोफत कुंडली PDF चे पान {n}",
        "free_heading": "मोफत कुंडली PDF", "paid_heading": "सविस्तर अहवाल",
        "free_price": "मोफत, साइन-अप नाही", "paid_price": "₹{price}",
        "free_points": (
            "लग्न, चंद्ररास आणि नक्षत्र (चरणासह)",
            "नऊ ग्रह: रास, अंश, नक्षत्र, वक्री स्थिती",
            "प्रत्येक ग्रह कोणत्या स्थानात, आणि पत्रिका चक्र",
            "विंशोत्तरी दशा, चालू महादशा-अंतर्दशेच्या तारखांसह",
            "मंगळ दोष आणि साडेसातीची तपासणी",
        ),
        "paid_points": (
            "मोफत PDF मधले सर्व, आणि त्याचे विवेचन",
            "लग्न, चंद्र आणि ग्रहस्थितींचा स्वभाव व कामावर काय अर्थ",
            "कोणती दशा चालू आहे, ती कशाला पाठबळ देते, आणि कधी बदलते",
            "नवांश, बल, दृष्टी आणि तुमच्या पत्रिकेत प्रत्यक्ष बनणारे योग",
            "याच पत्रिकेतून निघालेले उपाय, सर्वांना दिली जाणारी यादी नव्हे",
        ),
        "honest": "मोफत PDF ही संपूर्ण गणना आहे - सशुल्क चांगले दिसावे म्हणून काहीही राखून ठेवलेले "
                  "नाही. तुम्ही लेखनासाठी पैसे देता, गणितासाठी नाही.",
        "cta_free": "तुमची मोफत कुंडली PDF बनवा", "cta_paid": "सविस्तर अहवाल पाहा",
    },
}


#: The sample pages shown on this page, per language. Built by scripts/sample_preview.py and CHECKED IN:
#: rendering one needs Chromium, and a page render must never depend on that.
SAMPLE_PAGES = (1, 2)
SAMPLE_DIR = Path("app/static/img/sample")


def sample_pages(lang: str) -> list[dict]:
    """The sample images that actually EXIST, with their real pixel dimensions.

    The dimensions are read from the files rather than assumed, because they are what stops the page
    reflowing when the first picture decodes - a guessed height reserves the wrong box and causes the
    very shift it is meant to prevent. A missing file is skipped rather than rendered as a broken image:
    the page is useful without the sample and must not break because an asset was not regenerated.
    """
    found = []
    for number in SAMPLE_PAGES:
        path = SAMPLE_DIR / f"{lang}-free-{number}.webp"
        if not path.exists():
            continue
        size = webp_size(path)
        if size is None:
            continue                      # unreadable header: skip it rather than guess a box
        found.append({"number": number, "src": f"/static/img/sample/{path.name}",
                      "width": size[0], "height": size[1]})
    return found


def webp_size(path: Path) -> tuple[int, int] | None:
    """(width, height) of a WebP, read from its header with nothing but the standard library.

    THIS USED TO CALL PILLOW, AND PILLOW IS NOT A DEPENDENCY OF THIS APPLICATION. It is in the
    developer's environment because something else pulls it in, so every test passed and the page
    rendered here - and in production the import raised at REQUEST time and these three pages returned
    500 while the rest of the site was fine. An import inside a function is only deferred, not optional.

    The dimensions are still READ rather than assumed. A hardcoded number that silently disagrees with
    the file reserves the wrong box and causes the very layout shift the attributes exist to prevent,
    which is the mistake this function was written to avoid in the first place.

    Three chunk layouts, because a WebP is any of them: VP8 (lossy), VP8L (lossless), VP8X (extended).
    Anything else, or a short file, returns None and the caller leaves the image out.
    """
    try:
        head = path.read_bytes()[:32]
    except OSError:
        return None
    if len(head) < 30 or head[:4] != b"RIFF" or head[8:12] != b"WEBP":
        return None
    chunk = head[12:16]
    if chunk == b"VP8 ":                                  # 14-bit width and height, little endian
        if head[23:26] != b"\x9d\x01\x2a":
            return None
        return (int.from_bytes(head[26:28], "little") & 0x3FFF,
                int.from_bytes(head[28:30], "little") & 0x3FFF)
    if chunk == b"VP8L":
        if head[20] != 0x2F:
            return None
        bits = int.from_bytes(head[21:25], "little")
        return ((bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1)
    if chunk == b"VP8X":                                  # 24-bit canvas size, minus one
        return (int.from_bytes(head[24:27], "little") + 1,
                int.from_bytes(head[27:30], "little") + 1)
    return None


def add_routes(router, page_context, respond, _json_ld) -> None:
    for lang in i18n.PAGES["kundli-pdf"]:
        _add(router, page_context, respond, _json_ld, lang)


def _add(router, page_context, respond, _json_ld, lang: str) -> None:
    def pdf_page(request: Request):
        from app.payments import catalogue
        from app.web import seo as _seo

        words = dict(COPY[lang])
        price = catalogue._REPORT_PRICES_INR["kundali-report"]
        words["paid_price"] = words["paid_price"].format(price=price)
        context = page_context("kundli-pdf", lang)
        path = i18n.url_for("kundli-pdf", lang)
        context.update(words=words, title=words["title"],
                       sample_pages=sample_pages(lang),
                       sample_pdf=f"/static/img/sample/{lang}-free-sample.pdf",
                       free_href=i18n.url_for("kundali", lang),
                       paid_href=i18n.url_for("kundali", lang),
                       json_ld=[_json_ld(_seo.breadcrumbs(
                           [(context["ui"]["home"], i18n.url_for("home", lang)),
                            (words["h1"], path)]))])
        return respond(request, "kundli_pdf.html", context)

    router.add_api_route(i18n.url_for("kundli-pdf", lang), pdf_page, methods=["GET"],
                         response_class=HTMLResponse, name=f"kundli-pdf-{lang}")
