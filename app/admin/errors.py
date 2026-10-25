"""Where the system-health page gets its error counts: a logging handler that keeps what the app logged.

THE PROBLEM THIS SOLVES. The dashboard has to show "5xx errors in the last ten minutes", "Resend refused a
send" and "a Razorpay webhook signature failed", and none of those is recorded anywhere. They are all
already LOGGED, precisely and deliberately - `app.hardening` logs every unhandled request at ERROR with a
traceback, `app.mailer` logs a refused send at WARNING, `app.payments.routes` logs a rejected webhook
signature - but a log line lives in the journal, which the app cannot read and which a restart or a
retention policy takes away. So this attaches one `logging.Handler` and keeps those records in SQLite.

WHY A LOG HANDLER AND NOT A MIDDLEWARE. A middleware counting 5xx responses would be the obvious answer
and it is the wrong shape here: it would have to be installed into the app object, and the error path it
has to observe is the exception handler in app/hardening.py, which is not this package's file. A handler
needs nothing from anybody - it attaches to the root logger from inside this package and sees every record
the app already writes, including ones raised before a response exists.

WHAT IT IS NOT. It is not a copy of the log: only WARNING and above, only loggers under `app.`, message
text truncated, no traceback, and `metrics.scrub` applied on the way in - which masks e-mail addresses
AND removes the order-page token, because `app.hardening` logs the request path of every unhandled error and
that path is a bearer credential under `/order/`. Rows older than `RETAIN_DAYS` are
dropped on write. It is deduplicated: an identical kind+message inside `DEDUPE_SECONDS` bumps a counter on
the existing row instead of inserting, so a loop that logs the same failure a thousand times costs one row
and still reports a thousand.

**THE WRITE HAPPENS ON A DAEMON THREAD, NOT IN `emit`.** The first version wrote to SQLite inside `emit`,
which is synchronous in whichever thread logged. That puts a `BEGIN IMMEDIATE` on the path of every warning
the app raises - and if a warning is ever logged from inside a write transaction, that BEGIN waits on a lock
its own thread is holding, for the full 15-second busy timeout, before failing. No line in the app does that
today; a log line added inside a `db.transaction()` block later would, and it would look like the request had
hung. So `emit` only appends to a bounded queue and one writer thread drains it in batches. This is the
`QueueHandler` / `QueueListener` shape from the standard library, for the standard library's reason.

The queue is bounded (`QUEUE_LIMIT`): a log storm drops the oldest events and counts the drops, because the
one thing a diagnostic must never do is exhaust the memory of the process it is diagnosing.

Re-entrancy is guarded per thread as well. A handler that logs while handling a record is an infinite loop,
and `db.transaction` can itself log, so the guard is not theoretical.
"""

import logging
import os
import queue
import threading
import time

from app import db

from .metrics import ist_day, scrub, to_ist

RETAIN_DAYS = 14
DEDUPE_SECONDS = 60.0
MESSAGE_LIMIT = 400

db.register_schema("admin_errors", """
CREATE TABLE IF NOT EXISTS admin_error_events (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    at      REAL NOT NULL,
    last_at REAL NOT NULL,
    kind    TEXT NOT NULL,          -- server_error | email_refused | webhook_signature | ai_error | payment | other
    level   TEXT NOT NULL,
    logger  TEXT NOT NULL,
    message TEXT NOT NULL,
    times   INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS admin_error_events_at ON admin_error_events(last_at);
CREATE INDEX IF NOT EXISTS admin_error_events_kind ON admin_error_events(kind, last_at);
""")

SERVER_ERROR = "server_error"
EMAIL_REFUSED = "email_refused"
WEBHOOK_SIGNATURE = "webhook_signature"
AI_ERROR = "ai_error"
PAYMENT = "payment"
OTHER = "other"

KIND_LABELS = {
    SERVER_ERROR: "unhandled server errors (5xx)",
    EMAIL_REFUSED: "e-mail refused or undeliverable",
    WEBHOOK_SIGNATURE: "rejected payment or webhook signature",
    AI_ERROR: "AI provider errors",
    PAYMENT: "payment gateway errors",
    OTHER: "other warnings and errors",
}

QUEUE_LIMIT = 2000
FLUSH_SECONDS = 1.0

_local = threading.local()
_installed = False
_lock = threading.Lock()
_queue: "queue.Queue[tuple]" = queue.Queue(maxsize=QUEUE_LIMIT)
_dropped = 0
_writer: threading.Thread | None = None


def classify(logger_name: str, message: str) -> str:
    """Which counter a log record belongs to.

    Matched on the logger plus a phrase from the line that logs it, because the phrases are the contract:
    app/hardening.py's "unhandled error on", app/mailer.py's "refused", app/payments/routes.py's "REJECTED".
    If one of those lines is ever reworded this falls back to `other`, which still counts it - so a rewording
    blurs a category and never loses an error.
    """
    text = message.lower()
    if logger_name.startswith("app.hardening") and "unhandled error" in text:
        return SERVER_ERROR
    if logger_name.startswith("app.mailer") or ("e-mail" in text and "refused" in text):
        return EMAIL_REFUSED
    if "rejected" in text and ("signature" in text or "webhook" in text):
        return WEBHOOK_SIGNATURE
    if logger_name.startswith("app.ai"):
        return AI_ERROR
    if logger_name.startswith("app.payments"):
        return PAYMENT
    return OTHER


class _Recorder(logging.Handler):
    """Queues WARNING+ records from this application for the writer thread. Never blocks, never recurses."""

    def emit(self, record: logging.LogRecord) -> None:
        global _dropped

        if getattr(_local, "busy", False):
            return
        if record.levelno < logging.WARNING or not record.name.startswith("app."):
            return
        if record.name.startswith("app.admin.errors"):
            return  # our own complaints about not being able to write would be the loop
        _local.busy = True
        try:
            message = scrub(record.getMessage())[:MESSAGE_LIMIT]
            event = (classify(record.name, message), record.levelname, record.name, message, time.time())
            try:
                _queue.put_nowait(event)
            except queue.Full:
                _dropped += 1
        except Exception:  # noqa: BLE001 - a log record must never become an application failure
            pass
        finally:
            _local.busy = False


def note(kind: str, level: str, logger_name: str, message: str, at: float | None = None) -> None:
    """Record one event synchronously (or bump the identical recent one).

    This is the write itself, and it is called by the writer thread and directly by tests. Application code
    reaches it only through the queue - see the module docstring for why nothing writes from `emit`."""
    _write([(kind, level, logger_name, message, at or time.time())])


def _write(events) -> None:
    """One transaction for a batch. Batching is what makes the writer thread cheap under a log storm: a
    thousand queued events become one BEGIN IMMEDIATE rather than a thousand."""
    if not events:
        return
    newest = max(event[4] for event in events)
    with db.transaction() as conn:
        conn.execute("DELETE FROM admin_error_events WHERE last_at < ?", (newest - RETAIN_DAYS * 86400,))
        for kind, level, logger_name, message, when in events:
            bumped = conn.execute(
                "UPDATE admin_error_events SET times = times + 1, last_at = ? "
                "WHERE kind = ? AND message = ? AND last_at >= ?",
                (when, kind, message, when - DEDUPE_SECONDS)).rowcount
            if not bumped:
                conn.execute("INSERT INTO admin_error_events (at, last_at, kind, level, logger, message) "
                             "VALUES (?, ?, ?, ?, ?, ?)", (when, when, kind, level, logger_name, message))


def _drain(block: bool = True) -> int:
    """Move everything currently queued into the database. Returns how many events were written."""
    batch = []
    try:
        batch.append(_queue.get(timeout=FLUSH_SECONDS) if block else _queue.get_nowait())
    except queue.Empty:
        return 0
    while True:
        try:
            batch.append(_queue.get_nowait())
        except queue.Empty:
            break
    try:
        _write(batch)
    except Exception:  # noqa: BLE001 - losing a diagnostic must not kill the thread that records the next one
        return 0
    return len(batch)


def flush() -> int:
    """Write anything still queued, now. The admin page and the alert check call this before they read, so a
    5xx that happened a millisecond ago is already counted - a health page that lags its own process by a
    second is a health page somebody refreshes and mistrusts."""
    return _drain(block=False)


def _run_writer() -> None:
    while True:
        _drain(block=True)


def install() -> None:
    """Attach the handler to the root logger, once per process. Off with `ADMIN_ERROR_CAPTURE=0`.

    Called at import of app/admin/routes.py, i.e. when the admin router is wired into the app, because the
    single `include_router` line this package is allowed in app/main.py is also the only hook it has. The
    import IS the installation, and that is said here rather than left to be discovered.

    The writer is a daemon thread, so it never holds up a shutdown; at most it loses the events still queued
    when the process exits, which is the right trade for a diagnostic."""
    global _installed, _writer
    with _lock:
        if _installed or os.getenv("ADMIN_ERROR_CAPTURE", "1").strip() == "0":
            return
        handler = _Recorder(level=logging.WARNING)
        handler.set_name("admin-error-recorder")
        logging.getLogger().addHandler(handler)
        _writer = threading.Thread(target=_run_writer, daemon=True, name="admin-error-writer")
        _writer.start()
        _installed = True


def dropped() -> int:
    """Events the bounded queue had to discard. Shown on the health page, because a diagnostic that silently
    loses records is worse than one that says it did."""
    return _dropped


def counts_since(since: float) -> dict[str, int]:
    """{kind: how many events} since a timestamp - `times`, not rows, so a deduplicated storm counts fully."""
    flush()
    with db.transaction(write=False) as conn:
        rows = conn.execute("SELECT kind, SUM(times) AS n FROM admin_error_events WHERE last_at >= ? GROUP BY kind",
                            (since,)).fetchall()
    return {row["kind"]: int(row["n"] or 0) for row in rows}


def count_since(kind: str, since: float) -> int:
    return counts_since(since).get(kind, 0)


def recent(limit: int = 40, since: float | None = None) -> list[dict]:
    flush()
    query = "SELECT * FROM admin_error_events"
    params: list = []
    if since is not None:
        query += " WHERE last_at >= ?"
        params.append(since)
    query += " ORDER BY last_at DESC LIMIT ?"
    params.append(int(limit))
    with db.transaction(write=False) as conn:
        rows = conn.execute(query, params).fetchall()
    return [{**dict(row), "when": to_ist(row["last_at"]), "day": ist_day(row["last_at"]),
             "label": KIND_LABELS.get(row["kind"], row["kind"])} for row in rows]
