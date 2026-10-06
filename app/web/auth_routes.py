"""Sign in with an e-mail code, and the list of what this address has bought.

Four endpoints and two pages. There is no password to set, reset, leak or phish, and a session can do exactly
two things: spend credits the address already has, and read orders the address already placed. That is the
whole of the account, and it is why losing a session cookie is not a security event here - it can do nothing
a forwarded order e-mail could not.

THE FORM MUST NOT BECOME AN ORACLE. `request-code` answers the same for an address with twenty orders, an
address with none, and an address this site has never seen: anything else turns a public form into a way to
ask "is this person a customer of yours". The only answers that differ are the ones the person at the keyboard
caused themselves - a malformed address, a throwaway domain, or too many requests.
"""

import datetime as dt
import logging
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field

from app import mailer
from app.ai import chat_identity as identity
from app.ai import chat_store
from app.payments import catalogue
from app.payments import routes as payment_routes
from app.payments import store as payment_store
from app.rashifal import i18n as words
from app.web import accounts, i18n, pages, site
from app.web.routes import page_context, respond

log = logging.getLogger("app.auth")
router = APIRouter()
IST = ZoneInfo("Asia/Kolkata")


class CodeRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    name: str = Field(default="", max_length=60)
    language: str = Field(default="en", max_length=2)


class CodeVerify(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    code: str = Field(min_length=4, max_length=8)


@router.post("/api/auth/request-code")
def request_code(body: CodeRequest, request: Request) -> dict:
    ip_key = identity.ip_bucket(identity.client_ip(request))
    try:
        code = accounts.request_code(body.email, body.name, ip_key)
    except accounts.Rejected as rejected:
        raise HTTPException(status_code=400, detail={"reason": rejected.reason}) from None
    except accounts.RateLimited as limited:
        raise HTTPException(status_code=429, detail={"reason": "rate_limited",
                                                     "retry_after": limited.retry_after}) from None
    language = body.language if body.language in ("en", "hi", "mr") else "en"
    mailer.send_login_code(body.email, code, language, body.name)
    # The code is never returned to the browser. The journal records that one was sent, not what it was.
    log.info("sign-in code sent")
    return {"sent": True}


@router.post("/api/auth/verify-code")
def verify_code(body: CodeVerify, request: Request, response: Response) -> dict:
    ip_key = identity.ip_bucket(identity.client_ip(request))
    try:
        email = accounts.verify_code(body.email, body.code, ip_key)
    except accounts.RateLimited:
        raise HTTPException(status_code=429, detail={"reason": "too_many_accounts"}) from None
    if not email:
        raise HTTPException(status_code=400, detail={"reason": "bad_code"})

    # THE ADOPTION, and the only moment it can happen: the cookie that is about to stop being this person's
    # identity is still on the request. Anyone who bought a pack before sign-in was compulsory has their
    # balance on that cookie, and without this it becomes unreadable - paid credits lost, for customers who
    # already paid. Once per cookie, enforced in the store by a primary key rather than a check.
    # Whether this address has ever signed in before, read BEFORE the session is set: afterwards there is
    # no way to tell a new account from a returning one, and "sign-ups" is a different number from
    # "sign-ins".
    first_time = not chat_store.account_seen_before(accounts.account_id(email))
    cookie_user = identity.user_id_from_request(request)
    moved = chat_store.adopt_paid_balance(cookie_user, accounts.account_id(email)) if cookie_user else 0
    if moved:
        log.info("adopted %d paid message(s) from a pre-login cookie", moved)

    accounts.set_session(response, email)
    # A sign-in, and whether it was the first one for this address. No address is recorded - the account
    # id is already a hash - and nothing about the code is kept.
    try:
        from app import analytics

        analytics.record_event("auth", "sign-up" if first_time else "sign-in",
                               account_id=accounts.account_id(email),
                               is_admin=accounts.is_admin(email))
    except Exception:  # noqa: BLE001 - counting never blocks a sign-in
        log.exception("sign-in not counted")
    return {"signed_in": True, "adopted": moved}


@router.post("/api/auth/sign-out")
def sign_out(response: Response) -> dict:
    accounts.clear_session(response)
    return {"signed_out": True}


def _add_pages() -> None:
    for lang in i18n.LANGS:
        _add_login(lang)
        _add_orders(lang)


def _login_path(lang: str) -> str:
    return "/login" if lang == "en" else f"/{lang}/login"


def _orders_path(lang: str) -> str:
    return "/orders" if lang == "en" else f"/{lang}/orders"


def _add_login(lang: str) -> None:
    def login_page(request: Request) -> HTMLResponse:
        if accounts.session_email(request):
            return RedirectResponse(_orders_path(lang), status_code=303)
        context = page_context(None, lang, path=_login_path(lang))
        context.update(auth=pages.auth_copy(lang), orders_path=_orders_path(lang),
                       chat_path=i18n.url_for("consultation", lang),
                       free_messages=pages.chat_offer()["free_messages"], robots="noindex, nofollow")
        return respond(request, "login.html", context)

    router.add_api_route(_login_path(lang), login_page, methods=["GET"],
                         response_class=HTMLResponse, name=f"login_{lang}", include_in_schema=False)


def _add_orders(lang: str) -> None:
    def orders_page(request: Request) -> HTMLResponse:
        email = accounts.session_email(request)
        if not email:
            # ...and BACK to the orders page afterwards. A sign-in that lands the visitor on a different
            # page has made them navigate twice for something they already asked for.
            return RedirectResponse(f"{_login_path(lang)}?next={_orders_path(lang)}", status_code=303)
        context = page_context(None, lang, path=_orders_path(lang))
        # EVERY DISPLAY FIELD IS BUILT HERE, not reached for in the template.
        #
        # "My orders" was a 500 for every customer who actually had one. The order row's primary key is `id`
        # - there is no `order_id` - so `refunds_for(order["order_id"])` raised KeyError the moment the list
        # was not empty, and the template then reached for `product_label`, `created_label` and `amount_inr`,
        # none of which exist on an order either. An empty list exercises none of it, which is exactly what
        # the tests had: no orders in the database, so the loop never ran and the page always rendered.
        orders = []
        for order in payment_store.orders_for_email(email):
            refunds = payment_store.refunds_for(order["id"])
            item = catalogue.item(order["product"])
            orders.append({
                "token": order["token"],
                "product_label": item.name if item else order["product"],
                "created_label": words.format_date(
                    dt.datetime.fromtimestamp(order["created_at"], dt.timezone.utc)
                    .astimezone(IST).date().isoformat(), lang),
                "amount_inr": order["amount_paise"] // 100,
                "refunded_paise": order.get("refunded_paise") or 0,
                "paths": payment_routes.public_paths(order["token"]),
                "credit_notes": [payment_routes.credit_note_path(order["token"], refund["refund_id"])
                                 for refund in refunds if refund.get("credit_no")],
            })
        context.update(auth=pages.auth_copy(lang), email=email, orders=orders,
                       login_path=_login_path(lang), robots="noindex, nofollow")
        return respond(request, "orders.html", context)

    router.add_api_route(_orders_path(lang), orders_page, methods=["GET"],
                         response_class=HTMLResponse, name=f"orders_{lang}", include_in_schema=False)


_add_pages()
