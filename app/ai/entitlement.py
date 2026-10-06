"""Who may call the paid report endpoints. Cost control: AI runs only on paid actions.

Locked by default. Two ways in:

1. `REPORTS_UNLOCKED=1` in the environment / .env - development and tests only. Never set it in production
   (the app logs a loud warning when it is set while BASE_URL is not localhost).
2. `is_entitled()`: a PAID order (app/payments, Razorpay signature verified) exists for exactly this `report_id`,
   and the caller is its buyer - proven by the signed `uid` cookie, or by the order's unguessable access token
   (`?token=...` or header `X-Order-Token`), which is how a purchase survives cleared cookies / another device.

Everything else gets HTTP 402 Payment Required before any engine or AI work happens.
"""

import hmac
import logging
import os
from urllib.parse import urlparse

from fastapi import HTTPException, Request

log = logging.getLogger(__name__)
_warned = False


def reports_unlocked() -> bool:
    return os.getenv("REPORTS_UNLOCKED", "0").strip() == "1"


def warn_if_unlocked_in_production() -> bool:
    """True (and one loud log line per process) when the dev switch is on for what looks like a public site."""
    global _warned
    host = (urlparse(os.getenv("BASE_URL", "http://localhost:8000")).hostname or "").lower()
    risky = reports_unlocked() and host not in ("localhost", "127.0.0.1", "::1", "")
    if risky and not _warned:
        _warned = True
        log.critical("REPORTS_UNLOCKED=1 while BASE_URL is %s: EVERY PAID REPORT IS FREE AND EVERY VISITOR CAN SPEND "
                     "AI CREDITS. Remove REPORTS_UNLOCKED from the environment.", host)
    return risky


def is_entitled(request: Request, product: str, report_id: str | None = None) -> bool:
    """True only for the buyer of a paid order for this exact report (see the module docstring)."""
    if not report_id:
        return False
    from app.payments import store  # local import: app.payments imports app.ai
    from .chat_identity import user_id_from_request

    # BOTH IDENTITIES, because an order may have been placed under either. Since sign-in became compulsory
    # for the consultation a purchase is recorded against the ACCOUNT, while an order placed before that -
    # or on a server with CHAT_LOGIN=off - is recorded against the cookie. Accepting only one of them would
    # tell a customer who has paid that they have not, and which one it was would depend on when they bought.
    # The order token keeps working regardless, which is what makes the purchase e-mail a reliable fallback.
    from app.web import accounts, site

    token = request.query_params.get("token") or request.headers.get("x-order-token") or ""
    identities = {user_id_from_request(request)}
    if site.CHAT_LOGIN:
        email = accounts.session_email(request)
        if email:
            identities.add(accounts.account_id(email))
    identities.discard(None)
    for order in store.paid_orders_for_report(report_id):
        if order["product"] != product:
            continue
        if order["user_id"] in identities:
            return True
        if token and hmac.compare_digest(token.encode(), order["token"].encode()):
            return True
    return False


def require_entitlement(request: Request, product: str, report_id: str | None = None) -> None:
    warn_if_unlocked_in_production()
    if reports_unlocked() or is_entitled(request, product, report_id):
        return
    raise HTTPException(
        status_code=402,
        detail={"error": "payment_required", "product": product,
                "message": "This report is a paid product. Complete the payment to unlock it."},
    )
