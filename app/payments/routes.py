"""Payment API. Shapes are documented in docs/API.md ("Payments"); the operator's guide is docs/PAYMENTS.md.

Trust model: nothing is unlocked because a browser says so. `/verify` needs Razorpay's HMAC over (our stored
order id | payment id) made with the key secret; `/webhook` needs Razorpay's HMAC over the raw body made with the
webhook secret. Neither endpoint acts on cookies, so they need no CSRF token; `/order` only creates an unpaid
order (the uid cookie is SameSite=Lax + httpOnly) and is rate-limited.
"""

import json
import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field, model_validator

from app.ai import chat_identity as identity
from app.ai import chat_store
from app.ai.report import Birth
from app.api import BirthDetails

from . import catalogue, razorpay, service, store

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

    @model_validator(mode="after")
    def _right_shape(self):
        item = catalogue.sellable(self.product)
        if item is None:
            raise ValueError(f"{self.product} is not on sale")
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
    return {"enabled": razorpay.configured(), "key_id": razorpay.key_id() if razorpay.configured() else None,
            "test_mode": razorpay.is_test_mode(), "currency": catalogue.CURRENCY, "prices_inr": catalogue.prices_inr(),
            "packs": packs,
            # the consultation has two tiers now; `pack` stays as the first (Basic) one for older callers
            "pack": {**packs[0], "messages": packs[0]["messages"]} if packs else {}}


@router.post("/order")
def create_order(body: OrderRequest, request: Request, response: Response) -> dict:
    if not razorpay.configured():
        raise _not_configured()
    user_id = identity.user_id_from_request(request) or identity.new_user_id()
    identity.set_user_cookie(response, user_id)
    _limit(f"order:ip:{identity.ip_bucket(identity.client_ip(request))}", ORDERS_PER_HOUR_PER_IP)
    _limit(f"order:uid:{user_id}", ORDERS_PER_HOUR_PER_USER)
    item = catalogue.sellable(body.product)
    if item is None:  # the model validator already refused it; belt and braces if the two ever disagree
        raise _error(422, "not_on_sale", "This product is not on sale.")
    try:
        if item.kind == "pack":
            return service.create_order(item, user_id, session_id=body.session_id, email=body.email, phone=body.phone)
        return service.create_order(item, user_id, language=body.language, births=body.births(), names=body.names(),
                                    email=body.email, phone=body.phone)
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
        log.warning("REJECTED webhook: bad or missing X-Razorpay-Signature")
        raise _error(400, "bad_signature", "Invalid webhook signature.")
    try:
        event = json.loads(raw)
        name = str(event.get("event", ""))
        payment = (((event.get("payload") or {}).get("payment") or {}).get("entity")) or {}
    except (ValueError, AttributeError):
        raise _error(400, "bad_payload", "Webhook body is not the expected JSON.")
    event_id = request.headers.get("x-razorpay-event-id")
    if event_id and not await _in_thread(store.record_webhook_event, event_id, name):
        return {"status": "duplicate"}
    razorpay_order_id, payment_id = payment.get("order_id"), payment.get("id")
    if not razorpay_order_id or not payment_id:
        return {"status": "ignored"}
    order = await _in_thread(store.by_razorpay_id, razorpay_order_id)
    if order is None:
        return {"status": "ignored"}  # some other order on the same Razorpay account
    if name in ("payment.captured", "order.paid"):
        if payment.get("amount") != order["amount_paise"] or payment.get("currency") != order["currency"]:
            log.error("webhook %s for order %s: amount %r %r does not match %s %s - NOT fulfilling", name, order["id"],
                      payment.get("amount"), payment.get("currency"), order["amount_paise"], order["currency"])
            return {"status": "amount_mismatch"}
        await _in_thread(service.confirm_payment, razorpay_order_id, payment_id, "webhook")
        return {"status": "ok"}
    if name == "payment.failed":
        await _in_thread(store.mark_attempt_failed, razorpay_order_id, str(payment.get("error_description") or "payment failed"))
        return {"status": "noted"}
    return {"status": "ignored"}


async def _in_thread(function, *args):
    from starlette.concurrency import run_in_threadpool

    return await run_in_threadpool(function, *args)


@router.get("/order/{razorpay_order_id}")
def order_status(razorpay_order_id: str, request: Request, response: Response,
                 token: str | None = Query(default=None, max_length=80)) -> dict:
    """Polled by the page after paying. Only the buyer (uid cookie) or the holder of the order token may look."""
    order = store.by_razorpay_id(razorpay_order_id)
    owner = order is not None and (
        (token and _same(token, order["token"])) or identity.user_id_from_request(request) == order["user_id"])
    if not owner:
        raise _error(404, "order_not_found", "We could not find this order.")
    response.headers["Cache-Control"] = "private, no-store"
    return service.status(order, reveal_token=True)


def _same(a: str, b: str) -> bool:
    import hmac

    return hmac.compare_digest(a.encode(), b.encode())
