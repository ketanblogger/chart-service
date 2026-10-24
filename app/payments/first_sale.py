"""The first REAL paid sale - a milestone worth recording, and NOT a deadline.

**There is no licence countdown, and this module used to imply there was one.** It printed "5.8 days left"
and then "OVERDUE", which read like a licence violation in progress. It never was. The Swiss Ephemeris is
dual-licensed, and **the AGPL is one of the two licences** - we comply with it by publishing the source of
every deploy, which is what the publication procedure in the launch runbook exists to do. Complying with the
AGPL is not a grace period before buying something; it is a licence, in force, indefinitely.

The Astrodienst **Professional License** is what would let us STOP publishing. It is wanted for commercial
reasons - closing the prompts, the fact block, the repair logic and the validator - not to cure a breach, and
it cannot help at all while `pyswisseph` is imported, because that wrapper is AGPL-3.0 only (see
`app/engine/swe.py`, which replaces it). So the order is: own binding, then licence, then the repo goes
private. Until the last of those, publishing continues and we are compliant the whole way.

What this module still earns its place for: the first real sale is the first time a stranger's money arrives,
and that deserves to be unmissable and recorded once.

So when an order reaches `paid` while **live** Razorpay keys are in use (`rzp_live_...`), and it is the
first such order ever, this module:

1. logs it at **CRITICAL** with an unmissable marker (`FIRST LIVE SALE`), which is what a log alert or a
   `journalctl -p crit` sees;
2. writes a durable marker file, `var/first_live_sale.json` (env `FIRST_SALE_MARKER`), so it survives a
   lost database and can be read with `cat`;
3. records it in SQLite (`milestones`), whose primary key makes a second fire impossible - across
   restarts, across workers, across retries of the same webhook.

Nothing here sends anything anywhere. Razorpay's own payment e-mail is the primary signal; this is the
backstop that is under our control, and `scripts/first_sale_status.py` answers "has it happened?" at any
time. Test-mode orders (`rzp_test_...`) never count - that is the whole point of the check.
"""

import json
import logging
import os
import time
from pathlib import Path

from app import db
from app.ai.config import ROOT

from . import razorpay

log = logging.getLogger(__name__)

KEY = "first_live_sale"
# NO DEADLINE CONSTANT. There was a LICENCE_DAYS = 7 here and it encoded an obligation that does not exist:
# publishing the source satisfies the AGPL for as long as we keep doing it. A number like that gets believed.
LICENCE_URL = "https://www.astro.com/swisseph/swephprice_e.htm"

db.register_schema("milestones", """
CREATE TABLE IF NOT EXISTS milestones (
    key          TEXT PRIMARY KEY,          -- 'first_live_sale'
    order_id     TEXT NOT NULL,
    payment_id   TEXT,
    product      TEXT,
    amount_paise INTEGER,
    key_id       TEXT,                      -- the public Razorpay key id in use (never the secret)
    at           REAL NOT NULL
);
""")


def marker_path() -> Path:
    path = Path(os.getenv("FIRST_SALE_MARKER", "var/first_live_sale.json"))
    return path if path.is_absolute() else ROOT / path


def _row_to_dict(row) -> dict | None:
    return dict(row) if row is not None else None


def status() -> dict | None:
    """The recorded first live sale, or None if it has not happened yet.

    The database is the source of truth; if it was lost and the marker file is still there, the file is
    read back (and put back into the database), so the week is never restarted by a restore."""
    with db.transaction(write=False) as conn:
        row = _row_to_dict(conn.execute("SELECT * FROM milestones WHERE key = ?", (KEY,)).fetchone())
    if row:
        return row
    path = marker_path()
    if not path.is_file():
        return None
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.warning("first-sale marker %s exists but cannot be read", path)
        return None
    if not saved.get("order_id"):
        return None
    log.warning("first-sale marker file found but the database has no record: restoring it from %s", path)
    _insert(saved)
    return status()


def _insert(record: dict) -> bool:
    """True if this call created the record (so only one caller ever fires the alert)."""
    with db.transaction() as conn:
        return conn.execute(
            "INSERT OR IGNORE INTO milestones (key, order_id, payment_id, product, amount_paise, key_id, at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (KEY, record.get("order_id"), record.get("payment_id"), record.get("product"),
             record.get("amount_paise"), record.get("key_id"), record.get("at") or time.time())).rowcount == 1


def _write_marker(record: dict) -> None:
    path = marker_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(record, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:  # the database record and the log line are already there; never fail a payment
        log.error("could not write the first-sale marker %s: %s", path, exc)


def note_paid(order: dict) -> dict | None:
    """Call once for every order that has just become `paid`. Returns the milestone if THIS order was the
    first real sale, else None. Safe to call again with the same order, and safe to call for test orders."""
    if not order or order.get("status") != "paid":
        return None
    if razorpay.is_test_mode() or not razorpay.configured():
        return None  # test keys (or none): a real customer cannot have paid this
    record = {"order_id": order["id"], "payment_id": order.get("payment_id"), "product": order.get("product"),
              "amount_paise": order.get("amount_paise"), "key_id": razorpay.key_id(),
              "at": order.get("paid_at") or time.time()}
    if status() is not None or not _insert(record):
        return None  # it has already happened
    _write_marker(record)
    log.critical(
        "*** FIRST LIVE SALE *** order %s (%s, Rs %s) was paid with LIVE Razorpay keys. "
        "Swiss Ephemeris licence pending; AGPL publishing in force, so nothing is overdue (%s). "
        "Marker written to %s; scripts/first_sale_status.py prints this any time.",
        record["order_id"], record["product"], (record["amount_paise"] or 0) / 100,
        LICENCE_URL, marker_path())
    return status()


def summary() -> str:
    """One line for an operator - used by scripts/first_sale_status.py, fulfil_order.py and the smoke check.

    INFORMATIONAL, never a countdown. `deadline()` used to live here and produced "5.8 days left" and then
    "OVERDUE" - a licence violation that was not happening, printed on a deploy check, where a false alarm is
    worse than silence because it teaches the reader to skip the section.
    """
    record = status()
    if record is None:
        mode = "live" if razorpay.configured() and not razorpay.is_test_mode() else \
            "test" if razorpay.configured() else "not configured"
        return f"no real paid sale yet (Razorpay keys: {mode})"
    when = time.strftime("%Y-%m-%d %H:%M", time.localtime(float(record["at"])))
    return (f"FIRST LIVE SALE on {when}: order {record['order_id']} ({record['product']}, "
            f"Rs {(record['amount_paise'] or 0) / 100:g}) - Swiss Ephemeris licence pending; "
            f"AGPL publishing in force, nothing overdue: {LICENCE_URL}")
