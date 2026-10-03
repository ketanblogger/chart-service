"""Razorpay: Orders API over plain httpx, and the two signature checks. No SDK.

Verified against the Razorpay docs on 2026-09-21:
- create order   POST https://api.razorpay.com/v1/orders, basic auth key_id:key_secret, body {amount (paise, >= 100),
                 currency, receipt (<= 40 chars, unique), notes (<= 15 pairs, 256 chars each)}
                 https://razorpay.com/docs/api/orders/create/
- payments of an order   GET /v1/orders/{id}/payments -> {items: [{id, status, captured, amount, ...}]}
                 https://razorpay.com/docs/api/orders/fetch-payments/
- checkout success: signature = hex HMAC-SHA256(order_id + "|" + razorpay_payment_id, key_secret), where order_id
                 is the one **our server** stored, not the one the browser sends back
                 https://razorpay.com/docs/payments/payment-gateway/web-integration/standard/integration-steps/
- webhook: X-Razorpay-Signature = hex HMAC-SHA256(raw request body, webhook secret); never re-serialise the body
                 https://razorpay.com/docs/webhooks/validate-test/

Secrets are read from the environment at call time and never logged or returned; only `key_id` is public.
"""

import hashlib
import hmac
import logging
import os

import httpx

log = logging.getLogger(__name__)

API_BASE = "https://api.razorpay.com/v1"
CHECKOUT_JS = "https://checkout.razorpay.com/v1/checkout.js"
TIMEOUT_SECONDS = 20


class PaymentsNotConfigured(RuntimeError):
    """RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET are not set."""


class RazorpayError(RuntimeError):
    """Razorpay could not be reached or refused the request. `public_message` is safe to show."""

    public_message = "The payment service is not responding right now. You have not been charged. Please try again in a minute."


def key_id() -> str:
    return os.getenv("RAZORPAY_KEY_ID", "").strip()


def _key_secret() -> str:
    return os.getenv("RAZORPAY_KEY_SECRET", "").strip()


def _webhook_secret() -> str:
    return os.getenv("RAZORPAY_WEBHOOK_SECRET", "").strip()


def configured() -> bool:
    return bool(key_id() and _key_secret())


def webhook_configured() -> bool:
    return bool(_webhook_secret())


def is_test_mode() -> bool:
    return key_id().startswith("rzp_test_")


_transport: httpx.BaseTransport | None = None  # tests inject httpx.MockTransport here; None = real network


def _client() -> httpx.Client:
    if not configured():
        raise PaymentsNotConfigured("RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET are not set")
    return httpx.Client(base_url=API_BASE, auth=(key_id(), _key_secret()), timeout=TIMEOUT_SECONDS,
                        transport=_transport, headers={"Accept": "application/json"})


def _call(method: str, path: str, **kwargs) -> dict:
    try:
        with _client() as client:
            response = client.request(method, path, **kwargs)
    except httpx.HTTPError as exc:
        raise RazorpayError(f"{method} {path}: {type(exc).__name__}: {exc}") from exc
    if response.status_code >= 400:
        try:
            error = response.json().get("error", {})
            detail = f"{error.get('code')}: {error.get('description')}"
        except ValueError:
            detail = response.text[:200]
        raise RazorpayError(f"{method} {path} -> HTTP {response.status_code} {detail}")
    try:
        return response.json()
    except ValueError as exc:
        raise RazorpayError(f"{method} {path}: response is not JSON") from exc


def create_order(amount_paise: int, receipt: str, notes: dict[str, str] | None = None, currency: str = "INR") -> dict:
    """The Razorpay order entity ({"id": "order_...", "amount", "currency", "status": "created", ...})."""
    if not isinstance(amount_paise, int) or amount_paise < 100:
        raise ValueError("amount must be an integer number of paise, at least 100")
    if len(receipt) > 40 or not receipt.isascii():
        raise ValueError("receipt must be at most 40 ASCII characters")
    order = _call("POST", "/orders", json={"amount": amount_paise, "currency": currency, "receipt": receipt,
                                           "notes": {k: str(v)[:256] for k, v in (notes or {}).items()}})
    if not str(order.get("id", "")).startswith("order_") or order.get("amount") != amount_paise or order.get("currency") != currency:
        raise RazorpayError(f"unexpected order entity from Razorpay: {order.get('id')!r} amount={order.get('amount')!r}")
    return order


def order_payments(order_id: str) -> list[dict]:
    """All payment attempts for an order (used by scripts/fulfil_order.py --reconcile)."""
    return list(_call("GET", f"/orders/{order_id}/payments").get("items") or [])


def _hex_hmac(secret: str, message: bytes) -> str:
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def verify_payment_signature(order_id: str, payment_id: str, signature: str) -> bool:
    """True iff `signature` is Razorpay's HMAC for this (order, payment). `order_id` must come from our database."""
    secret = _key_secret()
    if not secret or not order_id or not payment_id or not signature:
        return False
    expected = _hex_hmac(secret, f"{order_id}|{payment_id}".encode())
    return hmac.compare_digest(expected.encode(), signature.strip().lower().encode())  # bytes: any input is safe


def verify_webhook_signature(raw_body: bytes, signature: str | None) -> bool:
    secret = _webhook_secret()
    if not secret or not signature:
        return False
    return hmac.compare_digest(_hex_hmac(secret, raw_body).encode(), signature.strip().lower().encode())
