"""Payment API. Shapes are documented in docs/API.md ("Payments"); the operator's guide is docs/PAYMENTS.md.

Trust model: nothing is unlocked because a browser says so. `/verify` needs Razorpay's HMAC over (our stored
order id | payment id) made with the key secret; `/webhook` needs Razorpay's HMAC over the raw body made with the
webhook secret. Neither endpoint acts on cookies, so they need no CSRF token; `/order` only creates an unpaid
order (the uid cookie is SameSite=Lax + httpOnly) and is rate-limited.
"""

import datetime as dt
import json
import logging
import time
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field, model_validator

from app.ai import chat_identity as identity
from app.web import accounts, site
from app.ai import chat_store
from app.ai.report import Birth
from app.api import BirthDetails

from . import catalogue, credit_note, gst, invoice, razorpay, service, states, store

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/payments")

ORDERS_PER_HOUR_PER_USER = 10
ORDERS_PER_HOUR_PER_IP = 30
VERIFIES_PER_HOUR_PER_IP = 60
MAX_WEBHOOK_BYTES = 256 * 1024  # real events are a few KB; this endpoint is unauthenticated until the HMAC is checked
_NAME = Field(default=None, max_length=60)


class OrderRequest(BaseModel):
    """`product` decides everything about the price. There is deliberately no amount field."""

    # Every id the catalogue sells. A retired id (`consultation-pack`) is deliberately absent: it still
    # works for the people who bought one, but it cannot be bought again.
    product: Literal["kundali-report", "kundali-report-simple", "matching-report", "mangal-dosha-remedy",
                     "sade-sati-guide", "consultation-basic", "consultation-premium"]
    language: Literal["en", "hi", "mr"] = "en"  # reports only; a consultation purchase uses the consultation's language
    birth: BirthDetails | None = None
    boy: BirthDetails | None = None
    girl: BirthDetails | None = None
    session_id: str | None = Field(default=None, min_length=10, max_length=80)
    name: str | None = _NAME
    boy_name: str | None = _NAME
    girl_name: str | None = _NAME
    # REQUIRED since 2026-09-26. It was optional, and the buyers who skipped it were exactly the ones who
    # could not be helped when they lost the tab - the order-link e-mail exists for that moment, so the
    # address it needs cannot be optional. The browser also asks for it twice (pay.js `validateForm`): a
    # typo here stops being a bad receipt and becomes, once accounts arrive, someone else's account.
    email: str = Field(max_length=120, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    phone: str | None = Field(default=None, pattern=r"^\+?[0-9]{10,13}$")
    # REQUIRED since 2026-09-28: the buyer's state, as a two-digit GST state code. It is the place of supply,
    # which decides whether the tax is CGST+SGST or IGST, and nothing can derive it - so a sale without it is a
    # sale that cannot be invoiced correctly. A two-digit string, not an int: "07" is Delhi and 7 is nothing.
    #
    # Making a checkout field required is the change that broke the consultation for two days in September: the
    # API began refusing orders without an e-mail while the paywall button still collected none, and the tests
    # passed a hand-written form no page produced. So this field arrives in the SAME commit as the select that
    # collects it on every path, and scripts/browser_check_payments.py asserts it for all seven products in a
    # real browser - a green unit suite is not evidence for this class of failure.
    place_of_supply: str = Field(min_length=2, max_length=2, pattern=r"^[0-9]{2}$")

    @model_validator(mode="after")
    def _right_shape(self):
        item = catalogue.sellable(self.product)
        if item is None:
            raise ValueError(f"{self.product} is not on sale")
        if not states.sells_to(self.place_of_supply):
            # The pattern above only proves it is two digits. 25 and 28 are retired codes and 99 is nothing:
            # a place of supply no return accepts has to be refused here rather than printed on an invoice.
            #
            # `sells_to`, not `is_known`, is also what keeps the EXPORT code ("96", Outside India) out while
            # `EXPORT_SALES_ENABLED` is off. That entry bills at 0% GST, so refusing it on the SERVER is the
            # whole of the protection: the option is absent from the dropdown, but a dropdown is a suggestion -
            # anyone can post `"place_of_supply": "96"` at this endpoint, and a validator that trusted the page
            # would hand them the zero rate for the price of opening devtools. This is that check.
            raise ValueError(f"place_of_supply {self.place_of_supply!r} is not a GST state code we sell to")
        if item.kind == "pack":
            if not self.session_id:
                raise ValueError(f"{self.product} needs `session_id`")
        elif self.product == "matching-report":
            if self.boy is None or self.girl is None:
                raise ValueError("matching-report needs `boy` and `girl` birth details")
        elif self.birth is None:
            raise ValueError(f"{self.product} needs `birth` details")
        return self

    def births(self) -> list[Birth]:
        people = [self.boy, self.girl] if self.product == "matching-report" else [self.birth]
        return [Birth(p.date, p.time, p.lat, p.lon, p.timezone, p.city) for p in people]

    def names(self) -> dict:
        raw = {"boy": self.boy_name, "girl": self.girl_name} if self.product == "matching-report" else {"self": self.name}
        return {key: " ".join(value.split())[:60] for key, value in raw.items() if value and value.strip()}


class VerifyRequest(BaseModel):
    razorpay_order_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_]+$")
    razorpay_payment_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_]+$")
    razorpay_signature: str = Field(min_length=32, max_length=128)


def _error(status: int, code: str, message: str, headers: dict | None = None) -> HTTPException:
    return HTTPException(status_code=status, detail={"error": code, "message": message}, headers=headers)


def _not_configured() -> HTTPException:
    return _error(503, "payments_not_configured", "Online payment is launching soon.")


def _limit(key: str, limit: int) -> None:
    try:
        chat_store.check_rate(key, limit, 3600)
    except chat_store.RateLimited as exc:
        raise _error(429, "rate_limited", "Too many payment attempts. Please wait a little and try again.",
                     {"Retry-After": str(exc.retry_after)}) from exc


@router.get("/config")
def config() -> dict:
    """What the page may know: whether payments are on, the public key id, and the price list."""
    packs = [{"product": entry.product, "price_inr": entry.price_inr, "messages": entry.messages,
              "includes_report": entry.bundled_report} for entry in catalogue.all_items() if entry.kind == "pack"]
    settings = gst.get_settings()
    # Split once per product and reuse. `entry.gst` re-reads the setting on every access, and a response that
    # read it seven times could describe two different rates in one payload if it changed mid-request.
    taxed = [(entry.product, gst.split(entry.base_paise, settings)) for entry in catalogue.all_items()]
    return {"enabled": razorpay.configured(), "key_id": razorpay.key_id() if razorpay.configured() else None,
            "test_mode": razorpay.is_test_mode(), "currency": catalogue.CURRENCY, "prices_inr": catalogue.prices_inr(),
            "packs": packs,
            # `prices_inr` above is and stays the LISTED price, because that is what every existing caller
            # reads it as. The tax sits in its own block: the rate, whether the list prices contain it, and
            # the charge each product actually produces - so a caller can show a total without recomputing
            # one. `charged_paise` is what Razorpay will be asked for, to the paisa.
            "gst": {"rate": settings.rate_text, "inclusive": settings.inclusive,
                    "amounts_inr": {product: {"base": tax.base_inr, "gst": tax.gst_inr, "total": tax.total_inr}
                                    for product, tax in taxed},
                    "charged_paise": {product: tax.total_paise for product, tax in taxed}},
            # the consultation has two tiers now; `pack` stays as the first (Basic) one for older callers
            "pack": {**packs[0], "messages": packs[0]["messages"]} if packs else {}}


# The public paths of a purchase, in ONE place - and built from the ROUTER'S OWN PREFIX, never spelled out.
#
# Spelled out, they were wrong: this router is mounted at `/api/payments`, so the invoice really lives at
# `/api/payments/invoice/{token}` and the credit note at `/api/payments/credit-note/{token}/{refund_id}`.
# "My orders" offered the unprefixed versions and both answered the site's 404 page, because nothing had
# ever matched them. The order page did not show the fault: `/order/{token}` is served by the WEB router,
# which has no prefix, so that one link was right by accident.
#
# Deriving from `router.prefix` means a remount moves these with it. The same class of mistake as the
# `order_id` key: a value invented in one module instead of taken from the module that owns it.
def public_paths(token: str) -> dict[str, str]:
    return {"order": f"/order/{token}",                      # the web router's page, deliberately unprefixed
            "invoice": f"{router.prefix}/invoice/{token}",
            "invoice_pdf": f"{router.prefix}/invoice/{token}/pdf"}


def credit_note_path(token: str, refund_id: str, pdf: bool = False) -> str:
    return f"{router.prefix}/credit-note/{token}/{refund_id}" + ("/pdf" if pdf else "")


def _buyer_id(request: Request, response: Response) -> str:
    """Who is buying, for entitlements and credits: the signed-in account, else the cookie.

    Always (re)sets the uid cookie as before, so a buyer who later signs out, or a server with
    `CHAT_LOGIN=off`, still has the identity the previous behaviour gave them."""
    cookie_user = identity.user_id_from_request(request) or identity.new_user_id()
    identity.set_user_cookie(response, cookie_user)
    if site.CHAT_LOGIN:
        email = accounts.session_email(request)
        if email:
            return accounts.account_id(email)
    return cookie_user


@router.post("/order")
def create_order(body: OrderRequest, request: Request, response: Response) -> dict:
    if not razorpay.configured():
        raise _not_configured()
    # ONE IDENTITY, the same one the consultation uses. A purchase credits questions and records who owns a
    # report; the chat reads both back. While the chat's identity was the cookie and this one was too, they
    # agreed by construction. Since sign-in became compulsory the chat's identity is the ACCOUNT, and a
    # purchase still keyed to the cookie would mean a bundle whose questions land on one identity and whose
    # report is owned by another - which showed up as "buy the PDF you already own" being offered twice.
    # The cookie is still set and still used when nobody is signed in, which is what CHAT_LOGIN=off restores.
    user_id = _buyer_id(request, response)
    _limit(f"order:ip:{identity.ip_bucket(identity.client_ip(request))}", ORDERS_PER_HOUR_PER_IP)
    _limit(f"order:uid:{user_id}", ORDERS_PER_HOUR_PER_USER)
    item = catalogue.sellable(body.product)
    if item is None:  # the model validator already refused it; belt and braces if the two ever disagree
        raise _error(422, "not_on_sale", "This product is not on sale.")
    try:
        if item.kind == "pack":
            return service.create_order(item, user_id, session_id=body.session_id, email=body.email,
                                        phone=body.phone, place_of_supply=body.place_of_supply)
        return service.create_order(item, user_id, language=body.language, births=body.births(), names=body.names(),
                                    email=body.email, phone=body.phone, place_of_supply=body.place_of_supply)
    except service.OrderError as exc:
        raise _error(exc.status, exc.code, str(exc)) from exc
    except razorpay.RazorpayError as exc:
        log.error("could not create a Razorpay order for %s: %s", body.product, exc)
        raise _error(503, "payment_service_unavailable", exc.public_message) from exc


@router.post("/verify")
def verify(body: VerifyRequest, request: Request) -> dict:
    """Checkout's success handler posts here. The signature is checked BEFORE anything is unlocked."""
    if not razorpay.configured():
        raise _not_configured()
    _limit(f"verify:ip:{identity.ip_bucket(identity.client_ip(request))}", VERIFIES_PER_HOUR_PER_IP)
    order = store.by_razorpay_id(body.razorpay_order_id)  # the id we stored when we created the order
    if order is None:
        raise _error(404, "order_not_found", "We could not find this order.")
    if not razorpay.verify_payment_signature(order["razorpay_order_id"], body.razorpay_payment_id, body.razorpay_signature):
        log.warning("REJECTED payment signature for order %s (payment id %s)", order["id"], body.razorpay_payment_id)
        raise _error(400, "bad_signature", "This payment could not be verified. If money was deducted, it will be "
                                           "confirmed automatically within a few minutes.")
    order = service.confirm_payment(order["razorpay_order_id"], body.razorpay_payment_id, via="verify")
    return service.public_view(order, reveal_token=True)  # a valid signature proves this caller is the payer


def _webhook_result(name: str, order_id: str | None, status: str) -> dict:
    """ONE INFO line per webhook event, whatever happens to it, and the body Razorpay gets back.

    Every exit from the handler goes through here, so "the journal shows nothing for that event" can only mean
    the event never arrived or the signature failed (both of which log a WARNING of their own). Before this,
    the only webhook that left a trace was one that went wrong - so the live refund on 2026-09-29 was
    diagnosed from the database rather than from the journal, and an `ignored` event left no evidence at all
    that it had been received. `status` is the word we return to Razorpay, so the journal and the HTTP
    response cannot disagree.

    OUR order id, never a customer detail: no e-mail, no name, no birth data, no amount for a payment we
    refused to fulfil. The amounts that do belong in the journal are logged by service.py against the same
    order id.
    """
    log.info("webhook %s: order %s -> %s", name or "(no event name)", order_id or "-", status)
    return {"status": status}


@router.post("/webhook")
async def webhook(request: Request) -> dict:
    """Razorpay -> us. Same idempotent fulfilment as /verify, so closing the tab after paying loses nothing."""
    if not razorpay.webhook_configured():
        raise _error(503, "webhook_not_configured", "RAZORPAY_WEBHOOK_SECRET is not set.")
    if int(request.headers.get("content-length") or 0) > MAX_WEBHOOK_BYTES:
        raise _error(413, "too_large", "Webhook body too large.")
    raw = await request.body()  # the exact bytes Razorpay signed - never re-serialise before checking
    if len(raw) > MAX_WEBHOOK_BYTES:
        raise _error(413, "too_large", "Webhook body too large.")
    if not razorpay.verify_webhook_signature(raw, request.headers.get("x-razorpay-signature")):
        # TWO DIFFERENT EVENTS, and only one of them is worth waking somebody for.
        #
        # A body that is not a Razorpay event at all - `{}`, a scan, the deploy smoke check proving this
        # endpoint rejects a bad signature - tells us nothing except that something knocked. A body that
        # LOOKS like a real event but is signed wrongly is the one that means either the secret has
        # drifted from the dashboard or somebody is trying to fulfil orders for free, and that is what the
        # alert is counting. Logged at INFO and WARNING respectively; `app/admin/errors.py` counts the
        # warning. The distinction is in the BODY, not in a header, because a header anybody can send
        # would be a way to switch the alert off from outside.
        if _looks_like_an_event(raw):
            log.warning("REJECTED webhook: bad or missing X-Razorpay-Signature on a well-formed event")
        else:
            log.info("webhook knocked with a body that is not an event (%d bytes); rejected", len(raw))
        raise _error(400, "bad_signature", "Invalid webhook signature.")
    try:
        event = json.loads(raw)
        name = str(event.get("event", ""))
        payload = event.get("payload") or {}
        payment = ((payload.get("payment") or {}).get("entity")) or {}
        # A REFUND EVENT CARRIES A REFUND ENTITY, not a payment one, and that entity has `payment_id` and NO
        # `order_id`. Assuming symmetry with payment.captured here would read an empty dict and silently ignore
        # every refund - which is what happened until 2026-09-29, when refund.processed fell through to
        # "ignored" while being subscribed on the live webhook.
        refund = ((payload.get("refund") or {}).get("entity")) or {}
    except (ValueError, AttributeError):
        raise _error(400, "bad_payload", "Webhook body is not the expected JSON.")
    event_id = request.headers.get("x-razorpay-event-id")
    if event_id and not await _in_thread(store.record_webhook_event, event_id, name):
        return _webhook_result(name, None, "duplicate")
    if name == "refund.processed":
        return await _refund_processed(name, refund)
    razorpay_order_id, payment_id = payment.get("order_id"), payment.get("id")
    if not razorpay_order_id or not payment_id:
        return _webhook_result(name, None, "ignored")
    order = await _in_thread(store.by_razorpay_id, razorpay_order_id)
    if order is None:
        return _webhook_result(name, None, "ignored")  # some other order on the same Razorpay account
    if name in ("payment.captured", "order.paid"):
        if payment.get("amount") != order["amount_paise"] or payment.get("currency") != order["currency"]:
            log.error("webhook %s for order %s: amount %r %r does not match %s %s - NOT fulfilling", name, order["id"],
                      payment.get("amount"), payment.get("currency"), order["amount_paise"], order["currency"])
            return _webhook_result(name, order["id"], "amount_mismatch")
        await _in_thread(service.confirm_payment, razorpay_order_id, payment_id, "webhook")
        return _webhook_result(name, order["id"], "ok")
    if name == "payment.failed":
        await _in_thread(store.mark_attempt_failed, razorpay_order_id, str(payment.get("error_description") or "payment failed"))
        return _webhook_result(name, order["id"], "noted")
    return _webhook_result(name, order["id"], "ignored")


async def _refund_processed(name: str, refund: dict) -> dict:
    """A refund Razorpay has actually paid back. Bookkeeping only - nothing is un-delivered.

    Deliberately NOT sharing the amount check that guards `payment.captured`: there the amount must equal the
    charge or we refuse to fulfil, whereas a PARTIAL refund legitimately differs, and copying that check across
    would have rejected exactly the case this exists to record.
    """
    refund_id, payment_id = refund.get("id"), refund.get("payment_id")
    amount = refund.get("amount")
    if not refund_id or not payment_id or not isinstance(amount, int) or amount <= 0:
        return _webhook_result(name, None, "ignored")
    order = await _in_thread(store.by_payment_id, payment_id)
    if order is None:
        return _webhook_result(name, None, "ignored")   # a refund on another order of this Razorpay account
    updated = await _in_thread(_record_refund, order["id"], refund_id, amount, refund.get("created_at"))
    if updated is None:
        return _webhook_result(name, order["id"], "ignored")
    # The credit note for this refund: its own consecutive series, reducing the taxable value and the tax
    # proportionally (app/payments/credit_note.py). Issued here rather than when the document is first opened,
    # for the same reason the invoice number is allocated at payment: the series has to be consecutive in the
    # thing being numbered, not in the order somebody happens to click. Idempotent, so a retried delivery
    # neither renumbers nor duplicates it.
    note = await _in_thread(credit_note.issue, updated, refund_id)
    if note:
        log.info("order %s: credit note %s for refund %s", order["id"], note, refund_id)
    else:
        log.warning("order %s: refund %s recorded with NO credit note (no invoice, or no GST on the sale) - "
                    "if this sale carried GST it has to be issued by hand", order["id"], refund_id)
    log.warning("REFUND %s on order %s: Rs %s of Rs %s refunded (%s). The reading is NOT withdrawn; issuing a "
                "credit note is a separate, open accounting decision.", refund_id, order["id"],
                (updated["refunded_paise"] or 0) / 100, (updated["amount_paise"] or 0) / 100,
                updated["refund_state"])
    return _webhook_result(name, order["id"], updated["refund_state"])


def _looks_like_an_event(raw: bytes) -> bool:
    """Is this shaped like a Razorpay webhook at all? Used only to decide how loudly to log a rejection.

    Deliberately cheap and structural: an `event` name and a `payload` object. It never decides whether to
    ACCEPT anything - the signature does that, before this is called and regardless of what this says.
    """
    try:
        body = json.loads(raw.decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        return False
    return isinstance(body, dict) and bool(body.get("event")) and isinstance(body.get("payload"), dict)


def _record_refund(order_id: str, refund_id: str, amount: int, created_at) -> dict | None:
    at = float(created_at) if isinstance(created_at, (int, float)) else time.time()
    recorded = store.record_refund(order_id, refund_id=refund_id, amount_paise=amount, at=at)
    if recorded:
        try:
            from app import analytics

            order = store.get_order(order_id) or {}
            # A refund is NEGATIVE revenue, so the margin on the dashboard is the real one rather than the
            # one before anybody asked for their money back.
            analytics.record_event("report", "refund", account_id=order.get("user_id") or "",
                                   revenue_inr=-(amount or 0) / 100, lang=order.get("language") or "",
                                   detail=order.get("product") or "")
        except Exception:  # noqa: BLE001 - counting never touches a refund
            log.exception("refund not counted")
    return recorded


async def _in_thread(function, *args):
    from starlette.concurrency import run_in_threadpool

    return await run_in_threadpool(function, *args)


@router.get("/order/{razorpay_order_id}")
def order_status(razorpay_order_id: str, request: Request, response: Response,
                 token: str | None = Query(default=None, max_length=80)) -> dict:
    """Polled by the page after paying. Only the buyer (uid cookie) or the holder of the order token may look."""
    order = store.by_razorpay_id(razorpay_order_id)
    owner = order is not None and (
        (token and _same(token, order["token"]))
        or identity.user_id_from_request(request) == order["user_id"]
        # ...or the account, for an order placed while signed in (the token link keeps working either way)
        or (site.CHAT_LOGIN and (email := accounts.session_email(request))
            and accounts.account_id(email) == order["user_id"]))
    if not owner:
        raise _error(404, "order_not_found", "We could not find this order.")
    response.headers["Cache-Control"] = "private, no-store"
    return service.status(order, reveal_token=True)


@router.get("/invoice/{token}", response_class=HTMLResponse)
def tax_invoice(token: str) -> HTMLResponse:
    """The GST tax invoice for a paid order, as HTML (app/payments/invoice.py says why not a PDF).

    The order token is the credential, exactly as it is for the order page and the report download - the
    customer reaches this from /order/{token}, and it works on any device without a login the site does not
    have yet. Not the uid cookie: an invoice outlives a cookie by years, and the whole point of the token is
    that the purchase survives losing one.

    404, never 403, for a bad token, an unpaid order, or a paid order with no invoice (a sale from before GST
    was charged has no tax document). Distinguishing those in the response would let someone with a wrong
    token learn that a right one exists.
    """
    order = store.by_token(token) if 20 <= len(token) <= 80 else None
    document = invoice.render(order) if order else None
    if document is None:
        raise _error(404, "invoice_not_found", "We could not find an invoice for this order.")
    # Same headers as the order page it is linked from: this document names the buyer and what they bought.
    return HTMLResponse(document, headers={"Cache-Control": "private, no-store",
                                           "X-Robots-Tag": "noindex, nofollow", "Referrer-Policy": "no-referrer"})


def _document_pdf(document: str | None, kind: str, number: str) -> FileResponse:
    """One of the two frozen documents, as a PDF file. 404 when there is no document to print.

    A DOWNLOAD, not a page: `Content-Disposition: attachment` with an ASCII file name, because the thing a
    customer actually does with an invoice is forward it to somebody who files it. The HTML stays where it is
    and stays the source this prints - it is what the order page links to for reading, and its text can be
    copied, which the Devanagari in a Chromium PDF cannot (37e5e62). Both exist deliberately.

    The render is BOUNDED, like the free chart sheet: this runs Chromium for a document that was already
    served as HTML a moment ago, so it must never be the request that queues behind a book. When the bound
    runs out it is a 503 saying to try again, not a failed download - and the HTML link on the order page is
    still there, which is why that failure is survivable.
    """
    if document is None:
        raise _error(404, "document_not_found", "We could not find this document.")
    from app.pdf import PdfError
    from app.pdf.browser import PdfBusy
    from app.pdf.service import document_download_name, ensure_document_pdf, free_wait_seconds

    try:
        path = ensure_document_pdf(document, wait=free_wait_seconds())
    except PdfBusy as exc:
        raise _error(503, "pdf_busy", "The PDF could not be prepared just now - the server is printing "
                                     "something else. Please try again in a moment.") from exc
    except PdfError as exc:
        log.error("%s PDF render failed: %s", kind, exc)
        raise _error(503, "pdf_unavailable", "The PDF could not be prepared right now. Please try again "
                                             "in a minute.") from exc
    return FileResponse(path, media_type="application/pdf",
                        filename=document_download_name(kind, number),
                        headers={"Cache-Control": "private, no-store", "X-Robots-Tag": "noindex, nofollow",
                                 "Referrer-Policy": "no-referrer"})


@router.get("/invoice/{token}/pdf", response_class=FileResponse)
def tax_invoice_pdf(token: str) -> FileResponse:
    """The tax invoice as a PDF file. Same credential and the same 404 rules as the HTML above."""
    order = store.by_token(token) if 20 <= len(token) <= 80 else None
    document = invoice.render(order, for_print=True) if order else None
    return _document_pdf(document, "invoice", (order or {}).get("invoice_no") or "invoice")


@router.get("/credit-note/{token}/{refund_id}/pdf", response_class=FileResponse)
def credit_note_pdf(token: str, refund_id: str) -> FileResponse:
    """The credit note as a PDF file. Same credential and the same 404 rules as the HTML below."""
    order = store.by_token(token) if 20 <= len(token) <= 80 else None
    refund = store.get_refund(refund_id) if order else None
    if not (order and refund and refund["order_id"] == order["id"]):
        raise _error(404, "credit_note_not_found", "We could not find a credit note for this refund.")
    return _document_pdf(credit_note.render(order, refund, for_print=True), "credit-note",
                         refund.get("credit_no") or "credit-note")


@router.get("/credit-note/{token}/{refund_id}", response_class=HTMLResponse)
def credit_note_document(token: str, refund_id: str) -> HTMLResponse:
    """The GST credit note for one refund on a paid order, as HTML.

    The order token is the credential, exactly as for the invoice and the report download. The refund id is
    in the path because an order can have several refunds and therefore several notes; it is not a second
    credential - a wrong refund id on a right token is a 404, and a right refund id on a wrong token is the
    same 404, so neither can be used to learn that the other exists.
    """
    order = store.by_token(token) if 20 <= len(token) <= 80 else None
    refund = store.get_refund(refund_id) if order else None
    document = credit_note.render(order, refund) if order and refund and refund["order_id"] == order["id"] else None
    if document is None:
        raise _error(404, "credit_note_not_found", "We could not find a credit note for this refund.")
    return HTMLResponse(document, headers={"Cache-Control": "private, no-store",
                                           "X-Robots-Tag": "noindex, nofollow", "Referrer-Policy": "no-referrer"})


def _same(a: str, b: str) -> bool:
    import hmac

    return hmac.compare_digest(a.encode(), b.encode())
