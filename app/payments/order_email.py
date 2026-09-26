"""The one e-mail this app sends at payment: the permanent link to the order.

WHY AT PAYMENT AND NOT WHEN THE REPORT IS READY. The link exists for the moment the customer loses the
page - a closed tab, a dead battery, a phone handed back. That moment is most likely DURING the five to
ten minutes the report takes, so an e-mail that waits for the report misses exactly the window it is
there to cover. The link is permanent and shows whatever the order is doing, so it is useful before the
report exists and stays useful after.

Plain text, in the language the order was placed in. The address is the one typed at checkout, which is
required from 2026-09-26 (with a re-typed confirmation) precisely so this can be relied on.
"""

import logging

from app import mailer
from app.web import site

from .order_page import PRODUCT_NAMES, order_language

log = logging.getLogger(__name__)

# {site}, {product}, {link}, {reference}. No marketing, no footer, no images: this is a receipt-shaped
# message to someone who paid sixty seconds ago, and every extra part of it costs deliverability.
TEXTS = {
    "en": (
        "{site}: your order link",
        "Thank you for your purchase.\n\n"
        "Your {product} is being prepared. This page is your permanent link to it - it works on any "
        "device, and you can open it any time to download the PDF again:\n\n"
        "{link}\n\n"
        "Keep this e-mail. Anyone who has this link can open the order, so share it only with people "
        "you trust.\n\n"
        "Order reference: {reference}\n"
        "Need help? Reply to this e-mail and quote that reference.\n"
    ),
    "hi": (
        "{site}: आपकी ख़रीद का लिंक",
        "आपकी ख़रीद के लिए धन्यवाद।\n\n"
        "आपकी {product} तैयार की जा रही है। यह पेज उसका स्थायी लिंक है - यह किसी भी डिवाइस पर खुलता है "
        "और आप जब चाहें इसे खोलकर PDF दोबारा डाउनलोड कर सकते हैं:\n\n"
        "{link}\n\n"
        "इस ई-मेल को सँभालकर रखें। जिसके पास यह लिंक है वह इस ऑर्डर को खोल सकता है, इसलिए इसे केवल "
        "भरोसेमंद लोगों के साथ साझा करें।\n\n"
        "ऑर्डर संदर्भ: {reference}\n"
        "मदद चाहिए? इसी ई-मेल का उत्तर दें और यह संदर्भ बताएँ।\n"
    ),
    "mr": (
        "{site}: तुमच्या खरेदीचा दुवा",
        "तुमच्या खरेदीबद्दल धन्यवाद.\n\n"
        "तुमचा {product} तयार होत आहे. हे पान त्याचा कायमचा दुवा आहे - तो कोणत्याही डिव्हाइसवर उघडतो "
        "आणि तुम्ही केव्हाही तो उघडून PDF पुन्हा डाउनलोड करू शकता:\n\n"
        "{link}\n\n"
        "हा ई-मेल जपून ठेवा. ज्याच्याकडे हा दुवा आहे तो ही ऑर्डर उघडू शकतो, म्हणून तो फक्त विश्वासू "
        "व्यक्तींनाच द्या.\n\n"
        "ऑर्डर क्रमांक: {reference}\n"
        "मदत हवी आहे? याच ई-मेलला उत्तर द्या आणि हा क्रमांक सांगा.\n"
    ),
}


def compose(order: dict) -> tuple[str, str, str]:
    """(to, subject, body) for one paid order, in the order's own language."""
    lang = order_language(order)
    subject, body = TEXTS[lang]
    names = PRODUCT_NAMES.get(order["product"], {})
    product = names.get(lang) or order.get("product_name") or order["product"]
    fields = {"site": site.SITE_NAME, "product": product.replace("{n}", str(order.get("messages") or 0)),
              "link": f"{site.base_url().rstrip('/')}/order/{order['token']}",
              "reference": order["razorpay_order_id"]}
    return (order.get("email") or "").strip(), subject.format(**fields), body.format(**fields)


def send_order_link(order: dict) -> bool:
    """Send it. False when there is no address, or the mailer is off, or the provider refused.

    Never raises: the caller is the payment path, where a failed send must cost nothing. The order page
    link is reachable without this e-mail, which is what makes that acceptable rather than lossy.
    """
    to, subject, body = compose(order)
    if not to:
        return False
    return mailer.send(to, subject, body)
