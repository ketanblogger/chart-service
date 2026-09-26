"""Consultation chat persistence (SQLite via app/db.py): users, quotas, sessions, messages, rate events.

**Phase 6 entry points** (call after Razorpay signature verification):

    from app.ai.chat_store import credit_session, credit_messages
    credit_session(session_id, 10, reference=razorpay_payment_id)   # the purchase event carries session_id
    credit_messages(user_id, 10, reference=razorpay_payment_id)     # if you already know the user id

Both are idempotent per `reference` (a replayed webhook never credits twice) and return the new paid balance.
"""

import json
import secrets
import time

from app import db

from .config import get_chat_settings

db.register_schema("consultation", """
CREATE TABLE IF NOT EXISTS chat_users (
    user_id      TEXT PRIMARY KEY,
    free_used    INTEGER NOT NULL DEFAULT 0,
    paid_balance INTEGER NOT NULL DEFAULT 0,
    busy_until   REAL NOT NULL DEFAULT 0,
    created_at   REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS chat_free_buckets (
    bucket_key TEXT PRIMARY KEY,
    free_used  INTEGER NOT NULL DEFAULT 0,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS chat_sessions (
    session_id   TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL REFERENCES chat_users(user_id),
    bucket_key   TEXT NOT NULL,
    ip_key       TEXT NOT NULL,
    name         TEXT,
    language     TEXT NOT NULL,
    birth_json   TEXT NOT NULL,
    as_of        TEXT NOT NULL,
    context_json TEXT NOT NULL,
    summary_json TEXT NOT NULL,
    facts_json   TEXT NOT NULL,
    created_at   REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS chat_messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES chat_sessions(session_id),
    role       TEXT NOT NULL,            -- user | assistant
    content    TEXT NOT NULL,
    kind       TEXT NOT NULL,            -- ai | safe (input screen) | fallback (output screen gave up)
    counted    INTEGER NOT NULL DEFAULT 0,
    meta_json  TEXT,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS chat_messages_session ON chat_messages(session_id, id);
CREATE TABLE IF NOT EXISTS chat_credits (
    reference  TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL,
    messages   INTEGER NOT NULL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS rate_events (
    key TEXT NOT NULL,
    ts  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS rate_events_key ON rate_events(key, ts);
""")

BUSY_SECONDS = 150  # a reply in flight holds the user's slot this long at most (then the lock expires)
DAY = 86400


class QuotaExhausted(Exception):
    """No free or paid messages left: show the paywall. No AI call may happen."""


class Busy(Exception):
    """The previous message of this user is still being answered."""


class RateLimited(Exception):
    def __init__(self, retry_after: int):
        super().__init__(f"rate limited, retry after {retry_after}s")
        self.retry_after = retry_after


# ---- users and quota -----------------------------------------------------------------------------


def ensure_user(user_id: str) -> None:
    with db.transaction() as conn:
        conn.execute("INSERT OR IGNORE INTO chat_users (user_id, created_at) VALUES (?, ?)", (user_id, time.time()))


def sync_free_usage(user_id: str, bucket_key: str) -> None:
    """On session start: free replies already used for these birth details (by a cleared cookie) are charged to
    this user as well, so switching to other birth details with the same cookie does not reset the trial."""
    with db.transaction() as conn:
        bucket = conn.execute("SELECT free_used FROM chat_free_buckets WHERE bucket_key = ?", (bucket_key,)).fetchone()
        if bucket:
            conn.execute("UPDATE chat_users SET free_used = MAX(free_used, ?) WHERE user_id = ?", (bucket["free_used"], user_id))


def _quota(conn, user_id: str, bucket_key: str, ip_key: str) -> dict:
    settings = get_chat_settings()
    user = conn.execute("SELECT free_used, paid_balance FROM chat_users WHERE user_id = ?", (user_id,)).fetchone()
    bucket = conn.execute("SELECT free_used FROM chat_free_buckets WHERE bucket_key = ?", (bucket_key,)).fetchone()
    used = max(user["free_used"] if user else 0, bucket["free_used"] if bucket else 0)
    free_left = max(0, settings.free_messages - used)
    if free_left:
        today = conn.execute("SELECT COUNT(*) AS n FROM rate_events WHERE key = ? AND ts > ?",
                             (f"free:{ip_key}", time.time() - DAY)).fetchone()["n"]
        free_left = min(free_left, max(0, settings.free_per_ip_per_day - today))
    paid_left = user["paid_balance"] if user else 0
    return {"free_left": free_left, "paid_left": paid_left, "messages_left": free_left + paid_left}


def quota(user_id: str, bucket_key: str, ip_key: str) -> dict:
    with db.transaction(write=False) as conn:
        return _quota(conn, user_id, bucket_key, ip_key)


def reserve_turn(user_id: str, bucket_key: str, ip_key: str) -> dict:
    """Atomically: quota left? nobody else answering for this user? -> take the slot. Call before the AI."""
    now = time.time()
    with db.transaction() as conn:
        current = _quota(conn, user_id, bucket_key, ip_key)
        if current["messages_left"] <= 0:
            raise QuotaExhausted()
        busy = conn.execute("SELECT busy_until FROM chat_users WHERE user_id = ?", (user_id,)).fetchone()
        if busy and busy["busy_until"] > now:
            raise Busy()
        conn.execute("UPDATE chat_users SET busy_until = ? WHERE user_id = ?", (now + BUSY_SECONDS, user_id))
        return current


def release_turn(user_id: str) -> None:
    with db.transaction() as conn:
        conn.execute("UPDATE chat_users SET busy_until = 0 WHERE user_id = ?", (user_id,))


def record_exchange(session_id: str, user_id: str, bucket_key: str, ip_key: str, user_text: str,
                    reply_text: str, kind: str, meta: dict | None = None) -> dict:
    """Store the user message + reply and, for a delivered AI reply only, spend one message
    (free first, then paid). Frees the user's slot. Returns the new quota."""
    now = time.time()
    counted = kind == "ai"
    with db.transaction() as conn:
        if counted:
            current = _quota(conn, user_id, bucket_key, ip_key)
            if current["free_left"] > 0:
                conn.execute("UPDATE chat_users SET free_used = free_used + 1 WHERE user_id = ?", (user_id,))
                conn.execute(
                    "INSERT INTO chat_free_buckets (bucket_key, free_used, updated_at) VALUES (?, 1, ?) "
                    "ON CONFLICT(bucket_key) DO UPDATE SET free_used = free_used + 1, updated_at = excluded.updated_at",
                    (bucket_key, now))
                conn.execute("INSERT INTO rate_events (key, ts) VALUES (?, ?)", (f"free:{ip_key}", now))
            else:
                conn.execute("UPDATE chat_users SET paid_balance = MAX(0, paid_balance - 1) WHERE user_id = ?", (user_id,))
        user_meta = json.dumps({"language": meta["language"]}) if meta and meta.get("language") else None
        conn.execute("INSERT INTO chat_messages (session_id, role, content, kind, counted, meta_json, created_at) "
                     "VALUES (?, 'user', ?, ?, 0, ?, ?)", (session_id, user_text, kind, user_meta, now))
        conn.execute("INSERT INTO chat_messages (session_id, role, content, kind, counted, meta_json, created_at) "
                     "VALUES (?, 'assistant', ?, ?, ?, ?, ?)",
                     (session_id, reply_text, kind, int(counted), json.dumps(meta) if meta else None, now))
        conn.execute("UPDATE chat_users SET busy_until = 0 WHERE user_id = ?", (user_id,))
        return _quota(conn, user_id, bucket_key, ip_key)


def credit_messages(user_id: str, messages: int, reference: str | None = None) -> int:
    """Add paid messages to a user. Idempotent per `reference`. Returns the paid balance."""
    if messages <= 0:
        raise ValueError("messages must be positive")
    now = time.time()
    with db.transaction() as conn:
        conn.execute("INSERT OR IGNORE INTO chat_users (user_id, created_at) VALUES (?, ?)", (user_id, now))
        fresh = True
        if reference:
            fresh = conn.execute("INSERT OR IGNORE INTO chat_credits (reference, user_id, messages, created_at) "
                                 "VALUES (?, ?, ?, ?)", (reference, user_id, messages, now)).rowcount == 1
        if fresh:
            conn.execute("UPDATE chat_users SET paid_balance = paid_balance + ? WHERE user_id = ?", (messages, user_id))
        return conn.execute("SELECT paid_balance FROM chat_users WHERE user_id = ?", (user_id,)).fetchone()["paid_balance"]


def credit_session(session_id: str, messages: int, reference: str | None = None) -> int:
    """Credit the user who owns this consultation session (what the `product:purchase` event carries)."""
    session = get_session(session_id)
    if session is None:
        raise KeyError(f"unknown consultation session {session_id!r}")
    return credit_messages(session["user_id"], messages, reference)


# ---- sessions and messages -----------------------------------------------------------------------


def create_session(user_id: str, bucket_key: str, ip_key: str, name: str | None, language: str, birth: dict,
                   as_of: str, context: dict, summary: dict, facts: dict) -> str:
    session_id = secrets.token_urlsafe(24)
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO chat_sessions (session_id, user_id, bucket_key, ip_key, name, language, birth_json, as_of, "
            "context_json, summary_json, facts_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (session_id, user_id, bucket_key, ip_key, name, language, json.dumps(birth), as_of,
             json.dumps(context, ensure_ascii=False), json.dumps(summary, ensure_ascii=False),
             json.dumps(facts), time.time()))
    return session_id


def update_session_data(session_id: str, as_of: str, context: dict, summary: dict, facts: dict) -> None:
    with db.transaction() as conn:
        conn.execute("UPDATE chat_sessions SET as_of = ?, context_json = ?, summary_json = ?, facts_json = ? "
                     "WHERE session_id = ?",
                     (as_of, json.dumps(context, ensure_ascii=False), json.dumps(summary, ensure_ascii=False),
                      json.dumps(facts), session_id))


def set_session_language(session_id: str, language: str) -> None:
    with db.transaction() as conn:
        conn.execute("UPDATE chat_sessions SET language = ? WHERE session_id = ?", (language, session_id))


def get_session(session_id: str) -> dict | None:
    with db.transaction(write=False) as conn:
        row = conn.execute("SELECT * FROM chat_sessions WHERE session_id = ?", (session_id,)).fetchone()
    if row is None:
        return None
    session = dict(row)
    for key in ("birth", "context", "summary", "facts"):
        session[key] = json.loads(session.pop(f"{key}_json"))
    return session


def get_messages(session_id: str) -> list[dict]:
    with db.transaction(write=False) as conn:
        rows = conn.execute("SELECT role, content, kind, meta_json, created_at FROM chat_messages "
                            "WHERE session_id = ? ORDER BY id", (session_id,)).fetchall()
    messages = []
    for row in rows:
        message = dict(row)
        meta = message.pop("meta_json")
        message["meta"] = json.loads(meta) if meta else None
        messages.append(message)
    return messages


# ---- rate limiting -------------------------------------------------------------------------------


def check_rate(key: str, limit: int, window_seconds: int) -> None:
    """Sliding window. Records the event if allowed, raises RateLimited otherwise."""
    now = time.time()
    with db.transaction() as conn:
        conn.execute("DELETE FROM rate_events WHERE ts < ? AND key NOT LIKE 'free:%'", (now - 3600,))
        conn.execute("DELETE FROM rate_events WHERE ts < ?", (now - 2 * DAY,))
        rows = conn.execute("SELECT ts FROM rate_events WHERE key = ? AND ts > ? ORDER BY ts",
                            (key, now - window_seconds)).fetchall()
        if len(rows) >= limit:
            raise RateLimited(max(1, int(rows[0]["ts"] + window_seconds - now) + 1))
        conn.execute("INSERT INTO rate_events (key, ts) VALUES (?, ?)", (key, now))
