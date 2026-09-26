"""Orders in var/app.db (SQLite via app/db.py). One row per checkout attempt; nothing here talks to Razorpay.

status:      created -> paid            (failed = Razorpay told us an attempt failed; a later success still flips it to paid)
fulfilment:  none (unpaid) -> pending -> generating -> ready        reports
                                      \\-> failed (retryable: attempts, next_retry_at, error)
             none -> pending -> ready                                consultation pack (credited)

`token` is the unguessable key of the permanent "your purchase" page (/order/{token}) and also unlocks the
report / PDF when the cookie is gone. `lease_until` lets a crashed or restarted worker's job be picked up again.
"""

import json
import secrets
import time

from app import db

db.register_schema("payments", """
CREATE TABLE IF NOT EXISTS orders (
    id                TEXT PRIMARY KEY,          -- ours; also the Razorpay receipt
    token             TEXT NOT NULL UNIQUE,
    product           TEXT NOT NULL,
    kind              TEXT NOT NULL,             -- report | pack
    amount_paise      INTEGER NOT NULL,
    currency          TEXT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'created',
    razorpay_order_id TEXT NOT NULL UNIQUE,
    payment_id        TEXT,
    paid_via          TEXT,                      -- verify | webhook | reconcile
    user_id           TEXT NOT NULL,
    report_id         TEXT,
    session_id        TEXT,
    language          TEXT,
    as_of             TEXT,
    request_json      TEXT,                      -- resolved births: what the report is generated from
    names_json        TEXT,                      -- names for the PDF cover
    email             TEXT,
    phone             TEXT,
    messages          INTEGER NOT NULL DEFAULT 0,
    fulfilment        TEXT NOT NULL DEFAULT 'none',
    attempts          INTEGER NOT NULL DEFAULT 0,
    next_retry_at     REAL NOT NULL DEFAULT 0,
    lease_until       REAL NOT NULL DEFAULT 0,
    error             TEXT,
    created_at        REAL NOT NULL,
    paid_at           REAL,
    updated_at        REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS orders_report ON orders(report_id, status);
CREATE INDEX IF NOT EXISTS orders_user ON orders(user_id, created_at);
CREATE TABLE IF NOT EXISTS webhook_events (
    event_id    TEXT PRIMARY KEY,
    event       TEXT NOT NULL,
    received_at REAL NOT NULL
);
""")


def _order(row) -> dict | None:
    if row is None:
        return None
    order = dict(row)
    order["request"] = json.loads(order.pop("request_json") or "null")
    order["names"] = json.loads(order.pop("names_json") or "{}")
    return order


def new_order_id() -> str:
    return "ord_" + secrets.token_hex(10)  # 24 chars; Razorpay receipts allow 40


def insert_order(*, order_id: str, product: str, kind: str, amount_paise: int, currency: str, razorpay_order_id: str,
                 user_id: str, report_id: str | None = None, session_id: str | None = None, language: str | None = None,
                 as_of: str | None = None, request: dict | None = None, names: dict | None = None,
                 email: str | None = None, phone: str | None = None, messages: int = 0) -> dict:
    now = time.time()
    token = secrets.token_urlsafe(24)
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO orders (id, token, product, kind, amount_paise, currency, razorpay_order_id, user_id, report_id, "
            "session_id, language, as_of, request_json, names_json, email, phone, messages, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (order_id, token, product, kind, amount_paise, currency, razorpay_order_id, user_id, report_id, session_id,
             language, as_of, json.dumps(request) if request else None, json.dumps(names or {}, ensure_ascii=False),
             email, phone, messages, now, now))
    return get_order(order_id)


def _get(where: str, value: str) -> dict | None:
    with db.transaction(write=False) as conn:
        return _order(conn.execute(f"SELECT * FROM orders WHERE {where} = ?", (value,)).fetchone())


def get_order(order_id: str) -> dict | None:
    return _get("id", order_id)


def by_razorpay_id(razorpay_order_id: str) -> dict | None:
    return _get("razorpay_order_id", razorpay_order_id)


def by_token(token: str) -> dict | None:
    return _get("token", token) if token else None


def find(reference: str) -> dict | None:
    """By our id, the Razorpay order id or the access token (admin CLI convenience)."""
    return get_order(reference) or by_razorpay_id(reference) or by_token(reference)


def paid_orders_owning_report(report_id: str) -> list[dict]:
    """Every paid order that carries this report: report orders AND consultation purchases (the bundle)."""
    with db.transaction(write=False) as conn:
        rows = conn.execute("SELECT * FROM orders WHERE report_id = ? AND status = 'paid' ORDER BY paid_at", (report_id,)).fetchall()
    return [_order(row) for row in rows]


def paid_orders_for_report(report_id: str) -> list[dict]:
    """The entitlement view used by app/ai/entitlement.is_entitled, which compares each order's `product` with the
    report product being requested: a consultation purchase is presented as an order for the Kundali report bundled
    into it (the real product stays available as `purchased_product`)."""
    from .catalogue import report_product

    orders = paid_orders_owning_report(report_id)
    for order in orders:
        order["purchased_product"] = order["product"]
        order["product"] = report_product(order) or order["product"]
    return orders


def orders_of_user(user_id: str, paid_only: bool = True) -> list[dict]:
    with db.transaction(write=False) as conn:
        rows = conn.execute("SELECT * FROM orders WHERE user_id = ?" + (" AND status = 'paid'" if paid_only else "") +
                            " ORDER BY created_at DESC LIMIT 50", (user_id,)).fetchall()
    return [_order(row) for row in rows]


def unfinished_paid_orders() -> list[dict]:
    with db.transaction(write=False) as conn:
        rows = conn.execute("SELECT * FROM orders WHERE status = 'paid' AND fulfilment != 'ready' ORDER BY paid_at").fetchall()
    return [_order(row) for row in rows]


def mark_paid(razorpay_order_id: str, payment_id: str, via: str) -> tuple[dict | None, bool]:
    """(order, newly_paid). Idempotent: only the first caller flips created/failed -> paid and records the payment id."""
    now = time.time()
    with db.transaction() as conn:
        changed = conn.execute(
            "UPDATE orders SET status = 'paid', payment_id = ?, paid_via = ?, paid_at = ?, updated_at = ?, "
            "fulfilment = 'pending', error = NULL WHERE razorpay_order_id = ? AND status != 'paid'",
            (payment_id, via, now, now, razorpay_order_id)).rowcount == 1
        row = conn.execute("SELECT * FROM orders WHERE razorpay_order_id = ?", (razorpay_order_id,)).fetchone()
    return _order(row), changed


def mark_attempt_failed(razorpay_order_id: str, reason: str) -> None:
    """A payment attempt failed (webhook payment.failed). Never downgrades a paid order."""
    with db.transaction() as conn:
        conn.execute("UPDATE orders SET status = 'failed', error = ?, updated_at = ? WHERE razorpay_order_id = ? AND status = 'created'",
                     (reason[:300], time.time(), razorpay_order_id))


def claim_fulfilment(order_id: str, lease_seconds: int, force: bool = False) -> dict | None:
    """Atomically take the job: paid and (pending | failed | generating with an expired lease). None = someone else has it
    or there is nothing to do. `force` ignores the retry time and a live lease (admin CLI)."""
    now = time.time()
    with db.transaction() as conn:
        condition = "fulfilment != 'ready'" if force else \
            "(fulfilment = 'pending' OR (fulfilment = 'failed' AND next_retry_at <= :now) OR (fulfilment = 'generating' AND lease_until <= :now))"
        changed = conn.execute(
            f"UPDATE orders SET fulfilment = 'generating', attempts = attempts + 1, lease_until = :lease, updated_at = :now "
            f"WHERE id = :id AND status = 'paid' AND {condition}",
            {"id": order_id, "now": now, "lease": now + lease_seconds}).rowcount == 1
        if not changed:
            return None
        return _order(conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone())


def finish_fulfilment(order_id: str, *, ok: bool, error: str | None = None, retry_in: float = 0) -> None:
    now = time.time()
    with db.transaction() as conn:
        conn.execute("UPDATE orders SET fulfilment = ?, error = ?, next_retry_at = ?, lease_until = 0, updated_at = ? WHERE id = ?",
                     ("ready" if ok else "failed", None if ok else (error or "")[:500], 0 if ok else now + retry_in, now, order_id))


def record_webhook_event(event_id: str, event: str) -> bool:
    """False if this event id was already processed (Razorpay retries and may deliver twice)."""
    with db.transaction() as conn:
        conn.execute("DELETE FROM webhook_events WHERE received_at < ?", (time.time() - 30 * 86400,))
        return conn.execute("INSERT OR IGNORE INTO webhook_events (event_id, event, received_at) VALUES (?, ?, ?)",
                            (event_id, event, time.time())).rowcount == 1
