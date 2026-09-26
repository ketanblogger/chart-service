"""Orders: create -> (signature-verified) paid -> fulfilled. Every step is idempotent and survives a restart.

A paid order is never lost: `mark_paid` and the fulfilment state live in SQLite before anything slow happens.
- consultation purchase (the bundle): the questions are credited at once (`chat_store.credit_messages`, idempotent
  per payment id) AND it carries a Kundali report for the birth details of that consultation, which is then
  handled exactly like a report order (below) - same order row, same /order/{token} page.
- report: entitlement is simply "a paid order with this report_id exists" (app/ai/entitlement.py), so the customer
  is entitled the moment the payment is verified; generating the report (~9 min for the book, may fail when the AI is down)
  runs in a background thread with a lease. A failure leaves the order `paid` + `fulfilment = failed` with a
  retry time; the next status poll after that time starts it again (up to MAX_AUTO_ATTEMPTS), and
  `scripts/fulfil_order.py` retries by hand. Refunds are manual (Razorpay dashboard) for the MVP.
"""

import datetime as dt
import logging
import os
import threading
import time
from urllib.parse import urlencode

from app.ai import chat_store
from app.ai.report import Birth, generate_report, load_report, report_id, today_ist

from . import first_sale, razorpay, store
from .catalogue import CURRENCY, Item, report_product

log = logging.getLogger(__name__)

LEASE_SECONDS = 15 * 60          # a generation job that has not finished by then is considered dead
RETRY_DELAYS = (30, 120, 600, 1800, 3600)  # seconds to wait after the 1st, 2nd ... failed attempt
MAX_AUTO_ATTEMPTS = len(RETRY_DELAYS) + 1   # after that only scripts/fulfil_order.py retries


class OrderError(ValueError):
    """The order cannot be created as asked (bad session, ...). `code` goes to the client."""

    def __init__(self, code: str, message: str, status: int = 422):
        super().__init__(message)
        self.code, self.status = code, status


def _spawn(function, *args) -> None:
    """Background job runner. Tests replace this to run jobs inline or not at all."""
    threading.Thread(target=function, args=args, daemon=True, name="order-fulfilment").start()


# ---- create ----------------------------------------------------------------------------------------


def _birth_json(birth: Birth) -> dict:
    return {"date": birth.date.isoformat(), "time": birth.time.isoformat(timespec="seconds"), "lat": birth.lat,
            "lon": birth.lon, "timezone": birth.timezone, "city": birth.city}


def _birth_from_json(data: dict) -> Birth:
    return Birth(dt.date.fromisoformat(data["date"]), dt.time.fromisoformat(data["time"]), data["lat"], data["lon"],
                 data.get("timezone"), data.get("city"))


def create_order(item: Item, user_id: str, *, language: str = "en", births: list[Birth] | None = None,
                 session_id: str | None = None, names: dict | None = None, email: str | None = None,
                 phone: str | None = None) -> dict:
    """Creates the Razorpay order and our row. Returns what Checkout needs (never a secret).
    The amount comes from `item` (the server catalogue) - callers have no way to pass one."""
    fields: dict = {}
    if item.kind == "pack":
        session = chat_store.get_session(session_id) if session_id else None
        if session is None:
            raise OrderError("session_not_found", "This consultation has expired. Please start it again, then buy the pack.", 404)
        user_id = session["user_id"]  # the pack goes to whoever owns the conversation, even if the cookie was lost
        fields = {"session_id": session_id, "messages": item.messages}
        if item.bundled_report:  # the consultation purchase always includes the Kundali PDF for this consultation's birth details
            births = [_birth_from_json(session["birth"])]
            language = session.get("language") if session.get("language") in ("en", "hi", "mr") else "en"
            names = {"self": session["name"]} if session.get("name") else {}
            fields.update(_bundled_report_fields(item.bundled_report, user_id, language, births))
    else:
        as_of = today_ist()  # pinned now and stored: the purchased report is this exact one, forever
        rid = report_id(item.product, language, births, as_of)
        for paid in store.paid_orders_owning_report(rid):
            # same person, same report, already bought today (alone, or inside a consultation purchase): never charge twice
            if paid["user_id"] == user_id and report_product(paid) == item.product:
                return {"already_paid": True, **public_view(paid, reveal_token=True)}
        fields = {"report_id": rid, "language": language, "as_of": as_of.isoformat(),
                  "request": {"births": [_birth_json(birth) for birth in births]}}

    order_id = store.new_order_id()
    remote = razorpay.create_order(item.amount_paise, receipt=order_id, notes={"product": item.product, "order": order_id})
    order = store.insert_order(order_id=order_id, product=item.product, kind=item.kind, amount_paise=item.amount_paise,
                               currency=CURRENCY, razorpay_order_id=remote["id"], user_id=user_id, names=names,
                               email=email, phone=phone, **fields)
    log.info("order %s created: %s %s paise, razorpay %s", order_id, item.product, item.amount_paise, remote["id"])
    prefill = {"name": next(iter((names or {}).values()), "") or "", "email": email or "", "contact": phone or ""}
    return {"already_paid": False, "order_id": order["razorpay_order_id"], "amount": item.amount_paise, "currency": CURRENCY,
            "key_id": razorpay.key_id(), "product": item.product, "description": item.name,
            "prefill": {key: value for key, value in prefill.items() if value}}


def _bundled_report_fields(product: str, user_id: str, language: str, births: list[Birth]) -> dict:
    """Report part of a consultation order. If this person already owns that Kundali report (bought alone, or with an
    earlier consultation purchase) for the same birth details and language, the new order points at the SAME report:
    nothing is generated twice and they keep one PDF. Otherwise the report is pinned to today, like any report order."""
    request = {"births": [_birth_json(birth) for birth in births]}
    for earlier in store.orders_of_user(user_id):
        if report_product(earlier) == product and earlier["language"] == language and earlier["request"] == request:
            return {"report_id": earlier["report_id"], "language": language, "as_of": earlier["as_of"], "request": request}
    as_of = today_ist()
    return {"report_id": report_id(product, language, births, as_of), "language": language, "as_of": as_of.isoformat(),
            "request": request}


# ---- paid + fulfilment -----------------------------------------------------------------------------


def confirm_payment(razorpay_order_id: str, payment_id: str, via: str) -> dict | None:
    """Call ONLY after a signature (checkout or webhook) or the Razorpay API has proven the payment.
    Idempotent: verify + webhook + a retry all end in one credit / one report job."""
    order, newly_paid = store.mark_paid(razorpay_order_id, payment_id, via)
    if order is None:
        return None
    if newly_paid:
        log.info("order %s PAID via %s (payment %s, %s paise)", order["id"], via, payment_id, order["amount_paise"])
        first_sale.note_paid(order)  # the very first LIVE-key payment starts the Swiss Ephemeris licence week
        # The permanent link, by e-mail, once per order - `newly_paid` is what makes it once, because
        # checkout-verify and the webhook both land here. In the background: it is a network call to a
        # third party on the path that answers a payment, and nothing about it may delay that answer.
        _spawn(_email_order_link, order)
    fulfil(order)
    return store.get_order(order["id"])


def _email_order_link(order: dict) -> None:
    """Send the order-link e-mail, swallowing everything. Runs in a daemon thread off the payment path.

    A paid order must never fail because an e-mail did. The customer already has the link on screen and
    the order page is permanent, so the worst case here is a message that never arrives, which is why
    this catches rather than retries."""
    from . import order_email

    try:
        order_email.send_order_link(order)
    except Exception:  # noqa: BLE001 - a third party's failure may not reach a paid order
        log.exception("order %s: sending the order-link e-mail failed", order["id"])


def _needs_work(order: dict, force: bool = False) -> bool:
    if order["status"] != "paid" or order["fulfilment"] == "ready":
        return False
    if force or order["fulfilment"] == "pending":
        return True
    now = time.time()
    if order["fulfilment"] == "generating":
        return order["lease_until"] <= now
    return order["fulfilment"] == "failed" and order["attempts"] < MAX_AUTO_ATTEMPTS and order["next_retry_at"] <= now


def fulfil(order: dict, *, sync: bool = False, force: bool = False) -> None:
    """Deliver what was bought, if it still needs delivering. Safe to call any number of times."""
    if not _needs_work(order, force):
        return
    if order["kind"] == "pack":
        # idempotent per payment id, so re-running it for the report part below never credits twice
        balance = chat_store.credit_messages(order["user_id"], order["messages"], reference=order["payment_id"])
        log.info("order %s: +%s consultation messages (paid balance now %s)", order["id"], order["messages"], balance)
        if not order["report_id"]:  # a pack sold before the bundle existed
            store.finish_fulfilment(order["id"], ok=True)
            return
    if load_report(order["report_id"]) is not None:  # generated earlier (e.g. same details bought twice): nothing to do
        store.finish_fulfilment(order["id"], ok=True)
        log.info("order %s fulfilled: report %s already generated", order["id"], order["report_id"])
    elif sync:
        _generate(order["id"], force)
    else:
        _spawn(_generate, order["id"], force)


def _generate(order_id: str, force: bool = False) -> None:
    order = store.claim_fulfilment(order_id, LEASE_SECONDS, force=force)
    if order is None:
        return  # another worker has it, or it is done
    try:
        births = [_birth_from_json(birth) for birth in order["request"]["births"]]
        report = generate_report(report_product(order), order["language"], births, as_of=dt.date.fromisoformat(order["as_of"]))
        if report["id"] != order["report_id"]:  # would mean the id recipe changed between purchase and generation
            raise RuntimeError(f"generated report id {report['id']} differs from the purchased {order['report_id']}")
    except Exception as exc:  # noqa: BLE001 - whatever went wrong, the paid order must stay retryable
        delay = RETRY_DELAYS[min(order["attempts"], len(RETRY_DELAYS)) - 1]
        store.finish_fulfilment(order_id, ok=False, error=f"{type(exc).__name__}: {exc}", retry_in=delay)
        final = order["attempts"] >= MAX_AUTO_ATTEMPTS
        log.error("PAID order %s: report generation failed (attempt %s/%s): %s: %s -- %s", order_id, order["attempts"],
                  MAX_AUTO_ATTEMPTS, type(exc).__name__, exc,
                  "automatic retries exhausted; run scripts/fulfil_order.py %s" % order_id if final else f"retry in {delay}s")
        return
    store.finish_fulfilment(order_id, ok=True)
    log.info("order %s fulfilled: report %s generated (attempt %s)", order_id, order["report_id"], order["attempts"])


# ---- what the customer sees --------------------------------------------------------------------------


def _name_query(order: dict) -> dict:
    names = order.get("names") or {}
    if "boy" in names or "girl" in names:
        return {key: value for key, value in (("boy_name", names.get("boy")), ("girl_name", names.get("girl"))) if value}
    return {"name": names["self"]} if names.get("self") else {}


def report_email_enabled() -> bool:
    """True when the "we will also e-mail this to you" promise can actually be kept.

    OFF by default, deliberately. The waiting screen offers to say that a copy is coming by e-mail, and
    the sending side does not exist yet - no provider, no verified sender domain, no key. A screen that
    promises an e-mail nobody sends is worse than one that promises nothing, because the customer stops
    watching the page that IS delivering. So the copy ships now, in three languages, and appears the day
    the sender does. Turn it on with REPORT_EMAIL_ENABLED=1 once report e-mail actually sends.
    """
    return os.getenv("REPORT_EMAIL_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}


def public_view(order: dict, *, reveal_token: bool = False) -> dict:
    """Status for the page. Tokened URLs only appear when `reveal_token` (caller proved payment or ownership)."""
    from . import order_page
    from .catalogue import item as catalogue_item

    entry = catalogue_item(order["product"])
    paid = order["status"] == "paid"
    view = {"order_id": order["razorpay_order_id"], "status": order["status"], "product": order["product"],
            "product_name": entry.name if entry else order["product"], "kind": order["kind"],
            "amount_inr": order["amount_paise"] / 100, "fulfilment": order["fulfilment"] if paid else "none",
            "retrying": paid and order["fulfilment"] == "failed" and order["attempts"] < MAX_AUTO_ATTEMPTS,
            "messages": order["messages"], "includes_report": bool(order["report_id"]),
            # How long to tell this customer the report takes. Computed here from the tier the order entitles,
            # so the browser never has to work it out: pay.js prints what the server says.
            "report_wait": order_page.wait_range(order),
            # When this order was paid, so the waiting screen can show real elapsed time rather than time
            # since this tab opened - the order page is reachable from any device, days later.
            # `.get`, not `[...]`: this builder is handed sparse dicts too, and a missing timestamp just
            # means "no real elapsed time" - the waiting screen then shows stage one, which is the truth
            # for a payment that has only just happened.
            "paid_at": order.get("paid_at") if paid else None,
            "order_url": None, "report_url": None, "pdf_url": None, "email_copy": None}
    if paid and reveal_token:
        view["order_url"] = f"/order/{order['token']}"
        # Behind the token like the URLs are: an e-mail address is the customer's personal data, and this
        # view is also served to callers who have only proved nothing.
        if report_email_enabled() and (order.get("email") or "").strip():
            view["email_copy"] = order["email"].strip()
        if order["report_id"] and order["fulfilment"] == "ready":
            view["report_url"] = f"/api/report/{order['report_id']}?{urlencode({'token': order['token']})}"
            view["pdf_url"] = f"/api/report/{order['report_id']}/pdf?{urlencode({**_name_query(order), 'token': order['token']})}"
    return view


def status(order: dict, *, reveal_token: bool) -> dict:
    """public_view + the self-healing poke: a paid order whose job is due (pending / retry time reached / dead lease)
    is started again by the customer's own status poll."""
    if _needs_work(order):
        fulfil(order)
        order = store.get_order(order["id"]) or order
    return public_view(order, reveal_token=reveal_token)


def resume_unfinished() -> int:
    """At startup: paid orders whose job is due (the process was restarted mid-generation, or a retry is due).
    Returns how many were (re)started. Orders that are not due yet wait for the customer's poll or the admin script."""
    started = 0
    for order in store.unfinished_paid_orders():
        if _needs_work(order):
            log.info("resuming paid order %s (fulfilment=%s, attempts=%s)", order["id"], order["fulfilment"], order["attempts"])
            fulfil(order)
            started += 1
    return started
