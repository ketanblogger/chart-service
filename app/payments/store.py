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
-- One row per PROCESSED REFUND. `webhook_events` already drops a repeated DELIVERY by its event id, but two
-- different events can carry the same refund, and a partial refund followed by another partial refund must add
-- up rather than collide. Keyed on the refund id, so the accumulation in `record_refund` is exactly-once.
CREATE TABLE IF NOT EXISTS webhook_refunds (
    refund_id    TEXT PRIMARY KEY,
    order_id     TEXT NOT NULL,
    amount_paise INTEGER NOT NULL,
    at           REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS webhook_refunds_order ON webhook_refunds(order_id);
CREATE TABLE IF NOT EXISTS webhook_events (
    event_id    TEXT PRIMARY KEY,
    event       TEXT NOT NULL,
    received_at REAL NOT NULL
);
-- One row per invoice series (a financial year: app/payments/invoice.py). A NEW table, so `register_schema`
-- reaches the live database on its own - CREATE TABLE IF NOT EXISTS is what does not work for a new COLUMN.
-- The counter is here and not derived from MAX(orders.invoice_no) because a number must never be reused
-- even if the order that held it is deleted, and because parsing a serial back out of a formatted string is
-- how a series silently restarts at 1.
CREATE TABLE IF NOT EXISTS invoice_numbers (
    series      TEXT PRIMARY KEY,
    last_number INTEGER NOT NULL
);
""")


# Cost of the AI work behind this order, written at fulfilment. On `orders` rather than only in the report
# file because the dashboard's margin figures have to join to a SALE, and a report file is shared by every
# order for the same chart. NULL means "not recorded" - orders paid before this column existed did not
# cost nothing, and a reader that treats NULL as 0 reports a 100% margin on them.
db.register_columns("orders", {
    "cost_inr": "REAL",        # our computed cost at the stored USD->INR rate, all calls of this order
    "usage_json": "TEXT",      # per-call tokens, attempts, repairs, redactions: the detail page reads this
})


# What the tax on this sale actually was. `amount_paise` is and stays the CHARGE, so nothing downstream
# changes meaning: these two are the charge broken up, and `base_paise + gst_paise == amount_paise` holds on
# every row written since 2026-09-28. Net revenue is `base_paise`, never `amount_paise`.
#
# The rate is stored per order, not read from the setting when an invoice is printed. The setting is a
# setting: it can change, and a reprint of March's invoice has to show the rate March's customer paid.
#
# NULL means NOT RECORDED on all three. Orders paid before these columns existed were charged a price with
# no tax line behind it; a reader that takes NULL as 0 prints a "GST ₹0.00" row on their order page and,
# worse, an invoice asserting that tax was collected and was nil. Every reader goes through
# `gst.recorded(order)`, which returns None for those rows, and nothing re-derives the split by applying
# today's rate to an old amount - today's rate is not what that customer paid.
db.register_columns("orders", {
    "base_paise":  "INTEGER",  # the listed price: the taxable value, and the net-revenue figure
    "gst_paise":   "INTEGER",  # the tax added (or, under inclusive pricing, the tax taken out)
    "gst_rate_bp": "INTEGER",  # basis points, as charged: 1800 = 18%
    "invoice_no":  "TEXT",     # the allocated tax-invoice number, e.g. RK/2627/00001. Written once, at payment
})


# The PLACE OF SUPPLY: the buyer's state, as a two-digit GST state code (app/payments/states.py). It decides
# whether the tax on the sale is filed as CGST+SGST or as IGST - a classification, never a change to what was
# charged. The CODE is stored and never a label, because the site renders in three languages and a place of
# supply matched on its display text would read as a different state per language.
#
# NULL is "not recorded" here too, and it is the reason this is a column rather than a rewrite: every order
# placed before the checkout asked for a state has no answer, and the honest invoice for those says the place
# of supply was not recorded. They are NOT backfilled - inventing one for a past sale would print a CGST/SGST
# split against a state nobody collected, which is a worse document than one admitting the gap.
db.register_columns("orders", {"place_of_supply": "TEXT"})


# THE CREDIT NOTE for a refund, on the refund's own row. A refund is not a correction to the invoice - the
# invoice records what was charged, and it was - it is a separate document under section 34 with its own
# consecutive series, reducing the taxable value and the tax proportionally. One per REFUND, because that is
# what a credit note references and dates, and Razorpay allows several partial refunds against one payment.
#
# The split is FROZEN here rather than recomputed when the document is printed, for the same reason the
# order's own `gst_rate_bp` is: the rate is a setting, the setting can change, and a credit note reprinted
# next year must show the rate that was actually credited. `invoice_no` is copied for the same reason - the
# document has to name the invoice it reduces even if that column were ever to move.
db.register_columns("webhook_refunds", {
    "credit_no":   "TEXT",      # e.g. RK-CN/2627/00001. Written once, in the same transaction as the counter bump
    "base_paise":  "INTEGER",   # the taxable value credited back
    "gst_paise":   "INTEGER",   # the tax credited back; base + gst == the refund amount, by construction
    "rate_bp":     "INTEGER",   # as credited: 1800 = 18%
    "invoice_no":  "TEXT",      # the invoice this note reduces
    "issued_at":   "REAL",
})

# REFUNDS. Razorpay refunds are issued by hand in its dashboard and reach us as `refund.processed` webhooks.
#
# `status` STAYS 'paid' and a refund gets its own fields. That is deliberate and it is the whole design
# decision here: `service.py` gates delivery on `status == "paid"`, so writing 'refunded' over it would take
# the PDF and the order link away from someone who already has them. A refund is BOOKKEEPING - the money went
# back - and revoking a delivered reading is a separate decision nobody has made. So the refund is recorded
# beside the payment, never on top of it.
#
# `refunded_paise` ACCUMULATES, because Razorpay allows several partial refunds against one payment: two Rs 30
# refunds on a Rs 59 order is fully refunded, and overwriting would have left it looking half-refunded forever.
# `refund_state` is derived from the total rather than stored independently, so the two cannot disagree.
db.register_columns("orders", {
    "refunded_paise": "INTEGER",   # NULL = never refunded; a sum, not the last refund's amount
    "refund_state":   "TEXT",      # 'partial' | 'full' - derived from refunded_paise vs amount_paise
    "refund_id":      "TEXT",      # the most recent Razorpay refund id, for tracing back to the dashboard
    "refunded_at":    "REAL",      # when the most recent refund was processed
})


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
                 email: str | None = None, phone: str | None = None, messages: int = 0,
                 base_paise: int | None = None, gst_paise: int | None = None, gst_rate_bp: int | None = None,
                 place_of_supply: str | None = None) -> dict:
    """`amount_paise` is what will be CHARGED; `base_paise` / `gst_paise` are that same figure split.

    The split is written at INSERT rather than at payment because it has to be the split that was quoted to
    the customer on the panel they clicked Pay on. Reading the setting again when the payment lands would
    invoice a rate change that happened in between, against a total the customer had already agreed to."""
    now = time.time()
    token = secrets.token_urlsafe(24)
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO orders (id, token, product, kind, amount_paise, currency, razorpay_order_id, user_id, report_id, "
            "session_id, language, as_of, request_json, names_json, email, phone, messages, created_at, updated_at, "
            "base_paise, gst_paise, gst_rate_bp, place_of_supply) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (order_id, token, product, kind, amount_paise, currency, razorpay_order_id, user_id, report_id, session_id,
             language, as_of, json.dumps(request) if request else None, json.dumps(names or {}, ensure_ascii=False),
             email, phone, messages, now, now, base_paise, gst_paise, gst_rate_bp, place_of_supply))
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


def by_payment_id(payment_id: str) -> dict | None:
    """A REFUND webhook names the payment, not the order: Razorpay's refund entity has `payment_id` and no
    `order_id`, so the symmetry with `payment.captured` does not hold and this lookup is why."""
    return _get("payment_id", payment_id) if payment_id else None


def record_refund(order_id: str, *, refund_id: str, amount_paise: int, at: float) -> dict | None:
    """Add a processed refund to an order. Returns the updated order, or None if there is nothing to update.

    ACCUMULATES and is idempotent on `refund_id`: Razorpay retries webhooks, and the same refund arriving
    twice must not double the total. Several DIFFERENT partial refunds do add up, which is the case that makes
    overwriting wrong. `status` is left alone - see the column comments.
    """
    with db.transaction() as conn:
        row = conn.execute("SELECT amount_paise, refunded_paise FROM orders WHERE id = ?",
                           (order_id,)).fetchone()
        if row is None:
            return None
        seen = conn.execute("SELECT 1 FROM webhook_refunds WHERE refund_id = ?", (refund_id,)).fetchone()
        if seen:
            return _order(conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone())
        conn.execute("INSERT INTO webhook_refunds (refund_id, order_id, amount_paise, at) VALUES (?, ?, ?, ?)",
                     (refund_id, order_id, int(amount_paise), float(at)))
        total = int(row["refunded_paise"] or 0) + int(amount_paise)
        charged = int(row["amount_paise"] or 0)
        state = "full" if charged and total >= charged else "partial"
        conn.execute("UPDATE orders SET refunded_paise = ?, refund_state = ?, refund_id = ?, refunded_at = ?, "
                     "updated_at = ? WHERE id = ?",
                     (total, state, refund_id, float(at), time.time(), order_id))
        return _order(conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone())


def refunds_for(order_id: str) -> list[dict]:
    """Every processed refund on this order, oldest first, with whatever credit note each one carries."""
    with db.transaction(write=False) as conn:
        rows = conn.execute("SELECT * FROM webhook_refunds WHERE order_id = ? ORDER BY at, refund_id",
                            (order_id,)).fetchall()
    return [dict(row) for row in rows]


def get_refund(refund_id: str) -> dict | None:
    with db.transaction(write=False) as conn:
        row = conn.execute("SELECT * FROM webhook_refunds WHERE refund_id = ?", (refund_id,)).fetchone()
    return dict(row) if row else None


def assign_credit_note(refund_id: str, counter: str, series: str, prefix: str, template: str, max_length: int,
                       *, base_paise: int, gst_paise: int, rate_bp: int, invoice_no: str,
                       issued_at: float) -> str | None:
    """Allocate the next credit-note number in `series` and write it, with its frozen split, to the refund.

    The same shape as `assign_invoice_number` and for the same reasons: the counter bump and the write are ONE
    transaction, so two refunds processed at the same instant cannot be handed the same number, and a refund
    that already has a number keeps it - Razorpay retries deliveries, and renumbering a credit note that is
    already in an accountant's hands is not an option.

    A GAP IN THE SERIES IS THE FAILURE MODE HERE, not a duplicate. Section 34 wants credit notes consecutively
    numbered, so the number may not be taken before the row that will hold it is certain to be written; both
    happen inside this transaction or neither does.

    `counter` and `series` are two different strings and the difference is the whole reason this is not just
    `assign_invoice_number`. `counter` is the row in `invoice_numbers` this series counts in ("CN2627"), and it
    must not be the invoice's ("2627") or the two series would interleave and both would have holes. `series`
    is what the NUMBER PRINTS ("2627"), because "RK-CN/2627/00001" already says CN and "RK-CN/CN2627/00001"
    both repeats it and is 18 characters against a 16-character limit - which is how this was first written.
    """
    with db.transaction() as conn:
        row = conn.execute("SELECT credit_no FROM webhook_refunds WHERE refund_id = ?", (refund_id,)).fetchone()
        if row is None:
            return None
        if row["credit_no"]:
            return row["credit_no"]
        conn.execute("INSERT OR IGNORE INTO invoice_numbers (series, last_number) VALUES (?, 0)", (counter,))
        conn.execute("UPDATE invoice_numbers SET last_number = last_number + 1 WHERE series = ?", (counter,))
        number = conn.execute("SELECT last_number FROM invoice_numbers WHERE series = ?", (counter,)).fetchone()[0]
        formatted = template.format(prefix=prefix, series=series, n=number)
        if len(formatted) > max_length:
            raise ValueError(f"credit note number {formatted!r} is longer than the {max_length} characters allowed")
        conn.execute("UPDATE webhook_refunds SET credit_no = ?, base_paise = ?, gst_paise = ?, rate_bp = ?, "
                     "invoice_no = ?, issued_at = ? WHERE refund_id = ?",
                     (formatted, int(base_paise), int(gst_paise), int(rate_bp), invoice_no,
                      float(issued_at), refund_id))
    return formatted


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


def assign_invoice_number(order_id: str, series: str, prefix: str, template: str, max_length: int) -> str | None:
    """Allocate the next number in `series` and write it to the order. Idempotent; returns what it now holds.

    The counter bump and the write to the order are ONE transaction, so two payments confirmed at the same
    instant - checkout-verify and the webhook race on every single sale - cannot be handed the same number.
    An order that already has one keeps it: this is called from the payment path, which runs more than once
    per order by design, and renumbering an invoice that may already be in somebody's inbox is not an
    option. `SELECT ... UPDATE ... SELECT` rather than `RETURNING`, which needs SQLite 3.35+.
    """
    with db.transaction() as conn:
        row = conn.execute("SELECT invoice_no FROM orders WHERE id = ?", (order_id,)).fetchone()
        if row is None:
            return None
        if row["invoice_no"]:
            return row["invoice_no"]
        conn.execute("INSERT OR IGNORE INTO invoice_numbers (series, last_number) VALUES (?, 0)", (series,))
        conn.execute("UPDATE invoice_numbers SET last_number = last_number + 1 WHERE series = ?", (series,))
        number = conn.execute("SELECT last_number FROM invoice_numbers WHERE series = ?", (series,)).fetchone()[0]
        formatted = template.format(prefix=prefix, series=series, n=number)
        if len(formatted) > max_length:
            # Refused rather than truncated. A truncated number is still a string and still unique-looking,
            # and it is the serial's own digits that would be cut off - the part that makes it consecutive.
            raise ValueError(f"invoice number {formatted!r} is longer than the {max_length} characters Rule 46(b) allows")
        conn.execute("UPDATE orders SET invoice_no = ? WHERE id = ?", (formatted, order_id))
    return formatted


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


def finish_fulfilment(order_id: str, *, ok: bool, error: str | None = None, retry_in: float = 0,
                      cost_inr: float | None = None, usage: dict | None = None) -> None:
    now = time.time()
    with db.transaction() as conn:
        conn.execute("UPDATE orders SET fulfilment = ?, error = ?, next_retry_at = ?, lease_until = 0, updated_at = ? WHERE id = ?",
                     ("ready" if ok else "failed", None if ok else (error or "")[:500], 0 if ok else now + retry_in, now, order_id))
        # Written only when the caller actually has a figure. A cached report costs nothing to serve, and
        # overwriting a recorded cost with 0 or NULL on a re-fulfilment would erase what the sale really cost.
        if cost_inr is not None:
            conn.execute("UPDATE orders SET cost_inr = ? WHERE id = ?", (float(cost_inr), order_id))
        if usage is not None:
            conn.execute("UPDATE orders SET usage_json = ? WHERE id = ?", (json.dumps(usage), order_id))


def record_cost(order_id: str, *, cost_inr: float | None, usage: dict | None) -> None:
    """Backfill path: set the cost of an order that was fulfilled before these columns existed."""
    with db.transaction() as conn:
        if cost_inr is not None:
            conn.execute("UPDATE orders SET cost_inr = ? WHERE id = ?", (float(cost_inr), order_id))
        if usage is not None:
            conn.execute("UPDATE orders SET usage_json = ? WHERE id = ?", (json.dumps(usage), order_id))


def record_webhook_event(event_id: str, event: str) -> bool:
    """False if this event id was already processed (Razorpay retries and may deliver twice)."""
    with db.transaction() as conn:
        conn.execute("DELETE FROM webhook_events WHERE received_at < ?", (time.time() - 30 * 86400,))
        return conn.execute("INSERT OR IGNORE INTO webhook_events (event_id, event, received_at) VALUES (?, ?, ?)",
                            (event_id, event, time.time())).rowcount == 1
