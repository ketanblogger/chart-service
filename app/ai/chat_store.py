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
-- Which cookies have already handed their paid balance to an account. A PRIMARY KEY, because "once per
-- cookie" is the whole safety property: without it, signing in twice would mint the balance twice.
CREATE TABLE IF NOT EXISTS chat_adoptions (
    user_id    TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    moved      INTEGER NOT NULL DEFAULT 0,
    at         REAL NOT NULL
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


def adopt_paid_balance(cookie_user_id: str, account_user_id: str) -> int:
    """Move a cookie's PAID balance onto the account, once per cookie, in one transaction.

    Chat requires a login now, so a request's identity is the account rather than the cookie. Anyone who
    bought a pack BEFORE that change has their balance sitting on a cookie id that nothing will ever read
    again - paid credits, silently lost, for customers who have already paid. This is the one-time bridge.

    THE FREE COUNT IS CARRIED TOO, BY `MAX` - which is the part this got wrong. It used to carry nothing but
    the balance, on the grounds that ASSIGNING a cookie's used count could hand a new account a spent trial
    or, worse for us, let a returning customer RESET one by arriving with a fresh cookie. Both of those are
    properties of assignment, not of carrying: `MAX(account, cookie)` can only ever move the count up. So
    answers used on this browser before signing in are charged to the account, a fresh cookie can never
    lower a count that is already there, and the allowance stops depending on which window you are in.

    THE PAID MOVE IS UNCHANGED: still a move rather than a copy, still zeroing the source, still once per
    cookie. The free carry rides inside the same claim so it cannot happen twice either.

    ONCE PER COOKIE, enforced by the primary key rather than by a check-then-write: two sign-ins racing on
    the same cookie would otherwise both read the balance and both add it. The INSERT is what takes the lock,
    so the second one moves nothing.
    """
    if not cookie_user_id or not account_user_id or cookie_user_id == account_user_id:
        return 0
    now = time.time()
    with db.transaction() as conn:
        claimed = conn.execute("INSERT OR IGNORE INTO chat_adoptions (user_id, account_id, moved, at) "
                               "VALUES (?, ?, 0, ?)", (cookie_user_id, account_user_id, now))
        if claimed.rowcount == 0:
            return 0                      # this cookie has already been adopted; nothing more to give
        row = conn.execute("SELECT free_used, paid_balance FROM chat_users WHERE user_id = ?",
                           (cookie_user_id,)).fetchone()
        moved = int(row["paid_balance"]) if row else 0
        used = int(row["free_used"]) if row else 0
        # The free count first, and whatever the balance turns out to be: a cookie with a spent trial and no
        # pack is the ordinary case, and returning early on `moved <= 0` would skip exactly it.
        if used > 0:
            conn.execute("INSERT INTO chat_users (user_id, free_used, paid_balance, busy_until, created_at) "
                         "VALUES (?, ?, 0, 0, ?) ON CONFLICT(user_id) DO UPDATE SET "
                         "free_used = MAX(chat_users.free_used, excluded.free_used)",
                         (account_user_id, used, now))
        if moved <= 0:
            return 0
        conn.execute("UPDATE chat_users SET paid_balance = 0 WHERE user_id = ?", (cookie_user_id,))
        conn.execute("INSERT INTO chat_users (user_id, free_used, paid_balance, busy_until, created_at) "
                     "VALUES (?, 0, ?, 0, ?) ON CONFLICT(user_id) DO UPDATE SET "
                     "paid_balance = chat_users.paid_balance + excluded.paid_balance",
                     (account_user_id, moved, now))
        conn.execute("UPDATE chat_adoptions SET moved = ? WHERE user_id = ?", (moved, cookie_user_id))
    return moved


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


# MANY CHATS PER ACCOUNT, each about a different person. Added as columns rather than a new table because
# a consultation already IS a chat - it has the birth details, the language and the history. What it did
# not have was a name a reader would recognise in a list, somebody it is ABOUT, and a way to be put away.
db.register_columns("chat_sessions", {
    "title": "TEXT NOT NULL DEFAULT ''",        # from the first question, renamable
    "subject": "TEXT NOT NULL DEFAULT ''",      # "me", or a free-text label: wife, friend, Aai
    "archived": "INTEGER NOT NULL DEFAULT 0",
    # The language AND SCRIPT this conversation is written in, settled by its first message. Empty on
    # every chat that existed before this column, which `chat.py` reads as "not settled yet" and fills in
    # from the first message it already has - so an old conversation locks to what it has been speaking.
    "style": "TEXT NOT NULL DEFAULT ''",
})

MAX_CHATS_PER_ACCOUNT = 50


class TooManyChats(Exception):
    """One account, fifty conversations. Past that the list stops being usable anyway."""


def chats_for_user(user_id: str, *, include_archived: bool = False, limit: int = 100) -> list[dict]:
    """This account's conversations, newest first - the sidebar's whole content."""
    if not user_id:
        return []
    clause = "" if include_archived else " AND s.archived = 0"
    with db.transaction(write=False) as conn:
        rows = conn.execute(
            # `summary_json` comes along for the ride so the sidebar can show each person's rashi without
            # reading every session back one at a time - fifty chats would otherwise be fifty extra queries
            # to draw one list.
            f"SELECT s.session_id, s.name, s.title, s.subject, s.language, s.archived, s.created_at, "
            f"       s.summary_json, s.style, "
            f"       (SELECT COUNT(*) FROM chat_messages m WHERE m.session_id = s.session_id) AS messages, "
            f"       (SELECT MAX(created_at) FROM chat_messages m WHERE m.session_id = s.session_id) AS last_at "
            f"FROM chat_sessions s WHERE s.user_id = ?{clause} "
            f"ORDER BY COALESCE(last_at, s.created_at) DESC LIMIT ?",
            (user_id, max(1, min(int(limit), 200)))).fetchall()
    return [dict(row) for row in rows]


def count_chats(user_id: str, *, include_archived: bool = False) -> int:
    clause = "" if include_archived else " AND archived = 0"
    with db.transaction(write=False) as conn:
        row = conn.execute(f"SELECT COUNT(*) AS n FROM chat_sessions WHERE user_id = ?{clause}",
                           (user_id,)).fetchone()
    return int(row["n"] or 0)


def set_title(session_id: str, user_id: str, title: str) -> bool:
    """Rename. Scoped to the owner, so an id alone is not enough to retitle somebody else's chat."""
    clean = " ".join((title or "").split())[:80]
    if not clean:
        return False
    with db.transaction() as conn:
        done = conn.execute("UPDATE chat_sessions SET title = ? WHERE session_id = ? AND user_id = ?",
                            (clean, session_id, user_id))
    return done.rowcount > 0


def title_if_unset(session_id: str, text: str) -> None:
    """The first question becomes the title, once. Never overwrites a name the reader chose."""
    clean = " ".join((text or "").split())[:60]
    if not clean:
        return
    with db.transaction() as conn:
        conn.execute("UPDATE chat_sessions SET title = ? WHERE session_id = ? AND title = ''",
                     (clean, session_id))


def set_subject(session_id: str, user_id: str, subject: str) -> bool:
    """Who the chat is about: "me", or a label the reader typed."""
    clean = " ".join((subject or "").split())[:40]
    with db.transaction() as conn:
        done = conn.execute("UPDATE chat_sessions SET subject = ? WHERE session_id = ? AND user_id = ?",
                            (clean, session_id, user_id))
    return done.rowcount > 0


def set_archived(session_id: str, user_id: str, archived: bool) -> bool:
    with db.transaction() as conn:
        done = conn.execute("UPDATE chat_sessions SET archived = ? WHERE session_id = ? AND user_id = ?",
                            (1 if archived else 0, session_id, user_id))
    return done.rowcount > 0


def delete_chat(session_id: str, user_id: str) -> bool:
    """REALLY delete: the messages go first, then the session, in one transaction.

    Not a flag. A reader who deletes a conversation about their marriage has asked for it to be gone, and
    a 'deleted' column that still holds every word is not what they asked for.
    """
    with db.transaction() as conn:
        owns = conn.execute("SELECT 1 FROM chat_sessions WHERE session_id = ? AND user_id = ?",
                            (session_id, user_id)).fetchone()
        if not owns:
            return False
        conn.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM chat_sessions WHERE session_id = ?", (session_id,))
    return True


def account_seen_before(user_id: str) -> bool:
    """Has this account ever been here? Used once, at sign-in, to tell a sign-up from a sign-in."""
    if not user_id:
        return False
    with db.transaction(write=False) as conn:
        row = conn.execute("SELECT 1 FROM chat_users WHERE user_id = ? LIMIT 1", (user_id,)).fetchone()
        if row:
            return True
        seen = conn.execute("SELECT 1 FROM chat_sessions WHERE user_id = ? LIMIT 1", (user_id,)).fetchone()
    return bool(seen)


def take_busy_slot(user_id: str) -> None:
    """Hold the one-answer-at-a-time lock WITHOUT spending anything.

    `reserve_turn` does two separate jobs - check the allowance and take the busy slot - and an account
    with no allowance to check still needs the second one. Two answers being written for one person at
    once is a mess for them, not a limit on them.
    """
    now = time.time()
    with db.transaction() as conn:
        busy = conn.execute("SELECT busy_until FROM chat_users WHERE user_id = ?", (user_id,)).fetchone()
        if busy and busy["busy_until"] > now:
            raise Busy()
        conn.execute("INSERT INTO chat_users (user_id, free_used, paid_balance, busy_until, created_at) "
                     "VALUES (?, 0, 0, ?, ?) ON CONFLICT(user_id) DO UPDATE SET busy_until = excluded.busy_until",
                     (user_id, now + BUSY_SECONDS, now))


def record_exchange(session_id: str, user_id: str, bucket_key: str, ip_key: str, user_text: str,
                    reply_text: str, kind: str, meta: dict | None = None, charge: bool = True) -> dict:
    """Store the user message + reply and, for a delivered AI reply only, spend one message
    (free first, then paid). Frees the user's slot. Returns the new quota.

    `charge=False` stores and frees the slot but spends nothing - an administrator's answer is recorded
    like any other and costs them nothing, because the allowance is there to meter strangers.
    """
    now = time.time()
    counted = kind == "ai" and charge
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


def quota_for_user(user_id: str) -> dict:
    """The free and paid balance on an account, with no session and no bucket in the question.

    `quota()` needs a bucket key and an IP because a free allowance can also be limited per birth and per
    network. This is the simpler question the consultation PAGE asks before any session exists: what does
    this account have left, so the page can stop promising two free answers to somebody who has none.
    """
    settings = get_chat_settings()
    with db.transaction(write=False) as conn:
        row = conn.execute("SELECT free_used, paid_balance FROM chat_users WHERE user_id = ?",
                           (user_id,)).fetchone()
    used = int(row["free_used"]) if row else 0
    paid = int(row["paid_balance"]) if row else 0
    return {"free_left": max(0, settings.free_messages - used), "paid_left": paid}


def sessions_for_user(user_id: str, limit: int = 20) -> list[dict]:
    """This user's consultations, newest first: (session_id, name, language, created_at, messages).

    THE CHAT HAS TO BELONG TO THE ACCOUNT, not to the window. The browser remembers its session id in
    sessionStorage, which is per-tab and empty in a new window - so a reader who signed in somewhere else,
    or just opened a second tab, saw no history at all and started a fresh consultation. The rows were
    always keyed to the right user; nothing ever asked for them by user.
    """
    if not user_id:
        return []
    with db.transaction(write=False) as conn:
        rows = conn.execute(
            "SELECT s.session_id, s.name, s.language, s.created_at, "
            "       (SELECT COUNT(*) FROM chat_messages m WHERE m.session_id = s.session_id) AS messages "
            "FROM chat_sessions s WHERE s.user_id = ? "
            "ORDER BY s.created_at DESC LIMIT ?", (user_id, max(1, min(int(limit), 50)))).fetchall()
    return [dict(row) for row in rows]


def set_style(session_id: str, style: str) -> None:
    """The one place a conversation's style changes: its first message, or an explicit request."""
    with db.transaction() as conn:
        conn.execute("UPDATE chat_sessions SET style = ? WHERE session_id = ?", (style, session_id))


def set_style_for_owner(session_id: str, user_id: str, style: str) -> bool:
    """The person changing the style of their OWN chat. False when the chat is not theirs."""
    with db.transaction() as conn:
        changed = conn.execute("UPDATE chat_sessions SET style = ?, language = ? "
                               "WHERE session_id = ? AND user_id = ?",
                               (style, style, session_id, user_id))
    return changed.rowcount > 0


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
