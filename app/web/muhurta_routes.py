"""The muhurta page and the search behind it, in all three trees.

OUTSIDE THE URL REGISTRY, deliberately, and `noindex` while it is young - the same treatment /login and
/orders get. The registry drives the sitemap, the hreflang alternates and the nav, and this feature ships
with `site.MUHURTA` OFF: a page that is in the sitemap but switched off is a 404 for a crawler that was
told to come. Moving it into the registry is a deliberate later step, not a side effect of building it.

With the flag off these routes are not registered at all, so the paths 404 exactly as they did before.
"""

from __future__ import annotations

import datetime as dt
import time

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field, model_validator

from app.ai import muhurta_report
from app.engine import muhurta
from app.web import i18n, site
from app.web.routes import page_context, respond

router = APIRouter()

MAX_RANGE_DAYS = 366
DEFAULT_RANGE_DAYS = 60


def path_for(lang: str) -> str:
    return "/muhurta" if lang == "en" else f"/{lang}/muhurta"


COPY = {
    "en": {
        "title": "Find an Auspicious Date (Muhurat) - with the reason for each",
        "heading": "Find an Auspicious Date (Muhurat)",
        "subline": "Shubh muhurat for your launch, business, griha pravesh or vehicle",
        "ask_ai": "Ask the AI Astrologer about these dates",
        "ask_ai_note": "The dates above are free and need no account. The astrologer is a chat, so it asks you to sign in with an e-mail code.",
        "lede": "The days in a range whose panchang suits what you are doing - each with the sunrise, tithi "
                "and nakshatra it was chosen on, and the Rahu Kaal to avoid within the day.",
        "purpose": "What is it for", "from": "From", "to": "To", "place": "Place",
        "submit": "Get Muhurat free", "searching": "Searching…",
        "none": "No day in this range satisfied the rule for this purpose. Try a longer range.",
        "found_one": "1 date found in {searched} days searched.",
        "found_many": "{found} dates found in {searched} days searched.",
        "basis": "This is arithmetic, not a guarantee. The sunrise, tithi and nakshatra are computed; which "
                 "of them suits a purpose is tradition, and tradition does not agree with itself everywhere.",
        "refused": "This finder does not answer questions about health, surgery or the outcome of a case.",
        "columns": ("Date", "Weekday", "Sunrise", "Tithi", "Nakshatra", "Rahu Kaal (avoid)"),
        "pdf": "Download as PDF",
    },
    "hi": {
        "title": "शुभ मुहूर्त खोजें - हर दिन का कारण भी",
        "heading": "शुभ मुहूर्त खोजें",
        "subline": "अपने काम के लिए अच्छा दिन और समय",
        "ask_ai": "इन दिनों के बारे में AI ज्योतिषी से पूछें",
        "ask_ai_note": "ऊपर के दिन मुफ़्त हैं, किसी खाते की ज़रूरत नहीं। ज्योतिषी से बात करने के लिए ई-मेल कोड से साइन इन करना होता है।",
        "lede": "दी गई अवधि में वे दिन जिनका पंचांग आपके काम के अनुकूल है - हर दिन के साथ सूर्योदय, तिथि और "
                "नक्षत्र, और दिन के भीतर जिससे बचना है वह राहु काल।",
        "purpose": "किस काम के लिए", "from": "से", "to": "तक", "place": "स्थान",
        "submit": "शुभ मुहूर्त मुफ्त पाएं", "searching": "खोज रहे हैं…",
        "none": "इस अवधि में कोई दिन इस काम के नियम पर खरा नहीं उतरा। अवधि बढ़ाकर देखें।",
        "found_one": "{searched} दिनों में से 1 दिन मिला।",
        "found_many": "{searched} दिनों में से {found} दिन मिले।",
        "basis": "यह गणित है, कोई गारंटी नहीं। सूर्योदय, तिथि और नक्षत्र गणना से निकले हैं; कौन सा दिन किस काम "
                 "के लिए शुभ है, यह परंपरा कहती है, और परंपरा हर जगह एक जैसी नहीं है।",
        "refused": "यह सुविधा स्वास्थ्य, ऑपरेशन या किसी मुक़दमे के नतीजे से जुड़े सवालों का उत्तर नहीं देती।",
        "columns": ("दिनांक", "वार", "सूर्योदय", "तिथि", "नक्षत्र", "राहु काल (टालें)"),
        "pdf": "PDF डाउनलोड करें",
    },
    "mr": {
        "title": "शुभ मुहूर्त शोधा - प्रत्येक दिवसाचे कारणही",
        "heading": "शुभ मुहूर्त शोधा",
        "subline": "तुमच्या कामासाठी चांगला दिवस आणि वेळ",
        "ask_ai": "या दिवसांबद्दल AI ज्योतिषाला विचारा",
        "ask_ai_note": "वरचे दिवस मोफत आहेत, खात्याची गरज नाही. ज्योतिषाशी बोलण्यासाठी मात्र ई-मेल कोडने साइन इन करावे लागते.",
        "lede": "दिलेल्या कालावधीतले ते दिवस ज्यांचे पंचांग तुमच्या कामाला अनुकूल आहे - प्रत्येक दिवसासोबत "
                "सूर्योदय, तिथी आणि नक्षत्र, आणि दिवसातला टाळायचा राहू काळ.",
        "purpose": "कशासाठी", "from": "पासून", "to": "पर्यंत", "place": "ठिकाण",
        "submit": "शुभ मुहूर्त मोफत मिळवा", "searching": "शोधत आहोत…",
        "none": "या कालावधीत एकही दिवस या कामाच्या नियमात बसला नाही. कालावधी वाढवून पाहा.",
        "found_one": "{searched} दिवसांपैकी 1 दिवस सापडला.",
        "found_many": "{searched} दिवसांपैकी {found} दिवस सापडले.",
        "basis": "हे गणित आहे, हमी नाही. सूर्योदय, तिथी आणि नक्षत्र गणनेतून आले आहेत; कोणता दिवस कोणत्या "
                 "कामाला योग्य हे परंपरा सांगते, आणि परंपरा सर्वत्र सारखी नाही.",
        "refused": "आरोग्य, शस्त्रक्रिया किंवा खटल्याच्या निकालाबद्दलच्या प्रश्नांना हे उत्तर देत नाही.",
        "columns": ("दिनांक", "वार", "सूर्योदय", "तिथी", "नक्षत्र", "राहू काळ (टाळा)"),
        "pdf": "PDF डाउनलोड करा",
    },
}


class SearchRequest(BaseModel):
    purpose: str = Field(min_length=2, max_length=40, pattern=r"^[a-z][a-z-]{1,39}$")
    from_date: dt.date
    to_date: dt.date
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    timezone: str = Field(default="Asia/Kolkata", max_length=64)
    city: str | None = Field(default=None, max_length=80)
    language: str = Field(default="en", pattern=r"^(en|hi|mr)$")

    @model_validator(mode="after")
    def _sane(self):
        if self.purpose not in muhurta.purposes():
            raise ValueError("unknown purpose")
        if self.to_date < self.from_date:
            raise ValueError("the range ends before it starts")
        if (self.to_date - self.from_date).days > MAX_RANGE_DAYS:
            raise ValueError("a search covers at most a year")
        return self


def purpose_choices(lang: str) -> list[dict]:
    return [{"key": key, "label": rule.get(lang) or rule["en"]} for key, rule in muhurta.purposes().items()]


def _count(feature: str, action: str, request: Request, *, lang: str = "", detail: str = "",
           ok: bool = True, cost_inr: float = 0.0) -> None:
    """Record one thing the site did, with the caller's account and whether they are an administrator."""
    from app import analytics
    from app.web import accounts

    email = accounts.session_email(request)
    analytics.record_event(feature, action, lang=lang, detail=detail, ok=ok, cost_inr=cost_inr,
                           account_id=accounts.account_id(email) if email else "",
                           is_admin=accounts.is_admin(email))


def _dark() -> bool:
    """The flag, read AT REQUEST TIME rather than at import.

    Registering the routes conditionally made the feature untestable from the inside: a test that patches
    `site.MUHURTA` cannot add a route that was never registered, so the off state could only be checked by
    reimporting the app. The routes exist either way now and every one of them answers 404 while the flag
    is off - which is what a visitor sees, and is also what the test can assert.
    """
    return not site.MUHURTA


def _page(lang: str):
    def muhurta_page(request: Request) -> HTMLResponse:
        if _dark():
            raise HTTPException(status_code=404)
        today = dt.date.today()
        context = page_context(None, lang, path=path_for(lang))
        context.update(
            copy=COPY[lang], purposes=purpose_choices(lang),
            default_from=today.isoformat(),
            default_to=(today + dt.timedelta(days=DEFAULT_RANGE_DAYS)).isoformat(),
            max_range_days=MAX_RANGE_DAYS,
            chart_path=i18n.url_for("kundali", lang),
            chat_path=i18n.url_for("consultation", lang),
            robots="noindex, nofollow",
            title=COPY[lang]["title"], description=COPY[lang]["lede"][:155])
        return respond(request, "muhurta.html", context)

    return muhurta_page


@router.post("/api/muhurta/search")
def search(body: SearchRequest, request: Request) -> dict:
    """The search itself. Engine only - no model is called, and nothing here is cached per user."""
    if _dark():
        raise HTTPException(status_code=404)
    try:
        muhurta.check_allowed(body.purpose)
    except muhurta.Refused as refusal:
        raise HTTPException(status_code=422, detail={"error": "refused", "reason": str(refusal)}) from refusal
    place = {"name": body.city, "lat": body.lat, "lon": body.lon, "tz": body.timezone}
    result = muhurta.find(body.purpose, body.from_date, body.to_date, place)
    _count("muhurta", "search", request, lang=body.language, detail=body.purpose)
    return {
        "purpose": body.purpose,
        # Handed back WITH the results: the PDF route will not print without it. See TOKEN_TTL_SECONDS.
        "token": issue_token(body),
        "found": result["found"],
        "searched_days": result["searched_days"],
        "basis": COPY[body.language]["basis"],
        "days": [{"date": day["date"],
                  "weekday": day["vara"]["key"] if body.language == "en" else day["vara"]["devanagari"],
                  "sunrise": day["sunrise"][11:16],
                  "tithi": (day["tithi"]["name"] if body.language == "en" else day["tithi"]["devanagari"]),
                  "paksha": (day["tithi"]["paksha"]["name"] if body.language == "en"
                             else day["tithi"]["paksha"]["devanagari"]),
                  "nakshatra": (day["nakshatra"]["name"] if body.language == "en"
                                else (day["nakshatra"].get("devanagari") or day["nakshatra"]["name"])),
                  "rahu_kaal": f"{day['rahu_kaal']['from'][11:16]}-{day['rahu_kaal']['to'][11:16]}"}
                 for day in result["days"]],
    }


# THE DAILY CAPS ON THE FREE PDF, with NO ACCOUNT ANYWHERE. The search is arithmetic - about 17ms of CPU
# for a month of dates - and the PDF runs Chromium for about a second on the ONE render slot this machine
# has, which the paid Kundali book also needs. So the PDF is the thing worth rationing.
#
# THE NETWORK CAP IS THE ONE THAT HOLDS. The per-cookie cap is deliberately soft: a cookie costs nothing
# to throw away, and anybody who clears one gets another ten. That is fine, and saying so is better than
# pretending otherwise - it exists to stop ordinary repeated clicking, not determined abuse. What stops
# determined abuse is the per-network cap, which a new cookie does not move.
PDFS_PER_COOKIE_PER_DAY = 10
PDFS_PER_IP_PER_DAY = 30
_DAY_SECONDS = 86400

# A SEARCH TOKEN, NOT A CAPTCHA. The PDF is of a search, so it may only be asked for with a token the
# SEARCH endpoint issued: an HMAC over the exact parameters plus the moment it was issued. A script that
# wants PDFs must therefore run the search first and use its answer, which is the difference between
# hammering one endpoint and walking the whole flow - and the search is cheap enough to rate-limit on its
# own terms. The token is not a secret and proves nothing about who is asking; it only proves THIS pdf
# request belongs to a search this server actually ran, recently, with these parameters.
#
# Deliberately NOT a CAPTCHA. A CAPTCHA would charge every honest visitor a puzzle to protect about a
# second of CPU that is already bounded by the render slot and the network cap, and it would be the only
# thing on this site that asks a reader to prove they are human.
TOKEN_TTL_SECONDS = 1800


def _token_payload(body: "SearchRequest") -> str:
    return "|".join([body.purpose, body.from_date.isoformat(), body.to_date.isoformat(),
                     f"{float(body.lat):.4f}", f"{float(body.lon):.4f}", body.language])


def issue_token(body: "SearchRequest", now: float | None = None) -> str:
    from app.ai import chat_identity as identity

    stamp = int(now if now is not None else time.time())
    return f"{stamp}.{identity._mac('muhurta-pdf', _token_payload(body), str(stamp))[:32]}"


def token_is_good(token: str | None, body: "SearchRequest", now: float | None = None) -> bool:
    """True when `token` was issued by this server, for exactly this search, within the TTL."""
    import hmac

    from app.ai import chat_identity as identity

    stamp_text, _, signature = (token or "").partition(".")
    if not signature or not stamp_text.isdigit():
        return False
    stamp = int(stamp_text)
    moment = now if now is not None else time.time()
    if not (0 <= moment - stamp <= TOKEN_TTL_SECONDS):
        return False        # expired, or issued in the future by a clock that is not ours
    expected = identity._mac("muhurta-pdf", _token_payload(body), stamp_text)[:32]
    return hmac.compare_digest(signature, expected)


class PdfRequest(SearchRequest):
    """The same search, plus the token the search endpoint handed back with its results."""

    token: str = Field(min_length=8, max_length=80)


@router.post("/api/muhurta/pdf")
def muhurta_pdf(body: PdfRequest, request: Request, response: Response):
    """The same dates as a PDF. FREE, and it asks for NOTHING - no payment, no account, no e-mail.

    A cold visitor with an empty cookie jar gets this. What protects it instead:

      * the SEARCH TOKEN above, so the PDF can only be asked for as the end of a flow that was walked;
      * a per-cookie daily cap, which is soft on purpose - clearing a cookie gets you another ten;
      * a per-NETWORK daily cap, which is the one that actually holds, because a new cookie does not
        move it;
      * the free render wait, so a free PDF never stands in front of a paid book;
      * a pruned cache, so the disk has a ceiling.

    The cookie is the one the site already sets for the chat; this route will set one if there is none,
    which is how the soft cap has anything to count at all.
    """
    if _dark():
        raise HTTPException(status_code=404)
    from app.ai import chat_identity as identity
    from app.ai import chat_store
    from app.pdf import browser as pdf_browser
    from app.pdf import service as pdf_service
    from app.pdf.render import render_report_html

    # A request shape check, before any work: this endpoint is called by our own page with JSON. It costs
    # nothing and turns away the laziest kind of script. `Sec-Fetch-Site` is absent on old browsers, so a
    # missing header is allowed through - a check that breaks Safari 13 to stop a curl loop is a bad trade.
    site_header = request.headers.get("sec-fetch-site")
    if site_header and site_header not in ("same-origin", "same-site", "none"):
        raise HTTPException(status_code=403, detail={"code": "cross_origin",
                                                     "message": "This can only be asked for from the page."})
    if not token_is_good(body.token, body):
        # Expired or not ours. The honest instruction is "search again", because the token comes WITH the
        # results and a stale one means the reader has had the page open for half an hour.
        raise HTTPException(status_code=409, detail={
            "code": "stale_token",
            "message": "Those results have gone stale. Press the button to find the dates again, then the "
                       "PDF."})

    muhurta.check_allowed(body.purpose)
    place = {"name": body.city, "lat": body.lat, "lon": body.lon, "tz": body.timezone}
    report = muhurta_report.build(body.purpose, body.language, body.from_date, body.to_date, place)

    cookie_id = identity.user_id_from_request(request) or identity.new_user_id()
    ip_key = identity.ip_bucket(identity.client_ip(request))

    from app.web import accounts

    admin = accounts.is_admin(accounts.session_email(request))

    def charge() -> None:
        """Counted only when a browser is really about to run - see `ensure_muhurta_pdf`. Asking twice for
        the same dates is a cache hit and costs nobody anything, so it must not cost the reader a slot.

        AN ADMINISTRATOR IS NOT RATIONED, because the caps exist to protect the box from strangers and the
        person who owns it is not one. It is still RECORDED, with `is_admin`, so their own use never shows
        up inside the numbers on their own dashboard.
        """
        if admin:
            return
        chat_store.check_rate(f"muhurta-pdf:ip:{ip_key}", PDFS_PER_IP_PER_DAY, _DAY_SECONDS)
        chat_store.check_rate(f"muhurta-pdf:uid:{cookie_id}", PDFS_PER_COOKIE_PER_DAY, _DAY_SECONDS)

    try:
        path = pdf_service.ensure_muhurta_pdf(render_report_html(report), before_render=charge)
    except chat_store.RateLimited as limited:
        raise HTTPException(status_code=429, detail={
            "code": "pdf_limit", "retry_after": limited.args[0] if limited.args else 3600,
            "message": "That is a lot of PDFs for one day. The dates are still on the page, and nothing "
                       "here costs money - try the download again tomorrow."}) from limited
    except pdf_browser.PdfBusy as busy:
        # The slot is taken, most likely by a paid book. Honest 503 rather than a queue: the dates are
        # already on the page, so nothing is lost by coming back in a moment.
        raise HTTPException(status_code=503, detail={
            "code": "busy", "message": "The printer is busy right now. The dates are on the page - try the "
                                       "PDF again in a minute."}) from busy

    _count("muhurta", "pdf", request, lang=body.language, detail=body.purpose)
    answer = FileResponse(path, media_type="application/pdf",
                          filename=f"muhurta-{body.purpose}-{body.from_date.isoformat()}.pdf",
                          headers={"Cache-Control": "private, no-store", "X-Robots-Tag": "noindex, nofollow"})
    identity.set_user_cookie(answer, cookie_id)   # so the soft cap has something to count next time
    return answer


def register() -> None:
    """Add the three pages. They answer 404 while the flag is off - see `_dark`."""
    for lang in i18n.LANGS:
        router.add_api_route(path_for(lang), _page(lang), methods=["GET"],
                             response_class=HTMLResponse, name=f"muhurta_{lang}", include_in_schema=False)


register()
