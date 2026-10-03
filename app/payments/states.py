"""Indian states and union territories, by GST state code - the place of supply of a sale.

WHY THE GST STATE CODE IS WHAT GETS STORED. The place of supply decides whether a sale is taxed as CGST+SGST
or as IGST, and that decision is a COMPARISON: buyer's state against seller's state. Whatever is compared has
to be stable, and a display label is not - this site renders in three languages, so a place of supply matched
on its label would read "Maharashtra" for an English buyer, "महाराष्ट्र" for a Marathi one, and silently
classify the second as inter-state. The two-digit GST state code is the identifier a GST return itself uses,
it is never translated, and it is the first two digits of every GSTIN - so the seller's own code is DERIVED
from `site.GSTIN` rather than written down a second place where it could drift from the registration.

The labels are reference data with a form per language, like `app/web/i18n.py`'s rashi and graha names, and
they live here rather than in the content modules for the same reason those do: they are not copy. Nobody
rewrites "Gujarat" for tone, and a missing one is a missing fact rather than a missing translation.

Codes 25 and 28 are deliberately absent. 25 (Daman and Diu) and the old 28 (pre-bifurcation Andhra Pradesh)
are retired: 25 merged into 26 and 28 became 37. A dropdown offering them would invite a buyer to pick a
place of supply that no return accepts. 97 ("Other Territory", for supplies in India's territorial waters)
is absent too - it is not somewhere a customer lives.

OUTSIDE INDIA IS ONE ENTRY, AND IT IS OFF. A sale to a buyer outside India is a different tax treatment - an
export of service, zero rated under LUT - so it is `EXPORT_CODE` ("96", the code the GST portal itself uses for
"Other Country") rather than a state, and it is offered only while `EXPORT_SALES_ENABLED` is on. It is off: the
LUT is not filed and Razorpay international is not approved, and `app/payments/gst.py` says what that means.
While it is off this file behaves exactly as it did before the code existed - `sells_to("96")` is False, so the
dropdown does not offer it and the API refuses it.

`is_known` deliberately did NOT grow to include it. That predicate answers "is this one of the 36 places a
return is filed for", which is what decides CGST+SGST against IGST, and 96 is neither. The three questions are
separate because they have different answers: `is_known` (an Indian state), `is_export` (outside India, true for
a stored order whatever the flag says today), and `sells_to` (may a NEW order name this, which is the only one
the flag touches). Collapsing them is how a flipped flag would rewrite last month's invoice.
"""

from app.web import site

from . import gst

# GST state code -> name per language. 28 states and 8 union territories.
STATES: dict[str, dict[str, str]] = {
    "01": {"en": "Jammu and Kashmir", "hi": "जम्मू और कश्मीर", "mr": "जम्मू आणि काश्मीर"},
    "02": {"en": "Himachal Pradesh", "hi": "हिमाचल प्रदेश", "mr": "हिमाचल प्रदेश"},
    "03": {"en": "Punjab", "hi": "पंजाब", "mr": "पंजाब"},
    "04": {"en": "Chandigarh", "hi": "चंडीगढ़", "mr": "चंदीगड"},
    "05": {"en": "Uttarakhand", "hi": "उत्तराखंड", "mr": "उत्तराखंड"},
    "06": {"en": "Haryana", "hi": "हरियाणा", "mr": "हरियाणा"},
    "07": {"en": "Delhi", "hi": "दिल्ली", "mr": "दिल्ली"},
    "08": {"en": "Rajasthan", "hi": "राजस्थान", "mr": "राजस्थान"},
    "09": {"en": "Uttar Pradesh", "hi": "उत्तर प्रदेश", "mr": "उत्तर प्रदेश"},
    "10": {"en": "Bihar", "hi": "बिहार", "mr": "बिहार"},
    "11": {"en": "Sikkim", "hi": "सिक्किम", "mr": "सिक्कीम"},
    "12": {"en": "Arunachal Pradesh", "hi": "अरुणाचल प्रदेश", "mr": "अरुणाचल प्रदेश"},
    "13": {"en": "Nagaland", "hi": "नागालैंड", "mr": "नागालँड"},
    "14": {"en": "Manipur", "hi": "मणिपुर", "mr": "मणिपूर"},
    "15": {"en": "Mizoram", "hi": "मिज़ोरम", "mr": "मिझोराम"},
    "16": {"en": "Tripura", "hi": "त्रिपुरा", "mr": "त्रिपुरा"},
    "17": {"en": "Meghalaya", "hi": "मेघालय", "mr": "मेघालय"},
    "18": {"en": "Assam", "hi": "असम", "mr": "आसाम"},
    "19": {"en": "West Bengal", "hi": "पश्चिम बंगाल", "mr": "पश्चिम बंगाल"},
    "20": {"en": "Jharkhand", "hi": "झारखंड", "mr": "झारखंड"},
    "21": {"en": "Odisha", "hi": "ओडिशा", "mr": "ओडिशा"},
    "22": {"en": "Chhattisgarh", "hi": "छत्तीसगढ़", "mr": "छत्तीसगड"},
    "23": {"en": "Madhya Pradesh", "hi": "मध्य प्रदेश", "mr": "मध्य प्रदेश"},
    "24": {"en": "Gujarat", "hi": "गुजरात", "mr": "गुजरात"},
    "26": {"en": "Dadra and Nagar Haveli and Daman and Diu", "hi": "दादरा और नगर हवेली और दमन और दीव",
           "mr": "दादरा आणि नगर हवेली आणि दमण आणि दीव"},
    "27": {"en": "Maharashtra", "hi": "महाराष्ट्र", "mr": "महाराष्ट्र"},
    "29": {"en": "Karnataka", "hi": "कर्नाटक", "mr": "कर्नाटक"},
    "30": {"en": "Goa", "hi": "गोवा", "mr": "गोवा"},
    "31": {"en": "Lakshadweep", "hi": "लक्षद्वीप", "mr": "लक्षद्वीप"},
    "32": {"en": "Kerala", "hi": "केरल", "mr": "केरळ"},
    "33": {"en": "Tamil Nadu", "hi": "तमिलनाडु", "mr": "तमिळनाडू"},
    "34": {"en": "Puducherry", "hi": "पुडुचेरी", "mr": "पुदुच्चेरी"},
    "35": {"en": "Andaman and Nicobar Islands", "hi": "अंडमान और निकोबार द्वीपसमूह",
           "mr": "अंदमान आणि निकोबार बेटे"},
    "36": {"en": "Telangana", "hi": "तेलंगाना", "mr": "तेलंगणा"},
    "37": {"en": "Andhra Pradesh", "hi": "आंध्र प्रदेश", "mr": "आंध्र प्रदेश"},
    "38": {"en": "Ladakh", "hi": "लद्दाख", "mr": "लडाख"},
}

CODES = tuple(STATES)
LANGS = ("en", "hi", "mr")

# 96 is the GST portal's own code for "Other Country" - it is not invented here, and it is two digits like every
# other place of supply, so the `place_of_supply` field on the API keeps its shape and nothing downstream has to
# learn a second format. 97 ("Other Territory") is still absent: territorial waters are in India and are a
# different thing entirely, and conflating them would file an export return for a domestic supply.
EXPORT_CODE = "96"
EXPORT_NAMES = {"en": "Outside India", "hi": "भारत के बाहर", "mr": "भारताबाहेर"}


def seller_code() -> str:
    """The seller's own state code, taken from the first two digits of the GSTIN.

    DERIVED, not declared. A second copy of "27" in this file could disagree with the registration the invoice
    prints, and the whole intra/inter decision - and therefore which tax heads a return is filed under - hangs
    on the two agreeing. Reading it off the GSTIN makes that impossible by construction.
    """
    code = site.GSTIN.strip()[:2]
    if code not in STATES:
        # Not a silent fallback to Maharashtra: guessing the seller's state would classify every sale, and a
        # wrong classification is invisible in the money and wrong in the return.
        raise ValueError(f"GSTIN {site.GSTIN!r} does not start with a known GST state code, so the seller's "
                         f"place of supply cannot be determined")
    return code


def is_known(code: str | None) -> bool:
    """One of the 36 Indian states and union territories - the codes a GST return is filed for.

    NOT true for `EXPORT_CODE`: an export is not a state, it has no CGST/SGST/IGST head, and every caller that
    asks this is asking whether it can classify the tax. `is_export` is the separate question.
    """
    return isinstance(code, str) and code in STATES


def is_export(code: str | None) -> bool:
    """The place of supply is outside India - a zero-rated export of service.

    Deliberately NOT gated on the flag. This describes a place of supply that is already recorded, and an
    invoice is frozen: an order taken while exports were on must still read as an export after they are
    switched off again, or turning the flag back off would reprint last month's document as a domestic sale
    with no tax on it. What the flag gates is whether a NEW order may name it - `sells_to`.
    """
    return code == EXPORT_CODE


def sells_to(code: str | None) -> bool:
    """May a NEW order name this place of supply? The only predicate the export flag touches.

    This is what the checkout dropdown is built from and what `POST /api/payments/order` validates against, so
    the two cannot disagree: with exports off there is no path, page or API, to the zero rate.
    """
    return is_known(code) or (is_export(code) and gst.export_sales_enabled())


def name(code: str | None, lang: str = "en") -> str:
    """The place of supply's name in a language, or "" for a sale with no recorded one.

    Answers for `EXPORT_CODE` whatever the flag says, for the same reason `is_export` does: a past invoice has
    to keep printing the place of supply it was issued with.
    """
    entry = EXPORT_NAMES if is_export(code) else STATES.get(code or "")
    return entry[lang if lang in LANGS else "en"] if entry else ""


def is_intra_state(code: str | None) -> bool:
    """True when the buyer's state is the seller's - CGST+SGST rather than IGST.

    An unknown or missing code is NOT treated as intra-state. Those are the orders placed before this field
    existed, and defaulting them to the seller's own state would invent a place of supply for a past sale and
    print a CGST/SGST split nobody collected against. An export is not intra-state either - it is not in
    `STATES`, so it answers False here without needing a case of its own.
    """
    return is_known(code) and code == seller_code()


def for_language(lang: str) -> tuple[tuple[str, str], ...]:
    """((code, name), ...) sorted by the name as that language writes it - what the dropdown offers.

    Sorted by label rather than by code, because a customer scans for their own state's name and the code
    order is a filing convention that means nothing to them.

    "Outside India" is appended LAST rather than sorted into the list, and only when exports are enabled. It is
    not a state, and alphabetical order would drop it between Odisha and Puducherry where a customer scanning
    for their own state reads straight past it - or picks it by accident, which on this entry means a 0% charge.
    ONE function builds every dropdown on the site (app/web/pages.py hands it to both checkout templates in all
    three languages), so an entry that is absent here is absent everywhere.
    """
    lang = lang if lang in LANGS else "en"
    offered = sorted(((code, entry[lang]) for code, entry in STATES.items()), key=lambda pair: pair[1])
    if gst.export_sales_enabled():
        offered.append((EXPORT_CODE, EXPORT_NAMES[lang]))
    return tuple(offered)


def tax_settings(code: str | None) -> gst.GstSettings:
    """The GST setting a sale to this place of supply is charged under - the rate that reaches the order row.

    The configured rate for anywhere in India; ZERO for an export, which is the whole of the zero-rating. The
    charge does not move (see `gst.zero_rated`): what changes is that the taxable value becomes the whole of
    the listed price and the tax becomes nothing.

    An export code arriving while the flag is off is a hard failure, not a 0% sale and not an 18% one. The route
    validator already refuses it, so reaching here means something bypassed the API model - and both fallbacks
    available at that point are wrong in a way nobody would notice: charging 18% invoices a tax against a
    country, and charging 0% is the revenue leak the flag exists to prevent. Refusing is the same doctrine as
    `gst._flag`: do not guess which one was meant.
    """
    if is_export(code):
        if not gst.export_sales_enabled():
            raise ValueError(f"place of supply {code!r} is an export, and EXPORT_SALES_ENABLED is off - refusing "
                             f"to choose between a zero rate nobody authorised and a tax on a foreign supply")
        return gst.zero_rated()
    return gst.get_settings()
