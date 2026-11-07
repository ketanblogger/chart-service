"""The admin audit log: who looked at which customer, and when.

Two things are written here, and they are the two the owner asked for by name:

- **every view of a single order**, because that page is the only place a customer's full e-mail address is
  shown, and a dashboard that can read personal data without leaving a trace is indistinguishable from one
  that cannot be audited at all;
- **every export**, because a CSV leaves the building.

Sign-ins and refused sign-ins are recorded too. They cost nothing to store and they are the first thing
anyone asks for after a scare ("when did this start?"), which is a question the application log can only
answer while its retention lasts.

WHAT IS NOT WRITTEN. Never a raw IP address: the rest of this codebase stores an HMAC of the /24 or /48
(app/ai/chat_identity.py) and there is no reason for the admin log to be the one place that keeps the real
one. Never the birth date, time or place - the audit trail records THAT a record was read, not a copy of
it, and a log full of the data it is protecting is just a second copy to lose. Any e-mail address that
reaches a `detail` string is masked on the way in, for the same reason.
"""

import logging
import time

from app import db

from .metrics import ist_day, scrub, to_ist

log = logging.getLogger(__name__)

db.register_schema("admin_audit", """
CREATE TABLE IF NOT EXISTS admin_audit (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    at      REAL NOT NULL,
    actor   TEXT NOT NULL,            -- the admin user name that was authenticated
    action  TEXT NOT NULL,            -- order_view | export | sign_in | sign_in_refused | locked_out
    subject TEXT,                     -- our order id, or the export's name
    detail  TEXT,                     -- short, masked; never birth details
    ip_key  TEXT                      -- HMAC of the network block, never the address itself
);
CREATE INDEX IF NOT EXISTS admin_audit_at ON admin_audit(at);
CREATE INDEX IF NOT EXISTS admin_audit_subject ON admin_audit(subject, at);
""")

ORDER_VIEW = "order_view"
EXPORT = "export"
SIGN_IN = "sign_in"
SIGN_IN_REFUSED = "sign_in_refused"
LOCKED_OUT = "locked_out"


def ip_key_of(request) -> str:
    """The HMAC'd network block of a request, or "" when there is no request (a cron-run digest).

    Reuses app/ai/chat_identity so the admin log buckets a network exactly the way the rate limiter does -
    two logs that bucket differently cannot be read side by side, which is when you most need them."""
    if request is None:
        return ""
    try:
        from app.ai import chat_identity

        return chat_identity.ip_bucket(chat_identity.client_ip(request))
    except Exception:  # noqa: BLE001 - an audit line must never be the thing that fails a request
        return ""


def record(actor: str, action: str, subject: str | None = None, detail: str | None = None,
           request=None, at: float | None = None) -> None:
    """Write one line. Never raises: an unwritable audit row must not take the page down with it.

    It DOES log at ERROR when it cannot write, because "the audit log silently stopped" is the failure this
    whole file exists to prevent, and a swallowed exception with no trace is exactly that failure."""
    try:
        with db.transaction() as conn:
            conn.execute("INSERT INTO admin_audit (at, actor, action, subject, detail, ip_key) VALUES (?, ?, ?, ?, ?, ?)",
                         (at or time.time(), actor or "?", action, subject,
                          scrub(detail or "")[:300] or None, ip_key_of(request)))
    except Exception:  # noqa: BLE001
        log.exception("ADMIN AUDIT WRITE FAILED: %s %s %s", actor, action, subject)


def recent(limit: int = 100) -> list[dict]:
    with db.transaction(write=False) as conn:
        rows = conn.execute("SELECT * FROM admin_audit ORDER BY at DESC LIMIT ?", (int(limit),)).fetchall()
    entries = []
    for row in rows:
        entry = dict(row)
        entry["when"] = to_ist(entry["at"])
        entry["day"] = ist_day(entry["at"])
        entries.append(entry)
    return entries


def views_of(order_id: str, limit: int = 20) -> list[dict]:
    """Who has already looked at this order - shown on the order page itself, so the trail is visible to
    the person creating it rather than only to whoever audits it later."""
    with db.transaction(write=False) as conn:
        rows = conn.execute("SELECT * FROM admin_audit WHERE subject = ? AND action = ? ORDER BY at DESC LIMIT ?",
                            (order_id, ORDER_VIEW, int(limit))).fetchall()
    return [{**dict(row), "when": to_ist(row["at"])} for row in rows]


def count_since(action: str, since: float) -> int:
    with db.transaction(write=False) as conn:
        return conn.execute("SELECT COUNT(*) AS n FROM admin_audit WHERE action = ? AND at >= ?",
                            (action, since)).fetchone()["n"]
